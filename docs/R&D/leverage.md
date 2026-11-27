# Reliever leverage (2026-11-27)

Our pitcher WAR, projected and actual, is FIP-based and leverage-free: every relief inning
counts the same. Closers and setup men pitch in close, late games, so their innings move more
wins than a mop-up reliever's.

## Proxy: roles from saves and holds, weights from team wins

No leverage index is in our data (MLB Stats API; FanGraphs' gmLI/pLI are not available to us).
The proxy uses roles instead.

**Actual seasons (2005–2026 without 2020, hindsight).** Each team's closer (most saves) and next
three relievers by saves + holds (about 60 and 170 innings a team); team wins regressed on team
WAR and on those relievers' WAR:

| Fit | Wins RMSE |
| --- | --- |
| Team WAR | 6.01 |
| + closer WAR, + setup WAR | 5.80 |

Implied weights: closer 2.7 (± about 0.4 in the coefficient), setup 2.5, against the usual
chained weights of about 1.4 and 1.2 ((1 + gmLI) / 2). Part of the excess is selection:
relievers who pitch well are moved into high-leverage roles during the season.

**Projected roles (marcel_ml_hitter_pa, walk-forward 2014–2026, simplified: no schedule
adjustment).** In each team's bullpen as the staff optimizer shares it out, the best reliever
by WAR per inning (20+ relief innings) closes and the next three set up (about 51 and 127
innings); their relief WAR is weighted before the WAR-to-wins line:

| Weights (closer / setup) | Record RMSE | Seasons better | t |
| --- | --- | --- | --- |
| none | 9.496 | | |
| 1.4 / 1.2 | 9.474 | 8 of 12 | −2.0 |
| 1.8 / 1.4 | 9.456 | 8 of 12 | −1.9 |
| **2.0 / 1.5** | **9.448** | 8 of 12 | −1.8 |
| 2.67 / 2.48 | 9.415 | 8 of 12 | −1.4 |
| fitted each season | 9.475 | 7 of 12 | −0.2 |

**Chosen: 2.0 / 1.5**, splitting the difference between the standard weights (fixed in
advance, the most consistent gain) and the largest gain (chosen on these seasons).

## In the model

`staff_optimizer.LEVERAGE` and `leverage_war`; `PlayerData(leverage=...)`, set in
`STAFF_SETTINGS` (the learned models). Applied after the staff optimizer shares out innings: the
allocation itself is unchanged (letting the optimizer chase leverage could move starters into
closing, which teams do not do). Players' own WAR stays leverage-free, as actual WAR is, so
player-level scores do not change; only team pitching WAR and the record do.

Registered backtests (`bucco backtest`, with the schedule adjustment):

| Model | Record RMSE, before | With leverage 2.0 / 1.5 |
| --- | --- | --- |
| `marcel_ml_hitter_pa` (2012–2026) | 9.45 | **9.40** |
| `marcel_ml_pitchers` (2009–2026) | 9.36 | **9.31** |

`marcel_ml_hitter_pa` from 2016 (`bucco evaluate`): 9.57 → 9.51. Adopted for the learned models.
The outlook's staff table still shows leverage-free pitcher WAR.

## Going deeper (costly; not done)

The proxy guesses roles and fits two weights. Real leverage would measure it:

- **Data:** pitch-by-pitch or play-by-play win expectancy, from which each reliever's average
  leverage index when entering (gmLI) follows. Baseball Savant's pitch-level search carries
  win-expectancy changes from 2015 (millions of rows; a long, throttled download); the MLB
  Stats API's game feeds have play-by-play for every game (about 2,430 a season) from which a
  win-expectancy table and leverage could be built ourselves.
- **Uses:** fit each pitcher's past leverage and project it (role persistence, team's other
  relievers); weight relief WAR by projected (1 + gmLI) / 2 per pitcher instead of two tiers;
  score actual WAR with leverage, so player-level accuracy covers it too.
- **Cost:** a new extract (days of download for pitch-level data, or a game-feed extract and a
  win-expectancy model), dbt models, and a refit. Worth it only if the proxy's gain holds up
  and the record still has room at the bullpen end.
