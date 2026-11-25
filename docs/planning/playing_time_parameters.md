# Playing-time parameters: inventory and a plan to streamline (2026-11-25)

## Why

`marcel_staff_optimized` now decides playing time through seven layers added one experiment at a
time: a projected-PA formula, baseline innings, Opening Day availability factors, the injury
simulation, fatigue curves, hard caps and team budgets. Several of them describe the same thing
(how often a player misses time, and what extra playing time costs), were calibrated in
different orders against different targets, and partly undo each other. This note lists every
parameter involved, groups them by the mechanism they stand for, and proposes a smaller,
deliberate structure. Rate parameters (how well a player plays) are listed at the end for
completeness; they overlap less.

## How playing time is decided now (`marcel_staff_optimized`)

1. **Anchor.** Batters: Marcel's formula, 0.5 × last season + 0.1 × the season before + 200 PA.
   Pitchers: baseline innings, a regression on past innings, role and age that counts seasons
   with 0 innings, so it is an expected value with injuries in it.
2. **Availability factor.** The anchor is multiplied by a factor for the player's Opening Day
   status (60-day injured list, short list, active, off the 40-man). In "absolute" mode the
   active factor also rescales healthy players: 0.86 for batters, 1.15 for pitchers.
3. **Injury simulation** (if adopted). Healthy capacity = anchor ÷ the group's mean
   availability; each simulated season draws availability and re-optimizes.
4. **Fatigue curves.** In the optimizers, a player's rate worsens as playing time passes his
   anchor (batters: relative curve; pitchers: relative, scaled by value, steeper with age) and
   improves below it (rest bonus).
5. **Hard caps.** 700 PA; 220 innings (can start) or 100 (cannot).
6. **Team budgets.** 640 PA at catcher and 700 at every other slot (6,240); 830 rotation and 620
   bullpen innings. What listed players do not fill goes to replacement level.
7. **Role.** Who can start (start share at least 0.1) and the starting penalty for relievers.

## Inventory

How set: **fitted** = estimated from data, walk-forward; **tuned** = chosen on a backtest or
error metric (in-sample); **hand** = set by judgment or convention; **FG** = FanGraphs
convention.

### Expected playing time (the anchor)

| Parameter | Where | Value | How set | Notes |
| --- | --- | --- | --- | --- |
| `PT_WEIGHTS` | marcel.py | 0.5, 0.1 | hand (Marcel) | Batter PA formula; never fitted. |
| `PA_BASE` | marcel.py | 200 PA | hand (Marcel) | Gives every batter, rookies included, 200 PA before scaling. |
| `SP_IP_BASE`, `RP_IP_BASE` | marcel.py | 60, 25 | hand (Marcel) | Not used by the staff model (baseline innings replace them). |
| Baseline innings line | innings.py | 11 coefficients | fitted | Includes injuries and lost jobs (0 IP counted), age, role. |
| `SHARE_WEIGHTS`, `PEAK_AGE` | innings.py | 3/2/1, 27 | hand | Feature definitions. |
| Fielded on Steamer's preseason lists | innings.py, availability.py | | data choice | Who counts as "rostered" for every fit. |

### Mean time lost (injuries, demotions, lost jobs)

| Parameter | Where | Value | How set | Notes |
| --- | --- | --- | --- | --- |
| Availability factors by Opening Day group | availability.py | 60-day 0.2, short 0.6-0.7, off 40-man 0.1-0.4 | fitted | |
| "absolute" active factor | availability.py | batters 0.86, pitchers 1.15 | fitted | Really a calibration of the anchor (the batter formula is too high, baseline innings too low for 40-man players), not an availability effect. |
| Zero-IP seasons in baseline innings | innings.py | | fitted | Injury mean inside the pitcher anchor. |
| Injury simulation mean availability | injury_sim.py | about 0.88 / 0.86 / 0.82 / 0.80 | fitted | Divided out to get healthy capacity, so the mean is unchanged by design. |

### Variance and shape of time lost

| Parameter | Where | Value | How set | Notes |
| --- | --- | --- | --- | --- |
| Availability draws by group | injury_sim.py | empirical | fitted | Groups: batters 32 and under, 33 and over, starters, relievers. |
| `ESTABLISHED` | injury_sim.py | 450 PA, 120 IP, 40 IP | hand | Who the draws are fitted on. |
| `OLD_AGE` | injury_sim.py | 33 | hand | |
| Availability = delivered ÷ group median, capped at 1 | injury_sim.py | | hand | Defines "fully available" as typical delivery. |
| `N_SIMS` | injury_sim.py | 100 | hand | Noise about 0.2 WAR per team. |

### Cost of extra playing time (fatigue, rest, platoons)

