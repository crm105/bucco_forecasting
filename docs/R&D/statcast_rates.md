# Statcast inputs for hitting and pitching rates: in the learned models (2026-11-27)

## Data

`bucco extract savant` saves Baseball Savant's custom leaderboard for batters and pitchers from
2015 (`stg_savant__players`): PA, strikeout and walk rates, xwOBA, exit velocity, launch angle,
barrel, hard-hit and sweet-spot rates, whiff rate, swing rates outside and inside the zone,
in-zone contact, sprint speed (batters) and average speed by pitch type (pitchers). It stays in
the pipeline, so each season adds history.

## Inputs

`ml.core.with_statcast`: for each player, the three seasons before (12 measures each plus PA, and
sprint speed for batters, fastball and slider speed for pitchers) as sc1_* to sc3_*, and the
PA-weighted three-season average of each as scavg_*. Missing before 2015.

- **Pitchers:** added to the learned FIP-based rate model (`ml.pitchers`).
- **Hitters:** a new learned offense model (`ml.hitters`): park-neutral offense runs per 600 PA,
  relative to the season, from Marcel's projected rate, age and three seasons of history plus the
  Statcast inputs; trained from 2004 on hitters with 100+ PA. In `marcel_ml_hitter_pa` its rate
  replaces Marcel's offense at the learned PA, and WAR moves by the change over runs per win.

Strict walk-forward, tuned per target season (`bucco fit-ml`).

## Results

Holdout RMSE, 2012–2026 without 2020:

| | Marcel | Learned, no Statcast | **Learned + Statcast** |
| --- | --- | --- | --- |
| Hitters, off runs per 600 | 16.24 | 16.21 | **16.19** (better in 7 of 14 seasons; 6 of the last 7 from 2022) |
| Pitchers, runs per 9 | 0.778 | 0.762 | **0.763** |

Through the forecast (`bucco evaluate`, 2016–2026; `bucco backtest`, record from 2012 for
`marcel_ml_hitter_pa`, 2009 for `marcel_ml_pitchers`):

| | Off runs per 600 | WAR per 600 | Team batting WAR | Team WAR | Record RMSE |
| --- | --- | --- | --- | --- | --- |
| `marcel_ml_hitter_pa`, Marcel offense (before) | 15.99* | 1.824 | 6.25 | 8.91 | 9.38 |
| `marcel_ml_hitter_pa`, learned offense + Statcast | **15.93** | **1.82** | 6.36 | 8.97 | 9.45 |
| `marcel_ml_pitchers`, rate + Statcast | | | | 8.91 | 9.36 (was 9.38) |

\* Marcel's offense rate as scored in `marcel_ml_pitchers`, which uses the same rates.

Adopted on player-level accuracy: per-player offense is a little better, but team batting WAR and
the record are a little worse. The learned offense is slightly compressed (season spread of
projected offense about 5% narrower than Marcel's among 300+ PA hitters; correlation 0.96 with
Marcel's) and its errors appear to add up less well across a roster. Pitchers gain nothing yet
(their target, FIP-based runs, is strikeouts, walks and home runs, which lagged rates already
carry).

## Why gains are small, and what to retest

- Under walk-forward, a target season's model sees Statcast only in its training seasons: two for
  a 2018 target, none for 2016. Hitters' gains are concentrated from 2022, when several training
  seasons carry it; they should grow with each new season.
- About 40 Statcast inputs on about 6,000 rows (hitters) dilute what signal there is.

Retest with: a compact set (three-season averages of xwOBA, barrel rate, exit velocity, whiff
rate, chase rate, sprint speed for hitters; whiff, chase, in-zone contact, fastball speed,
barrel rate against for pitchers); fixed model settings; seasons left out one at a time (training
on all others) to rank variants, then a walk-forward backtest for any variant that wins. Repeat
after each new season, and check whether team batting WAR recovers.
