# BlueSky Open Air Traffic Simulator — Technical Overview

**Scope:** architecture, conflict generation, configuration, and data logging, for use in human-factors research (e.g., scenario design, log-based dependent measures, synchronization with external sensors such as EEG).

**Grounded in:** the actual source of `bluesky-simulator` **v1.1.1** as installed in this repository's `venv` (`bluesky/`). Many BlueSky tutorials online describe an older or different command set — where this document diverges from common tutorials, that divergence is called out explicitly, because it was verified directly against source rather than assumed.

---

## 1. System Overview

BlueSky uses a **client–server, multi-process architecture** with a hard separation between the simulation engine and the user interface. This matters for research use because it means the simulation's state, timing, and logs are authoritative on the *simulation* side — the GUI is just one possible consumer of that state.

### 1.1 The three layers

```
┌─────────────────────┐        TCP/UDP (ZeroMQ)        ┌──────────────────────────┐
│   UI Client(s)       │ <-----------------------------> │   Simulation Node(s)     │
│  (Qt/OpenGL "QTGL",  │   msgpack-serialized state      │  bluesky/simulation/     │
│   headless console,  │   + stack commands               │  bluesky/traffic/        │
│   or pygame)          │                                 │  bluesky/traffic/asas/   │
└─────────────────────┘                                  └──────────────────────────┘
                                                                     │
                                                            ┌────────┴────────┐
                                                            │  Command Stack   │
                                                            │ bluesky/stack/   │
                                                            └──────────────────┘
```

- **UI process** (`BlueSky.py`, entry point): renders the radar screen, the command console, and forwards typed commands to the simulation process. Implementations include the default Qt/OpenGL client (`bluesky/ui/qtgl/`), a text-only console (`bluesky/ui/console/`), and a legacy `pygame` client (`BlueSky_pygame.py`).
- **Simulation engine** (headless-capable): owns `traf` (the `Traffic` object — the array-based state of all aircraft), the autopilot (`bluesky/traffic/autopilot.py`), conflict detection/resolution (`bluesky/traffic/asas/`), performance models, navigation database, and the datalog subsystem. This process can run **completely headless** (`BlueSky.py --headless`), which is the relevant mode for unattended experiment batches.
- **Command Stack** (`bluesky/stack/`): the single control-plane through which *everything* happens — GUI button clicks, typed console commands, and scenario-file (`.scn`) lines all resolve to the same stack commands (e.g., `CRE`, `HDG`, `ALT`). This is why scenario files are just plain text logs of stack commands with timestamps — there is no separate "scenario format."

### 1.2 Multi-node simulation

BlueSky supports running several simulation instances (**nodes**) in parallel under one server process, addressed individually from the client (`NODES`, `ADDNODES`, `SWITCH`). This is directly useful for research: independent parallel runs (e.g., different participants or conditions) can be dispatched to separate nodes from a single controlling process, each with independent state, timing, and log files.

### 1.3 Key global singletons (importable in plugins/scripts)

| Object | Module | Purpose |
|---|---|---|
| `bs.traf` | `bluesky.traffic.Traffic` | Array-based state of all aircraft (lat, lon, alt, hdg, spd, …) |
| `bs.traf.cd` | `bluesky.traffic.asas.ConflictDetection` (active implementation) | Current conflict/LoS pairs, distances, times |
| `bs.traf.cr` | `bluesky.traffic.asas.ConflictResolution` | Active resolution/avoidance logic |
| `bs.sim` | `bluesky.simulation.Simulation` | Simulation clock, state (INIT/OP/HOLD), utc/simt |
| `bs.stack` | `bluesky.stack` | Command parser/dispatcher |
| `bs.scr` | screen proxy | Sends state to connected UI client(s) |
| `bs.settings` | `bluesky.settings` | Parsed `settings.cfg` values |

---

## 2. Scenario Files (`.scn`) — Goal and Usage

### 2.1 What a scenario is, conceptually

A BlueSky scenario is **not a special data format** — it is a plain-text, timestamped transcript of stack commands (the same commands you type at the console, in `HH:MM:SS.hh>COMMAND` form). This falls directly out of the architecture in §1.1: since the command stack is the single control-plane for the whole simulator, "scripting a simulation" and "recording a sequence of console commands" are the same operation. There is no separate scenario compiler or schema — `readscn()` (`bluesky/stack/simstack.py`) just parses each line into a `(time, command)` pair.

**The goal of a scenario file, for research purposes, is to make a trial fully reproducible and unattended:** initial traffic, airspace/experiment-area definition, conflict geometry, loggers, and timed events are all specified once, in a file, so that (a) every participant/run sees an identical setup, (b) runs can be launched non-interactively (headless, via `IC file.scn` or `BATCH`), and (c) the exact sequence of events for a trial is version-controllable and auditable after the fact.

### 2.2 File format

```
# Comment lines (anything starting with '#') and blank lines are ignored.
# Lines shorter than 10 characters are also silently skipped.

HH:MM:SS.hh>COMMAND arg1,arg2,...

# A line ending in a backslash continues onto the next line:
00:00:00.00>CRE VERYLONGCALLSIGN,A320,52.0,4.0,090,FL200,250 \
            ;VERYLONGCALLSIGN LNAV ON
```

Real example (`scenario/_tutorial_example_commands.scn`):

```
# Example scenario

00:00:00.00>CRE KL204,B744,52,4,90,FL250,350
00:00:00.00>KL204 ORIG eham
00:00:00.00>KL204 DEST ehgg
00:00:00.00>KL204 addwpt SPL,fl250
00:00:00.00>KL204 addwpt RTM,,350
00:00:00.00>KL204 after spl addwpt SSB
00:00:00.00>KL204 LNAV ON;KL204 VNAV ON
```

Key points from `readscn()`:

