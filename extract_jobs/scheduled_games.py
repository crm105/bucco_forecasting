"""
Script for retreiving completed games from MLB stats api 'schedule' endpoint
Request returns highly nested json. Longer term I should aspire to having a single script for 
retreiving data from API and loading into DB. For now, I plan to hardcode and slowly abstract away 

ToDo: Allow script to be executed via shell script
ToDo: Move hardcoded params to configs
ToDo: Unify completed, future endgames to draw from same request!
ToDo: Parse Additional fields 
    - Home Score
    - Away Score
"""

import pandas as pd
import requests
import yaml

import sys
sys.path.append('..')

from datetime import date
from utils.utils import pg_engine

today = date.today().strftime("%Y-%m-%d")

endpoint = "schedule"
#ToDo: Allow for endDate to be determined dynamically
#i.e. just end of calendar year? 
params = {"sportId" :1,
          "teamId":134,
          "startDate":today,
          "endDate":"2025-12-31",
          }

url = f"https://statsapi.mlb.com/api/v1/{endpoint}"
response = requests.get(url, params = params)

games = []
for date in response.json().get("dates"):
    for game in date.get("games"):
        if game['status']['statusCode'] == 'F':
            pass
        else:
            #ToDo: Define a function or use config to define these? 
            #More on gameTypes https://statsapi.mlb.com/api/v1/gameTypes
            gametype = game['gameType']
            away_id = game['teams']['away']['team']['id']
            home_id = game['teams']['home']['team']['id']
            home_wins = game['teams']['home']['leagueRecord']['wins']
            home_losses = game['teams']['home']['leagueRecord']['losses']
            home_pct =  game['teams']['home']['leagueRecord']['pct']
            away_wins = game['teams']['away']['leagueRecord']['wins']
            away_losses = game['teams']['away']['leagueRecord']['losses']
            away_pct =  game['teams']['away']['leagueRecord']['pct']

            game_info = {"gamepk":game["gamePk"],
                        "gamedate":game["officialDate"],
                        "gamedt": game['gameDate'].replace('T', ' ')[:-1],
                        "gametype":gametype,
                        "home_id":home_id,
                        "away_id":away_id,
                        "home_wins":home_wins,
                        "home_losses":home_losses,
                        "home_pct":home_pct,
                        "away_wins":away_wins,
                        "away_losses":away_losses,
                        "away_pct":away_pct
                        }
            games.append(game_info)

scheduled_game_frame = pd.DataFrame.from_records(games)

#Load retreived data into Postgres DB 
with open("../db_config.yml", "r") as file:
    db_config = yaml.safe_load(file)

engine = pg_engine(db_config)

#ToDo: Modify process to appends new data to existing table
scheduled_game_frame.to_sql('scheduled_games', engine, schema = "staging", if_exists="replace", index=False)
