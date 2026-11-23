# Command-line guide

Everything is run through the `bucco` command, from the repo root. Prefix commands with `uv run`, or activate the environment first with `source .venv/bin/activate`.

## Typical order

```
bucco extract all      # 1. download and check raw data
bucco build            # 2. clean it into tables with dbt
bucco backtest         # 3. score the models
bucco leaderboard      # 4. view results
bucco forecast --model last_year   # 5. forecast the upcoming season
bucco report                       # 6. write the HTML report
```

## Extract: get raw data

| Command | What it does |
| --- | --- |
| `bucco extract mlb-seasons` | Downloads the season calendar (Opening Day, season end dates). Always re-fetched. Writes `data/cache/mlb_api/seasons.parquet`. |
| `bucco extract mlb-standings` | Downloads final standings, one file per completed season since 2000. Skips seasons already saved and refuses to save a season that fails the 30-team and wins-equal-losses checks. |
| `bucco extract mlb-positions` | Downloads who played which position (games, starts and innings by player, team and season) for every completed season since 2000, 30 requests per season. Skips seasons already saved and refuses to save a season that fails the 30-team and main-position checks. Writes `data/cache/mlb_api/fielding/season=<year>.parquet`. Takes `--seasons` and `--refresh` like `mlb-standings`. |
| `bucco extract projections` | Reads the CSVs collected by hand in `data/manual/projections/`, validates them, and writes `data/snapshots/preseason_projections.parquet`. An empty folder is fine. |
| `bucco extract player-projections` | Reads the player-level FanGraphs downloads (e.g. `zips_batters_individual_2024.csv`) from the same folder, validates them, and writes `data/snapshots/player_projections.parquet`. Download dates come from `_player_downloads.csv`. See the [folder README](../data/manual/projections/README.md). |
| `bucco extract all` | Runs all five. |

Options for `mlb-standings` and `mlb-positions`:

- `--seasons 2024 2025` fetches only those seasons.
- `--refresh` downloads seasons again even if they are already saved.

`projections` and `player-projections` check each projection date against Opening Day, so it needs the season calendar from `mlb-seasons`. `extract all` runs them in a working order.

## Build: clean and join

```
bucco build                                   # dbt deps, then dbt build (seeds, models, tests)
bucco build run --select stg_mlb__standings   # anything after "build" is passed to dbt
bucco build test
```

Builds `data/bucco.duckdb` with the `team_seasons`, `team_season_features`, `external_projections`, `player_projections` and `player_positions` tables, and runs the data checks. dbt always runs from `transform/` with the right environment variables.

## Backtest: score the models

```
bucco backtest
bucco backtest --models constant last_year holt depth_chart
bucco backtest --first-season 2010
bucco backtest --include-shortened
```

For each past season from 2001 to 2026, each model is trained on earlier seasons only, predicts all 30 teams, and is compared with what happened. Results are saved to `evaluate.backtest_results` in `bucco.duckdb`, replacing earlier rows for the models you run and leaving other models' rows alone. The leaderboard is then printed.

| Option | Effect |
| --- | --- |
| `--models` | Which models to run. Default is all registered models: `constant`, `last_year`, `holt` and `depth_chart`. |
| `--first-season` | Score only seasons from this year on. |
| `--include-shortened` | Include the 60-game 2020 season in the scores. It is excluded by default. |

`depth_chart` (rung 5a) needs the player-level ZiPS files, so it is scored only on seasons that have them (2011 on, skipping 2010 and with the 60-game 2020 left out of the scores). To compare it fairly with the other models, use the same first season for all of them: `bucco leaderboard --first-season 2011`.

## Forecast: predict the upcoming season

```
bucco forecast --model last_year
bucco forecast --model last_year --as-of 2027-03-15
bucco forecast --model last_year --no-save
```

Fits the model on every completed season, then predicts the season after the latest one (2027 once 2026 is complete). It prints each team's expected wins and an 80% range, best first, with the Pirates marked `*`.

| Option | Effect |
| --- | --- |
| `--model` | Required. One of the registered models (`constant`, `last_year`, `holt`, `depth_chart`). |
| `--season` | Forecast a specific season. Completed seasons are refused; use `backtest` for those. |
| `--as-of` | Forecast date to record, `YYYY-MM-DD`. Default is today. A warning is printed if it is after Opening Day. |
| `--no-save` | Print only; do not store. |

`depth_chart` can only forecast a season once that season's ZiPS player files are in `data/manual/projections/` (run `bucco extract player-projections` and `bucco build` after adding them); until then it stops with `no ZiPS player projections for <season>`.

Forecasts are saved to `forecasts.season_forecasts` in `bucco.duckdb`. Running again with the same model, season and as-of date replaces that row set; a different as-of date is kept as a separate version. The version made on or before Opening Day is the forecast of record.

## Report: write the HTML forecast report

```
bucco report
bucco report --model last_year
bucco report --as-of 2027-03-15
```

Builds one self-contained web page from saved results and writes it to `reports/<season>/<model>_<as-of>.html`. Open it in a browser or publish it anywhere that serves static files. It reads only saved forecasts and backtest results, so run `bucco backtest` and `bucco forecast --model <name>` first.

| Option | Effect |
| --- | --- |
| `--model` | Default is the best model on the leaderboard (lowest RMSE, 2020 excluded). |
| `--season` | Default is the upcoming season. |
| `--as-of` | Use the saved forecast with this as-of date. Default is the latest one. |

The page shows the Pirates headline (expected wins, 80% range, chance of finishing above .500, chance of beating last season), what changed since the previous saved forecast, a timeline of the Pirates forecast when there are two or more as-of dates, a range chart for all 30 teams, and the backtest scores with the Pirates' past errors. A badge marks whether it is the forecast of record (the latest one made on or before Opening Day, once Opening Day has passed), preliminary, or made too late. See [reporting.md](reporting.md) for the design.

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
