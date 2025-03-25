import datetime
import requests
import numpy as np
import pandas as pd
import requests

from utils.utils import pg_engine
from sqlalchemy.dialects.postgresql import insert

import sys
sys.path.append('..')

def _postgres_upsert(table, conn, keys, data_iter):
    """Function for upserting records into PG
    """

    data = [dict(zip(keys, row)) for row in data_iter]

    insert_statement = insert(table.table).values(data)
    upsert_statement = insert_statement.on_conflict_do_update(
        constraint=f"pk_{table.table.name}",
        set_={c.key: c for c in insert_statement.excluded},
    )
    conn.execute(upsert_statement)

def _extract_probable_pitcher_info(game_response):
    """
    Extracts season stats of probable pitchers listed in game from schedule endpoint response

    Args:
        game_response (dict): Individual game level dict housed within schedule endpoint response
    
    Returns: 
        dict: dict containing home, away probable pitcher season stats for game
    """
    #Find dict containing season stats
    probable_pitchers = {}
    for team, info in game_response['teams'].items():
        if "probablePitcher" in info:
            probable_pitchers.update({f'{team}_pitcher_postgame_' + key: value for key, value in
                                    info['probablePitcher']['stats'][3]['stats'].items()})
            
            probable_pitchers.update({f'{team}_pitcher_game_' + key: value for key, value in
                                    info['probablePitcher']['stats'][1]['stats'].items()})
            
    probable_pitchers['gamePk'] = game_response['gamePk']

    return probable_pitchers

#ToDo: Move JSON parsing to its own function. Make this a wrapper
#for individual functions
def process_schedule_response(response, game_status = "any"):
    """Extracts relevant data from MLB stats api and formats into data frame
    Args:
        response (dict): Response from request to MLB stats api schedule endpoint
        game_status (str): Indicating whether response contains "final", "scheduled", or "any" games
    
    Returns:
        pd.DataFrame
    """

    games = []
    for date in response.json().get("dates"):
        for game in date.get("games"):
            #ToDo: Determine if endpoint param can be used to filter responses
            if (game_status == "final") & (game['status']['statusCode'] != 'F'):
                pass
            elif (game_status == "scheduled") & (game['status']['statusCode'] == 'F'):
                pass
            #Ignore games that are cancelled or postponed
            # Allows for uniqueness on gamepk
            elif game['status']['statusCode'] in ['DI', 'DR','CR', 'D']:
                pass
            elif 'resumeDate' in game:
                pass
            else:
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

                if game['status']['statusCode'] == 'F':
                    home_win = game['teams']['home']['isWinner']
                    home_score = game['teams']['home']['score']
                    away_score = game['teams']['away']['score']

                else:
                    home_win = np.nan
                    home_score = np.nan
                    away_score = np.nan

                probable_pitchers = (_extract_probable_pitcher_info(game))

                game_info = {"gamepk":game["gamePk"],
                            "calendar_event_id": game['calendarEventID'],
                            "gamedate":game["officialDate"],
                            "gamedt": game['gameDate'].replace('T', ' ')[:-1],
                            "gametype":gametype,
                            "game_status":game['status']['statusCode'],
                            "home_win":home_win,
                            "home_score":home_score,
                            "away_score":away_score,
                            "home_id":home_id,
                            "away_id":away_id,
                            "home_wins":home_wins,
                            "home_losses":home_losses,
                            "home_pct":home_pct,
                            "away_wins":away_wins,
                            "away_losses":away_losses,
                            "away_pct":away_pct,
                            "away_pitcher_era_postgame":pd.to_numeric(probable_pitchers.get('away_pitcher_postgame_era'), errors = 'coerce'),
                            "home_pitcher_era_postgame":pd.to_numeric(probable_pitchers.get('home_pitcher_postgame_era'), errors ='coerce'),
                            "home_pitcher_innings_pitched_postgame": pd.to_numeric(probable_pitchers.get('home_pitcher_postgame_inningsPitched'), errors = 'coerce'),
                            "away_pitcher_innings_pitched_postgame": pd.to_numeric(probable_pitchers.get('away_pitcher_postgame_inningsPitched'), errors = 'coerce'),
                            "away_pitcher_earned_runs_game": pd.to_numeric(probable_pitchers.get('away_pitcher_game_earnedRuns'), errors = 'coerce'),
                            "away_pitcher_earned_runs_postgame": pd.to_numeric(probable_pitchers.get('away_pitcher_postgame_earnedRuns'), errors = 'coerce'),
                            "home_pitcher_earned_runs_postgame": pd.to_numeric(probable_pitchers.get('home_pitcher_postgame_earnedRuns'), errors = 'coerce'),
                            "away_pitcher_innings_pitched_game": pd.to_numeric(probable_pitchers.get('away_pitcher_game_inningsPitched'), errors = 'coerce'),
                            "home_pitcher_innings_pitched_game": pd.to_numeric(probable_pitchers.get('home_pitcher_game_inningsPitched'), errors = 'coerce'),
                            "home_pitcher_earned_runs_game": pd.to_numeric(probable_pitchers.get('home_pitcher_game_earnedRuns'), errors = 'coerce'),
                            "last_updated_datetime": datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                            }
                games.append(game_info)

    return pd.DataFrame.from_records(games)
