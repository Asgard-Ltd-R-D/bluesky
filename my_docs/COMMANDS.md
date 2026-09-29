# BlueSky Command Reference (this checkout)

Every command below was verified directly against this repo's installed
`bluesky` source (not copied from BlueSky's own shipped `docs/` folder,
which describes an older package layout - see
`BLUESKY_TECHNICAL_OVERVIEW.md` §3.1 for a worked example of where that
divergence bites). Where a command has aliases, they're listed after it.

Syntax convention: `acid` = aircraft callsign, `[x]` = optional,
`x/y` = choose one, `alt` accepts `FL250`, `25000` (ft) or a value with a
unit. Commands are typed in the console, or placed in a `.scn` file as
`HH:MM:SS.hh> COMMAND args`.

## 1. Simulation control

| Command | Aliases | Does |
|---|---|---|
| `OP` | | Start/run the simulation, or resume after `HOLD` |
| `HOLD` | | Pause the simulation |
| `RESET` | | Reset the simulation (clears traffic, loggers, plugin state) |
| `IC [file]` | `LOAD`, `OPEN` | Load a scenario file (resets first, then reads the `.scn`) |
| `QUIT` | `CLOSE`, `END`, `EXIT`, `Q`, `STOP` | Quit BlueSky |
| `DT [dt]` | | Set the simulation timestep |
| `DTMULT factor` | | Fast-time multiplier (e.g. `DTMULT 5` runs 5x real time) |
| `FF [seconds]` | | Fast-forward, optionally for a fixed duration |
| `REALTIME [ON/OFF]` | | Toggle real-time pacing vs. running as fast as possible |
| `BATCH file` | | Run a scenario as an unattended batch job |
| `TIME [RUN/HH:MM:SS.hh/REAL/UTC]` | | Set/show the simulated clock |
| `DATE [day,month,year,HH:MM:SS.hh]` | | Set the simulation date |
| `SEED value` | | Set the RNG seed (affects `MCRE`, noise, etc.) |
| `SCHEDULE time,command` | | Run a stack command at a given future `simt` |
| `DELAY time,command` | | Same idea, delay relative to now |

## 2. Aircraft creation & deletion

| Command | Does |
|---|---|
| `CRE acid,type,lat,lon,hdg,alt,spd` | Create an aircraft |
| `CRECONFS id,type,targetid,dpsi,cpa,tlos_hor,dH,tlos_ver,spd` | Create an aircraft on a deterministic collision course with `targetid` - the recommended way to script a guaranteed conflict, see `BLUESKY_TECHNICAL_OVERVIEW.md` §3.2 |
| `MCRE n,[type,alt,spd,dest]` | Randomly create `n` aircraft in the current view |
| `DEL acid/ALL/WIND/shape` | Delete an aircraft (or all traffic, wind, or a shape) |
| `MOVE acid,lat,lon,[alt,hdg,spd,vspd]` | Teleport an existing aircraft to a new state |
| `POS acid/waypoint` | Print full info on an aircraft, airport or waypoint |

## 3. Aircraft control (autopilot / FMS)

