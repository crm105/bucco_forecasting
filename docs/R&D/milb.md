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

- **Deep minor-leaguers get MLB playing time.** The lineup optimizer's fatigue curve is on an
  absolute 600-PA scale (rate falls with (PA/600)²), so a small projected PA barely holds a
  player back: Kerrington Cross (mostly Single-A, High-A) gets 275 PA for the 2027 Padres. A
  curve relative to the projected PA, as for pitchers, would fix this and give availability its
  full effect on batters.
- Minor-league pitching, the same way.
- Minor-league fielding positions for rookies not in Steamer's file.

## Status

Adopted in `marcel_staff_optimized` (9.63; Steamer 9.50).
