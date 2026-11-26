# Learned models instead of Marcel: playing time and rates (2026-11-26)

## What we tried

Whether a learned model (gradient-boosted trees, and plain linear regression for reference)
beats our Marcel pipeline, first at the player level, then at the team level. Everything is
walk-forward: each target season's model is fitted only on earlier target seasons, 2020 left out
of fitting and scoring. Hyperparameters were fixed up front, not tuned (boosting: learning rate
0.05, 300 trees, 15 leaves, 40 rows per leaf). Run with scikit-learn loaded for the test only
(`uv run --with scikit-learn`); not a project dependency.

## Playing time

Population: players on Opening Day 40-man rosters with a projection (about 550 hitters and 650
pitchers a season, 2009 on); target next season's PA or innings, 0 if he did not play.
Features: three seasons of lagged PA or innings, games, starts and batters faced (2020 scaled to
162 games), age, last season's minor-league volume by level, our projected rates (offense,
defense, WAR or FIP runs per inning, start share), Opening Day status this year and last (60-day
or short injured list, on a 40-man), and the availability factor. "+ pipeline" adds our
pipeline's playing time as a feature. Player-level error, 2012–2026:

| | Hitters PA RMSE | Within team | Pitchers IP RMSE | Within team |
| --- | --- | --- | --- | --- |
| Our pipeline | 164.6 | 164.2 | 38.8 | 39.0 |
| Linear | 148.7 | 148.5 | 38.2 | 38.4 |
| Boosting | 148.7 | 148.4 | 38.2 | 38.2 |
| Boosting + pipeline | **148.2** | **148.0** | **38.0** | **38.1** |

("Within team": each method's predictions scaled to the same team total, i.e. who gets the
time.) Hitters' PA: 10% less error, and linear does as well as boosting, so the gain is from
fitting the weights, not from ML: Marcel's 0.5 / 0.1 / 200 formula is crude. Last season's PA
dominates; quality, age, the season before, games and Triple-A volume add to it.

**Teams** (wins RMSE; learned values from 2011, the first season with two earlier ones to fit):

| | 2012–26 | 2012–19 | 2021–26 | Better | t |
| --- | --- | --- | --- | --- | --- |
| `marcel_staff_optimized` | 9.576 | 9.254 | 9.988 | | |
| Hitters' PA learned, linear | 9.613 | 9.265 | 10.059 | 5 of 14 | +1.1 |
| Hitters' PA learned, boosting + pipeline | 9.583 | 9.196 | 10.076 | 7 of 14 | +0.2 |
| **Pitchers' innings learned, boosting + pipeline** | **9.470** | 9.214 | 9.800 | 10 of 14 | **−1.8** |
| Pitchers' innings learned, linear | 9.499 | 9.177 | 9.912 | 11 of 14 | −1.6 |
| Both, boosting + pipeline | 9.474 | 9.151 | 9.888 | 10 of 14 | −1.3 |

The hitters' gain vanishes at team level: the lineup optimizer re-divides each team's PA by
talent and position anyway. Pitchers' innings are the opposite: 2% at player level but 0.1 wins
at team level, from both learners. The likely reason: the baseline-innings line uses past innings,
age and role but not quality, so it gives a good pitcher and a poor one with the same history the
same innings; the learned model gives the better one more, which is what teams do. (Steamer 9.50
on the same seasons.)

## Rates

Population: every pitcher or hitter with MLB history (fitted from 2003), scored on those with
100+ PA or 30+ IP; target park-neutral offense runs per 600 PA or FIP runs per 9 innings,
relative to the season, weighted by playing time. Features: three seasons of rates (offense,
strikeout, walk, home-run, steal rates, ISO, BABIP; pitchers' four FIP parts per batter faced,
start share, ground-out share) with volumes and age.

| | Hitters | 2012–19 | 2021–26 | Pitchers | 2012–19 | 2021–26 |
| --- | --- | --- | --- | --- | --- | --- |
| **Marcel (ours)** | **16.04** | 15.96 | 16.14 | 0.764 | 0.739 | 0.797 |
| Linear | 16.91 | 17.08 | 16.68 | 0.774 | 0.754 | 0.801 |
| Boosting | 16.48 | 16.49 | 16.48 | 0.757 | 0.741 | 0.778 |
| Boosting + Marcel | 16.16 | 16.18 | 16.15 | **0.754** | 0.740 | 0.772 |

Marcel's hitter rates are not beaten; pitchers gain about 1%, all since 2021 (about 0.01–0.02
wins at team level). With these features, the tuned Marcel has taken most of what history offers;
new inputs (Statcast contact and swing data, 2015 on) would be needed for more.

## Conclusion

The case for ML is playing time, and specifically pitchers' innings: a learned innings model is
worth about 0.1 wins (9.58 to 9.47, t −1.8). A linear fit gets most of it (9.50) without a new
dependency. Rates and hitters' PA: no.

## Status

Tested only (scripts not in the repo). Next: build the innings model into `innings.py` as an
option, rerun the registered backtest, and check the 2027 staffs.