| Command | Aliases | Does | Example |
|---|---|---|---|
| `ALT acid,alt,[vspd]` | | Altitude command | `ALT INTRUDER1 FL120` - climb/descend to FL120, autopilot-selected rate |
| `VS acid,vspd` | | Vertical speed (ft/min) | `VS INTRUDER1 1500` - climb/descend at 1500 ft/min |
| `HDG acid,hdg` | `HEADING`, `TURN` | Heading command (deg, True or Magnetic) | `HDG INTRUDER1 300` - turn to heading 300 |
| `SPD acid,spd` | `SPEED` | CAS (kts) or Mach if `<1` | `SPD TARG2 220` - slow to 220 kt CAS |
| `DEST acid,latlon/airport` | | Set destination | `DEST TARG1 EHAM` - route to Schiphol |
| `ORIG acid,latlon/airport` | | Set origin airport | `ORIG TARG1 EHAM` - set origin to Schiphol |
| `VNAV acid,[ON/OFF]` | | Vertical FMS mode | `VNAV TARG1 ON` - let the FMS manage climb/descent per the route |
| `LNAV acid,[ON/OFF]` | | Lateral FMS mode (follow route) | `LNAV TARG1 ON` - follow the programmed route instead of a fixed heading |
| `DIRECT acid,wpname` | `DIRECTTO`, `DIRTO`, `DCT` | Go direct to a route waypoint | `DIRECT TARG1 EH007` - cut straight to waypoint EH007 |
| `ADDWPT acid,(wpname/lat,lon),[alt,spd,after,before]` | `WPTYPE` | Add a route waypoint | `ADDWPT TARG1 52.2,4.0,FL100,250` - add a waypoint with alt/speed constraints |
| `AFTER acid,wpinroute ADDWPT ...` | | Insert a waypoint after another one in the route | `AFTER TARG1 EH007 ADDWPT 52.3,4.2` - insert a new fix right after EH007 |
| `BEFORE acid,wpinroute ADDWPT ...` | | Insert a waypoint before another one | `BEFORE TARG1 EH007 ADDWPT 52.1,3.9` - insert a new fix right before EH007 |
| `AT acid,wpinroute [DEL] SPD/ALT [val]` | | Edit/clear a speed or altitude constraint at a waypoint | `AT TARG1 EH007 ALT FL80` - constrain altitude at EH007 to FL80 |
| `RTA acid,wpname,time` | | Required time of arrival at a waypoint | `RTA TARG1 EH007 00:05:00` - be at EH007 at exactly t=5:00 |
| `LISTRTE acid,[pagenr]` | | List an aircraft's route | `LISTRTE TARG1` - print TARG1's full route |
| `DELWPT acid,wpname` | `DELWP` | Delete one waypoint from a route | `DELWPT TARG1 EH007` - remove that one waypoint |
| `DELRTE acid` | `DELROUTE` | Delete the entire route | `DELRTE TARG1` - clear TARG1's route entirely |
| `DUMPRTE acid` | | Write the route to `output/routelog.txt` | `DUMPRTE TARG1` |
| `ATALT acid,alt,cmd` | | Run `cmd` once the aircraft reaches `alt` | `ATALT TARG1 FL150 SPD TARG1 280` - speed up once level at FL150 |
| `ATSPD acid,spd,cmd` | | Run `cmd` once the aircraft reaches `spd` | `ATSPD TARG1 250 HDG TARG1 090` - turn once slowed to 250 kt |
| `ATDIST acid,pos,dist,cmd` | | Run `cmd` once within `dist` nm of `pos` | `ATDIST TARG1 EHAM 20 ALT TARG1 FL50` - start descent 20 nm from EHAM |
| `SWTOC acid,[ON/OFF]` / `SWTOD acid,[ON/OFF]` | | Top-of-climb / top-of-descent automation switches | `SWTOD TARG1 OFF` - disable automatic top-of-descent |
| `THR acid,IDLE/0.0-1.0/AUTO` | | Manual throttle override | `THR TARG1 IDLE` - pull throttle to idle |
| `BANK acid,bankangle` | | Bank-angle limit | `BANK TARG1 20` - limit turns to 20 deg of bank |
| `CRUISESPD acid,spd` | | Set cruise speed used by the autopilot | `CRUISESPD TARG1 280` |
| `NOM acid` | | Reset aircraft to nominal performance |
| `CASMACHTHR threshold` | | Threshold below which a speed value is read as Mach |

## 4. Conflict detection & resolution (ASAS)

**Requires `CDMETHOD ON` to detect anything - see the docstring in
`hitl_conflog.py` and `BLUESKY_TECHNICAL_OVERVIEW.md` §3.**

| Command | Aliases | Does |
|---|---|---|
| `CDMETHOD [method/ON/OFF]` | `ASAS` | Select/toggle the conflict-detection method (`ON` = `STATEBASED`) |
| `DTLOOK [time]` | | Conflict-detection lookahead time (default **300 s**) |
| `DTNOLOOK [time]` | | Interval between conflict-detection passes |
| `ZONER [radius]` | `PZR`, `RPZ`, `PZRADIUS` | Horizontal protected-zone radius (nm) |
| `ZONEDH [height]` | `PZDH`, `DHPZ`, `PZHEIGHT` | Vertical protected-zone half-height (ft) |
| `RESO [method]` | | Select the conflict-resolution method (e.g. `MVP`, `OFF`) |
| `RMETHH [method]` | | Horizontal resolution method |
| `RMETHV [method]` | | Vertical resolution method |
| `RFACH [factor]` | `RESOFACH` | Horizontal resolution margin factor |
| `RFACV [factor]` | `RESOFACV` | Vertical resolution margin factor |
| `RSZONER [radius]` | `RESOZONER` | Resolution-zone horizontal radius override |
| `RSZONEDH [height]` | `RESOZONEDH` | Resolution-zone vertical half-height override |
| `PRIORULES [ON/OFF,code]` | | Right-of-way priority rules |
| `NORESO [acid]` | | Mark aircraft that nobody will avoid |
| `RESOOFF [acid]` | | Mark aircraft that won't avoid anybody |
| `RESNAV` | | Select a "resume navigation" (post-conflict) method |
| `FTRINTENT` | | How the FTR resolver reads intruder intent |

## 5. Areas & shapes

| Command | Does |
|---|---|
| `AREA shapename/OFF` or `AREA lat,lon,lat,lon,[top,bottom]` | Deletion area - traffic leaving it is auto-deleted |
| `EXP shapename/OFF` or `EXP lat,lon,lat,lon,[top,bottom]` | Experiment area of interest (used by `FLSTLOG`/`CONFLOG`) |
| `TAXI ON/OFF,[alt]` | Ground/low-altitude mode; `OFF` auto-deletes traffic below 1500 ft |
| `BOX name,lat,lon,lat,lon,[top,bottom]` | Define a box-shaped area |
| `CIRCLE name,lat,lon,radius,[top,bottom]` | Define a circle-shaped area |
| `POLY name,[lat,lon,...]` | Define a polygon-shaped area |
| `POLYALT name,top,bottom,lat,lon,...` | 3D polygon area between two altitudes |
| `LINE name,lat,lon,lat,lon` | Draw a line on the radar screen |
| `POLYLINE name,lat,lon,...` | Draw a multi-segment line |
| `DEFWPT wpname,lat,lon,[type]` | Define a scenario-local waypoint |

