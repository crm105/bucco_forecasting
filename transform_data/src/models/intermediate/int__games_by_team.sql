{{ config(materialized='table') }}

WITH team_games AS (
SELECT 
home_id AS team_id
, season
, gamepk
, gamedate
, gamedt
, gametype
, away_id AS opponent
, game_status
, home_win AS team_win
, home_score AS team_score
, away_score AS opponent_score
--ToDo: Deal with leakage in total team wins and win percentage
, 1 AS home_game
, last_updated_datetime
FROM {{ ref('stg__schedule') }}
UNION
SELECT
away_id AS team_id
, season
, gamepk
, gamedate
, gamedt
, gametype
, home_id AS opponent
, game_status
, 1-home_win AS team_win
, away_score AS team_score
, home_score AS opponent_score
, 0 AS home_game 
, last_updated_datetime
FROM {{ ref('stg__schedule') }}
ORDER BY team_id, gamedt
)

, cumulative_game_stats AS (
    SELECT
    team_id
    , gamepk
    , gamedt
    , gametype
    , ROW_NUMBER() OVER(PARTITION BY team_id, gametype, season ORDER BY gamedt ) - 1  AS total_games_played
    , SUM(team_win) OVER (PARTITION BY team_id, gametype, season ORDER BY gamedt ASC ROWS BETWEEN UNBOUNDED PRECEDING AND 1 PRECEDING) AS total_team_wins
    , SUM(1-team_win) OVER (PARTITION BY team_id, gametype, season ORDER BY gamedt ASC ROWS BETWEEN UNBOUNDED PRECEDING AND 1 PRECEDING) AS total_team_losses
    , SUM(team_score) OVER (PARTITION BY team_id, gametype, season ORDER BY gamedt ASC ROWS BETWEEN UNBOUNDED PRECEDING AND 1 PRECEDING) AS total_team_runs_scored
    , SUM(opponent_score) OVER (PARTITION BY team_id, gametype, season ORDER BY gamedt ASC ROWS BETWEEN UNBOUNDED PRECEDING AND 1 PRECEDING) AS total_team_runs_allowed
 
    FROM team_games
)

, final AS (
    SELECT
    team_games.*
    , cumulative_game_stats.total_games_played
    , cumulative_game_stats.total_team_wins
    , cumulative_game_stats.total_team_losses
    , cumulative_game_stats.total_team_wins::FLOAT / NULLIF( cumulative_game_stats.total_games_played, 0) AS team_win_pct
    , cumulative_game_stats.total_team_runs_scored
    , cumulative_game_stats.total_team_runs_allowed
    , cumulative_game_stats.total_team_runs_scored - cumulative_game_stats.total_team_runs_allowed   AS run_differential
    , cumulative_game_stats.total_team_runs_scored::FLOAT / cumulative_game_stats.total_games_played AS runs_per_game
    , cumulative_game_stats.total_team_runs_allowed::FLOAT / cumulative_game_stats.total_games_played AS runs_allowed_per_game
    , (cumulative_game_stats.total_team_runs_scored - cumulative_game_stats.total_team_runs_allowed)::FLOAT/ NULLIF(cumulative_game_stats.total_games_played,0) AS run_differential_per_game
    , 1/(1 + (cumulative_game_stats.total_team_runs_allowed::FLOAT/NULLIF(cumulative_game_stats.total_team_runs_scored,0))^2 ) AS pythagorean_win_percentage
    FROM team_games
    LEFT JOIN cumulative_game_stats USING(team_id, gamepk, gamedt, gametype)
)

SELECT * FROM final

--https://www.mlb.com/glossary/advanced-stats/pythagorean-winning-percentage