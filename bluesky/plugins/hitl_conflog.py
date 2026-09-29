""" HITL conflict onset/offset logger.

    Logs the exact simulation time at which each aircraft pair enters and
    leaves a predicted conflict (CONFSTART/CONFEND), two ways:

    1. As an ECHO stack command. ECHO is a normal stack command, so if
       SAVEIC is running it gets timestamped and written straight into
       the SAVEIC recording (e.g. HITL_2con_run.scn), right alongside the
       operator's manually typed resolution commands - one file, one
       timeline, easy to eyeball the reaction gap.
    2. As a row in a dedicated HITLCONFLOG CSV file, for later analysis.

    Independent of the AREA/EXP plugin: logs every pair globally, no
    experiment area needs to be defined.

    Load with:  PLUGIN LOAD HITL_CONFLOG
    Start with: HITLCONFLOG ON  (starts a fresh CSV; run this again on
                every scenario run for a clean file each time, same as
                FOVACLOG/OPCMDLOG/HEARTBEATLOG)

    Requires CDMETHOD ON (Conflict Detection) to actually detect
    anything - see bs.traf.cd.confpairs_unique.
"""
import bluesky as bs
from bluesky.tools import datalog
from bluesky.core import Entity, timed_function

confheader = \
    '#######################################################\n' + \
    'HITL CONFLICT LOG\n' + \
    'Per-pair predicted-conflict onset and offset times\n' + \
    '#######################################################\n\n' + \
    'Parameters [Units]:\n' + \
    'Simulation time [s], ' + \
    'Event [CONFSTART/CONFEND], ' + \
    'Aircraft 1 [-], Aircraft 2 [-]\n'

hitlconflog = None


def init_plugin():
    global hitlconflog
    hitlconflog = HitlConflog()

    config = {
        'plugin_name':     'HITL_CONFLOG',
        'plugin_type':     'sim'
    }
    stackfunctions = {}
    return config, stackfunctions


class HitlConflog(Entity):
    def __init__(self):
        super().__init__()
        self.logger = datalog.crelog('HITLCONFLOG', None, confheader)
        self.prevconf = set()

    @timed_function(name='HITL_CONFLOG', dt=1.0)
    def update(self, dt):
        curconf = set(bs.traf.cd.confpairs_unique)

        for pair in curconf - self.prevconf:
            ac1, ac2 = tuple(pair)
            self.logger.log('CONFSTART', ac1, ac2)
            bs.stack.stack(f'ECHO CONFSTART {ac1} {ac2}')
        for pair in self.prevconf - curconf:
            ac1, ac2 = tuple(pair)
            self.logger.log('CONFEND', ac1, ac2)
            bs.stack.stack(f'ECHO CONFEND {ac1} {ac2}')

        self.prevconf = curconf

    @timed_function(name='HITL_CONFLOG.reset', hook='reset')
    def reset(self):
        """ Drop conflict-pair state left over from a previous run, so a
            fresh scenario load never logs a spurious CONFEND for a pair
            of aircraft that no longer exist. """
        self.prevconf = set()
