{{ config(materialized='table') }}

WITH team_seed AS (
    SELECT * FROM {{ ref('team_ids') }}
)

SELECT
DATE_PART('year', gamedate::DATE)::INT AS season
, gamepk::BIGINT
, gamedate::DATE
, gamedt::TIMESTAMPTZ
, gametype::VARCHAR
, game_status::VARCHAR
, home_id::INT
,  home_join.team_name::VARCHAR AS home_team_name
,  home_join.team_abbr::VARCHAR AS home_team_abbr
, away_id::INT
,  away_join.team_name::VARCHAR AS away_team_name
,  away_join.team_abbr::VARCHAR AS away_team_abbr
, home_win::INT
, home_score::INT
, away_score::INT
, home_wins::INT
, away_wins::INT
, away_losses::INT
, home_losses::INT
, home_pct::FLOAT
, away_pct::FLOAT
, home_pitcher_id
, away_pitcher_id
, home_pitcher_fullname
, away_pitcher_fullname
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
FROM {{ source('mlb_api', 'schedule_endpoint') }} a
LEFT JOIN team_seed AS home_join ON a.home_id = home_join.team_id
LEFT JOIN team_seed AS away_join ON a.away_id = away_join.team_id
