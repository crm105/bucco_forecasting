# ZiPS through the optimizer, and a Steamer + ZiPS blend (2026-11-23)

## `zips_optimized`

ZiPS projects every player in an organization at roughly full-time playing time (about 16,000
PA per team), so it has always gone through the depth chart (`depth_chart`). The lineup
optimizer is built for exactly that choice, so ZiPS batters now go through it too; ZiPS pitchers
still go through the depth chart (a raw list). Fatigue is anchored at each player's ZiPS PA.

Anchoring everyone at a fixed 600 PA instead (playing time decided entirely by the optimizer)
was worse for both systems, so the projections' own PA carry information even for ZiPS:

| RMSE (wins), schedule-adjusted | all seasons | 2022–2026 |
| --- | --- | --- |
| `depth_chart` (ZiPS, 2011–2026) | 9.755 | 9.558 |
| `zips_optimized`, ZiPS PA anchor | **9.702** | **9.508** |
| `zips_optimized`, 600 PA anchor | 9.766 | 9.625 |
| `steamer_optimized`, Steamer PA anchor (2012–2026) | **9.581** | **9.405** |
| `steamer_optimized`, 600 PA anchor | 9.653 | 9.434 |

`optimize_league(..., anchor_pa=600)` and `PlayerData(optimizer_options=...)` keep the fixed
anchor available for experiments.

## `blend_optimized`

The two systems' errors are correlated at 0.94, but averaging still helps. Looking at all
seasons at once (not a fair test), an even split scored 9.505 over 2012–2026 and 9.339 over
2022–2026.

The registered model (`bucco.models.blend.BlendModel`) tunes the weight without look-ahead: for
each target season, both components are refitted on the seasons before each earlier season and
predict it; the ZiPS weight is the least-squares fit to those out-of-sample forecasts, clipped to
[0, 1] (an even split until there are 3 such seasons). The 80% range uses the spread of the
blend's out-of-sample errors. When ZiPS has no file for a season (2027, until it is released),
the blend is `steamer_optimized`.

ZiPS weight by target season: 0.50 (2011–2014, too little history), then 0.07 (2015), 0.25,
0.21, 0.24, 0.32, 0.43 (2021), 0.37, 0.34, 0.42, 0.38, 0.41 (2026): settling near 0.4.

| RMSE (wins) | 2012–2026 | 2016–2026 | 2022–2026 |
| --- | --- | --- | --- |
| `steamer` | **9.501** | **9.601** | 9.388 |
| `blend_optimized` | 9.544 | 9.645 | **9.350** |
| `steamer_optimized` | 9.581 | 9.723 | 9.405 |
| `zips_optimized` | 9.724 | 9.779 | 9.508 |

The honest, walk-forward blend gives up about 0.04 against the even split chosen with hindsight,
mostly in the early seasons when the weight was fitted on 3 to 6 seasons (0.07 in 2015). It is
the best model over 2022–2026 and beats both of its components everywhere; `steamer` (Steamer's
own playing time, not the optimizer) is still best over the full period.

## Open

- Blend `steamer` (as given) with `zips_optimized`, or all three.
- Shrink the fitted weight toward 0.5 when it rests on few seasons.
