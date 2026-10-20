""" HITL FOV-filtered aircraft logger.

    Load with:   PLUGINS LOAD HITL_FOVACLOG   (or add 'hitl_fovaclog' to
                 enabled_plugins in settings.cfg to load it automatically)
    Start with:  FOVACLOG ON

    Every update_interval seconds (default 1s), logs only the aircraft
    that are currently visible in the operator's radar-screen view,
    timestamped on the simulation clock (bs.sim.simt) for alignment with
    the screen recording (HITL_SCREENREC) and separately collected EEG
    data.

    IMPORTANT: turn FOVACLOG ON only *after* a scenario is already loaded
    (either from inside the .scn itself, or interactively once aircraft
    are already showing on screen) - loading a scenario always resets the
    sim first, which closes any logger that was already open and silently
    drops all further rows.

    -----------------------------------------------------------------------
    HOW THE VIEW IS TRACKED

    BlueSky is client-server: the pan/zoom state lives only in the Qt
    RadarWidget on the *client* side (bluesky/ui/qtgl/radarwidget.py).
    The client sends it to the sim as a 'PANZOOM' broadcast, which this
    plugin subscribes to:
      - after every finished view change (mouse-drag release, a settled
        mouse wheel, typed PAN/ZOOM, window resize), and
      - while a drag/wheel/pinch gesture is still in progress, at most
        every 0.2 s (PANZOOM_LIVE_DT in radarwidget.py).
    So the tracked view lags the screen by at most ~0.2 s.

    WHAT COUNTS AS VISIBLE

    An aircraft is drawn as a symbol at its position with a 3-line label
    (callsign / FL / speed) to the right of and below the symbol. An
    aircraft just off the left or top edge of the screen therefore still
    shows its label. Each logged row says which:
      - SYMBOL: the aircraft position itself is inside the view
      - LABEL:  the position is just outside, but its label (or part of
                the symbol) is on screen
    The label size is an estimate in screen pixels (LABEL_W/LABEL_H
    below, matching text_size=13, ac_size=16 in settings.cfg); a client
    that doesn't send its pixel size gets no LABEL margin.
    -----------------------------------------------------------------------
"""
import numpy as np

import bluesky as bs
from bluesky.tools import datalog
from bluesky.tools.aero import ft, kts, fpm
from bluesky.network.subscriber import subscriber

# Screen-pixel extent of an aircraft's symbol + label around its position
# (see bluesky/ui/qtgl/gltraffic.py: label of 8x3 chars of text_size,
# offset (ac_size, -0.5 * ac_size) from the symbol)
SYMBOL_HALF = 10    # half symbol size, all directions
LABEL_W = 130       # label reaches this far right of the position
LABEL_H = 75        # label reaches this far below the position

fovheader = \
    '#######################################################\n' + \
    'FOVACLOG\n' + \
    'Aircraft currently visible in the operator radar view\n' + \
    '(see plugin docstring for how the view is tracked)\n' + \
    '#######################################################\n\n' + \
    'Parameters [Units]:\n' + \
    'Simulation time [s], ' + \
    'Call sign [-], ' + \
    'Visible part [SYMBOL/LABEL], ' + \
    'Latitude [deg], ' + \
    'Longitude [deg], ' + \
    'Altitude [ft], ' + \
    'Heading [deg], ' + \
    'Track [deg], ' + \
    'CAS [kts], ' + \
    'Vertical Speed [fpm]\n'

fovlog = None
viewtracker = None


def init_plugin():
    global fovlog, viewtracker

    fovlog = datalog.crelog('FOVACLOG', None, fovheader)
    viewtracker = ViewTracker()

    config = {
        'plugin_name':     'HITL_FOVACLOG',
        'plugin_type':     'sim',
        'update_interval': 1.0,
        'update':          update,
        'reset':           reset,
    }
    stackfunctions = {}
    return config, stackfunctions


