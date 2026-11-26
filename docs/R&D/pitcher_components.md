# Pitchers by component: strikeouts, walks, home runs (2026-11-25)

## What we tried

Marcel regressed a pitcher's FIP-based runs as one number, with 1,200 weighted batters faced of
league average. But FIP's parts settle at very different speeds: a strikeout rate means something
after a few hundred batters, a home-run rate takes years. Regressing each part by its own amount
is the standard fix, and pitchers with middle and heavy MLB history were our largest player-level
gap to Steamer (the part minor-league data could not help).

## How

**The split.** FIP-based runs are linear in the counts, so each season's pitching runs split
exactly into parts against the season's league rate per batter faced (`player_pitching_seasons`):

    k_runs     = 2/9 x (K - league K rate x BF)
    bb_runs    = -3/9 x (BB + HBP - league rate x BF)
    hr_runs    = -13/9 x (HR - league rate x BF)
    other_runs = pitching runs - the three

`other_runs` is innings per batter faced against the league (more outs per batter, from balls in
play and double plays, give more innings for the same events). Each part sums to zero over the
league; park-neutral versions (`*_neutral`) use the park-adjusted counts. The minor-league mart
splits the same way against each minor league.

**Marcel by part** (`marcel.project_pitchers(..., components=)`): each part gets its own
weighted history, its own aging curve (delta method on that part), its own minor-league
translation (the same chain, drops fitted per part, which add up to the total drop) and its own
fitted prior; the rate is the sum. All of this is linear, so with every part at 1,200 the
projections equal the one-number ones exactly (checked on all 70,868 pitcher-seasons; a test).

## Choosing the weights

Next-season park-neutral FIP runs per 9 innings (relative to the season, weighted by innings,
pitchers with 30+ IP), chosen on target seasons **2003–2011, before the backtest**, so the
2012–2026 numbers and the team backtest are an independent check. Each part alone (error of that
part's runs per 9):

| Batters faced of average | | | | |
| --- | --- | --- | --- | --- |
| Strikeouts | 150: 0.297 | **300: 0.293** | 600: 0.293 | 1,200: 0.303 |
| Walks + HBP | 300: 0.271 | 600: 0.265 | **1,200: 0.265** | 2,400: 0.273 |
| Home runs | 1,200: 0.516 | **2,400: 0.509** | 4,800: 0.511 | 9,600: 0.517 |
| The rest | 1,200: 0.054 | **4,800: 0.053** | 20,000: 0.055 | all average: 0.056 |

Kept: 300 / 1,200 / 2,400 / 4,800 (`marcel.COMPONENT_REG_BF`), within 0.0004 of the best of the
256 combinations. Total:

| | 2003–11 (chosen on) | 2012–26 |
| --- | --- | --- |
| One number (1,200) | 0.732 | 0.786 |
| **By part (kept)** | **0.722** | **0.778** |

By MLB history, 2012–2026, pitchers Steamer also lists:

| | Rookies | Thin | Middle | Heavy | All |
| --- | --- | --- | --- | --- | --- |
| One number | 0.923 | 0.874 | 0.816 | 0.647 | 0.773 |
| **By part** | 0.928 | 0.872 | **0.807** | **0.638** | **0.765** |
| Steamer | 0.927 | 0.852 | 0.776 | 0.635 | 0.746 |

Pitchers with long histories are now level with Steamer; the gap left is mostly the middle group
(0.031) and thin histories (0.020).

## Teams

Wins RMSE, 2012–2026 without 2020:

| | 2012–26 | 2012–19 | 2021–26 | Better | t |
| --- | --- | --- | --- | --- | --- |
| `marcel_staff_optimized` before | 9.570 | 9.216 | 10.021 | | |
| **+ pitchers by part (kept)** | **9.538** | 9.173 | 10.005 | 9 of 14 | −1.5 |

Steamer: 9.501. Correlation with Steamer's backtest forecasts 0.926 to 0.930; with its 2027
forecasts 0.842 to 0.851 (mean gap 2.77 to 2.67 wins).

**2027**: teams move under a win (Toronto −0.8, Cleveland +0.6). Pirates 84.3 to 84.7, still 7th;
pitching staff 4th to 3rd, bullpen 2nd to 1st. Jared Jones (strikeouts) 3.66 to 3.53 FIP, Bubba
Chandler (walks) 3.97 to 4.03, Mason Montgomery 3.54 to 3.30, Carmen Mlodzinski 3.82 to 3.96.

## Limits and next

- The parts are still FIP's: no batted-ball quality (ground balls, exit velocity) or pitch-level
  skill (whiff rate), which settle faster than outcomes and are where Steamer likely keeps its
  edge on the middle group.
- Weights are one set for all pitchers; starters and relievers might differ.

## Status

Adopted in `marcel_staff_optimized` (9.54).
