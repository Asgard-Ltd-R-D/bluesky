# HITL logging setup

This experiment uses three files together: two logger plugins and the
scenario that wires them up. This document explains what each one is,
why it exists, and how to actually turn the loggers on.

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

### `scenario/hitl_test/2con_test.scn`

The actual experiment scenario: two conflict trials (a head-on and a
crossing conflict) plus background traffic. This is the file that
**turns both loggers on** (see "How to start logging" below) and also
runs `SAVEIC HITL_2con_run`, so a single scenario run produces all
three outputs described here.

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

Both loggers are already loaded automatically at BlueSky startup
(`enabled_plugins` in `settings.cfg` includes `hitl_fovaclog` and
`hitl_opcmdlog`) - you don't need `PLUGIN LOAD` anywhere. But loading a
logger is not the same as it being *on*: `2con_test.scn` contains

```
00:00:00.00> FOVACLOG ON
00:00:00.00> OPCMDLOG ON
```

which is what actually starts writing to the CSV files, right after
`CDMETHOD ON` and before anything else happens. Two things worth
knowing:

- **You can also type `FOVACLOG ON` / `OPCMDLOG ON` yourself in the
  console**, any time *after* a scenario is already loaded and aircraft
  are showing on screen - it works exactly like the built-in `FLSTLOG`.
- **Never type `... ON` before loading/switching a scenario.** Loading
  a scenario always resets the simulation first, which closes any
  logger that was already open and silently drops everything from then
  on - the scenario file's own `ON` lines avoid this because they run
  *after* that same reset. Turn a logger off any time with `... OFF`.

## Where the output goes

Both CSVs are written to `output/`, named
`FOVACLOG_2con_test_<timestamp>.log` and
`OPCMDLOG_2con_test_<timestamp>.log` (the scenario's own filename,
`2con_test`, not `HITL_2con_run` - that name belongs only to the
`SAVEIC` replay file in `scenario/`). Both use `simt` as their first
column, so they line up with each other and with `HITL_2con_run.scn`'s
own timestamps.
