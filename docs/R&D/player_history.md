# Player history for our own projections (2026-11-24)

## What this is

The data our own player projections (rung 5b) will be built on: what every player did each
season since 2000, valued in runs and wins, and laid out so a model can only see the seasons
before the one it forecasts. No projection model yet; this is the foundation.

## Source

MLB Stats API, `bucco extract mlb-player-stats`. One league-wide request per season gives every
player's batting and pitching counts (full-season totals, last team, number of teams); `/people`
gives birth date, bats and throws. Free, rebuildable, no scraping.

The per-team query used for fielding does **not** work for batting and pitching: it leaves out
players who left a team during the season (the 2025 Pirates came out 654 PA short). The
league-wide rows match league batters faced exactly. Fielding was checked and is complete.

## Tables (dbt marts)

| Table | Grain | What it holds |
| --- | --- | --- |
| `league_seasons` | season | League wOBA, wOBA scale and weights, runs per win, FIP constant, replacement runs per PA and per inning |
| `player_batting_seasons` | player × season | Age, position, counts, AVG/OBP/SLG/ISO/BABIP, K%, BB%, wOBA, batting and baserunning runs, positional adjustment, `off_runs`, `def_runs`, `war_approx` |
| `player_pitching_seasons` | player × season | Age, role (SP/RP), counts, IP, K%, BB%, HR rate, BABIP, ERA, RA9, FIP, `pitching_runs`, `war_approx` |
| `batter_projection_frame` | player × target season | Inputs `y1_`–`y3_` from the three prior seasons, age in the target season, outcomes `target_` |
| `pitcher_projection_frame` | player × target season | Same layout for pitchers |

The frames are what models should read. A dbt test checks every input comes from the three
seasons before the target season. Outcomes are 0 for a player who did not play in a completed
season (useful for playing-time models) and null for the upcoming season (2027: 905 batters and 1310 pitchers,
ready to be projected).

## How close the value is to FanGraphs

The constants match FanGraphs' Guts table closely (2019: wOBA scale 1.167 vs 1.157, FIP constant
3.214 vs 3.214, runs per win 10.30 vs 10.30). 2024 batting leaders: Judge 11.6 (FanGraphs 11.2),
Soto 8.1 (8.1), Ohtani 8.8 (9.2). Known gaps:

- **No fielding runs.** The MLB API has none, so `def_runs` is the positional adjustment only and
  great defenders come out low (Witt 2024: 8.9 vs 10.4).
- **One replacement level for pitchers.** FanGraphs uses a lower one for starters, so our
  starters run about half a win low and relievers a little high (Sale 2024: 5.8 vs 6.4).
- **No park or league adjustment**, and baserunning is stolen bases only.
- League batting WAR sums to about 515–545 per season, not 570: the positional adjustments do not
  net to zero and pitchers' batting is included.

## First check: is there signal?

A bare-bones Marcel on the batter frame (weights 5/4/3 by PA, 1,200 PA of league average mixed
in, no aging, no park) against Steamer on the same 3,650 player-seasons (2012–2026, 300+ PA,
2020 left out), wOBA relative to league:

| | Correlation | RMSE (wOBA points) |
| --- | --- | --- |
| Naive Marcel | 0.502 | 30.6 |
| Steamer | 0.539 | 29.2 |

So history alone gets most of the way; the gap is what aging, components, park and
playing-time modeling have to close.

## Next steps

1. Marcel for batters and pitchers by component (K, BB, HR, BABIP...), with an age curve fitted
   walk-forward from the frames.
2. Playing time from the frames (`target_pa` including zeros).
3. Write projections in the `player_projections` shape (source `bucco`) so the lineup optimizer
   and the backtest run on them unchanged.
4. Rookies: the frames leave them out; they need a separate rule.
