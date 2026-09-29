# HITL Scenario Library

Five scenarios, escalating in difficulty, all living in
`scenario/hitl_test/`. Each is fully self-contained: it loads the four
HITL loggers fresh (see `LOGGERS.md`), starts its own `SAVEIC`
recording, and needs `CDMETHOD ON` (already included) to actually alert
on the conflicts below. All conflict geometry was computed and then
independently verified by simulating each aircraft pair forward and
confirming near-zero separation at the stated meeting time (flat-earth
approximation at 52N, matching the method `2con_test.scn` itself
documents inline).

Default conflict-detection settings in this repo (`bluesky/traffic/asas/detection.py`):
**lookahead 300s, protection radius 5 NM, protection height 1000 ft**
(`DTLOOK`, `ZONER`/`RPZ`, `ZONEDH`). Every trial below is timed so the
conflict starts alerting comfortably within that 300s window as soon as
both aircraft exist.

**A resolution is not unique.** For any conflict, turning one aircraft
(`HDG`), climbing/descending one aircraft by at least 1000+ ft (`ALT`),
or slowing/speeding one aircraft (`SPD`) can all work. The "expected
commands" below are *one* valid model solution each, given as a
concrete answer key to compare a run against - not the only correct
answer.

## Overview

Duration scales with difficulty, all capped at **3 minutes**: the easy
tier is a short 75s drill, not padded out to the full cap just because
it's allowed to be that long. Tier 2 (`2con_test.scn`) is the one
exception - it already has a real recorded HITL run
(`HITL_2con_run.scn`), so its original timing (ends t=00:03:30, the
only tier over the cap) was left untouched rather than risk breaking
comparability with that data.

| Tier | File | Conflicts | Background | Peak overlap | Duration | SAVEIC name |
|---|---|---|---|---|---|---|
| 1 - Easy | `1con_easy.scn` | 1 | 2 | none | 00:01:15 | `HITL_1con_run` |
| 2 - Medium | `2con_test.scn` | 2 | 4 | none (sequential) | 00:03:30 | `HITL_2con_run` |
| 3 - Moderate | `3con_overlap.scn` | 3 | 6 | 2 conflicts at once | 00:01:55 | `HITL_3con_run` |
| 4 - Hard | `4con_hard.scn` | 4 | 8 | 2 conflicts at once (x2 clusters) | 00:02:20 | `HITL_4con_run` |
| 5 - Extreme | `5con_extreme.scn` | 5 | 10 | 3 conflicts at once | 00:02:45 | `HITL_5con_run` |

---

## Tier 1 - `1con_easy.scn`

Onboarding run: one head-on conflict, no time pressure, nothing else
to look at.

| Trial | Aircraft | Alt | Type | Spawn | Meets at | dpsi |
|---|---|---|---|---|---|---|
| 1 | TARG1 / INTRUDER1 | FL100 | Head-on | t=00:00:00 (both) | t=00:01:15 | 180 deg |

**Expected commands (one valid solution):**
1. `HDG INTRUDER1 300` (or `ALT INTRUDER1 FL120`) - issue any time
   before ~t=00:01:00.

---

## Tier 2 - `2con_test.scn` (existing)

Two sequential trials, never overlapping - the original scenario.

| Trial | Aircraft | Alt | Type | Spawn | Meets at | dpsi |
|---|---|---|---|---|---|---|
| 1 | TARG1 / INTRUDER1 | FL100 | Head-on | t=00:00:05 / 00:00:30 | t=00:01:30 | 180 deg |
| 2 | TARG2 / INTRUDER2 | FL150 | Crossing | t=00:02:00 (both) | t=00:03:30 | 90 deg |

**Expected commands (one valid solution):**
1. `HDG INTRUDER1 300` (or `ALT INTRUDER1 FL120`) - by ~t=00:01:00.
2. `ALT INTRUDER2 FL170` (or `HDG INTRUDER2 045`) - by ~t=00:03:00.

---

## Tier 3 - `3con_overlap.scn`

Trials 1-2 are the same recipe as tier 2. Trial 3 is timed to start
alerting while trial 2 is still open - the first real split-attention
test.

