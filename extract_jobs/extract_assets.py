import dagster as dg
import pandas as pd
import requests
import yaml

import sys
sys.path.append('..')

from datetime import date
from utils.utils import pg_engine
from utils.extract_utils import process_schedule_response, _postgres_upsert
from dagster_dbt import get_asset_key_for_source
from transform_data import dbt_definitions as la



dbt_assets = dg.load_assets_from_modules([la])


today = date.today().strftime("%Y-%m-%d")

endpoint = "schedule"
#ToDo: Allow for endDate to be determined dynamically
#i.e. just end of calendar year?
params = {"sportId":1,
          "gameTypes":'R',
          "startDate":"2025-01-01",
          "endDate":"2025-12-31",
          "hydrate":'probablePitcher,stats'
          }

engine = pg_engine()

@dg.asset(key=get_asset_key_for_source(dbt_assets, "mlb_api"))
def schedule_endpoint():
    ## Read data from the CSV
    url = f"https://statsapi.mlb.com/api/v1/{endpoint}"
    response = requests.get(url, params = params)

    schedule_data = process_schedule_response(response, game_status = "any")

    #ToDo: Modify process to append new data to existing table
    schedule_data.to_sql('schedule_endpoint', engine, schema = "mlb_api", if_exists="append", index=False,
                         method = _postgres_upsert)

    return "Data loaded successfully"

del dbt_assets

defs = dg.Definitions(assets=[schedule_endpoint])