| Parameter | Where | Value | How set | Notes |
| --- | --- | --- | --- | --- |
| `RELATIVE_FATIGUE_RUNS` (batters, staff model) | lineup_optimizer.py | 0.0075 | tuned | PA error and wins, before the injury simulation. |
| `FATIGUE_RUNS` (batters, absolute, Steamer/ZiPS) | lineup_optimizer.py | 0.015 | tuned | On Steamer playing time. |
| `FATIGUE_POWER` (batters) | lineup_optimizer.py | 2 | tuned | On Steamer. |
| `REST_BONUS` (batters) | lineup_optimizer.py | 0.5 | hand | Never tuned for Marcel. |
| `FATIGUE_RUNS` c0 (pitchers) | staff_optimizer.py | 0.05 | tuned | In-sample innings error, before availability and swingmen. |
| `AGE_SLOPE` g (pitchers) | staff_optimizer.py | 0.05 | hand (from headroom data) | Innings and wins flat in g; double-counts age already in baseline innings. |
| `PROPORTIONAL`, `REFERENCE_VALUE`, `MIN_VALUE` | staff_optimizer.py | on, 0.15, 0.02 | hand | Kept an ace off the cap. |
| `FATIGUE_POWER`, `REST_BONUS` (pitchers) | staff_optimizer.py | 2, 0.5 | hand | Copied from batters. |
| `MIN_ANCHOR_PA`, `MIN_BASE_IP` | both | 10 PA, 5 IP | hand | Numerical floors. |

### Hard caps

| Parameter | Where | Value | How set | Notes |
| --- | --- | --- | --- | --- |
| `MAX_PA` | lineup_optimizer.py | 700 | FG | |
| `MAX_SP_IP`, `MAX_RP_IP` | staff_optimizer.py | 220, 100 | hand | With the relative curves these may rarely bind. |

### Team totals and the unlisted

| Parameter | Where | Value | How set | Notes |
| --- | --- | --- | --- | --- |
| Slot PA (`SLOT_PA`) | depth_chart.py | 640 C, 700 others | FG | |
| `ROTATION_IP`, `BULLPEN_IP` | staff_optimizer.py | 830, 620 | hand (57% of 1,450) | Estimated actual since 2021: about 890 and 545. Season budgets tested only with the old 0.5 cutoff. |
| Replacement level for what listed players do not fill | both optimizers | | structural | Stands in for in-season additions: about 510-590 PA a team now; real unlisted PA about 400 from off-40-man players plus trades and call-ups. Not calibrated. |
| `RESERVE_PA` | lineup_optimizer.py | 0 | tuned | Explicit in-season additions; made wins worse. Unused. |

### Role

| Parameter | Where | Value | How set | Notes |
| --- | --- | --- | --- | --- |
| `ROTATION_MIN_SHARE` | staff_optimizer.py | 0.1 | tuned | On wins. |
| Starting penalty | innings.py | about 0.03 runs/IP | fitted | |

### Older models only (depth chart, Steamer/ZiPS)

`RANK_DECAY` 0.7, `SECONDARY_WEIGHT` 0.25, `MAX_SLOT_SHARE` 0.92, `MAX_PLAYER_PA` 700,
`IP_BUDGET` 1,500, `STARTER_IP_SHARE` 0.57, `SP_DECAY` 0.5, `RP_DECAY` 0.85, `MIN_RP_IP` 20,
`MIN_STARTS` 15, `ROTATION_SIZE` 5 (depth_chart.py); `PA_BUDGET`, `N_REGULARS`, `DEFAULT_*`
(playing_time.py). Tuned on ZiPS and Steamer. Not used by `marcel_staff_optimized`.

## Where they overlap

**1. Mean time lost is counted in three places.** Baseline innings include injuries, the
availability factors include injuries for listed groups, and the "absolute" active factor
rescales healthy players. The batter anchor has no injury model of its own; the 0.86 active
factor does the job of calibrating Marcel's formula. Each fix landed where it was easiest, so
"expected playing time" has no single home.

**2. The anchor means different things.** For pitchers it is an expectation that includes
injuries; for batters it is a convention (0.5/0.1 + 200) rescaled after the fact; inside the
injury simulation it is turned into healthy capacity by dividing out the mean. The fatigue
curves are anchored on whichever of these they receive, and were calibrated before the
simulation existed. With the simulation on, the curve sees realized capacity, which is a
different point than it was tuned on.

**3. Fatigue absorbs uncertainty.** Before the simulation, a soft fatigue curve was the only
way to let good players play more than their expected time (because others get hurt) without
modeling injuries. With injuries simulated, part of what the curve does is double-counted: a
backup can already take a hurt starter's time. Expect a different (probably steeper) c once
injuries are simulated.

**4. Age enters workload three times.** Baseline innings have age terms; the staff curve
steepens with age (`AGE_SLOPE`, which did not improve accuracy); the injury simulation splits
batters at 33. Only the first was shown to matter.

**5. Who plays when nobody listed can.** Replacement level absorbs in-season additions,
injuries beyond the listed depth, and players off the 40-man, all at once and uncalibrated.
The relative curve moved about 500 PA a team there.