- The timestamp is **elapsed simulation time since the scenario started** (`hh:mm:ss.hh`), not wall-clock time — consistent with §8's `simt` discussion.
- Multiple commands can be placed on one timestamped line separated by `;`.
- Lines are internally sorted by timestamp before being queued, so authoring order in the file doesn't have to be chronological (though keeping it chronological is far more readable).
- If a line's first token isn't a recognized command but matches an existing aircraft callsign, the simulator infers a `POS <acid>` — this is why you'll sometimes see bare `KL204` lines in older scenarios.

### 2.3 How a scenario actually runs

1. **`IC <filename>.scn`** (aliases `LOAD`, `OPEN`) is the command that loads a scenario: it resets the simulation (`bs.sim.reset()`), parses the whole file via `readscn()`, and loads all `(time, command)` pairs into `Stack.scentime` / `Stack.scencmd` — an internal, time-sorted queue on the simulation side (`bluesky/stack/simstack.py`, `bluesky/stack/stackbase.py`).
2. Every simulation timestep, `checkscen()` (`bluesky/stack/stackbase.py`) pops and executes all queued commands whose timestamp is `<= bs.sim.simt`, in order. This is why scenario timing is tied to simulation time, not wall time — a scenario run with `FF` (fast-forward) or a high `dtmult` fires its events sooner in wall-clock terms, but at the identical `simt` values.
3. **`SCENARIO <name>`** (alias `SCEN`) can set an explicit scenario name (`Stack.scenname`), which — importantly for §5 — is exactly the string used to build log filenames (`<LOGGER>_<scenarioname>_<timestamp>.log` in `datalog.makeLogfileName()`). If not set explicitly, the scenario name defaults to the `.scn` file's stem. Naming your scenario deliberately (e.g. per condition/trial ID) is the simplest way to keep log files traceable back to experimental conditions.
4. BlueSky remembers the last-loaded scenario in `scenario/ic.scn`, so `IC IC` reloads whatever was run last — convenient for quick manual re-testing, not something to rely on for a controlled experiment run (be explicit with filenames in automation).

### 2.4 Composing and parameterizing scenarios

For an experiment with many trials that share structure (e.g., common airspace/logger setup + a per-trial conflict geometry), BlueSky provides two composition commands, both handled the same as a normal scenario load but merged into the currently running one instead of replacing it (`merge()` in `simstack.py`):

- **`PCALL <filename> [REL/ABS] [arg0, arg1, ...]`** (alias `CALL`) — imports another `.scn` file's command list into the current run.
  - By default (`REL`), the imported file's timestamps are treated as **relative to the moment `PCALL` is issued** (i.e., its own `00:00:00.00` = "now"), which is what makes it useful as a reusable "sub-scenario" or procedure (e.g., a fixed 90-second conflict-buildup sequence you replay at different points in a trial). `ABS` instead treats its timestamps as absolute simulation time.
  - `%0`, `%1`, … placeholders in the imported file are substituted with the extra arguments passed to `PCALL` — a lightweight parameterization mechanism (e.g., pass in a callsign, a target altitude, or a conflict angle per trial without duplicating the file).
- **`SCHEDULE <time> <cmdline>`** — inserts a single command at an absolute future `simt`.
- **`DELAY <time> <cmdline>`** — inserts a single command at `simt + time` (relative to now).

Example use for a parameterized, reusable conflict block (`conflict_template.scn`):

```
00:00:00.00>CRECONFS %0,A320,%1,%2,0,%3
```

...called per trial from a master scenario as, e.g.:

```
00:01:00.00>PCALL conflict_template INTRUD01,OWNSHIP,180,120
00:03:00.00>PCALL conflict_template INTRUD02,OWNSHIP,90,90
```

This constructs two different `CRECONFS` conflicts at two different times in the trial from one reusable template, which is a natural way to keep a bank of standard conflict-geometry building blocks and combine them per condition rather than writing full geometry into every trial file.

### 2.5 Running scenarios for an experiment (headless/batch)

- **Single run, headless:** `BlueSky.py --headless` starts the simulation node only (no GUI); issue `IC <scenario>.scn` (e.g. by pre-seeding it as a startup command, or driving the node over the network) to run one trial and let its loggers write to `output/`.
- **`BATCH <filename>`** (`bluesky/simulation/simulation.py: batch()`) — treats the given file as **a list of scenarios to run sequentially** on the server rather than as a single trial's commands; each is loaded and run in turn, which is the built-in mechanism for unattended multi-trial/multi-participant batches without scripting the network API yourself.
- Because everything is just stack commands, an experiment runner (e.g., a Python controller script) can equally well drive trials directly over BlueSky's network interface — connecting as a client and issuing `IC`, `EXP`, `CRELOG`, `CRECONFS`, etc. programmatically per trial — rather than relying purely on static `.scn` files, if trial parameters need to be generated dynamically (e.g., randomized per participant).

---

## 3. Triggering Conflicts (Step-by-Step)

### 3.1 Important correction vs. common tutorials

In this installed version, **`CD` is *not* the conflict-detection toggle** — `CD` is the command to **change the scenario folder** (`bluesky/stack/basecmds.py`, "`CD [path]` — Change to a different scenario folder"). This is a frequent source of confusion because older BlueSky material used `CD ON`/`CD OFF`. In v1.1.1 the equivalent commands are:

