# Strength of schedule (2026-11-23)

The player-projection models (`steamer_optimized`, `steamer`, `depth_chart`) turn team WAR into a
win percentage against an average opponent. Teams do not play an average schedule: until 2022
each played 76 games against its own division (19 against each rival), and since 2023 it plays
52 (13 each), with every team playing all 15 teams in the other league. A team in a strong
division should win a little less than its talent alone suggests.

## Method

Each team's forecast is read as its neutral win percentage p. Against its real schedule (the
`team_matchups` mart, from `bucco extract mlb-schedules`) its expected wins are the sum over its
games of the log5 chance of beating each opponent:

    P(i beats j) = p_i (1 - p_j) / (p_i (1 - p_j) + p_j (1 - p_i))

P(i beats j) + P(j beats i) = 1, so league wins still add up to the number of games (2,430).
There is nothing to fit. Code: `bucco.models.schedule`, applied at the end of
`DepthChartModel.predict` when the season's schedule is in the database (it is fixed before the
season, so this is not look-ahead).

## Results

First tried on the saved walk-forward forecasts, then built into the models and backtested.

| RMSE (wins) | before | after |
| --- | --- | --- |
| `steamer_optimized` 2012–2026 | 9.675 | **9.585** |
| `steamer_optimized` 2022–2026 | 9.487 | **9.411** |
| `steamer` 2012–2026 | 9.581 | **9.501** |
| `steamer` 2022–2026 | 9.445 | **9.388** |
| `depth_chart` (ZiPS) 2011–2026 | 9.748 | 9.755 |

By schedule format (`steamer_optimized`): 9.735 to 9.615 in 2012–2022, 9.523 to 9.509 in
2023–2026. The adjustment moved a team by about 1.4 wins (sd) under the old format and 0.75
under the balanced one, so nearly all the gain is from before 2023. ZiPS does not benefit
(+0.007, noise); kept on for all three models for consistency, since there is no parameter.

**Full or scaled.** The adjustment could be multiplied by a weight λ fitted on past errors, in
case the WAR-to-wins line (fit on actual records, which already include each season's schedule)
had absorbed part of it. Fitted on all seasons, λ = 1.05 ± 0.37 (Steamer: 0.92 ± 0.35), so the
full adjustment is about right; fitted walk-forward, λ was noisy early (0.4 to 1.0) and scored
worse (9.607). The full adjustment is used.

## 2027

The shifts are small under the balanced schedule. Dodgers +1.8 (NL West: Rockies 65, Padres 75,
Giants 76), Brewers +0.9, Pirates +0.3 (8th easiest); in the AL East the weaker teams lose most,
since they face all three strong teams: Blue Jays -0.9, Orioles -0.8, Rays -0.5, Yankees -0.4,
Red Sox -0.3.

## Not done

- The 80% ranges are unchanged (the sd is the residual sd of the unadjusted fit, so very
  slightly wide).
- The WAR-to-wins line is still fit on actual records; fitting it on schedule-neutral records
  would be cleaner, but λ near 1 says the difference is small.
- Home field and travel are ignored (every team has 81 home games).
