# Minor-league batting: major-league equivalents (2026-11-25)

## What we tried

Add batters' minor-league seasons to Marcel's history, translated to MLB terms, and project
rookies (minor-league but no MLB history), who had no projection. The biggest player-level gaps
to Steamer were young hitters with thin MLB history (Walker Jenkins, Jackson Holliday, Cole
Young: about 1 WAR each), and rookies were worth about 0.1 wins of the gap to Steamer.

## The data

`bucco extract mlb-minor-batting`: the MLB Stats API's season lines for Triple-A, Double-A,
High-A and Single-A (sport ids 11 to 14), 2009–2026 (no 2020), one row per player and level,
with age and league; 3,300 to 4,400 lines a season. Mart `minor_batting_seasons` values each line
against its own league with that season's MLB run values (wOBA weights and scale; stolen bases as
in wSB), which takes out league environments (Pacific Coast League). The unaffiliated Mexican
League, classed Triple-A until 2020, is left out. The 2021 reorganization moved whole leagues
between High-A and Single-A (Midwest and South Atlantic up, Florida State, California and
Carolina down); levels follow MLB's classification.

## Translation

Same-season pairs at two adjacent levels (100+ PA at the lower, 50+ at the higher), PA-weighted
mean change in runs per PA, chained up to MLB (park-neutral Off). Per 600 PA:

| Step | Pairs | Drop | Total drop to MLB |
| --- | --- | --- | --- |
| Triple-A to MLB | 2,417 | −27.3 | −27 |
| Double-A to Triple-A | 1,891 | −17.5 | −45 |
| High-A to Double-A | 1,960 | −19.3 | −64 |
| Single-A to High-A | 1,910 | −18.9 | −83 |

The same in both eras (Triple-A to MLB −26.4 and −28.4) and with 50 or 100 PA. Only Triple-A has
many direct MLB pairs (Double-A 234, High-A 22), hence the chain. A fitted slope instead of
slope 1 was ruled out: Triple-A pairs include veterans on rehab assignments, and Marcel already
regresses. Refitted for each target season on earlier seasons (`milb.fit_drops`).

## Into Marcel

Each translated season joins the 5/4/3 history like an MLB season, aged the same way, its PA
counted at a weight. Rookies with 100+ minor-league PA over three seasons get rows.

**The drops are too harsh as fitted**: players promoted mid-season were often promoted because
they were hot. At full drops, projections came out 11 to 17 runs per 600 PA low for rookies and
4 to 7 for thin-history players. Drop scale and weight were chosen together on next-season Off
per 600 PA (relative to the season average, weighted by PA, players with 100+ PA, 2012–2026
without 2020):

| | Thin (<300 PA a year) | 300–800 | 800+ | Rookies | All |
| --- | --- | --- | --- | --- | --- |
| No minor-league history | 19.64 (bias −1.8) | 17.16 | 15.28 | none | 16.55 |
| Drops × 1, weight 0.25 | 18.70 (−3.6) | 16.86 | 15.36 | 22.11 (−10.9) | 16.73 |
| Drops × 0.7, weight 0.5 | 17.98 (−1.7) | 16.63 | 15.26 | 20.27 (−6.5) | 16.36 |
| **Drops × 0.5, weight 0.5 (kept)** | **17.85 (+0.7)** | **16.60** | **15.23** | **19.16 (−1.6)** | **16.24** |
| Drops × 0.3, weight 0.5 | 18.21 (+3.1) | 16.64 | 15.28 | 19.42 (+3.4) | 16.36 |
| Steamer (players it lists) | 17.67 (−1.7) | 16.01 | 15.09 | 19.61 (−5.2) | 15.85 |

(Rookies scored are the ones who got 100+ PA, so every system is biased low on them.) With the
kept setting thin-history hitters are about as accurate as Steamer's. Translated drops: Triple-A
−14, Double-A −22, High-A −32, Single-A −41 runs per 600 PA (`DROP_SCALE`, `MILB_WEIGHT`).

**Rookies' positions.** With no MLB positional history, Steamer's whole Def was counted as
fielding, the implied positional adjustment came out 0 and almost every rookie was placed at
2B/3B/CF (catchers included). Now their fielding share is left unknown and the lineup optimizer
reads the position from the whole Def (catchers at C, shortstops at SS).

## Teams

Wins RMSE, 2012–2026 without 2020 (all with Opening Day availability):

| | 2012–26 | 2012–19 | 2021–26 | Better | t |
| --- | --- | --- | --- | --- | --- |
| `marcel_staff_optimized` before | 9.691 | 9.331 | 10.151 | | |
| + minor-league history, no rookies | 9.717 | 9.336 | 10.203 | 6 of 14 | +0.6 |
| + history and rookies (positions before the fix) | 9.642 | 9.329 | 10.045 | 7 of 14 | −0.6 |
| **+ history and rookies (kept)** | **9.633** | 9.312 | 10.046 | 9 of 14 | −0.7 |

The player-level gain is clear; at team level it comes with the rookies (who replace
replacement-level time) and is modest. Weight and drop scale were chosen at player level, so
the team backtest is an independent check.

**2027**: our spread of team wins now matches Steamer's (sd 6.7 vs 6.5; it was 5.6), but the
mean distance from Steamer grew (3.0 to 3.6 wins). Minnesota 78.9 to 82.8 (Steamer 83.1), Seattle
to 83.1, Philadelphia and Cleveland up about 4; San Diego 71.8 to 66.8 (Steamer 74.9): every team
now gets credit for its prospects, and the Padres' are few. Pirates 87.2 (6th).

