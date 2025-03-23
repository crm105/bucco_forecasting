--ToDO: Move addition heavy logic into a macro
SELECT 
home_id AS team_id
--ToDo: Move this to a staging model
--ToDo: Cast gamedate to date
, DATE_PART('year', gamedate::DATE) AS season 
, gamepk
, gamedate
, gamedt
--ToDo: Come up with better name than "postgame" given ambiguity as to when ERA reflects 
, away_pitcher_era_postgame
, home_pitcher_era_postgame
, home_pitcher_innings_pitched_postgame
, away_pitcher_innings_pitched_postgame
, COALESCE(away_pitcher_earned_runs_game, 0) AS away_pitcher_earned_runs_game
, COALESCE(away_pitcher_innings_pitched_game, 0) away_pitcher_innings_pitched_game
, COALESCE(home_pitcher_earned_runs_game, 0) AS home_pitcher_earned_runs_game
, COALESCE(home_pitcher_innings_pitched_game, 0) home_pitcher_innings_pitched_game
, home_pitcher_innings_pitched_postgame - home_pitcher_innings_pitched_game AS home_pitcher_innings_pitched_pregame
, away_pitcher_innings_pitched_postgame - away_pitcher_innings_pitched_game AS away_pitcher_innings_pitched_pregame
, away_pitcher_earned_runs_postgame - away_pitcher_earned_runs_game AS away_pitcher_earned_runs_pregame
, home_pitcher_earned_runs_postgame - home_pitcher_earned_runs_game AS home_pitcher_earned_runs_pregame
, 9 * (home_pitcher_earned_runs_postgame - home_pitcher_earned_runs_game )/NULLIF((home_pitcher_innings_pitched_postgame - home_pitcher_innings_pitched_game), 0) AS home_pitcher_era_pregame
, 9 * (away_pitcher_earned_runs_postgame - away_pitcher_earned_runs_game)/NULLIF((away_pitcher_innings_pitched_postgame - away_pitcher_innings_pitched_game),0) AS away_pitcher_era_pregame

FROM {{ ref('stg__schedule') }}