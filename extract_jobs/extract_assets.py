import dagster as dg
import pandas as pd
import requests
import yaml

import sys
sys.path.append('..')

from datetime import date
from utils.utils import pg_engine
from utils.extract_utils import process_schedule_response


today = date.today().strftime("%Y-%m-%d")

endpoint = "schedule"
#ToDo: Allow for endDate to be determined dynamically
#i.e. just end of calendar year? 
params = {"sportId" :1,
          "teamId":134,
          "startDate":"2024-01-01",
          "endDate":"2025-12-31",
          }

@dg.asset
def schedule_endpoint():
    ## Read data from the CSV
    url = f"https://statsapi.mlb.com/api/v1/{endpoint}"
    response = requests.get(url, params = params)

    schedule_data = process_schedule_response(response, game_status = "any")

    #Load retreived data into Postgres DB 
    with open("db_config.yml", "r") as file:
        db_config = yaml.safe_load(file)

    engine = pg_engine(db_config)

    #ToDo: Modify process to append new data to existing table
    schedule_data.to_sql('schedule_endpoint', engine, schema = "staging", if_exists="replace", index=False)

    return "Data loaded successfully"

defs = dg.Definitions(assets=[schedule_endpoint])