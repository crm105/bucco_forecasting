
{{ config(materialized='table') }}

WITH final AS (
SELECT
a.season
, a.gamedate
, a.gamepk
, a.home_team_abbr
, a.away_team_abbr
, a.home_win
, home_join.total_team_wins AS total_home_team_wins_todate
, home_join.total_team_losses AS total_home_team_losses_todate
, home_join.team_win_pct AS home_team_win_percentage_todate
, away_join.total_team_wins AS total_away_team_wins_todate
, away_join.total_team_losses AS total_away_team_losses_todate
, away_join.team_win_pct AS away_team_win_percentage_todate
, home_join.team_win_pct - away_join.team_win_pct AS win_pct_diff
, home_pitcher.pitcher_era_season AS home_pitcher_era_season
, away_pitcher.pitcher_era_season AS away_pitcher_era_season
, home_pitcher.pitcher_era_previous_season AS home_pitcher_era_previous_season
, away_pitcher.pitcher_era_previous_season AS away_pitcher_era_previous_season
, home_pitcher.pitcher_era_career AS home_pitcher_era_career
, away_pitcher.pitcher_era_career AS away_pitcher_era_career
, home_pitcher.cumulative_pitcher_innings_season AS home_pitcher_innings_pitched_season
, away_pitcher.cumulative_pitcher_innings_season AS away_pitcher_innings_pitched_season
, home_pitcher.cumulative_pitcher_innings_career AS home_pitcher_innings_pitched_career
, away_pitcher.cumulative_pitcher_innings_career AS away_pitcher_innings_putched_career
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
, away_season_stats.total_team_payroll AS away_team_payroll
, home_season_stats.total_team_payroll AS home_team_payroll
, (home_season_stats.total_team_payroll - away_season_stats.total_team_payroll) AS team_payroll_diff
, home_season_stats.team_total_wins_last_season AS total_home_team_wins_last_season
, home_season_stats.avg_team_age AS avg_home_team_age
, away_season_stats.team_total_wins_last_season AS total_away_team_wins_last_season
, away_season_stats.avg_team_age AS avg_away_team_age
, (home_season_stats.avg_team_age - away_season_stats.avg_team_age) AS avg_team_age_diff

, timezone('utc', now())AS last_updated_datetime

FROM {{ ref('stg__schedule') }} a
LEFT JOIN {{ ref('int__pitcher_statistics') }} home_pitcher
   ON a.gamepk = home_pitcher.gamepk
   AND a.home_pitcher_id = home_pitcher.pitcher_id
LEFT JOIN {{ ref('int__pitcher_statistics') }} away_pitcher
   ON a.gamepk = away_pitcher.gamepk
   AND a.away_pitcher_id = away_pitcher.pitcher_id
LEFT JOIN {{ ref('int__games_by_team') }} home_join
    ON a.gamepk = home_join.gamepk
    AND a.home_id = home_join.team_id
    AND home_join.home_game = 1
LEFT JOIN {{ ref('int__games_by_team') }} away_join
    ON a.gamepk = away_join.gamepk
    AND  a.away_id = away_join.team_id
    AND away_join.home_game = 0
LEFT JOIN {{ ref('team_season_statistics')}} home_season_stats
   ON a.season = home_season_stats.season
   AND a.home_id = home_season_stats.team_id
LEFT JOIN {{ ref('team_season_statistics')}} away_season_stats
   ON a.season = away_season_stats.season
   AND a.away_id = away_season_stats.team_id

WHERE a.game_status = 'F' AND a.gametype = 'R'
)

SELECT * FROM final
