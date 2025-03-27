{{ config(materialized='table') }}

WITH games_by_pitcher AS (
    SELECT
    season
    , gamepk
    , gamedt
    , home_pitcher_id AS pitcher_id
    , home_pitcher_fullname AS pitcher_fullname
    , home_pitcher_innings_pitched_game AS pitcher_innings_pitched_game
    , home_pitcher_earned_runs_game AS pitcher_earned_runs_game
    FROM {{ ref('stg__schedule') }}
    WHERE gametype = 'R'
    UNION
    SELECT
    season
    , gamepk
    , gamedt
    , away_pitcher_id AS pitcher_id
    , away_pitcher_fullname AS pitcher_fullname
    , away_pitcher_innings_pitched_game AS pitcher_innings_pitched_game
    , away_pitcher_earned_runs_game AS pitcher_earned_runs_game
    FROM {{ ref('stg__schedule') }}
    WHERE gametype = 'R'
)

, cumulative_stats AS (
SELECT
season
, pitcher_id
, pitcher_fullname
, gamepk
, gamedt
, SUM(pitcher_innings_pitched_game) OVER(PARTITION BY pitcher_id, season ORDER BY gamedt ASC
 ROWS BETWEEN UNBOUNDED PRECEDING AND 1 PRECEDING) AS cumulative_pitcher_innings_season
, SUM(pitcher_earned_runs_game) OVER(PARTITION BY pitcher_id, season ORDER BY gamedt ASC
 ROWS BETWEEN UNBOUNDED PRECEDING AND 1 PRECEDING) AS cumulative_pitcher_earned_runs_season

 , SUM(pitcher_innings_pitched_game) OVER(PARTITION BY pitcher_id ORDER BY gamedt ASC
 ROWS BETWEEN UNBOUNDED PRECEDING AND 1 PRECEDING) AS cumulative_pitcher_innings_career
, SUM(pitcher_earned_runs_game) OVER(PARTITION BY pitcher_id ORDER BY gamedt ASC
 ROWS BETWEEN UNBOUNDED PRECEDING AND 1 PRECEDING) AS cumulative_pitcher_earned_runs_career
 FROM games_by_pitcher
)

, previous_season_stats AS (
SELECT
(season + 1) AS season
, pitcher_id
, SUM(pitcher_innings_pitched_game)  AS previous_season_innings_pitched
, SUM(pitcher_earned_runs_game) AS previous_season_earned_runs
FROM games_by_pitcher
GROUP BY season, pitcher_id
)

, final AS (
    SELECT *
    , 9 * cumulative_pitcher_earned_runs_season::FLOAT/NULLIF(cumulative_pitcher_innings_season,0) AS pitcher_era_season
    , 9 * previous_season_earned_runs::FLOAT/NULLIF(previous_season_innings_pitched,0) AS pitcher_era_previous_season
    , 9 * cumulative_pitcher_earned_runs_career::FLOAT/NULLIF(cumulative_pitcher_innings_career,0) AS pitcher_era_career
    FROM cumulative_stats
    LEFT JOIN previous_season_stats USING (pitcher_id, season)
)

SELECT * FROM final