def update():
    """ Called every update_interval seconds by the plugin loader. """
    try:
        if not fovlog.isopen() or bs.traf.ntraf == 0:
            return

        lat, lon = bs.traf.lat, bs.traf.lon
        south, west, north, east = viewtracker.get_bounds()
        insymbol = (lat >= south) & (lat <= north) & (lon >= west) & (lon <= east)

        # Expand the view by the symbol/label extent: the label sits to the
        # right of and below the position, so it can still be on screen
        # when the position is just past the left or top edge.
        dlat_px, dlon_px = viewtracker.deg_per_px()
        inlabel = (lat >= south - SYMBOL_HALF * dlat_px) & \
                  (lat <= north + LABEL_H * dlat_px) & \
                  (lon >= west - LABEL_W * dlon_px) & \
                  (lon <= east + SYMBOL_HALF * dlon_px)
        inview = insymbol | inlabel
        if not np.any(inview):
            return

        fovlog.log(
            np.array(bs.traf.id)[inview],
            np.where(insymbol, 'SYMBOL', 'LABEL')[inview],
            lat[inview],
            lon[inview],
            bs.traf.alt[inview] / ft,
            bs.traf.hdg[inview],
            bs.traf.trk[inview],
            bs.traf.cas[inview] / kts,
            bs.traf.vs[inview] / fpm,
        )
    except Exception as e:
        # A logging glitch must never bring down the simulation.
        print(f'[HITL_FOVACLOG] update failed: {e}')


def reset():
    try:
        viewtracker.reset()
    except Exception as e:
        print(f'[HITL_FOVACLOG] reset failed: {e}')


class ViewTracker:
    """ Tracker of the operator's radar view (pan/zoom/ar/pixel size),
        fed by the client's 'PANZOOM' network broadcast. See the module
        docstring.
    """

    def __init__(self):
        self.reset()

    def reset(self):
        self.pan = list(self._default_pan())
        self.zoom = 0.4   # BlueSky's own startup default, bluesky/stack/simstack.py
        self.ar = 1.0     # Assume a square viewport until told otherwise
        self.size = None  # Radar widget size in pixels, if the client sent it

    @staticmethod
    def _default_pan():
        """ Mirrors BlueSky's own startup pan: PAN <settings.start_location>. """
        try:
            from bluesky.stack.argparser import PosArg
            lat, lon, _ = PosArg().parse(bs.settings.start_location)
            return lat, lon
        except Exception:
            return 52.3086, 4.7639  # EHAM, BlueSky's built-in default

    def on_panzoom(self, pan=None, zoom=None, ar=None, size=None):
        """ Handler for the 'PANZOOM' broadcast. The client always sends a
            full snapshot (pan, zoom, ar, size), not a delta, so we just
            replace our stored state. """
        try:
            if pan is not None:
                self.pan = list(pan)
            if zoom is not None:
                self.zoom = zoom
            if ar is not None:
                self.ar = ar
            if size is not None:
                self.size = tuple(size)
        except Exception as e:
            print(f'[HITL_FOVACLOG] PANZOOM handling failed: {e}')

    def _flat_earth(self):
        return np.cos(np.deg2rad(self.pan[0])) or 1e-9

    def get_bounds(self):
        """ Same formula as RadarWidget.viewportlatlon() in
            bluesky/ui/qtgl/radarwidget.py, evaluated with the last known
            pan/zoom/ar. Returns (south, west, north, east) in degrees.

            NOTE: does not handle the antimeridian wrap-around case - fine
            for the typical European/regional ATC scenarios this is meant
            for, but the view box math would need adjusting for a view
            that straddles +/-180 longitude.
        """
        dlat = 1.0 / (self.zoom * self.ar)
        dlon = 1.0 / (self.zoom * self._flat_earth())
        south = self.pan[0] - dlat
        north = self.pan[0] + dlat
        west = self.pan[1] - dlon
        east = self.pan[1] + dlon
        return south, west, north, east

    def deg_per_px(self):
        """ Degrees latitude / longitude per screen pixel, or (0, 0) if the
            client never sent its pixel size. """
        if not self.size or min(self.size) <= 0:
            return 0.0, 0.0
        width, height = self.size
        return (2.0 / (self.zoom * self.ar) / height,
                2.0 / (self.zoom * self._flat_earth()) / width)


@subscriber(topic='PANZOOM')
def _on_panzoom(pan=None, zoom=None, ar=None, absolute=True, size=None, finished=True):
    if viewtracker is not None:
        viewtracker.on_panzoom(pan=pan, zoom=zoom, ar=ar, size=size)
