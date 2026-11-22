# Legacy: per-game win model

Archived on 2026-11-21 when the project moved from predicting single Pirates games to forecasting the Pirates' full-season record. See [docs/planning](../docs/planning/) for the new plan.

This folder holds the original project unchanged, with its layout intact, so it can still run from here.

## What's here

| Path | What it is |
| --- | --- |
| `extract_jobs/` | Dagster asset that pulls the MLB Stats API schedule endpoint (with probable pitchers) into Postgres; Spotrac payroll scraper |
| `transform_data/` | dbt project (Postgres): staging, game-by-team and pitcher intermediates, `modeling_frame` and `prediction_frame` marts; `team_ids` seed; `z_score` and `log5_ratio` macros |
| `modeling/` | XGBoost classifier with Bayesian hyperparameter search; saved model; analysis notes |
| `forecasting/` | Dagster asset that scores upcoming games into `crm_mart.completed_predictions`; payroll loader |
| `utils/` | Postgres engine, API response parsing and upsert helpers, model QC helpers |
| `dagster_definitions.py`, `dagster.yaml`, `workspace.yaml` | Dagster definitions, instance config, daily 09:00 UTC schedule |
| `docker-compose.yaml`, `Dockerfile_*`, `.dockerignore` | Postgres + Dagster webserver, daemon and code server |
| `pyproject.toml`, `requirements.txt`, `Pipfile` | Old dependency and Dagster module config |
| `dagster/`, `logs/` | Local Dagster run history and logs (gitignored) |

## Parts likely to be reused

- MLB Stats API schedule extraction and date pagination (`utils/extract_utils.py`)
- `transform_data/src/seeds/team_ids.csv`
- `z_score` and `log5_ratio` dbt macros
- `utils/ml_utils.py` calibration and QC helpers

Copy these into the new project when they're needed rather than importing from `legacy/`.

## Restoring it

Everything runs from inside this folder:

1. Copy the root `.env` into `legacy/` (`docker-compose.yaml` reads `.env` from its own folder).
2. Make sure `transform_data/src/profiles.yml` still has the Postgres connection details (it's gitignored and moved here with the rest).
3. `cd legacy && docker compose up --build`, then open Dagster at http://localhost:3000.

Known issue carried over: `transform_data/src/models/intermediate/team_season_statistics.sql` scales wins for `season = 2021`, but the 60-game season was 2020.