| Purpose | Command | Notes |
|---|---|---|
| Select/enable a conflict-detection method | `CDMETHOD <name>` (alias `ASAS`) | `CDMETHOD ON` enables the first registered method (normally `STATEBASED`); `CDMETHOD OFF` disables detection entirely; `CDMETHOD` with no argument reports the current method and lists available ones |
| Select a conflict-resolution (avoidance) method | `RESO <name>` | e.g. `RESO MVP`; `RESO OFF` disables resolution (aircraft will still be *detected* as in conflict, but won't maneuver) |
| Set protected-zone horizontal radius | `ZONER <nm>` (aliases `PZR`, `RPZ`, `PZRADIUS`) | Default from `asas_pzr` in `settings.cfg` (5.0 NM) |
| Set protected-zone vertical half-height | `ZONEDH <ft>` (aliases `PZDH`, `DHPZ`, `PZHEIGHT`) | Default from `asas_pzh` (1000 ft) |
| Set detection lookahead time | `DTLOOK <sec>` | Default from `asas_dtlookahead` (300 s) |

### 3.2 Two ways to create a conflict

#### Method A — `CRECONFS`: purpose-built, deterministic (recommended for experiments)

BlueSky ships a dedicated stack command that geometrically constructs an aircraft guaranteed to conflict with a chosen target, given the desired encounter geometry — this is by far the most reliable way to script repeatable conflicts for an experiment, since you specify the conflict parameters directly instead of back-computing headings/speeds/positions.

```
CRECONFS acid, actype, targetid, dpsi, cpa, tlosh, [dH, tlosv, spd]
```

Arguments (`bluesky/traffic/traffic.py: creconfs`):

| Arg | Meaning |
|---|---|
| `acid` | Callsign of the new (intruder) aircraft |
| `actype` | ICAO aircraft type (e.g. `A320`) |
| `targetid` | Callsign of the existing "ownship" aircraft to conflict with |
| `dpsi` | Conflict angle — difference between the two tracks, in degrees (e.g. `180` = head-on, `90` = crossing) |
| `cpa` | Predicted closest-point-of-approach distance, in NM (use `0` for a direct hit) |
| `tlosh` | Time to horizontal loss of separation, in seconds (or `hh:mm:ss`) — i.e., "conflict occurs N seconds from now" |
| `dH` *(optional)* | Vertical offset from target's altitude, ft (omit for same-altitude conflict) |
| `tlosv` *(optional)* | Time to vertical loss of separation |
| `spd` *(optional)* | New aircraft's speed (CAS/kts or Mach); defaults to matching the target's speed |

**Example — deterministic head-on conflict in ~2 minutes:**

```
00:00:00.00>CRE OWNSHIP,A320,52.0,4.5,090,FL200,250
00:00:00.00>CRECONFS INTRUD01,A320,OWNSHIP,180,0,120
```

This creates `OWNSHIP` heading east at FL200/250kt, then creates `INTRUD01` on a reciprocal head-on track (`dpsi=180`), with zero miss distance (`cpa=0`), timed to reach the loss-of-separation point in `120` seconds.

#### Method B — Manual `CRE` + `HDG`/`ALT`/`SPD` (full manual control)

```
CRE acid, type, lat, lon, hdg, alt, spd
```

Manually position two aircraft on converging tracks and let physics do the rest:

```
00:00:00.00>CRE AC001,B738,52.30,4.40,090,FL100,280
00:00:00.00>CRE AC002,B738,52.30,4.60,270,FL100,280
```

Then use `HDG acid, hdg`, `ALT acid, alt`, `SPD acid, spd` to adjust tracks in real time so the pair's protected zones (default 5 NM horizontal / 1000 ft vertical) will be violated at CPA. This method requires manually working out geometry/timing — for repeatable experimental trials, `CRECONFS` is strongly preferred since it removes trigonometry from the scenario-authoring process.

### 3.3 How BlueSky visually indicates a conflict / LoS

Rendering is handled per-frame in `bluesky/ui/qtgl/gltraffic.py`, driven by the per-aircraft `inconf` flag computed each detection cycle by `bs.traf.cd` (`bluesky/traffic/asas/statebased.py`):

- **Aircraft color:** normal aircraft render in the default aircraft color (green, RGB `(0,255,0)` in the default palette); any aircraft with `inconf == True` (i.e., inside its predicted-conflict lookahead window) switches to the **conflict color**, orange `(255,160,0)` (`palette.conflict`, `bluesky/resources/graphics/palettes/bluesky-default`).
- **CPA line:** for each in-conflict aircraft, a line is drawn from the aircraft's current position to its predicted closest-point-of-approach location (`self.cpalines` in `gltraffic.py`), computed from `tcpamax` and current track/groundspeed.
- **Status bar / node info:** the running counters `#CONF` (current unique conflicts) and `#LOS` (current unique actual losses of separation) are pushed to the UI at 1 Hz (`SIMINFO_RATE` in `bluesky/simulation/screenio.py`) and shown in the console/status panel (`bluesky/ui/console/consoleui.py`, `bluesky/ui/pygame/screen.py`).
- **Important nuance:** BlueSky v1.1.1 does **not** render a visually distinct color for an actual Loss of Separation (`lospairs`, i.e. protected zones physically overlapping) versus a mere predicted conflict (`inconf`, within the lookahead window but zones not yet overlapping) — both use the same orange color and CPA-line treatment. The distinction between "conflict" (`confpairs`/`inconf`) and "LoS" (`lospairs`, where `dist < rpz` and `|Δalt| < hpz` right now) is tracked internally and is what feeds the `#CONF`/`#LOS` counters and the logs below, but is not colour-coded differently on the radar screen out of the box. If your experiment needs a visually distinct LoS indicator, this is a natural small QTGL/plugin customization point, not a built-in feature.

---

## 4. The `settings.cfg` File

### 4.1 What it is

`settings.cfg` is a plain Python-syntax key–value file at the project root (there is also a packaged default at `bluesky/resources/default.cfg`, which is copied to the project root on first run if no `settings.cfg` exists). Every line is a valid Python assignment, parsed and exec'd by `bluesky/settings.py`, then exposed as attributes on `bs.settings` (e.g., `bs.settings.simdt`).

### 4.2 Full breakdown of default sections

```ini
# --- Networking ---
recv_port = 11000          # Port the sim node listens on
send_port = 11001          # Port the sim node publishes state on

# --- Core simulation ---
performance_model = 'openap'   # 'openap' | 'bada' | 'legacy'
verbose = False                 # Verbose internal debug logging
simdt = 0.05                    # Simulation physics timestep [s]  -> 20 Hz
performance_dt = 1.0             # Aircraft-performance model update interval [s]
fms_dt = 1.0                     # Flight-management-system update interval [s]
prefer_compiled = True           # Use compiled cgeo/casas extensions if available
max_nnodes = 999                 # Max parallel simulation nodes

# --- Filesystem paths (all relative to project root unless absolute) ---
log_path       = 'output'        # Where .log files are written
scenario_path  = 'scenario'      # Where .scn scenario files live
gfx_path       = 'graphics'
cache_path     = 'cache'
navdata_path   = 'navdata'
perf_path      = 'performance'
perf_path_bada = 'performance/BADA'   # Leave '' if BADA license not available
plugin_path    = 'plugins'

# --- Plugins ---
enabled_plugins = ['area', 'datafeed']   # Loaded automatically at startup

# --- Radar screen ---
start_location = 'EHAM'          # [lat, lon] or ICAO code for initial radar view

#=== ASAS (conflict detection/resolution) defaults ===
asas_dtlookahead = 300.0   # Lookahead time [s]  -> DTLOOK
asas_dt          = 1.0     # ASAS update interval [s]
asas_pzr         = 5.0     # Protected-zone horizontal radius [NM]  -> ZONER
asas_pzh         = 1000.0  # Protected-zone vertical half-height [ft]  -> ZONEDH
asas_marh        = 1.05    # Resolution horizontal margin factor
asas_marv        = 1.05    # Resolution vertical margin factor

#=== QTGL GUI-specific ===
text_size = 13
apt_size  = 10
wpt_size  = 10
ac_size   = 16
stack_text_color       = 0, 255, 0
stack_background_color = 102, 102, 102
```

### 4.3 How settings are actually used

- **`bs.settings.set_variable_defaults(...)`** is called by individual modules (e.g., `bluesky/traffic/asas/detection.py` calls `set_variable_defaults(asas_pzr=5.0, asas_pzh=1000.0, asas_dtlookahead=300.0)`) — this means a module's true defaults live in the module itself; `settings.cfg` only *overrides* whatever a module registers. If you add a new plugin that needs a config value, it registers its own default the same way, and you can then add an override line to `settings.cfg`.
- **Enabling plugins:** either statically via `enabled_plugins = ['area', 'datafeed', 'yourplugin']` in `settings.cfg` (loaded at every startup), or dynamically at runtime/from a scenario file with the stack command `PLUGIN LOAD <name>` (equivalently `PLUGINS LOAD`). Use the static list for anything your experiment always needs (e.g., a custom EEG-sync logger plugin); use runtime loading for optional/conditional plugins.
- **Performance/UI tuning:** `simdt` is the physics integration step; `performance_dt`/`fms_dt` throttle how often the heavier performance/FMS calculations run (both can be relaxed to `> simdt` for speed on large scenarios). The QTGL section only affects the rendering client, not the simulation engine — irrelevant when running `--headless`.
- **Loggers are *not* configured in `settings.cfg` directly** — only `log_path` (where files land) is set here. Which loggers exist and their variables are defined in code/plugins and activated via stack commands or scenario lines (Section 6).

---

## 5. Comprehensive Log Files Guide

### 5.1 Architecture: BlueSky logging is generic, not a fixed set of "modes"

Unlike some ATM sims, BlueSky has **no built-in enum of log types**. Instead, `bluesky/tools/datalog.py` provides a generic `CSVLogger` class and a factory function `crelog(name, dt, header)`. Any module or plugin can call `crelog()` to register a brand-new named logger, which automatically gets its own stack command (named after the logger) for turning it on/off and selecting variables. This means the "list of log files" is really "whatever loggers the currently-loaded plugins happen to register" — in this codebase, that is:

| Logger name | Registered by | Type |
|---|---|---|
| **`FLSTLOG`** | `bluesky/plugins/area.py` (`AREA` plugin) | Event-triggered (per-aircraft, on area exit) |
| **`CONFLOG`** | `bluesky/plugins/area.py` (`AREA` plugin) | Event-triggered (per new conflict) |
| **`OCCUPANCYLOG`** | `bluesky/plugins/sectorcount.py` (`SECTORCOUNT` plugin) | Periodic (every `update_interval`, default 3 s) |
| *(custom via `CRELOG`)* | Any scenario/plugin, at will | Periodic or manual, fully user-defined columns |

**On `CMDLOG`/`OPLOG`:** these names do **not** exist in this installed version's source (`bluesky-simulator` v1.1.1) — they are not defined anywhere in `bluesky/`. If your workflow references them, they likely come from a different fork/version, a research group's custom plugin, or a mix-up with the generic `CRELOG` mechanism. What v1.1.1 provides instead for "what commands were issued when" is the **`SAVEIC`** scenario recorder (`bluesky/stack/recorder.py`) — see §5.6 — which is a *command* record, not a `.log` CSV.

### 5.2 `FLSTLOG` — Flight Statistics Log

- **Source:** `Area.update()` in `bluesky/plugins/area.py`, logged when an aircraft's position transitions from *inside* to *outside* the defined experiment area (`EXP`).
- **Trigger type:** **event-based** — one row is written per aircraft **at the moment it exits the experiment area** (or is deleted after descending below the taxi-altitude threshold, if `TAXI OFF` is set). It is *not* a continuous time series and *not* a batch export — rows accumulate throughout the run, one per aircraft-exit event.
- **Requires:** the `AREA`/`EXP` plugin active and an experiment area defined (`EXP <shapename>` or `EXP lat,lon,lat,lon,[top,bottom]`) — the logger only starts writing once `self.flst.start()` is called, which happens inside `Area.set_area()`.

**Columns** (order as written in `area.py`):

| # | Column | Unit |
|---|---|---|
| 1 | Deletion/exit time (`simt`, auto-prepended by `CSVLogger`) | s |
| 2 | Call sign | – |
| 3 | Spawn time | s |
| 4 | Flight time (time inside experiment area) | s |
| 5 | Actual 2D distance flown | NM |
| 6 | Actual 3D distance flown | NM |
| 7 | Work done (force × distance) | MJ |
| 8 | Latitude at exit | deg |
| 9 | Longitude at exit | deg |
| 10 | Altitude at exit | ft |
| 11 | TAS at exit | kts |
| 12 | Vertical speed at exit | fpm |
| 13 | Heading at exit | deg |
| 14 | Origin latitude | deg |
| 15 | Origin longitude | deg |
| 16 | Destination latitude | deg |
| 17 | Destination longitude | deg |
| 18 | ASAS/conflict-resolution active flag | bool |
| 19 | Autopilot-commanded (pilot) altitude | ft |
| 20 | Autopilot-commanded (pilot) TAS | kts |
| 21 | Autopilot-commanded (pilot) heading | deg |
| 22 | Autopilot-commanded (pilot) VS | fpm |

### 5.3 `CONFLOG` — Conflict Statistics Log

- **Source:** also `Area.update()` in `area.py`.
- **Trigger type:** **event-based**, but coarser than FLST — by default it logs only a **running total conflict count**, and only when a *new* conflict pair appears where at least one aircraft is inside the experiment area. It does not, by default, log full conflict geometry.
- **Default columns:** `simt`, cumulative conflict count in experiment area (`confinside_all`).
- **Extending it:** because `CONFLOG` is a generic `CSVLogger`, you can attach additional variables straight from the conflict-detection object using `ADD FROM`. An example shipped in this repo (`scenario/Loggers/conflog.scn`) shows the intended pattern:

```
0:00:00.00>CRELOG CONFLOG 1.0 Conflict log
0:00:00.00>CONFLOG ADD FROM traf.asas confpairs_new dcpa_new tcpa_new tLOS_new qdr_new dist_new
0:00:00.00>CONFLOG ON
```

  **This shipped example is stale and will not work as-is in v1.1.1** — it references `traf.asas`, but the conflict-detection object now lives at `traf.cd` (`bs.traf.cd`, per §1.3), and the `_new`-suffixed variable names (`confpairs_new`, `dcpa_new`, …) don't exist as attributes on `ConflictDetection` (`bluesky/traffic/asas/detection.py`) — the real attribute names are `confpairs`, `confpairs_unique`, `dcpa`, `tcpa`, `tLOS`, `qdr`, `dist` (see the table in §9). It's included here only to illustrate the *intended pattern* — reaching into a registered `Entity`'s attributes by dotted path via the variable explorer (`ve.findvar`) — not as a command to copy verbatim. The corrected, working version is:

```
0:00:00.00>CRELOG CONFLOG 1.0 Conflict log
0:00:00.00>CONFLOG ADD FROM traf.cd confpairs_unique dcpa tcpa tLOS qdr dist
0:00:00.00>CONFLOG ON
```

### 5.4 `OCCUPANCYLOG` — Sector Occupancy Count

- **Source:** `bluesky/plugins/sectorcount.py`.
- **Trigger type:** **periodic**, driven by the plugin's `update_interval` (default 3.0 s, set via the plugin's `config` dict — not user-configurable without editing the plugin or re-`CRELOG`-ing with a different `dt`).
- **Columns:** for each registered sector (added via `SECTORCOUNT ADD <shapename>`), a `<sectorname>, <count>` pair, all sectors on one row per interval.

