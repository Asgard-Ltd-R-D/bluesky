""" HITL simulation heartbeat logger.

    Logs the simulation time every second, unconditionally - independent
    of any other HITL logger's ON/OFF state or content. Its only job is
    to prove the sim's update loop was still alive at that instant, so a
    silent second in a periodic logger (FOVACLOG, HITLCONFLOG, ...) can
    be told apart from a genuinely idle second versus a dropped/failed
    tick in that logger's own code.

    Load with:   PLUGINS LOAD HITL_HEARTBEATLOG   (or add
                 'hitl_heartbeatlog' to enabled_plugins in settings.cfg
                 to load it automatically, same as hitl_fovaclog and
                 hitl_opcmdlog)
    Start with:  HEARTBEATLOG ON  (starts a fresh CSV; run this again
                 on every scenario run for a clean file each time,
                 same as FOVACLOG/OPCMDLOG/HITLCONFLOG)
"""
from bluesky.tools import datalog
from bluesky.core import Entity, timed_function

heartbeatheader = \
    '#######################################################\n' + \
    'HEARTBEATLOG\n' + \
    'One row per simulation second - proof the sim was ticking,\n' + \
    'independent of any other HITL logger.\n' + \
    '#######################################################\n\n' + \
    'Parameters [Units]:\n' + \
    'Simulation time [s]\n'

heartbeatlog = None


def init_plugin():
    global heartbeatlog
    heartbeatlog = HitlHeartbeatlog()

    config = {
        'plugin_name':     'HITL_HEARTBEATLOG',
        'plugin_type':     'sim'
    }
    stackfunctions = {}
    return config, stackfunctions


class HitlHeartbeatlog(Entity):
    def __init__(self):
        super().__init__()
        self.logger = datalog.crelog('HEARTBEATLOG', None, heartbeatheader)

    @timed_function(name='HITL_HEARTBEATLOG', dt=1.0)
    def update(self, dt):
        self.logger.log()
