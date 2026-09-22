""" HITL FOV-filtered aircraft logger.

    Load with:   PLUGINS LOAD HITL_FOVACLOG   (or add 'hitl_fovaclog' to
                 enabled_plugins in settings.cfg to load it automatically)
    Start with:  FOVACLOG ON

    Every update_interval seconds (default 1s), logs only the aircraft
    that are currently inside the operator's radar-screen view, timestamped
    on the simulation clock (bs.sim.simt) for alignment with an external
    screen recording and separately collected EEG data.

    IMPORTANT: turn FOVACLOG ON only *after* a scenario is already loaded
    (either from inside the .scn itself, or interactively once aircraft
    are already showing on screen) - loading a scenario always resets the
    sim first, which closes any logger that was already open and silently
    drops all further rows.

    -----------------------------------------------------------------------
    IMPORTANT LIMITATION - verified directly against this BlueSky checkout
    (bluesky/ui/qtgl/radarwidget.py, bluesky/ui/qtgl/mainwindow.py,
    bluesky/simulation/screenio.py):

    BlueSky is client-server. The simulation process has NO live access to
    the operator's pan/zoom/range - that state exists only inside the Qt
    RadarWidget on the *client* side. The sim-side bs.scr object
    (ScreenIO) only has unused, never-updated def_pan/def_zoom attributes.
    Typed PAN/ZOOM console commands are registered and executed entirely
    client-side and are never forwarded to the sim - there is no way for a
    sim-side plugin to see them.

    The one thing that *does* cross the network is a 'PANZOOM' broadcast
    the client sends whenever a mouse-drag/touch pan or pinch-zoom gesture
    *finishes*. This plugin subscribes to that broadcast and uses it as a
    best-effort estimate of the current view. Consequences:
      - A zoom done purely with the mouse scroll wheel, with no click
        afterwards, will NOT update the tracked view.
      - Typed PAN/ZOOM commands will NOT update the tracked view.
      - Before the very first such gesture, the plugin falls back to
        BlueSky's own default startup view (PAN <start_location>, ZOOM 0.4).

    If you need FOV tracking that is 100% accurate for every possible way
    of changing the view, the Qt client itself (bluesky/ui/qtgl) would need
    to be modified to broadcast on every view change - that is outside
    what a sim-side plugin can do. This best-effort approach is the
    simplest option that is still technically correct for the common case
    (mouse drag-pan / pinch/click-zoom).
    -----------------------------------------------------------------------
"""
import numpy as np

import bluesky as bs
from bluesky.tools import datalog
from bluesky.tools.aero import ft, kts, fpm
from bluesky.network.subscriber import subscriber

fovheader = \
    '#######################################################\n' + \
    'FOVACLOG\n' + \
    'Aircraft currently visible in the operator radar view\n' + \
    '(best-effort view tracking - see plugin docstring for limitations)\n' + \
    '#######################################################\n\n' + \
    'Parameters [Units]:\n' + \
    'Simulation time [s], ' + \
    'Call sign [-], ' + \
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

        south, west, north, east = viewtracker.get_bounds()
        lat, lon = bs.traf.lat, bs.traf.lon
        inview = (lat >= south) & (lat <= north) & (lon >= west) & (lon <= east)
        if not np.any(inview):
            return

        fovlog.log(
            np.array(bs.traf.id)[inview],
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
    """ Best-effort tracker of the operator's radar view (pan/zoom/ar),
        fed by the client's 'PANZOOM' network broadcast. See the module
        docstring for exactly which view changes this does and doesn't
        capture.
    """

    def __init__(self):
        self.pan = list(self._default_pan())
        self.zoom = 0.4   # BlueSky's own startup default, bluesky/stack/simstack.py
        self.ar = 1.0     # Assume a square viewport until told otherwise

    def reset(self):
        self.pan = list(self._default_pan())
        self.zoom = 0.4
        self.ar = 1.0

    @staticmethod
    def _default_pan():
        """ Mirrors BlueSky's own startup pan: PAN <settings.start_location>. """
        try:
            from bluesky.stack.argparser import PosArg
            lat, lon, _ = PosArg().parse(bs.settings.start_location)
            return lat, lon
        except Exception:
            return 52.3086, 4.7639  # EHAM, BlueSky's built-in default

    def on_panzoom(self, pan=None, zoom=None, ar=None, absolute=True):
        """ Handler for the 'PANZOOM' broadcast. The client always sends a
            full snapshot (pan, zoom, ar), not a delta, so we just replace
            our stored state - see radarwidget.py:342. """
        try:
            if pan is not None:
                self.pan = list(pan)
            if zoom is not None:
                self.zoom = zoom
            if ar is not None:
                self.ar = ar
        except Exception as e:
            print(f'[HITL_FOVACLOG] PANZOOM handling failed: {e}')

    def get_bounds(self):
        """ Same formula as RadarWidget.viewportlatlon() in
            bluesky/ui/qtgl/radarwidget.py, evaluated with the last known
            pan/zoom/ar. Returns (south, west, north, east) in degrees.

            NOTE: does not handle the antimeridian wrap-around case - fine
            for the typical European/regional ATC scenarios this is meant
            for, but the view box math would need adjusting for a view
            that straddles +/-180 longitude.
        """
        flat_earth = np.cos(np.deg2rad(self.pan[0])) or 1e-9
        dlat = 1.0 / (self.zoom * self.ar)
        dlon = 1.0 / (self.zoom * flat_earth)
        south = self.pan[0] - dlat
        north = self.pan[0] + dlat
        west = self.pan[1] - dlon
        east = self.pan[1] + dlon
        return south, west, north, east


@subscriber(topic='PANZOOM')
def _on_panzoom(pan=None, zoom=None, ar=None, absolute=True):
    if viewtracker is not None:
        viewtracker.on_panzoom(pan=pan, zoom=zoom, ar=ar, absolute=absolute)