### 5.5 Custom loggers (`CRELOG`) — general mechanism

Any script, plugin, or scenario file can define an arbitrary logger at runtime:

```
CRELOG <name> [dt] [header text]
<name> ADD [FROM parent] var1, var2, ...
<name> ON [dt]
<name> OFF
```

- Omitting `dt` in `CRELOG` creates a **non-periodic** logger (you must call `.log()` explicitly from code, as `area.py` does for `FLSTLOG`/`CONFLOG`); supplying `dt` creates a **periodic** logger that auto-writes every `dt` seconds of *simulation* time via `datalog.update()`, called once per sim timestep.
- Every column is written with 8-decimal precision (`logprecision = '%.8f'`) for numeric data; the first column is always `simt` (simulation time in seconds), auto-prepended.
- All CSV log files are prefixed with a `#`-commented header block plus a final `#`-commented column-name row, then land in `log_path` (default `output/`) named `<LOGGERNAME>_<scenarioname>_<YYYYMMDD_HH-MM-SS>.log`.

### 5.6 `SAVEIC` — the closest analogue to a command/operations log

Not a `CSVLogger` at all, but directly relevant if you need "what happened and when" at the command level (the likely intent behind "CMDLOG/OPLOG"):

- **Command:** `SAVEIC <filename>` starts recording; `SAVEIC CLOSE` stops.
- **Trigger type:** event-based — one line written **every time a stack command is executed** (via `savecmd()`, called from the stack dispatcher), timestamped relative to the moment `SAVEIC` was issued, in the same `HH:MM:SS.hh>COMMAND` format as a scenario file.
- **Output:** a `.scn`-formatted file in `scenario_path`, not `log_path` — it's designed to let you *replay* a run, not primarily to analyze it as tabular data.
- By default it excludes purely-UI commands (`PAN`, `ZOOM`, `POS`, …) and a few others (see `defexcl` list in `recorder.py`); `SAVEIC ... EXCEPT NONE` records everything except the bare minimum.