## Limits and next

- **Deep minor-leaguers got MLB playing time** (Kerrington Cross, mostly Single-A and High-A:
  275 PA for the 2027 Padres): the lineup optimizer's fatigue curve was on an absolute 600-PA
  scale. Fixed with a curve relative to each batter's projected PA
  ([lineup_optimizer.md](lineup_optimizer.md)).
- Minor-league fielding positions for rookies not in Steamer's file.

## Pitchers (2026-11-25)

**Why.** Rookie pitchers had no projection at all, and pitchers with thin MLB history were our
largest player-level gap to Steamer.

**Data.** `bucco extract mlb-minor-pitching` (same levels and seasons, 3,500 to 4,700 lines a
season); mart `minor_pitching_seasons`: FIP-based runs above the pitcher's own league average,
(league FIP − FIP) × IP / 9, the scale of MLB `pitching_runs` (the FIP constant cancels).

**Translation.** The same chain on runs per batter faced (2,100 to 3,000 pairs a step), to
park-neutral MLB pitching runs. Per 700 batters faced: Triple-A −20, Double-A −31 to −34,
High-A −40 to −46, Single-A −51 to −58 (larger with a 100- than a 200-batter threshold,
promotion selection again).

**Into Marcel.** Translated runs, batters faced, innings, starts and games join the 3/2/1
history at a weight, so a rookie starter gets a starter's role and replacement level.

**Player level** (next-season FIP-based runs per 9, relative to the season, weighted by innings,
pitchers with 30+ IP, 2012–2026 without 2020):

| | Thin MLB history | Middle | Heavy | Rookies (667) |
| --- | --- | --- | --- | --- |
| No minor-league history | 0.915 | 0.827 | 0.661 | none |
| Drops × 1, weight 0.5 | 0.893 | 0.820 | 0.672 | 0.966 (bias −0.23) |
| **Drops × 0.5, weight 0.5 (kept)** | **0.886** | **0.824** | **0.659** | **0.938 (+0.07)** |
| Drops × 0.7, weight 0.5 | 0.884 | 0.821 | 0.663 | 0.936 (−0.05) |
| Steamer (pitchers it lists) | 0.860 | 0.778 | 0.639 | |

The same settings as hitters (`PITCHER_DROP_SCALE`, `PITCHER_MILB_WEIGHT` 0.5).

**Rookie innings.** The first version put minor-league innings into the shared baseline-innings
line; fitted on all rostered pitchers (thousands of minor-league arms on Steamer's lists who never
pitch in MLB, plus veterans' rehab innings), it gave rookies about nothing: rookies who went on to
throw 80+ MLB innings were projected for 6. Two changes:

1. A separate walk-forward line for rookies (`innings.ROOKIE_FEATURES`): last season's
   minor-league innings by level and role (Triple-A and Double-A as starter and in relief,
   lower levels), age, and Opening Day 40-man status (on the roster, on its injured list, and
   on the roster times upper-level starter innings).
2. Rookie pitchers are left out of the Opening Day availability scaling, which had counted
   40-man status a second time.

| Rostered rookies, 2014–2026 | Projected IP | Actual IP |
| --- | --- | --- |
| All | 2.0 | 2.3 |
| On the 40-man, active | 19.5 | 23.1 |
| Off the 40-man (20,600) | 1.1 | 1.2 |
| Our 400 highest-projected | 28 | 34 |

(Before: all 0.7, top 400 13.) Rookies who went on to throw 80+ IP now average 17 projected
(selected on the outcome, so always low).

**Pitcher rates at 0 innings.** The staff optimizer took a pitcher's rate as runs / innings, so
anyone projected for 0 innings counted as an average pitcher. Marcel now keeps the rate
(`runs_per_ip`) and the optimizers, the injury simulation and the outlook use it. No effect on
the backtest on its own (9.633 to 9.634), but it matters for rookies with small baselines.

**Teams** (wins RMSE, 2012–2026 without 2020):

| | 2012–26 | 2012–19 | 2021–26 | Better | t |
| --- | --- | --- | --- | --- | --- |
| `marcel_staff_optimized` before (rate fix in) | 9.634 | 9.293 | 10.071 | | |
| **+ minor-league pitching (kept)** | **9.568** | 9.222 | 10.012 | 9 of 14 | −1.5 |

The largest single gain since minor-league hitting. 80% cover 77.9% to 76.9%.

**Relief innings follow the role.** With rookie starters competing for the rotation, the outlook
showed Bubba Chandler as a 145-inning reliever, then (with a flat 100-inning relief cap) Paul
Skenes. Swapping two pitchers between the rotation and the bullpen barely changes team WAR (the
replacement levels and the starting penalty cancel), so the staff optimizer split pitchers
between pools arbitrarily; stamina, which keeps starters in rotations, is not in the rates. Now
a pitcher's relief innings are at most 100 × (1 − start share) + 10: a pure starter gets long
relief only, Carmen Mlodzinski (0.29) about 81. No one throws 100+ relief innings; the 2027
Pirates rotation is Skenes 170, Chandler 145, Ashcraft 140, Jones 115, Keller 110.

**Cost.** Projections now carry about 20,000 rookie pitcher rows; loading them takes several
minutes (to speed up: keep only rookies on a preseason list before projecting).

## Status

Hitting and pitching adopted in `marcel_staff_optimized` (9.57; Steamer 9.50), with the relative batter
fatigue curve.
