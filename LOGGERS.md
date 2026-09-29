# HITL logging setup

This experiment uses several files together: four logger plugins and
the scenario that wires them up. This document explains what each one
is, why it exists, and how to actually turn the loggers on.

## Quick reference

| Logger | Plugin file | Turned on by | Output file | Captures |
|---|---|---|---|---|
| `FOVACLOG` | `hitl_fovaclog.py` | `FOVACLOG ON` | `FOVACLOG_2con_test_<ts>.log` | Aircraft currently in the operator's view - one row per aircraft per second, silent when none are in view |
| `HEARTBEATLOG` | `hitl_heartbeatlog.py` | `HEARTBEATLOG ON` | `HEARTBEATLOG_2con_test_<ts>.log` | One row every simulation second, unconditionally - proves the sim was ticking, independent of every other logger |
| `OPCMDLOG` | `hitl_opcmdlog.py` | `OPCMDLOG ON` | `OPCMDLOG_2con_test_<ts>.log` | Every stack command that reaches the simulation |
| `HITLCONFLOG` | `hitl_conflog.py` | `HITLCONFLOG ON` (after `PLUGIN LOAD HITL_CONFLOG`; needs `CDMETHOD ON` first) | `HITLCONFLOG_2con_test_<ts>.log` | Per-pair conflict onset/offset (`CONFSTART`/`CONFEND`), also `ECHO`ed into the SAVEIC recording |
| `SAVEIC` recording | n/a (built into BlueSky) | `SAVEIC HITL_2con_run` (inside `2con_test.scn`) | `scenario/HITL_2con_run.scn` | Replayable log of every command that *succeeded*, real elapsed-time stamps |

## The files

### `bluesky/plugins/hitl_fovaclog.py` -> `FOVACLOG`

Every second, logs only the aircraft that are currently inside the
operator's radar-screen view (pan/zoom), not every aircraft in the
simulation. Columns: simulation time, callsign, lat, lon, altitude,
heading, track, CAS, vertical speed.

**Why it exists:** so the recorded aircraft data reflects what the
operator was actually *looking at* on screen at each moment, for later
alignment with a screen recording and EEG data.

**Name:** `FOV` (Field Of View) + `AC` (**Aircraft**, the standard
abbreviation used throughout BlueSky's own code, e.g. `DEL acid`) +
`LOG`. "The aircraft-in-view log."

**Known limitation:** BlueSky's simulation process has no direct access
to the operator's screen. This plugin tracks the view on a best-effort
basis, via a network message the client only sends when a mouse-drag
pan or a click+drag zoom *finishes*. It will NOT pick up a view change
made by typing `PAN`/`ZOOM` as text commands, or a zoom done with the
mouse scroll wheel alone (no click afterwards) - see the comments at
the top of the plugin file for the full technical explanation.

### `bluesky/plugins/hitl_conflog.py` -> `HITLCONFLOG`

Logs the exact simulation time each aircraft pair enters and leaves a
predicted conflict (`CONFSTART`/`CONFEND`), both as a row in its own
CSV and as an `ECHO` stack command - so if `SAVEIC` is running, the
same events land in the replay file too, timestamped right alongside
the operator's manual resolution commands.

**Why it exists:** to see, on the same `simt` clock as the other logs,
exactly when a conflict started/ended versus when (and how fast) the
operator reacted to it.

**Requires `CDMETHOD ON`** (conflict detection) to detect anything.
Independent of any experiment-area plugin - logs every pair globally.
Needs its own `HITLCONFLOG ON` to start writing, same as the other
three loggers - each run of `2con_test.scn` gives it a fresh CSV and
resets its in-memory conflict-pair state, so nothing carries over from
a previous run in the same BlueSky session.

### `bluesky/plugins/hitl_opcmdlog.py` -> `OPCMDLOG`

Logs every stack command that reaches the simulation (`ALT`, `HDG`,
`SPD`, `CRE`, ...), with its simulation time and, when available, the
id of the network client that sent it (a non-empty id means it was
typed live through a connected console/GUI, not read from a scenario
file).

**Why it exists:** to know exactly *when* the operator issued each
command, on the same simt clock as FOVACLOG, for the same
screen-recording/EEG alignment purpose.

**Coverage note:** `PAN`, `ZOOM`, `HELP`, `ECHO`, `MAKEDOC` and the
`+`/`-`/`=` zoom shortcuts are handled entirely on the client side and
never reach the simulation - they cannot appear in this log. Every
other command does.

### `bluesky/plugins/hitl_heartbeatlog.py` -> `HEARTBEATLOG`

Its own plugin, independent of every other logger. Every second, logs
just the simulation time - unconditionally, regardless of what any
other logger did or didn't find that second. Loaded automatically at
BlueSky startup (like FOVACLOG/OPCMDLOG), but needs its own
`HEARTBEATLOG ON` to actually start writing - and each run of
`2con_test.scn` gives it a fresh CSV, same as the other three loggers.

**Why it exists:** loggers like FOVACLOG and HITLCONFLOG stay silent,
by design, whenever there's nothing to report that second (empty view,
no conflict event). On its own, silence in one of those files is
ambiguous - genuinely nothing happened, or that logger's own tick
silently failed? HEARTBEATLOG answers that for *any* of them: if a
second is present here but missing from another log, that log's
silence was legitimate; if it's missing here too, the sim itself
wasn't ticking (or something has gone badly wrong).

