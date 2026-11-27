# Evaluating player-projection models (2026-11-26)

`bucco evaluate [--models ...] [--first-season 2012]` prints three layers of tables for any
player-projection model; `bucco team-war` prints the team-WAR layer alone. Player projections are
judged on player-level accuracy first; the team layers are secondary checks.

## What each table measures

**1. Player projection error** (hitters and pitchers separately, RMSE):

- *Rate*: projected WAR per 600 PA (per 180 innings) against what the player did, for players
  with 100+ PA (30+ innings), weighted by playing time, after removing each season's league mean.
  Where the source has them: offense runs per 600 PA, and FIP-based runs per 9 innings.
- *Playing time*: the PA or innings the model gave each player after the lineup and staff
  optimizers, against what he got; and the bias (projected minus actual).
- *Production*: the WAR the model gave each player against his actual WAR (season mean removed).

Playing time and production are scored on one population for every model: everyone on an Opening
Day 40-man roster or in an organization's minor-league depth (marts.organization_depth), plus
everyone who played, with 0 for any player a model did not project. Without it, a source that
lists whole organizations (Steamer: 40,000 hitter-seasons, most of whom never play) is flattered
by thousands of easy zeros; with the minor leaguers in it, a model that gives them time they never
get pays for it. (The population included only the 40-man until the organization-depth pitcher
test; adding the minor leaguers adds many near-zero errors, so playing-time RMSEs fell, for
example our hitters' PA from 160 to 87 and Steamer's from 89 to 97 once its spurious minor-league
time counted.)

**2. Forecast error**: team WAR against what each team produced (batting, pitching, total; season
mean removed) and team record (the wins backtest). Team WAR leaves out game-to-game luck, run
sequencing and the WAR-to-wins line, so it shows player-level gains the wins backtest cannot: the
learned innings model was t −1.3 to −1.9 on wins and −2.9 to −4.3 on team pitching WAR.

**3. Rate against playing time**: team WAR recomputed with *perfect playing time* (each projected
rate times the PA or innings the player actually got, with the team he got them with; players the
model did not project at replacement level), with *perfect rates* (each player's actual rate times
his projected playing time; his projected rate if he played too little to have one), and with
*perfect both* (what is left: players the model never projected).

Actual values are our own park-neutral approximations (`player_team_seasons`, `team_war_seasons`):
FIP-based pitching, offense plus positional adjustment, no measured fielding. Our model projects
exactly that; Steamer and ZiPS project FanGraphs WAR, so across systems the WAR-based numbers lean
our way. Comparisons between versions of one model are fair. A season's actual rate includes that
season's luck (balls in play, sequencing), so "rate error" includes noise no projection can remove.

## First results, 2012–2026

Hitters:

| | PA RMSE | PA bias | Production (WAR) | Rate (WAR/600) | Off runs/600 |
| --- | --- | --- | --- | --- | --- |
| `marcel_staff_optimized` | **160.0** | −13.8 | **1.15** | **1.69** | **15.94** |
| `steamer_optimized` | 171.0 | −11.9 | 1.17 | 1.73 | 16.34 |
| `zips_optimized` | 185.6 | −10.6 | 1.24 | 1.75 | 16.39 |

Pitchers:

| | IP RMSE | IP bias | Production (WAR) | Rate (WAR/180) |
| --- | --- | --- | --- | --- |
| `marcel_staff_optimized` | 38.7 | −10.8 | 0.83 | 1.62 |
| `steamer_optimized` | **37.7** | +1.6 | **0.80** | **1.60** |
| `zips_optimized` | 52.5 | −12.1 | 0.92 | 1.71 |

Forecast:

| | Team WAR: batting | pitching | total | Record RMSE | Typical miss | In 80% range |
| --- | --- | --- | --- | --- | --- | --- |
| `marcel_staff_optimized` | 5.46 | 4.76 | 7.98 | 9.58 | 7.67 | 78% |
| `steamer_optimized` | 5.88 | 4.77 | 8.07 | 9.58 | 7.71 | 78% |
| `zips_optimized` | 5.82 | 5.01 | 8.32 | 9.72 | 7.84 | 79% |

Rate against playing time, team WAR RMSE (total):

| | Full projection | Perfect playing time | Perfect rates | Perfect both |
| --- | --- | --- | --- | --- |
| `marcel_staff_optimized` | 7.98 | 7.33 | 4.55 | 2.25 |
| `steamer_optimized` | 8.07 | 7.12 | 4.55 | 0.73 |
| `zips_optimized` | 8.32 | 7.19 | 5.29 | 0.70 |

Readings:

- **Rates are most of the team error** for every model: knowing playing time exactly takes 8.0 to
  7.3 (ours), knowing rates exactly takes it to 4.6. Much of that "rate error" is single-season
  luck that no projection can remove.
- **Our model leaves more out**: players it never projected (no MLB history and too little in
  the minors, or not on a 40-man) are worth 2.25 WAR of team error against Steamer's 0.73.
- **Pitchers' innings run low** in our model (−10.8 innings a pitcher on average): the learned
  innings model (ml_playing_time.md) should fix part of it.