---

## 6. Log Structure & Timing — Summary Table

| Log | Columns recorded | Timing behavior |
|---|---|---|
| `FLSTLOG` | 22 flight-summary fields per exiting aircraft (see §5.2) | **Event-based**: one row per aircraft, at the instant it exits the experiment area (or auto-deletes). Not periodic, not a batch dump. |
| `CONFLOG` (default) | `simt`, cumulative in-area conflict count | **Event-based**: one row per *new* unique conflict pair involving the experiment area. Can be converted to periodic + geometry-rich via `CRELOG ... dt` + `ADD FROM traf.cd ...`. |
| `OCCUPANCYLOG` | Per-sector `(name, count)` pairs | **Periodic**: fixed 3 s wall-of-sim-time interval by default. |
| Custom `CRELOG` logger | Whatever variables you `ADD` | **Either**, your choice: periodic (`CRELOG name dt ...`) or manual/event-driven (`CRELOG name` with no `dt`, then call `.log()` from a plugin at the moment you want). |
| `SAVEIC` | Full stack command line + relative timestamp | **Event-based**: one line per executed stack command (state-changing commands only, and only those not in the exclusion list). |

None of BlueSky's built-in logs are **batch-export-at-end-of-run** — all are written incrementally to disk during the simulation (`np.savetxt` appends to an already-open file handle each time `.log()` fires), and are only closed/flushed on `<LOGGER> OFF`, on scenario `RESET`, or on quit (`datalog.reset()`).

