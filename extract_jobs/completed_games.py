"""
Script for retreiving completed games from MLB stats api 'schedule' endpoint
Request returns highly nested json. Longer term I should aspire to having a single script for 
retreiving data from API and loading into DB. For now, I plan to hardcode and slowly abstract away 

ToDo: Move hardcoded params to config 
ToDo: Offload parsing functionality to outside utils
ToDo: Allow for start and end dates to be dynamically determined given what already exists in DB
"""

import pandas as pd
import statsapi
import requests

endpoint = "schedule"
params = {"sportId" :1,
          "teamId":134,
          "startDate":"2024-04-20",
          "endDate":"2025-12-31",
          "status":"Final"}
url = f"https://statsapi.mlb.com/api/v1/{endpoint}"

games = []
for date in test.json().get("dates"):
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

#ToDo: Load retreived data into DB 