| Trial | Aircraft | Alt | Type | Spawn | Meets at | dpsi |
|---|---|---|---|---|---|---|
| 1 | TARG1 / INTRUDER1 | FL100 | Head-on | t=00:00:00 / 00:00:15 | t=00:00:45 | 180 deg |
| 2 | TARG2 / INTRUDER2 | FL150 | Crossing | t=00:00:55 (both) | t=00:01:35 | 90 deg |
| 3 | TARG3 / INTRUDER3 | FL180 | Crossing | t=00:01:15 (both) | t=00:01:55 | 90 deg |

Trials 2 and 3 are both live from ~t=00:01:15 to ~t=00:01:35 - resolve
trial 2 first (it's due sooner), then trial 3.

**Expected commands (one valid solution):**
1. `HDG INTRUDER1 300` - by ~t=00:00:30.
2. `ALT INTRUDER2 FL170` - by ~t=00:01:15 (trial 2 is due first).
3. `ALT INTRUDER3 FL200` - by ~t=00:01:40.

---

## Tier 4 - `4con_hard.scn`

Two clusters of two, ~20s apart within each cluster - the operator
must split attention twice per run instead of once.

| Trial | Aircraft | Alt | Type | Spawn | Meets at | dpsi |
|---|---|---|---|---|---|---|
| 1 | TARG1 / INTRUDER1 | FL100 | Head-on | t=00:00:00 / 00:00:15 | t=00:00:45 | 180 deg |
| 2 | TARG2 / INTRUDER2 | FL150 | Crossing | t=00:00:25 (both) | t=00:01:05 | 90 deg |
| 3 | TARG3 / INTRUDER3 | FL180 | Crossing | t=00:01:20 (both) | t=00:02:00 | 90 deg |
| 4 | TARG4 / INTRUDER4 | FL190 | Head-on | t=00:01:50 (both) | t=00:02:20 | 180 deg |

**Expected commands (one valid solution):**
1. `HDG INTRUDER1 300` - by ~t=00:00:30 (cluster 1, resolve first - due
   sooner).
2. `ALT INTRUDER2 FL170` - by ~t=00:00:50.
3. `ALT INTRUDER3 FL210` - by ~t=00:01:40 (cluster 2).
4. `HDG INTRUDER4 300` - by ~t=00:02:00.

---

## Tier 5 - `5con_extreme.scn`

One warm-up conflict, then a genuine 3-way simultaneous cluster
(trials 2-4 all live together for ~60s), then a final conflict placed
after the cluster to check whether focus recovers once the pressure
is off.

| Trial | Aircraft | Alt | Type | Spawn | Meets at | dpsi |
|---|---|---|---|---|---|---|
| 1 | TARG1 / INTRUDER1 | FL100 | Head-on | t=00:00:00 / 00:00:15 | t=00:00:45 | 180 deg |
| 2 | TARG2 / INTRUDER2 | FL150 | Crossing | t=00:00:50 (both) | t=00:01:30 | 90 deg |
| 3 | TARG3 / INTRUDER3 | FL180 | Head-on | t=00:01:00 (both) | t=00:01:40 | 180 deg |
| 4 | TARG4 / INTRUDER4 | FL200 | Crossing | t=00:01:05 (both) | t=00:01:50 | 120 deg |
| 5 | TARG5 / INTRUDER5 | FL220 | Crossing | t=00:02:05 (both) | t=00:02:45 | 60 deg |

Trials 2, 3 and 4 are all open at once from roughly t=00:00:50 to
t=00:01:40 - the hardest single stretch across all five tiers.
Suggested triage order: whichever meets soonest first (trial 2, due
t=00:01:30), then trial 3 (t=00:01:40), then trial 4 (t=00:01:50).

**Expected commands (one valid solution):**
1. `HDG INTRUDER1 300` - by ~t=00:00:30.
2. `ALT INTRUDER2 FL170` - by ~t=00:01:10 (due soonest in the cluster).
3. `HDG INTRUDER3 090` - by ~t=00:01:25.
4. `ALT INTRUDER4 FL230` - by ~t=00:01:40 (FL230 is deliberately not
   FL220 - trial 5 below uses FL220, so climbing into it here would
   just trade one conflict for another).
5. `HDG INTRUDER5 300` - by ~t=00:02:30 (after the cluster - tests
   recovery, not triage).