### `scenario/hitl_test/2con_test.scn`

The actual experiment scenario: two conflict trials (a head-on and a
crossing conflict) plus background traffic. This is the file that
loads `HITL_CONFLOG` and **turns all four loggers on** (see "How to
start logging" below) and also runs `SAVEIC HITL_2con_run`, so a
single scenario run produces all five outputs described here, every
one of them starting fresh.

### `scenario/HITL_2con_run.scn`

Not something you write by hand - it's the output of the
`SAVEIC HITL_2con_run` line inside `2con_test.scn`. `SAVEIC` is
BlueSky's own built-in recorder: while it's running, every command that
*successfully* executes in the simulation gets written here, in
replayable `.scn` format (with real elapsed-time timestamps), so you
can literally re-run this exact file later (`IC HITL_2con_run`) to
reproduce the session. Unlike `OPCMDLOG`, it only records commands that
succeeded (no failed/mistyped ones), and it's a scenario file, not a
CSV, so it's better for replaying a run than for data analysis.

## How to start logging

All four loggers follow the same two-step pattern: **loaded**, then
**turned on**, and being loaded is never the same as being *on*.

`FOVACLOG`, `OPCMDLOG` and `HEARTBEATLOG` are loaded automatically at
BlueSky startup (`enabled_plugins` in `settings.cfg` includes
`hitl_fovaclog`, `hitl_opcmdlog` and `hitl_heartbeatlog`) - no
`PLUGIN LOAD` needed for those. `HITLCONFLOG` isn't in
`enabled_plugins`, so `2con_test.scn` loads it explicitly. None of the
four starts writing on its own - each needs its own `... ON`, and
`2con_test.scn` issues all four:

```
00:00:00.00> CDMETHOD ON
00:00:00.00> PLUGIN LOAD HITL_CONFLOG
00:00:00.00> FOVACLOG ON
00:00:00.00> OPCMDLOG ON
00:00:00.00> HITLCONFLOG ON
00:00:00.00> HEARTBEATLOG ON
```

Because loading a scenario always resets the simulation first - which
closes any logger that was already open, and clears HITLCONFLOG's
in-memory conflict-pair state - and these four `ON` lines run *after*
that reset, **every run of `2con_test.scn` starts all four loggers
completely fresh**: new files, no leftover state from a previous run
in the same BlueSky session. Things worth knowing:

- **You can also type any of these commands yourself in the
  console**, any time *after* a scenario is already loaded and
  aircraft are showing on screen - it works exactly like the built-in
  `FLSTLOG`.
- **Never type `... ON` before loading/switching a scenario.** Loading
  a scenario always resets the simulation first, which closes any
  logger that was already open and silently drops everything from then
  on - the scenario file's own `ON` lines avoid this because they run
  *after* that same reset. Turn a logger off any time with `... OFF`.
- **`HITLCONFLOG` needs `CDMETHOD ON` first** - without conflict
  detection enabled, it has nothing to detect and its CSV stays empty.

## Where the output goes

All four CSVs are written to `output/`, named
`FOVACLOG_2con_test_<timestamp>.log`, `HEARTBEATLOG_2con_test_<timestamp>.log`,
`OPCMDLOG_2con_test_<timestamp>.log` and `HITLCONFLOG_2con_test_<timestamp>.log`
(the scenario's own filename, `2con_test`, not `HITL_2con_run` - that
name belongs only to the `SAVEIC` replay file in `scenario/`). Note
each file's `<timestamp>` is its own *wall-clock* creation time, so
filenames can differ by a second between them - it's cosmetic, all
four use `simt` as their first column, so they line up with each other
and with `HITL_2con_run.scn`'s own timestamps.
