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

    Checked against the actual dispatch logic in
    bluesky/stack/clientstack.py: most commands that resolve locally on
    the client (unknown to the sim) still get forwarded to the sim
    afterwards (e.g. typed HELP/MAKEDOC almost always forward), so they
    DO end up here. The only commands that are *never* forwarded, and so
    can never appear as literal command text in this log, are:
      - ECHO (rare in practice - a "print a note" command, not an ATC
        action)
      - PAN, ZOOM, and the +/-/= zoom keyboard shortcuts

    For the second group, this plugin also subscribes to the 'PANZOOM'
    network broadcast (bluesky/ui/qtgl/radarwidget.py) and logs a
    synthesized "VIEWCHANGE PAN ... ZOOM ..." row whenever the tracked
    view changes - see _on_panzoom below. This is a RECONSTRUCTED view
    state, not the literal text the operator typed (a raw broadcast
    doesn't distinguish "typed PAN" from "typed ZOOM" from a mouse
    drag), and is subject to the same best-effort limitations as
    hitl_fovaclog.py's view tracking (see that plugin's docstring).

    Every other console command (ALT, HDG, SPD, CRE, DEL, ...) reaches
    here as literal command text and is logged, including
    scenario-file-originated ones and commands that fail/error (unlike
    BlueSky's own SAVEIC, which only records commands that executed
    successfully).
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
from bluesky.network.subscriber import subscriber
import bluesky.network.context as ctx

cmdheader = \
    '#######################################################\n' + \
    'OPCMDLOG\n' + \
    'Every stack command that reached the simulation, with its\n' + \
    'simulation time, for sync with screen recording / EEG data\n' + \
    '#######################################################\n\n' + \
    'Parameters [Units]:\n' + \
    'Simulation time [s], ' + \
    'Command text [-] (quoted CSV field, may itself contain commas; ' + \
    'a "VIEWCHANGE PAN .. ZOOM .." row is a reconstructed view state, ' + \
    'not literal typed text - see plugin docstring), ' + \
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


# ---------------------------------------------------------------------
# PAN/ZOOM (and the +/-/= zoom shortcuts) never reach Stack.commands() -
# see VERIFIED LIMITATION #1 above. Reuse the same 'PANZOOM' broadcast
# hitl_fovaclog.py listens to, and log a reconstructed view-change row
# instead of literal command text.
# ---------------------------------------------------------------------
@subscriber(topic='PANZOOM')
def _on_panzoom(pan=None, zoom=None, ar=None, absolute=True):
    try:
        if cmdlog is not None and cmdlog.isopen() and pan is not None and zoom is not None:
            sender = ctx.sender_id.hex() if ctx.sender_id else ''
            text = f'VIEWCHANGE PAN {pan[0]:.6f} {pan[1]:.6f} ZOOM {zoom:.6f}'
            quoted = '"' + text.replace('"', '""') + '"'
            cmdlog.log(quoted, sender)
    except Exception as e:
        print(f'[HITL_OPCMDLOG] PANZOOM logging failed: {e}')
