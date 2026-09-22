""" HITL operator-command logger.

    Load with:   PLUGINS LOAD HITL_OPCMDLOG   (or add 'hitl_opcmdlog' to
                 enabled_plugins in settings.cfg to load it automatically)
    Start with:  OPCMDLOG ON

    Logs every stack command that reaches the simulation process, with its
    simulation time (bs.sim.simt) and (when available) the id of the client
    that sent it - for alignment with an external screen recording and
    separately collected EEG data.

    IMPORTANT: turn OPCMDLOG ON only *after* a scenario is already loaded
    (either from inside the .scn itself, or interactively once aircraft
    are already showing on screen) - loading a scenario always resets the
    sim first, which closes any logger that was already open and silently
    drops all further rows.

    -----------------------------------------------------------------------
    VERIFIED LIMITATION #1 - command coverage:

    PAN, ZOOM, HELP, ECHO, MAKEDOC and the +/-/= zoom shortcuts are
    resolved entirely client-side (bluesky/ui/qtgl/mainwindow.py) and never
    reach the simulation process - they cannot be logged from here. Every
    other console command (ALT, HDG, SPD, CRE, DEL, ...) does reach here
    and is logged, including scenario-file-originated ones and commands
    that fail/error (unlike BlueSky's own SAVEIC, which only records
    commands that executed successfully).
    -----------------------------------------------------------------------

    -----------------------------------------------------------------------
    VERIFIED LIMITATION #2 - same-tick commands:

    The patch below (see _patch_stack_command_logging) only takes effect
    starting with the *next* simulation step after
    "PLUGINS LOAD HITL_OPCMDLOG" runs - Python cannot retroactively rewrite
    a for-loop that is already executing. This is never an issue for a
    live operator typing commands one at a time (each keypress lands on
    its own simulation step), but it DOES mean: if you load this plugin
    from *inside* a .scn file, any other command stacked at that exact
    same timestamp (e.g. several "00:00:00.00>..." lines right after the
    PLUGINS LOAD line) will be silently missed. Verified directly by
    running a real headless sim node with such a scenario.

    Recommended fix: add 'hitl_opcmdlog' to the enabled_plugins list in
    settings.cfg so the plugin (and its patch) is active from the very
    first simulation step, before any scenario command ever runs.
    -----------------------------------------------------------------------
"""
from bluesky.tools import datalog
from bluesky.stack.stackbase import Stack

cmdheader = \
    '#######################################################\n' + \
    'OPCMDLOG\n' + \
    'Every stack command that reached the simulation, with its\n' + \
    'simulation time, for sync with screen recording / EEG data\n' + \
    '#######################################################\n\n' + \
    'Parameters [Units]:\n' + \
    'Simulation time [s], ' + \
    'Command text [-] (quoted CSV field, may itself contain commas), ' + \
    'Sender id [-] (non-empty = command arrived from a network client)\n'

cmdlog = None


def init_plugin():
    global cmdlog

    cmdlog = datalog.crelog('OPCMDLOG', None, cmdheader)
    _patch_stack_command_logging()

    config = {
        'plugin_name': 'HITL_OPCMDLOG',
        'plugin_type': 'sim',
    }
    stackfunctions = {}
    return config, stackfunctions


# ---------------------------------------------------------------------
# Reliable patch point, verified against the current source: Stack is a
# static/classmethod-only namespace (bluesky/stack/stackbase.py). Its
# generator classmethod `commands()` is what bluesky/stack/simstack.py's
# process() calls, every simulation step, to pull the next command line
# to execute - via a fresh `Stack.commands(...)` attribute lookup on the
# shared class object each time, so patching the class attribute here is
# seen immediately by simstack.process().
#
# We deliberately do NOT monkeypatch `bluesky.stack.stack` (the queueing
# function): other modules bind it locally via
# `from bluesky.stack.stackbase import stack` at import time, so
# reassigning it afterwards would silently miss those call sites.
# ---------------------------------------------------------------------
_orig_stack_commands = Stack.commands.__func__


def _logging_stack_commands(cls, ext_cmds=None):
    for cmdline in _orig_stack_commands(cls, ext_cmds):
        try:
            if cmdlog is not None and cmdlog.isopen():
                sender = cls.sender_id.hex() if cls.sender_id else ''
                quoted = '"' + cmdline.replace('"', '""') + '"'
                cmdlog.log(quoted, sender)
        except Exception as e:
            print(f'[HITL_OPCMDLOG] logging failed: {e}')
        yield cmdline


def _patch_stack_command_logging():
    if getattr(Stack, '_hitl_opcmdlog_patched', False):
        return
    Stack.commands = classmethod(_logging_stack_commands)
    Stack._hitl_opcmdlog_patched = True
