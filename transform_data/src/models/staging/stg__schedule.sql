SELECT 
DATE_PART('year', gamedate::DATE)::INT AS season 
, gamepk::BIGINT
, gamedate::DATE
, gamedt::TIMESTAMPTZ
, gametype::VARCHAR
, game_status::VARCHAR
, home_id::INT
, away_id::INT
, home_win::INT
, home_score::INT
, away_score::INT 
, home_wins::INT 
, away_wins::INT
, away_losses::INT
, home_losses::INT 
, home_pct::FLOAT 
, away_pct::FLOAT
, away_pitcher_era_postgame::FLOAT
, home_pitcher_era_postgame::FLOAT
, home_pitcher_innings_pitched_postgame::FLOAT
, away_pitcher_innings_pitched_postgame::FLOAT
, away_pitcher_earned_runs_game::INT
, away_pitcher_earned_runs_postgame::INT
, away_pitcher_innings_pitched_game::FLOAT
, home_pitcher_innings_pitched_game::FLOAT
, home_pitcher_earned_runs_game::INT
, home_pitcher_earned_runs_postgame::INT
, CURRENT_TIMESTAMP AS last_updated_datetime
FROM {{ source('mlb_api', 'schedule_endpoint') }}