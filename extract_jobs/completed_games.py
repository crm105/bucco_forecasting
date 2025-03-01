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

import numpy as np
import pandas as pd
import pickle
import requests
import yaml

import sys
sys.path.append('..')

from utils.utils import pg_engine
from sklearn.linear_model import LinearRegression
from sqlalchemy import Float

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


            #ToDo: Allow for handling of ties, incomplete games
            #Should winner field be reserved for downstream transform steps?
            if game['teams']['away']['isWinner']:
                game_winner = away_id
                home_win = 0
            else:
                game_winner = home_id
                home_win = 1

            game_info = {"gamepk":game["gamePk"],
                        "gamedate":game["officialDate"],
                        "gamedt": game['gameDate'].replace('T', ' ')[:-1],
                        "gametype":gametype,
                        "home_id":home_id,
                        "away_id":away_id,
                        "winner": game_winner,
                        "home_win": home_win,
                        "home_wins":home_wins,
                        "home_losses":home_losses,
                        "home_pct":home_pct,
                        "away_wins":away_wins,
                        "away_losses":away_losses,
                        "away_pct":away_pct
                        }
            games.append(game_info)

completed_game_frame = pd.DataFrame.from_records(games)

#ToDo: Offload Engine Creation to Util, Draw from environmental variables 
with open("../db_config.yml", "r") as file:
    db_config = yaml.safe_load(file)

engine = pg_engine(db_config)

#ToDo: Modify process to appends new data to existing table
completed_game_frame.to_sql("completd_games", engine, schema = "staging", if_exists="replace", index=False,
                            dtype = {"home_pct":Float(), 
                                     "away_pct":Float()})