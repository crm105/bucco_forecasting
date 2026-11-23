# Steamer player projections (rung 5a, second source)

Steamer's player projections from FanGraphs for 2012–2026, run through the same analysis as ZiPS
(see [depth_chart.md](depth_chart.md)). Summary: **Steamer's own playing time beats our depth
chart, so the `steamer` model sums each team's projected WAR as it is.** It is the best model on
the leaderboard: 9.58 RMSE over 2012–2026 against 9.78 for `depth_chart` on the same seasons.

## The data

The files are named `streamer_<batters|pitchers>_individual_<season>.csv`. The extractor maps
the `streamer` spelling to the source `steamer`, and the files keep their names. No new dbt
models were needed: `stg_projections__player_projections` and `marts.player_projections` already
hold any source, keyed by `source`.

What sets Steamer apart from ZiPS:

| | Steamer | ZiPS |
| --- | --- | --- |
| Projected PA per team | 5,500–6,100 (2014 on) | 16,000–25,000 |
| Projected IP per team | about 1,500 | 3,100–4,450 |
| Meaning | Playing time already shared out within each team, close to real totals (about 6,200 PA and 1,450 IP) | Every player projected on his own; the team's playing time must be shared out |

Exceptions and cleaning:

- **2013** is a raw list of every player (3,430 batters, about 15,800 PA per team, negative total
  batting WAR). The model detects this from the median team total and runs that season through the
  depth chart (thresholds `RAW_LIST_PA` = 10,000 and `RAW_LIST_IP` = 2,500).
- **2012** has 663 batters and no games column. The models don't use games.
- **2020** is scaled to the 60-game season (about 2,240 PA per team), so it was made after the
  schedule was set in late June 2020, before the July 23 Opening Day. ZiPS 2020 is scaled the
  same way. 2020 is left out of every score.
- About 34,000 rows have no team (unsigned players and minor leaguers) and are dropped, as for
  ZiPS. Rows with no MLB id are dropped too (one named Steamer 2025 player projected for 1 PA, plus
  unnamed rows), because playing time and positions are matched on that id.

## Results, spec by spec (2026-11-23)

Wins error is leave-one-season-out, with team WAR centered on each season's league average, the
same as in `scripts/eval_depth_chart.py`. Seasons 2012–2026 without 2020.

| Spec | 2012–26 | Without 2013 | Holdout 2022–26 |
| --- | --- | --- | --- |
| Steamer WAR summed as given, no playing-time adjustment | 9.84 | **9.67** | 9.50 |
| Steamer scaled to 6,240 PA and 1,450 IP per team | 9.74 | 9.74 | **9.49** |
| Steamer through the depth chart, batters and pitchers | 9.74 | 9.84 | 9.64 |
| Blend, 0.5 × Steamer PA + 0.5 × depth-chart PA | 9.63 | 9.67 | 9.50 |
| **As given, depth chart for 2013 only (the `steamer` model)** | **9.58** | 9.67 | 9.50 |
| ZiPS depth chart (`depth_chart`), for comparison | 9.75 | | 9.61 |
| Average of ZiPS and Steamer team WAR (25–75% Steamer) | 9.66–9.77 | | 9.58–9.64 |

All Steamer specs land within about 0.15 wins of each other on the holdout, which is within noise
on five seasons. What decides it is 2013, where the depth chart cuts that season's error from 11.5
to 8.3, and the rule that the simplest spec should win a tie.

**PA error.** On the 14,529 batters both systems project for the same team-season (2012–2026,
without 2013 and 2020), RMSE against real PA:

| Playing time | RMSE | Bias |
| --- | --- | --- |
| **Steamer as given** | **114.6** | +7.3 |
| Steamer through our depth chart | 120.0 | −5.8 |
| ZiPS through our depth chart | 136.4 | +1.2 |
| ZiPS as given | 340.2 | +282.9 |

**Tuning the depth chart on Steamer** (coordinate descent on PA error, trained on 2012–2021 and
held out 2022–2026, same grids and 0.3 PA tolerance as for ZiPS, plus `max_slot_share`): no
parameter moved. Every setting scored within about 1 PA of the current defaults, and wins error
moved by at most 0.05. The defaults tuned on ZiPS are already the best for Steamer, and even at
its best the depth chart is worse than Steamer's own PA (79.0 vs 76.5 on the holdout, over all
Steamer players). The depth chart ignores the projected PA except as the WAR/PA denominator, which
throws away Steamer's playing-time estimate.

**Rates aren't better, playing time is.** Projected rates times real PA (the oracle) score 8.97
for Steamer and 8.93 for ZiPS. Steamer's advantage is all in playing time.

## Is it really a preseason forecast?

FanGraphs doesn't date these files, so look-ahead can't be ruled out directly. Two checks found no
sign of it:

- **Team on in-season trades.** Using the MLB transactions API (trades and free-agent signings
  between the first game and the last regular-season game of each year), Steamer lists the pre-trade
  team for about 95% of traded players, the same rate as ZiPS. Almost every post-trade case is a
  trade made between March 18 and 27, after the international opener (Tokyo 2019 and 2025, Seoul
  2024) but before the domestic Opening Day. So the Steamer files are snapshots from just before
  domestic Opening Day, a little later than ZiPS. The other three are minor leaguers, and ZiPS
  shows two of them the same way.
- **Early-season injuries.** Steamer projects a full workload for stars hurt soon after Opening
  Day: Strider 2024 (185 IP), Bieber 2024 (193 IP), deGrom 2023 (163 IP), Acuña 2024 (695 PA),
  Trout 2021 (671 PA), Syndergaard 2017 (199 IP). A file made later would have cut them. It does
  cut injuries known before the season, such as Tatis 2022 (326 PA after his March wrist surgery;
  ZiPS, released earlier, had 553).

So the edge looks real: Steamer is updated through spring training (late trades, spring injuries,
roster battles), and ZiPS is a winter release. To reproduce it live, Steamer has to be downloaded
just before Opening Day each year.

## As a registered model: `steamer` (rung 5a)

`PlayerData(..., playing_time="as_given")` sums each team's projected WAR, falling back to the
depth chart for a season whose median team PA or IP looks like a raw list. The rest (centering,
the least-squares line to wins fit on earlier seasons, the spread) is the same `DepthChartModel`
as `depth_chart`. Registered as `steamer` in `src/bucco/models/__init__.py`.

Walk-forward backtest (every model trained on earlier seasons only, 2020 left out):

| Seasons | steamer | depth_chart | holt |
| --- | --- | --- | --- |
| 2012–2026 (420 team-seasons) | **9.58** | 9.78 | 11.08 |
| 2014–2026 | **9.57** | 9.69 | 11.10 |
| 2022–2026 | **9.45** | 9.57 | 10.80 |

Pirates error (predicted minus actual wins), `steamer` vs `depth_chart`: 2022 +5.7 / +6.0,
2023 −2.7 / −4.5, 2024 −1.9 / +0.7, 2025 +4.6 / +5.9, 2026 −4.7 / −4.0.

To rerun the comparisons: `uv run python scripts/eval_depth_chart.py --source steamer --compare`.