**6. Budgets are constants in a changing league.** Rotation 830 is below every season's
estimate (990 in 2012, 890 now); the bullpen budget is above. The swingman change made the
rotation budget bind, which pushes the top starters below their usual workloads.

**7. Calibration order.** Parameters were tuned one at a time, each with the others fixed at
whatever they were then: batter c before the injury simulation, pitcher c0 before availability
and swingmen, the MiLB weight before the relative curve. None was re-checked after later
changes.

## A streamlined structure

One explicit model of playing time per player, in three parts, each with a single job:

1. **Healthy capacity H** — what he plays if healthy, in his role, on this roster.
   - Batters: a fitted baseline PA model like innings.py (past PA, age, role, 40-man status),
     replacing `PT_WEIGHTS` and `PA_BASE`, fitted on seasons where the player was available
     (or on expectations, dividing out mean availability as below).
   - Pitchers: baseline innings ÷ mean availability.
2. **Availability A** — one fitted distribution of the share of H he can give, by role, age
   band and Opening Day status. This merges the availability factors (status shifts the
   distribution: a 60-day player's mean A is about 0.2) and the injury draws. The point
   forecast uses its mean; the simulation uses draws. The "absolute" active rescale goes away,
   because H is fitted directly.
3. **Diminishing returns** — one relative fatigue curve per side, anchored at H × A, with c
   (and possibly the rest bonus) refitted once, jointly, after parts 1 and 2. `AGE_SLOPE` is
   removed (age lives in H and A). Hard caps stay only if they bind.

Team totals: rotation and bullpen budgets from recent seasons (refit with the current role
rules), and replacement level calibrated to the playing time unlisted players really get.

**Removed or merged:** `PT_WEIGHTS`, `PA_BASE` (staff model), "absolute" active factor,
`AGE_SLOPE`, separate availability factors (into A), possibly the caps and `REST_BONUS`.
**Refitted once, jointly:** both fatigue c's, budgets, `ROTATION_MIN_SHARE`, `MILB_WEIGHT`.

## Plan

Each step on its own branch, backtested, with the same scorecard so steps are comparable:

| Metric | Now |
| --- | --- |
| Wins RMSE, 2012–2026 without 2020 | 9.633 (Steamer 9.501) |
| Batter PA RMSE, rostered | 87.8 |
| Pitcher IP RMSE, rostered | 37.7 |
| PA a team to players off the 40-man (real about 406) | 35 |
| 600+ PA seasons a year (real 74) / 180+ IP (real about 21 since 2021) | 67 / to measure |
| Replacement PA and IP a team | about 510-590 / to measure |

1. **Finish the injury simulation test** (running now) and record it. Its result decides
   whether part 2 is a distribution or a mean.
2. **Batter healthy capacity.** Fit a baseline PA model; drop `PT_WEIGHTS`/`PA_BASE` from the
   staff model. Check the "absolute" active factor falls to about 1.
3. **One availability distribution.** Fold the Opening Day factors into the simulation's draws
   (status as a group); point forecasts use the mean.
4. **Refit the curves together.** Batter and pitcher c (and rest bonus), with injuries on;
   remove `AGE_SLOPE`; check whether caps bind.
5. **Budgets and the unlisted.** Season or recent-average rotation and bullpen budgets;
   compare replacement playing time with what unlisted players really got.
6. **Retire what is unused.** Document the older models' depth-chart parameters as frozen;
   remove `SP_IP_BASE`/`RP_IP_BASE` from the staff path and `RESERVE_PA` if still unused.

**Acceptance:** wins RMSE no worse than now (within noise, about ±0.03), playing-time errors no
worse, and fewer hand-set parameters. A simpler model that ties is a win.

## Rate parameters (for completeness)

Less overlap, listed so nothing is hidden: Marcel `BATTER_WEIGHTS` 5/4/3, `PITCHER_WEIGHTS`
3/2/1, `REG_PA`/`REG_BF` 1,200 (hand, Marcel); fitted prior (`PRIOR_SCALE` 500/200 hand, means
fitted); age curves (fitted; `AGE_RANGE` hand); park-neutral history (fitted factors); fielding
from Steamer and ZiPS; MiLB `DROP_SCALE` 0.5 and `MILB_WEIGHT` 0.5 (tuned, player level),
`MIN_LOW_PA` 100, `MIN_PAIRS` 100, `ROOKIE_MIN_PA` 100 (hand); lineup `SELECTION_BASE` 2.0,
`SELECTION_UP` 0.5, `RARITY_PENALTY`, `TIE_BREAK`, `PART_TIME_CATCHER_FLD` (tuned or hand on
Steamer). One possible overlap: `MILB_WEIGHT` and `REG_PA` both set how much thin history is
trusted, and the fitted prior adjusts the mean on top.
