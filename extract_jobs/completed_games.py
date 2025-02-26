"""
Script for retreiving completed games from MLB stats api 'schedule' endpoint
Request returns highly nested json. Longer term I should aspire to having a single script for 
retreiving data from API and loading into DB. For now, I plan to hardcode and slowly abstract away 

ToDo: Allow script to be executed via shell script
ToDo: pre-commit hook
ToDo: Move hardcoded params to configs
ToDo: Offload parsing functionality to outside utils
ToDo: Allow for start and end dates to be dynamically determined given what already exists in DB
ToDo: Parse Additional fields 
    - Home Score
    - Away Score
"""

import pandas as pd
import requests
import yaml

from sqlalchemy import create_engine


endpoint = "schedule"
params = {"sportId" :1,
          "teamId":134,
          "startDate":"2024-04-20",
          "endDate":"2025-12-31",
          "status":"Final"}

url = f"https://statsapi.mlb.com/api/v1/{endpoint}"

response = requests.get(url, params = params)

games = []
for date in response.json().get("dates"):
    for game in date.get("games"):
        #Skip incomplete games due to rainouts
        if game['status']['statusCode'] != 'F':
            pass
        else:
            away_id = game['teams']['away']['team']['id']
            home_id = game['teams']['home']['team']['id']

            #ToDo: Allow for handling of ties, incomplete games
            #Should winner field be reserved for downstream transform steps?
            if game['teams']['away']['isWinner']:
                game_winner = away_id
            else:
                game_winner = home_id

            game_info = {"gamePk":game["gamePk"],
                        "gameDate":game["gameDate"], 
                        "home_id":home_id,
                        "away_id":away_id,
                        "winner": game_winner
                        }
            games.append(game_info)

completed_game_frame = pd.DataFrame.from_records(games)

#Load retreived data into Postgres DB 
with open("../db_config.yml", "r") as file:
    config = yaml.safe_load(file)

DB_USERNAME = config["DB_USERNAME"]
DB_PASSWORD = config["DB_PASSWORD"]
DB_HOST = config["DB_HOST"]
DB_PORT = config["DB_PORT"]
DB_NAME = config["DB_NAME"]
TABLE_NAME = "game_results"

engine = create_engine(f"postgresql://{DB_USERNAME}:{DB_PASSWORD}@{DB_HOST}:{DB_PORT}/{DB_NAME}")

#ToDo: Modify process to appends new data to existing table
completed_game_frame.to_sql(TABLE_NAME, engine, schema = "staging", if_exists="replace", index=False)