## 6. View / display (client-side)

These only affect what the *operator sees* - see the important caveat in
`hitl_fovaclog.py`'s docstring about what the sim can and can't observe
about the view.

| Command | Does |
|---|---|
| `PAN latlon/acid/airport/waypoint/LEFT/RIGHT/UP/DOWN` | Pan the radar view |
| `ZOOM IN/OUT/factor` | Zoom the radar view |
| `SWRAD GEO/GRID/APT/VOR/WPT/LABEL/TRAIL/...` | Toggle map/radar display layers |
| `TRAIL ON/OFF,[dt]` or `TRAIL acid,colour` | Aircraft trails |
| `SSD acid/ALL/OFF` | State-space diagram (predictive conflict display) |
| `ND acid` | Navigation display for one aircraft |
| `SYMBOL` | Toggle aircraft symbol style |
| `COLOUR txt,color` | `COLOR`, `COL` | Set a custom colour for an aircraft or shape |
| `INFO` | Open the info window |

## 7. Scenario, recording & plugins

| Command | Aliases | Does |
|---|---|---|
| `SAVEIC filename` | | Record every successful command from now on into a replayable `.scn` |
| `PCALL filename,[REL/ABS]` | `CALL` | Splice another scenario file in at this point |
| `SCENARIO name` | `SCEN` | Name the current scenario (affects log filenames, see `LOGGERS.md`) |
| `CD [path]` | | Change the scenario search folder |
| `PLUGINS [LOAD/REMOVE] name` | `PLUGIN`, `PLUG-IN` | List, load or unload a plugin |
| `ECHO text` | | Print text to the console (and into `SAVEIC`/`OPCMDLOG`, see `LOGGERS.md`) |

## 8. Logging

Covered in depth in `BLUESKY_TECHNICAL_OVERVIEW.md` §5-7 (built-in
`FLSTLOG`/`CONFLOG`, the general `CRELOG` mechanism) and in
`LOGGERS.md` (this experiment's four HITL-specific loggers). Quick
index:

| Command | Does |
|---|---|
| `CRELOG name,[dt],[header]` | Define a new custom logger (general mechanism) |
| `<LOGGERNAME> ON/OFF,[dt]` | Start/stop any logger by name - built-in (`FLSTLOG`, `CONFLOG`) or custom (`FOVACLOG`, `HEARTBEATLOG`, `OPCMDLOG`, `HITLCONFLOG`, ...) |
| `<LOGGERNAME> ADD [FROM parent] var1,...` | Add extra variables to a custom logger |

## 9. Utility & inspection

| Command | Aliases | Does |
|---|---|---|
| `HELP [command]` | `?` | Show help for a command, or list all commands |
| `DOC [command]` | | Open the extended help/docs page for a command |
| `MAKEDOC` | | Generate markdown help templates for every stack command |
| `DIST lat0,lon0,lat1,lon1` | | Distance/bearing between two positions |
| `CALC expression` | | Inline calculator |
| `MAGVAR lat,lon` | | Magnetic variation at a position |
| `GETWIND lat,lon,[alt]` | | Query the wind field |
| `WIND ...` | | Define a wind vector |
| `LSVAR path.to.variable` | | Inspect any live variable in the running sim |
| `GROUP [name,(area/acid,...)]` | | Group aircraft together (e.g. for bulk commands) |
| `UNGROUP name,acid` | | Remove an aircraft from a group |
| `PLOT [x],y,[dt,colour,figure]` | | Live-plot a variable over time |
| `LEGEND label1,...` | | Add a legend to the last plot |
| `IMPLEMENTATION [base,impl]` | | Switch the active implementation of a replaceable BlueSky class (e.g. performance model) |
| `RUNWAYS icao` | | List available runways at an airport |
| `AIRWAY wp/airway` | | Info on an airway or a waypoint's connections |
| `ENG acid,[engine_id]` | | Change an aircraft's engine type |
| `PERF acid` | | Select a performance-model implementation |
| `PERFSTATS acid` | `PERFINFO`, `PERFDATA` | Show an aircraft's performance parameters |
| `NOISE [ON/OFF]` | | Turbulence/noise toggle |

## Not covered here

Deliberately left out because they're either GUI-rendering internals
with no operator-facing behaviour of their own (`glmap`/`gltraffic`/
`glpoly`/`glhelpers` command hooks), or belong to optional plugins this
experiment doesn't load (`opensky`, `windgfs`, `windecmwf`, `metrics`,
`optimize`, `synthetic`, `geofence`, `example`, `qtexample`,
`guiexample` - see `enabled_plugins` in `settings.cfg` for what
actually loads). `HELP` and `DOC` at the console always reflect this
exact installed version if something here goes stale.