---

## 7. Logging Configuration

### 7.1 There is no single global `DATALOG ON`

Because every logger is independently named (per §5), there is **no single command that turns "all logging" on** in this version. Each logger is switched on/off individually, by its own name:

```
FLSTLOG ON
CONFLOG ON
OCCUPANCYLOG ON
```

(If your training material refers to `DATALOG ON` as a universal switch, that is not present in v1.1.1's source — it may be conflating this with the per-logger `<NAME> ON` pattern, or with a different BlueSky fork.)

### 7.2 Via terminal / console

```
>>> PLUGIN LOAD AREA          # ensure the plugin that owns FLSTLOG/CONFLOG is active
>>> EXP 52.0,4.0,52.6,4.9      # define an experiment area (box: lat,lon,lat,lon)
>>> FLSTLOG ON                 # (also auto-started by AREA/EXP activation — see area.py: set_area() calls self.flst.start())
>>> CONFLOG ON
>>> AREA 52.0,4.0,52.6,4.9      # (optional) separate deletion area; also triggers logger start
```

Practically: simply issuing `EXP <shape>` or `AREA <coords>` already calls `self.flst.start()` / `self.conflog.start()` internally (see `Area.set_area()` in `area.py`), so defining the experiment area is normally sufficient to begin logging — explicit `FLSTLOG ON` is mainly useful if you want to add/select variables first, or restart logging mid-run.

To add custom variables to an existing logger before starting it:

```
>>> CONFLOG ADD FROM traf.cd confpairs_unique
>>> CONFLOG ON
```

### 7.3 Via scenario file (`.scn`)

Because the command stack is the same regardless of source, the identical commands go straight into a scenario file with timestamps, and execute automatically when the scenario is loaded with `IC <file>.scn` or on startup (see §2 for the full scenario-file mechanism):

```
00:00:00.00>PLUGIN LOAD AREA
00:00:00.00>EXP 52.0,4.0,52.6,4.9
00:00:00.00>CRELOG MYLOG 0.5 Custom per-trial log
00:00:00.00>MYLOG ADD FROM traf lat lon alt hdg cas
00:00:00.00>MYLOG ADD FROM traf.cd inconf
00:00:00.00>MYLOG ON
00:00:00.00>CRE OWNSHIP,A320,52.0,4.5,090,FL200,250
00:00:05.00>CRECONFS INTRUD01,A320,OWNSHIP,180,0,120
```

This pattern — a custom periodic `CRELOG` pulling straight from `traf` and `traf.cd` at a fixed `dt` — is the recommended way to get a clean, fixed-rate time series per trial (e.g., aircraft state + `inconf` flag every 0.5 s) rather than relying on the coarse, event-only built-in `FLSTLOG`/`CONFLOG`.

### 7.4 Enabling plugins at startup vs. runtime

- Startup (applies to every run): add to `enabled_plugins` in `settings.cfg`.
- Runtime/scenario (applies to this run only): `PLUGIN LOAD <NAME>` as a stack command or scenario line, as shown above.

---

## 8. Real-Time Data Limitations

For a human-factors experiment that needs to align BlueSky events with external hardware (EEG, eye-tracking, physiological sensors), the built-in CSV logs have real constraints worth knowing before you design your synchronization approach:

- **Time base is simulation time, not wall-clock time.** Every log's first column is `simt` — elapsed *simulated* seconds since scenario start — not a wall-clock/UTC timestamp. If BlueSky is not run strictly real-time (`dtmult` ≠ 1, fast-forward via `FF`, or paused via `HOLD`), `simt` diverges from wall-clock time, so naively matching `simt` to your EEG device's system-clock timestamps will drift. You must either (a) force strict real-time execution (`REALTIME ON`, which caps the timestep so `1 s` of `simt` ≈ `1 s` of wall time — see `bs.sim.realtime()` in `bluesky/simulation/simulation.py`) and separately record a wall-clock reference point at scenario start (e.g., log `time.time()` the instant you send `IC`/first `CRE`), or (b) have your own plugin stamp true wall-clock time (`datetime.now()`/`time.time_ns()`) alongside `simt` in a custom `CRELOG`.
- **Precision is second-level by construction, not millisecond-level.** The built-in periodic loggers default to coarse intervals (`OCCUPANCYLOG` at 3 s; the shipped `CONFLOG` example at 1 s), and even a maximally aggressive custom `CRELOG` is bounded below by the simulation physics step `simdt` (default `0.05 s` = 20 Hz — see `settings.cfg`). Getting below `simdt` resolution requires lowering `simdt` itself, which slows the whole simulation proportionally. Sub-`simdt` precision (true millisecond alignment) is not something the CSV logging path can give you at all, because logger calls only ever fire at simulation-timestep boundaries.
- **Event-based logs (`FLSTLOG`, default `CONFLOG`) are inherently asynchronous with respect to a fixed sampling clock.** They fire on state transitions (area exit, new conflict), not at regular intervals — fine for post-hoc epoch construction, unsuitable for anything that needs a continuous, evenly-spaced signal to cross-correlate against EEG sample streams.
- **Client/UI update rate is decoupled and lower-resolution still.** What the *GUI* displays (and what a screen-based reaction-time measurement might implicitly rely on) is only pushed from sim to client at `ACUPDATE_RATE = 5 Hz` for aircraft state and `SIMINFO_RATE = 1 Hz` for conflict/LoS counters (`bluesky/simulation/screenio.py`) — this is a separate, coarser bottleneck from the underlying `simdt`, relevant if your sync signal is derived from what's rendered rather than from the logs directly.
- **CSV writes are buffered/incremental but not guaranteed flushed per row**, and there is no built-in per-row wall-clock timestamp or hardware trigger/TTL output — BlueSky has no notion of an external synchronization pulse.

### Recommended approach for tight synchronization

For millisecond-accurate alignment with external hardware, don't rely on the built-in CSV logs at all — write a small **custom plugin** (structured like `bluesky/plugins/area.py`/`sectorcount.py`, registered in `enabled_plugins`) that:

1. Hooks the simulation's per-timestep update (via `@timed_function` or the plugin `update`/`update_interval` mechanism) so it runs at your required cadence, down to `simdt` resolution.
2. Reads `bs.sim.simt` **and** a genuine wall-clock timestamp (`time.time_ns()`) on every call, writing both.
3. Optionally emits a hardware trigger (e.g., a serial/TTL pulse, an LSL marker via the `pylsl` library, or a UDP packet to your EEG acquisition software) at the exact moment a conflict/LoS event fires (`traf.cd.confpairs_unique` / `lospairs_unique` transitions), rather than waiting for the coarse built-in loggers to catch up.
4. Runs with `REALTIME ON` and `simdt` set low enough (e.g., `0.01`–`0.02 s`) to bound your worst-case timing error to an acceptable value for your EEG epoch requirements.

This gives sample-accurate, wall-clock-anchored, event-triggered data suitable for sensor fusion — something the stock `FLSTLOG`/`CONFLOG`/`OCCUPANCYLOG` files are not designed to provide.

---

## 9. Command Cheat Sheet — Getting Data Out of BlueSky

Every command below is verified against v1.1.1 source (file/line references given inline in earlier sections). Grouped by what you're trying to accomplish, since "get data" spans several independent subsystems (conflict engine, area/logger plugin, generic `CRELOG`, live inspection, and command recording).

### 9.0 Minimal working sequence

This is the smallest set of commands that gets conflict data flowing to disk, corrected from the pattern in your example (`CDMETHOD ON`, not `CD ON`; there is no standalone `DATALOG ON` — see §7.1):

```
CDMETHOD ON          # enable conflict detection (picks STATEBASED by default)
RESO OFF              # (optional) keep conflicts un-resolved if you want them to play out for measurement
PLUGIN LOAD AREA       # ensure FLSTLOG/CONFLOG exist (AREA is enabled by default via settings.cfg)
EXP 52.0,4.0,52.6,4.9   # define the experiment area -> this alone starts FLSTLOG and CONFLOG
FLSTLOG ON              # explicit (usually redundant after EXP, but harmless / makes intent clear)
CONFLOG ON
```

### 9.1 Conflict detection & resolution (prerequisite for any conflict/LoS data)

| Command | Effect |
|---|---|
| `CDMETHOD ON` | Enable conflict detection using the first registered method (`STATEBASED`) — **this is the correct on-switch**, not `CD ON` (§3.1) |
| `CDMETHOD STATEBASED` | Explicitly select the state-based detector |
| `CDMETHOD OFF` | Disable detection entirely and clear the conflict database |
| `CDMETHOD` (no arg) | Report current method + list available methods |
| `RESO <name>` (e.g. `RESO MVP`) | Enable a conflict-*resolution* (avoidance-maneuver) method |
| `RESO OFF` | Disable resolution — aircraft are still *detected* as in conflict (so `inconf`/logs still populate) but won't maneuver away, useful if you want conflicts to actually resolve into a LoS for measurement |
| `ZONER <nm>` (aliases `PZR`, `RPZ`, `PZRADIUS`) | Set/report horizontal protected-zone radius (default 5 NM) |
| `ZONEDH <ft>` (aliases `PZDH`, `DHPZ`, `PZHEIGHT`) | Set/report vertical protected-zone half-height (default 1000 ft) |
| `DTLOOK <sec>` | Set/report conflict-detection lookahead time (default 300 s) |
| `DTNOLOOK <sec>` | Set interval after a resolution during which detection is skipped for that pair |

### 9.2 Built-in loggers — start/stop and area setup

| Command | Effect |
|---|---|
| `PLUGIN LOAD AREA` | Load the plugin that defines `FLSTLOG`/`CONFLOG` (on by default per `settings.cfg: enabled_plugins`) |
| `EXP <shape>` / `EXP lat,lon,lat,lon,[top,bottom]` | Define the **experiment area** — aircraft entering/exiting it drive `FLSTLOG`/`CONFLOG`; also auto-calls `.start()` on both loggers |
| `AREA <shape>` / `AREA lat,lon,lat,lon,[top,bottom]` | Define the **deletion area** (aircraft leaving it are deleted); also auto-starts the loggers |
| `AREA OFF` | Switch the deletion area off |
| `TAXI ON/OFF [alt]` | Toggle ground/low-altitude auto-delete behavior (`OFF` auto-deletes below 1500 ft by default) |
| `FLSTLOG ON` | (Explicit) start the flight-statistics logger — see §5.2 for the 22 columns written per aircraft on area exit |
| `CONFLOG ON` | (Explicit) start the conflict-count logger — see §5.3; extend with `ADD FROM traf.cd ...` first for real geometry |
| `<LOGGERNAME> OFF` | Stop and close any logger (flushes the file) |
| `PLUGIN LOAD SECTORCOUNT` | Load the sector-occupancy plugin |
| `SECTORCOUNT ADD <shapename>` | Register a sector to be counted (drives `OCCUPANCYLOG`, periodic at 3 s) |
| `SECTORCOUNT LIST` / `SECTORCOUNT REMOVE <name>` | Manage registered sectors |

### 9.3 Custom logging — the general `CRELOG` mechanism

| Command | Effect |
|---|---|
| `CRELOG <name> [dt] [header]` | Define a new logger; give `dt` for periodic (fixed-interval), omit it for manual/event logging |
| `<name> ADD [FROM <parent>] var1,var2,...` | Attach one or more variables to that logger, optionally from a named parent object (`traf`, `traf.cd`, `traf.ap`, `sim`, or any plugin registered via `register_data_parent`, keyed by its lower-cased `plugin_name`) |
| `<name> ON [dt]` | Start logging (optionally overriding the interval) |
| `<name> OFF` | Stop logging and close the file |
| `<name>` (no args) | Report whether it's periodic/manual, its current variable list, and ON/OFF status |
| `LSVAR` (no arg) | **List all top-level parent objects** currently available to log from (`sim`, `traf`, plus any loaded plugin) |
| `LSVAR <path>` (e.g. `LSVAR traf.cd`) | Inspect one variable/object: its type, size, parent, and child attribute names — the fastest way to discover exactly what's loggable before writing `ADD FROM` |

**Worked example — fixed-rate per-trial state log at 0.5 s, correcting the stale shipped `conflog.scn` pattern (§5.3):**

```
CRELOG TRIALLOG 0.5 Per-trial state + conflict log
TRIALLOG ADD FROM traf id lat lon alt hdg cas
TRIALLOG ADD FROM traf.cd inconf confpairs_unique
TRIALLOG ON
```

### 9.4 Verified loggable variable paths (for `ADD FROM`)

| Parent | Variables | Source |
|---|---|---|
| `traf` | `id`, `type`, `lat`, `lon`, `alt` [m], `hdg` [deg], `trk` [deg], `tas`/`gs`/`cas` [m/s], `vs` [m/s], `work` [J], `ntraf` | `bluesky/traffic/traffic.py` |
| `traf.cd` | `confpairs`, `confpairs_unique`, `confpairs_all`, `lospairs`, `lospairs_unique`, `lospairs_all`, `inconf`, `tcpamax`, `qdr`, `dist`, `dcpa`, `tcpa`, `tLOS`, `rpz`, `hpz`, `dtlookahead` | `bluesky/traffic/asas/detection.py` |
| `traf.ap` | `alt`, `tas`, `vs`, `trk` (autopilot-*commanded* values, i.e. "pilot" targets — same fields `FLSTLOG` logs as Pilot ALT/SPD/HDG/VS) | `bluesky/traffic/autopilot.py` |
| `traf.cr` | `active` (per-aircraft bool: is conflict-resolution currently maneuvering this aircraft) | `bluesky/traffic/asas/resolution.py` |
| `sim` | `simt` (elapsed sim seconds), `utc` | `bluesky/simulation/simulation.py` |

Use `LSVAR traf.cd` (etc.) at runtime to confirm current attribute names before relying on this table — internal names have already changed once between BlueSky versions (§5.3), so re-verifying against a live `LSVAR` call costs nothing and avoids silently-empty log columns.

### 9.5 Live / one-off inspection (console output, not written to a log file)

| Command | Effect |
|---|---|
| `POS <acid>` | Print full current state of one aircraft to the console |
| `LSVAR <path>` | Print type/size/attributes of any variable (see §9.3) |
| `PLOT [x], y [,dt,colour,figure]` | Live in-session graph of one or two variable paths over time (visual sanity-check, not a data-export mechanism) |
| `DIST lat0,lon0,lat1,lon1` | One-off distance/bearing calculation between two points |
| `HELP >filename` | Dump every registered stack command (name, usage, args) to a tab-delimited reference file — useful to generate a full, current command list for your own records rather than trusting any external doc, including this one |

### 9.6 Recording *commands* (not CSV data) for reproducibility

| Command | Effect |
|---|---|
| `SAVEIC <file>` | Start recording every executed stack command to a replayable `.scn` file (§5.6) |
| `SAVEIC EXCEPT <cmd1,...>` / `SAVEIC EXCEPT NONE` | Change/clear the exclusion list (UI-only commands like `PAN`/`ZOOM` are excluded by default) |
| `SAVEIC CLOSE` | Stop recording and close the file |

### 9.7 Timing & synchronization controls (affect how logged `simt` maps to wall-clock time — §8)

| Command | Effect |
|---|---|
| `REALTIME ON/OFF` | Force/release strict real-time pacing (`ON` keeps `simt` ≈ wall-clock time) |
| `DTMULT <factor>` | Speed multiplier relative to real-time (only meaningful with `REALTIME` handling; `FF` ignores pacing entirely) |
| `FF [seconds]` | Fast-forward the simulation, optionally by a fixed amount of `simt` |
| `HOLD` | Pause the simulation |
| `OP` | Resume/start running |
| `DT <sec>` or `DT <target>,<sec>` | Set the simulation timestep globally, or per named sub-system (e.g. `performance_dt`) — overrides `settings.cfg` (§4.2) for the running session |

### 9.8 Scenario-driven / batch automation (full detail in §2)

| Command | Effect |
|---|---|
| `IC <file>.scn` (aliases `LOAD`, `OPEN`) | Reset sim and load/run a scenario file |
| `SCENARIO <name>` (alias `SCEN`) | Set the scenario name embedded in every log filename |
| `PCALL <file> [REL/ABS] [args]` (alias `CALL`) | Merge a reusable scenario template into the current run, with `%0,%1,...` substitution |
| `SCHEDULE <time> <cmdline>` | Queue a command at an absolute future `simt` |
| `DELAY <time> <cmdline>` | Queue a command at `simt + time` |
| `BATCH <file>` | Run a list of scenario files sequentially — the built-in mechanism for unattended multi-trial data collection |

### 9.9 Aircraft/geometry creation (full detail in §3)

| Command | Effect |
|---|---|
| `CRE acid,type,lat,lon,hdg,alt,spd` | Create an aircraft |
| `CRECONFS acid,type,targetid,dpsi,cpa,tlosh,[dH,tlosv,spd]` | Create an aircraft in a deterministic, parameterized conflict with an existing one — the reliable way to generate conflict *events* for your logs on a schedule |
| `HDG` / `ALT` / `SPD` | Manually command heading / altitude / speed (for the manual conflict-construction method) |
