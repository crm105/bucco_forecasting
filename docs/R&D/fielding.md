# Fielding from Statcast: measured and projected (2026-11-27)

## Data

`bucco extract savant` saves Baseball Savant's fielding run value for every fielder from 2016:
runs saved, total and by part (range, arm, double plays, receiving at first; framing, throwing
and blocking for catchers), and outs on the field at each position (`stg_savant__fielding`).
Savant counts framing in fielding run value only from 2018, so 2016–2017 framing comes from its
older catcher-framing leaderboard (`framing_source`). The parts add up to the total in every
season; league totals are near zero (fielding is measured against average).

## Measured fielding in actual WAR

From 2016 a batter's actual WAR (`marts.player_team_seasons`, the target of `bucco evaluate`)
includes his fielding runs over runs per win. Team fielding spreads about 2.5–2.8 WAR a season
and correlates about 0.3 with team offense. Before 2016 actual WAR stays offense plus positional
adjustment.

## Our own fielding projection

Each batter's fielding runs per PA over the three seasons before, weighted 3:2:1 (last season
first), with 1,000 PA of average (zero) fielding added in (`statcast_fielding_rates`;
weights and ballast chosen on 2017–2019 from a small grid; a separate ballast for catchers was
not better). It replaces the fielding part of the borrowed Steamer/ZiPS Def wherever a batter
has Statcast fielding (`marcel.apply_fielding_rates`, targets from 2017); rookies and players
without any keep the borrowed projection.

Fielding runs per 600 PA, hitters with 300+ actual PA, 2021–2026 (1,596 player-seasons):

| | RMSE | Catchers (180) | Others (1,416) |
| --- | --- | --- | --- |
| Projecting zero | 7.69 | | |
| Borrowed (mean of Steamer's and ZiPS's projected Def) | 7.01 | 10.81 | 6.45 |
| **Ours** | **6.51** | **9.68** | **6.06** |
| Half each | 6.53 | 9.86 | 6.05 |

Ours is better in all six seasons. Through the forecast (`marcel_ml_hitter_pa`, scored
2016–2026 against WAR with measured fielding):

| | WAR per 600 | Production | Team batting WAR | Team WAR | Record RMSE |
| --- | --- | --- | --- | --- | --- |
| Borrowed fielding | 1.844 | 0.655 | 6.35 | 9.04 | 9.56 |
| **Ours** | **1.824** | **0.649** | **6.25** | **8.91** | **9.46** |

Record better in 7 of 10 seasons (t −1.9). Adopted for the learned models (`STAFF_SETTINGS`,
`statcast_fielding`): registered backtests `marcel_ml_hitter_pa` 9.45 → 9.38 (2012–2026),
`marcel_ml_pitchers` 9.40 → 9.38 (2009–2026). `marcel_staff_optimized` keeps the borrowed Def as
the reference.
