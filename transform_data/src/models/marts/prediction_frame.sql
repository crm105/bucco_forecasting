
{{ config(materialized='table') }}

WITH final AS (
SELECT 
a.gamepk
, a.gamedate
, a.gamedt
, home_join.total_team_wins AS total_home_team_wins_todate
, home_join.total_team_losses AS total_home_team_losses_todate
, home_join.team_win_pct AS home_team_win_percentage_todate
, away_join.total_team_wins AS total_away_team_wins_todate
, away_join.total_team_losses AS total_away_team_losses_todate
, away_join.team_win_pct AS away_team_win_percentage_todate
, b.home_pitcher_era_pregame
, b.away_pitcher_era_pregame
, b.home_pitcher_innings_pitched_pregame
, b.away_pitcher_innings_pitched_pregame
, home_join.total_team_runs_scored AS total_home_team_runs_scored_todate
, home_join.total_team_runs_allowed AS total_home_team_runs_allowed_todate
, home_join.run_differential_per_game AS home_team_run_differential_per_game
, home_join.runs_per_game AS home_team_runs_per_game
, home_join.runs_allowed_per_game AS home_team_runs_allowed_per_game
, home_join.pythagorean_win_percentage AS home_team_pythagorean_win_percentage
, home_join.total_games_played AS total_home_team_games_played_season
, away_join.total_team_runs_scored AS total_away_team_runs_scored_todate
, away_join.total_team_runs_allowed AS total_away_team_runs_allowed_todate
, away_join.run_differential_per_game AS away_team_run_differential_per_game
, away_join.runs_per_game AS away_team_runs_per_game
, away_join.runs_allowed_per_game AS away_team_runs_allowed_per_game
, away_join.pythagorean_win_percentage AS away_team_pythagorean_win_percentage
, away_join.total_games_played AS total_away_team_games_played_season
, CURRENT_TIMESTAMP AS last_updated_datetime

FROM {{ ref('stg__schedule') }} a
LEFT JOIN {{ ref('int__pitcher_gametime_era') }} b USING(gamepk)
LEFT JOIN {{ ref('int__games_by_team') }} home_join
    ON a.gamepk = home_join.gamepk
    AND a.home_id = home_join.team_id
    AND home_join.home_game = 1
LEFT JOIN {{ ref('int__games_by_team') }} away_join
    ON a.gamepk = away_join.gamepk
    AND  a.away_id = away_join.team_id
    AND away_join.home_game = 0
WHERE a.gamedt::timestamptz > CURRENT_TIMESTAMP
)

SELECT * FROM final


