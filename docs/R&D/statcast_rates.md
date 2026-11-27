# Statcast inputs for hitting and pitching rates: kept, not yet in the models (2026-11-27)

## Data

`bucco extract savant` saves Baseball Savant's custom leaderboard for batters and pitchers from
2015 (`stg_savant__players`): PA, strikeout and walk rates, xwOBA, exit velocity, launch angle,
barrel, hard-hit and sweet-spot rates, whiff rate, swing rates outside and inside the zone,
in-zone contact, sprint speed (batters) and average speed by pitch type (pitchers). It stays in
the pipeline, so each season adds history.

## First test

The learned rate models (hitter offense runs per 600 PA; pitcher FIP-based runs per 9), each
with its current inputs and with Statcast added: the three seasons before (12 measures each, plus
PA) and PA-weighted three-season averages, about 40 inputs. Strict walk-forward, tuned per target
season. Holdout RMSE:

| | Marcel | Learned, current | + Statcast | Better from 2016 |
| --- | --- | --- | --- | --- |
| Hitters, off runs per 600 | 16.24 | 16.21 | 16.19 | 5 of 10 seasons (t −0.5) |
| Pitchers, runs per 9 | 0.778 | **0.762** | 0.763 | 4 of 10 (t +0.2) |

Hitters gained in 2022–2024 (2024: 16.51 to 16.19) and lost in 2017, 2021 and 2026; pitchers did
not gain (their target, FIP-based runs, is strikeouts, walks and home runs, which lagged rates
already carry). Not adopted; the data is kept. Statcast fielding, by contrast, is adopted
(docs/R&D/fielding.md).

## Why this test was weak, and what to retest

- Under walk-forward, a target season's model sees Statcast only in its training seasons: two for
  a 2018 target, none for 2016. The inputs cannot help until several training seasons carry them.
- About 40 inputs on about 6,000 rows (hitters) dilute what signal there is.

Retest with: a compact set (three-season averages of xwOBA, barrel rate, exit velocity, whiff
rate, chase rate, sprint speed for hitters; whiff, chase, in-zone contact, fastball speed,
barrel rate against for pitchers); fixed model settings; seasons left out one at a time (training
on all others) to rank variants, then a walk-forward backtest for any variant that wins. Repeat
after each new season.
