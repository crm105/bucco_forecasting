# transform

The dbt project that turns raw files into the tables models use. Runs on DuckDB. Nothing here has been run yet; the first thing to do is `bucco build` and fix whatever it finds.

## Run it

From the repo root, after `uv sync`:

```
uv run bucco extract mlb-seasons      # season calendar
uv run bucco extract mlb-standings    # final standings, 2000 to the latest completed season
uv run bucco extract projections      # hand-collected projections (empty is fine for now)
uv run bucco build                    # dbt deps, then dbt build (seeds, models, tests)
uv run dbt docs generate && uv run dbt docs serve   # from this folder, to browse the docs
```

`bucco build` sets `BUCCO_DATA_DIR` so dbt reads the same data folder the extract code writes to. If you run `dbt` by hand, run it from this folder and set `DBT_PROFILES_DIR=.`.

## Layers

| Layer | Folder | What it does |
| --- | --- | --- |
| Raw | `data/` (not dbt) | Files written by `src/bucco/extract`, unchanged. dbt reads them in place |
| Staging | `models/staging` | One model per raw table. Casts types, renames, trims text. No joins |
| Intermediate | `models/intermediate` | Joins and derived columns |
| Marts | `models/marts` | Tables that models and the backtest read |
| Seeds | `seeds` | Small hand-maintained lookups (`teams.csv`) |

## Tables models and the backtest use

| Table | One row per | Used for |
| --- | --- | --- |
| `team_seasons` | team and completed season | Actual results. Only the backtest reads this to score forecasts |
| `team_season_features` | team and season to forecast | Model inputs. Only prior-season columns, so the target season is never visible. Includes the upcoming season |
| `external_projections` | team, source and as-of date | Public projections and betting totals for model step 2 |

## Model steps and the data they need

| Step | Reads |
| --- | --- |
| 0. Constant | Nothing (81 wins). Scored against `team_seasons` |
| 1. Last year | `team_season_features.prior_win_pct` |
| 2. Blend of public forecasts | `external_projections` |

## Data checks

Column tests are in the `.yml` files next to each model. Checks across rows are in `tests/`:

| Test | Catches |
| --- | --- |
| `assert_30_teams_per_season` | A partial or failed download |
| `assert_league_wins_equal_losses` | Missing or corrupted team rows |
| `assert_playoff_team_counts` | A wrong playoff flag (compares against the real count for each era) |
| `assert_prior_season_present_after_first_season` | A gap in the season history |
| `assert_projections_published_before_opening_day` | A projection that could contain game results |
| `assert_projection_sets_complete` | A projection set missing teams |

## Conventions

- `team_id` (the MLB team id) is the franchise key. It doesn't change when a team moves or renames.
- Models predict `win_pct`, not wins. 2020 had 60 games.
- Preseason data must be dated on or before Opening Day.
- Each team is keyed by id, but team names in the data are today's names (the 2020 Guardians show as Guardians).

## Not collected yet

- Player-level data (needed for model steps 4a and 4b). The planning doc named the Lahman database, but the GitHub repository it was downloaded from no longer exists. SABR publishes the same database; a source needs picking before step 4.
- Payroll, FanGraphs team WAR, schedules and game logs (steps 3 and 5).
