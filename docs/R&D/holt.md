# Rung 2: Holt's damped-trend smoothing

Code: [src/bucco/models/smoothing.py](../../src/bucco/models/smoothing.py) · Registry name: `holt` · Run it: `bucco backtest --models holt`

## In one paragraph

Holt's model forecasts a team's next win percentage from its own past seasons. It keeps a running estimate of the team's true talent (the **level**) and nudges that estimate toward each new season's result, but only part of the way, because one season's record is partly luck. A second, optional piece (the **trend**) tracks whether talent has been rising or falling and carries some of that momentum forward. In the backtest the fit switched the trend off entirely. What remains is a weighted average of a team's past seasons, with about half the weight on last season, and it beat "repeat last year" by about 0.7 wins RMSE.

## The intuition

### Why not just use last year?

A team's record is true talent plus luck. Over 162 games, luck alone has a standard deviation of about 6.4 wins. A team that went 90–72 might really be an 85-win team that got lucky, or a 92-win team that got unlucky. Repeating last year's record treats the luck as if it were talent, so it overreacts.

The opposite extreme is to ignore the past and predict 81 for everyone. That throws away real information, because good teams tend to stay good.

Smoothing sits between the two. It asks how much of a new season's result to believe.

### Level: the running talent estimate

> new level = α × (this season's win%) + (1 − α) × (old level)

Worked example, with α = 0.5 and made-up win totals:

| Season | Wins | Level before | Forecast for this season | Level after |
| --- | --- | --- | --- | --- |
| 1 | 70 | (start) | – | 70.0 (starts at the first season) |
| 2 | 85 | 70.0 | 70.0 | 0.5 × 85 + 0.5 × 70 = 77.5 |
| 3 | 75 | 77.5 | 77.5 | 0.5 × 75 + 0.5 × 77.5 = 76.25 |

The forecast for the next season is simply the current level, 76.25 wins here. Each season's result moves the estimate partway, so one lucky or unlucky year doesn't swing it.

Unrolled, the level is a weighted average of all past seasons, and the weights shrink geometrically (α, α(1−α), α(1−α)², …). With the fitted α of about 0.5:

| Seasons back | 1 | 2 | 3 | 4 | 5 |
| --- | --- | --- | --- | --- | --- |
| Weight | 51% | 25% | 12% | 6% | 3% |

### Trend: momentum

The trend term keeps a second running estimate, the slope: how much the level has been changing per year. A team whose level has gone 70 → 77 → 84 has a positive slope, and the model forecasts that it keeps rising. The forecast becomes level + slope.

This is the rebuild-is-working story. The risk is that noisy data can fake a trend. A few lucky years in a row look like improvement, and the model extrapolates it.

### Damping: momentum that fades

A damped trend multiplies the slope by a factor φ between 0 and 1 before using it. It says momentum is real but doesn't last. φ = 1 means the trend continues unchanged, and φ = 0 means the trend is ignored. Without damping, a trend model forecasting several years out would predict absurd records. Since we forecast one season ahead, damping mostly acts as a dial that scales how much of the slope shows up.

## The three parameters

| Parameter | statsmodels name | What it controls | 0 means | 1 means |
| --- | --- | --- | --- | --- |
| α (alpha) | `smoothing_level` | How fast the level follows the latest season | Ignore new seasons; talent never changes | Believe only the latest season (`last_year`) |
| β (beta) | `smoothing_trend` | How fast the slope follows the latest change in level | The slope never updates from its start of 0 | The slope is just the latest change in level |
| φ (phi) | `damping_trend` | How much of the slope carries into the forecast | No trend; forecast is the level | Full trend, never fading |

Note that β is the *update speed* of the slope, not the slope itself. The slope is a separate running value the model tracks for each team.

Special cases:

- (α = 1, β = 0, φ = 0) is exactly the `last_year` model. The model falls back to this when it has fewer than 4 seasons of history.
- (β = 0 or φ = 0) with α between 0 and 1 is plain exponential smoothing, with no trend.

## How the model is fitted

- **One parameter set for all 30 teams (pooled).** A single team has only about 25 seasons, far too few to estimate three smoothing parameters reliably. Pooling all teams gives hundreds of one-year-ahead forecast errors to fit against.
- **Objective:** minimize the squared one-year-ahead error across every team and every season in the training history. Each team's series starts at its first season, with an initial slope of 0, and the first season is not scored.
- **Search:** a coarse grid of 27 starting points, then a Nelder–Mead local search from the best, with all three parameters bounded to [0, 1].
- **No peeking:** the backtest refits the parameters for every target season using only earlier seasons, so the parameters are never tuned on the season being forecast.
- **Spread:** the forecast's standard deviation is the standard deviation of the pooled one-year-ahead errors (never below the 6.4-win luck floor), as with the other models.
- **Teams with no history** (not seen in the training data) get a forecast of .500.
- **No seasonal term.** There is one number per team per year, so there is no seasonal cycle to model.

## Results

Backtest: every team, every season from 2001 to 2026, trained on earlier seasons only. 2020 (60 games) is excluded from the scores. 750 team-seasons per model.

| Model | MAE (wins) | RMSE (wins) | Bias | Avg. spread (wins) | 80% interval coverage |
| --- | --- | --- | --- | --- | --- |
| **holt** | **8.43** | **10.74** | 0.00 | 10.43 | 0.79 |
| last_year | 9.16 | 11.47 | 0.00 | 11.12 | 0.79 |
| constant | 9.93 | 12.09 | 0.00 | 11.84 | 0.79 |

- Holt improves on `last_year` by 0.73 wins RMSE, and on `constant` by 1.35.
- The ranking holds over later windows: RMSE from 2010 on is 10.90 (holt), 11.65 (last_year), 12.22 (constant); from 2016 on it is 11.07, 11.89 and 12.92.
- Season by season, holt has a lower RMSE than `last_year` in 18 of the 22 scored seasons where the two differ. The other four are 2012, 2015, 2018 and 2023.
- The 80% intervals are about right (coverage 0.79).
- 2001–2003 are identical to `last_year`, because there were too few seasons to fit the parameters.

### What the fitted parameters were

The parameters refit every season. Each row uses only the seasons before the target year.

| Target season | α | β | φ | Spread (wins) |
| --- | --- | --- | --- | --- |
| 2004 | 0.467 | 0.654 | 0.574 | 10.24 |
| 2005 | 0.546 | 0.000 | 0.000 | 11.09 |
| 2006 | 0.523 | 0.000 | 0.000 | 10.66 |
| 2007 | 0.511 | 0.000 | 0.000 | 10.46 |
| 2008 | 0.533 | 0.000 | 0.000 | 10.30 |
| 2009 | 0.499 | 0.000 | 0.000 | 10.39 |
| 2010 | 0.462 | 0.000 | 0.000 | 10.23 |
| 2011 | 0.463 | 0.000 | 0.000 | 10.07 |
| 2012 | 0.447 | 0.000 | 0.000 | 10.11 |
| 2013 | 0.489 | 0.000 | 0.000 | 10.22 |
| 2014 | 0.516 | 0.000 | 0.000 | 10.23 |
| 2015 | 0.502 | 0.000 | 0.000 | 10.25 |
| 2016 | 0.511 | 0.000 | 0.000 | 10.37 |
| 2017 | 0.528 | 0.000 | 0.000 | 10.31 |
| 2018 | 0.523 | 0.000 | 0.000 | 10.38 |
| 2019 | 0.552 | 0.000 | 0.000 | 10.52 |
| 2020 | 0.580 | 0.000 | 0.000 | 10.54 |
| 2021 | 0.565 | 0.000 | 0.000 | 10.79 |
| 2022 | 0.550 | 0.000 | 0.000 | 10.85 |
| 2023 | 0.529 | 0.000 | 0.000 | 10.89 |
| 2024 | 0.531 | 0.000 | 0.000 | 11.01 |
| 2025 | 0.531 | 0.000 | 0.000 | 11.00 |
| 2026 | 0.531 | 0.000 | 0.000 | 10.91 |
| 2027 (preseason forecast) | 0.507 | 0.000 | 0.000 | 10.84 |

### What the results say

1. **There is no usable trend in annual win%.** From 2005 on, the fit set β and φ to exactly 0 every time. The one exception, 2004, was fitted on only four seasons of history (three one-year-ahead errors per team), so it is likely noise. Given the 6.4-win luck floor, apparent momentum in a team's record is mostly luck.
2. **α sits near 0.5 and is stable** (0.45–0.58, typically 0.50–0.55). About half the weight goes to last season, a quarter to the one before, and so on. This is the whole gain: last year's record is a noisy measure of talent, and averaging it with earlier seasons reduces the noise.
3. **The effective model is plain exponential smoothing.** The "Holt" label is kept because the trend terms are still fitted and could switch on if the data ever supported them.
4. **The gain is modest.** About 0.7 wins RMSE is meaningful against the other baselines. The README's rough figure for the best public projection systems is a 7 to 8 win miss, so there is still a large gap to close. That's what the later rungs (roster and projection-based) are for.

## Limitations and ideas to revisit

- **No regression toward the league mean.** The level is smoothed toward each team's own history, never toward .500. Since extreme seasons are partly luck, blending the smoothed level toward 81 wins (shrinkage) is a likely next gain.
- **Starting level.** Each team's level starts at its first season (2000), which is a noisy starting point. It only matters in the early seasons of the backtest.
- **Win% only.** The model sees no roster, run differential, or payroll information. Run differential would be a better measure of talent than wins and losses.
- **One parameter set for every team.** Pooling is deliberate, but it assumes all teams share the same noise-to-talent ratio.
- **Short 2020 season.** 2020's 60-game win% is used as a normal observation when fitting, even though it is noisier. It's excluded from the scores but not from the training data.
- **Trend variants.** A per-model comparison of undamped and level-only versions was skipped on purpose. Since the fit chose no trend, there is little reason to revisit it unless the data changes.
