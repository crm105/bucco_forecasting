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

## Second round: richer features and tuning (2026-11-26)

Inputs reworked: each past season combines MLB and minor-league lines (with the share of playing
time in the minors and the average level), injured-list days, stints and 60-day stints
(`player_il_seasons`), ground-out share, rates against each season's league, a season term and
recency weights (x0.9 a year); missing values left missing. Settings tuned for each target season
on the two seasons before it (18: leaves 15/7/4, rows per leaf 40/100/200, trees 300/150). Player
level, 2012–2026, with Steamer on the same players:

| | Current pipeline | Tuned boosting + current | Steamer |
| --- | --- | --- | --- |
| Pitcher innings (RMSE) | 38.79 | **37.43** | 39.47 |
| Hitter PA (RMSE) | 164.6 | **146.2** | 146.3 |
| Pitcher rate (runs per 9) | 0.778 | **0.762** | 0.761 |
| Hitter rate (off runs per 600) | 16.24 | **16.21** | 16.31 |

Through the forecast (`bucco evaluate` tables, 2012–2026, wins line from 2012):

| | Team WAR batting | pitching | total | Record RMSE |
| --- | --- | --- | --- | --- |
| Current | 5.46 | 4.76 | 7.98 | 9.56 |
| All four learned, summed as given | 5.54 | 4.65 | 7.86 | 9.56 |
| All four learned, through the optimizers | 5.52 | 4.63 | 7.84 | 9.52 |
| **Learned pitchers only, through the optimizers** | **5.46** | **4.63** | **7.82** | **9.46** |

Learned hitter PA is better player by player but makes team batting WAR worse, as given or
through the lineup optimizer (which re-divides PA). It does not compress teams (projected team
batting WAR spread 4.8 against 4.4 now; actual 6.9); why it hurts is open. Learned hitter rates
tie Marcel.

## Status

Adopted for pitchers as `marcel_ml_pitchers` (`bucco.models.ml_pitchers`): `marcel_staff_optimized`
with learned pitcher innings and rates through the staff optimizer. Registered backtest 9.50 on
2012–2026 (Steamer 9.50, `marcel_staff_optimized` 9.58). `bucco fit-ml-pitchers` fits both models
(about an hour) and saves predictions for 2012 to the upcoming season; innings before 2012 stay the
pipeline's. 2027 Pirates 82.4 wins (12th): their pitching WAR rises (17.9 to 19.3) but the league's
rises more (14.0 to 16.2), as the learned innings give more time to projected pitchers everywhere.

## Minor-league pitchers (organization depth): not adopted

Players off the Opening Day 40-man are never projected, and the pitchers among them were worth
1.55 WAR of team pitching error ("perfect both"). The innings model was refitted on the 40-man plus
each organization's minor-league depth (`bucco fit-ml-pitchers --roster mlb_org`, 27 minutes;
an "on the 40-man" flag added, which is constant, so unused, for the 40-man model) and pitchers
joined those wider rosters (`load_marcel_data(pitcher_roster="mlb_org")`); hitters and every
Marcel projection unchanged. Minor leaguers got 2.2 innings each on average, about 140 per team
season taken from replacement level.

`bucco evaluate`, 2012–2026, population now including organization depth:

| | Innings RMSE | bias | WAR per 180 | Team pitching WAR | unprojected | Record RMSE |
| --- | --- | --- | --- | --- | --- | --- |
| `marcel_ml_pitchers` | **21.50** | −2.4 | **1.61** | **4.64** | 1.55 | **9.50** |
| with organization depth | 21.99 | −0.6 | 1.64 | 4.67 | **0.98** | 9.53 |
| Steamer, optimized | 21.75 | 1.4 | 1.60 | 4.77 | 0.57 | 9.58 |

(2009–2026: 9.39 against 9.41.) The unprojected share fell from 1.55 to 0.98, but the minor
leaguers' rates are poor enough that the rate error rose by more (perfect playing time 4.46 to
4.56), and innings error rose: spreading 2 innings over every minor leaguer misses on the few who
pitch a lot. Worse on player accuracy, so kept only as an option.
