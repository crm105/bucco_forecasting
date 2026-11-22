# Command-line guide

Everything is run through the `bucco` command, from the repo root. Prefix commands with `uv run`, or activate the environment first with `source .venv/bin/activate`.

## Typical order

```
bucco extract all      # 1. download and check raw data
bucco build            # 2. clean it into tables with dbt
bucco backtest         # 3. score the models
bucco leaderboard      # 4. view results
bucco forecast --model last_year   # 5. forecast the upcoming season
```

## Extract: get raw data

| Command | What it does |
| --- | --- |
| `bucco extract mlb-seasons` | Downloads the season calendar (Opening Day, season end dates). Always re-fetched. Writes `data/cache/mlb_api/seasons.parquet`. |
| `bucco extract mlb-standings` | Downloads final standings, one file per completed season since 2000. Skips seasons already saved and refuses to save a season that fails the 30-team and wins-equal-losses checks. |
| `bucco extract projections` | Reads the CSVs collected by hand in `data/manual/projections/`, validates them, and writes `data/snapshots/preseason_projections.parquet`. An empty folder is fine. |
| `bucco extract all` | Runs all three. |

Options for `mlb-standings`:

- `--seasons 2024 2025` fetches only those seasons.
- `--refresh` downloads seasons again even if they are already saved.

`projections` checks each projection date against Opening Day, so it needs the season calendar from `mlb-seasons`. `extract all` runs them in a working order.

## Build: clean and join

```
bucco build                                   # dbt deps, then dbt build (seeds, models, tests)
bucco build run --select stg_mlb__standings   # anything after "build" is passed to dbt
bucco build test
```

Builds `data/bucco.duckdb` with the `team_seasons`, `team_season_features` and `external_projections` tables, and runs the data checks. dbt always runs from `transform/` with the right environment variables.

## Backtest: score the models

```
bucco backtest
bucco backtest --models constant last_year
bucco backtest --first-season 2010
bucco backtest --include-shortened
```

For each past season from 2001 to 2026, each model is trained on earlier seasons only, predicts all 30 teams, and is compared with what happened. Results are saved to `evaluate.backtest_results` in `bucco.duckdb`, replacing earlier rows for the models you run and leaving other models' rows alone. The leaderboard is then printed.

| Option | Effect |
| --- | --- |
| `--models` | Which models to run. Default is all registered models: `constant` and `last_year`. |
| `--first-season` | Score only seasons from this year on. |
| `--include-shortened` | Include the 60-game 2020 season in the scores. It is excluded by default. |

## Forecast: predict the upcoming season

```
bucco forecast --model last_year
bucco forecast --model last_year --as-of 2027-03-15
bucco forecast --model last_year --no-save
```

Fits the model on every completed season, then predicts the season after the latest one (2027 once 2026 is complete). It prints each team's expected wins and an 80% range, best first, with the Pirates marked `*`.

| Option | Effect |
| --- | --- |
| `--model` | Required. One of the registered models (`constant`, `last_year`). |
| `--season` | Forecast a specific season. Completed seasons are refused; use `backtest` for those. |
| `--as-of` | Forecast date to record, `YYYY-MM-DD`. Default is today. A warning is printed if it is after Opening Day. |
| `--no-save` | Print only; do not store. |

Forecasts are saved to `forecasts.season_forecasts` in `bucco.duckdb`. Running again with the same model, season and as-of date replaces that row set; a different as-of date is kept as a separate version. The version made on or before Opening Day is the forecast of record.

## Leaderboard: view saved results

```
bucco leaderboard
bucco leaderboard --pirates
bucco leaderboard --first-season 2010 --include-shortened
```

Reads the saved results without re-running anything. The columns are:

| Column | Meaning |
| --- | --- |
| `team_seasons` | Number of team-seasons scored |
| `MAE`, `RMSE` | Average miss in wins per 162 games. RMSE penalizes big misses more |
| `bias` | Whether the model runs high (positive) or low (negative) |
| `avg_sd` | Typical size of the model's stated uncertainty, in wins |
| `80%_cover` | How often the real result fell inside the 80% interval. Should be near 0.80 |

`--pirates` adds a Pirates-only table of prediction errors by season. It is for interest only and is not used to choose models. `--first-season` and `--include-shortened` work as in `backtest`.

## Help and troubleshooting

- `bucco --help` and `bucco <command> --help` list every option.
- `command not found: dbt` or `bucco`: use `uv run`, or activate `.venv`.
- `bucco.duckdb not found`: run `bucco extract all` and `bucco build` first.
- `No backtest results yet`: run `bucco backtest` before `bucco leaderboard`.
- dbt reports `No dbt_project.yml found`: dbt was run from the wrong folder. Use `bucco build`, or `cd transform` first.
