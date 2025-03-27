{{ config(materialized='table') }}

WITH season_win_totals AS (
    SELECT
    season + 1 AS season
    , team_id
    , SUM(team_win) AS total_wins
    , SUM(1-team_win) AS total_losses
    , SUM(team_win)::FLOAT/ (SUM(team_win) + SUM(1-team_win)) AS win_pct
    FROM {{ ref('int__games_by_team') }}
    WHERE gametype = 'R'
    GROUP BY season, team_id
)

, final AS (
SELECT
payroll.season
, team_ids.team_id
, team_ids.team_name
, team_ids.team_abbr
, payroll."Total AAV"::FLOAT AS total_team_payroll
, payroll."Avg Age"::FLOAT AS avg_team_age
, CASE WHEN season_win_totals.season = 2021 THEN (162 * win_pct)
    ELSE season_win_totals.total_wins END AS team_total_wins_last_season

FROM {{ ref('team_ids') }}  team_ids
LEFT JOIN {{ source('spotrac', 'payroll_tables') }} payroll
ON team_abbr = payroll."Team"
LEFT JOIN season_win_totals
 ON team_ids.team_id = season_win_totals.team_id
 AND payroll.season = (season_win_totals.season)
)

SELECT * FROM final
