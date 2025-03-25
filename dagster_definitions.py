import dagster as dg
from dagster_dbt import dbt_assets, DbtCliResource, DbtProject

from extract_jobs import extract_assets
from transform_data import transform_assets
from forecasting import forecasting_assets


from pathlib import Path


all_assets = dg.load_assets_from_modules([extract_assets, transform_assets, forecasting_assets])

# Points to the dbt project path
dbt_project_directory = Path(__file__).absolute().parent/ "transform_data/src"
dbt_project = DbtProject(project_dir=dbt_project_directory)

# References the dbt project object
dbt_resource = DbtCliResource(project_dir=dbt_project)

daily_schedule = dg.ScheduleDefinition(
    name = "run_full_pipeline",
    cron_schedule="0 0 * * *", 
    target = dg.AssetSelection.keys(["mlb_api", "schedule_endpoint"]).downstream(),
    default_status=dg.DefaultScheduleStatus.RUNNING
)

defs = dg.Definitions(
    assets=all_assets,
    schedules=[daily_schedule],
    resources={"dbt": dbt_resource},
)