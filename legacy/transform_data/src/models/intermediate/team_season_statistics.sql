{{ config(materialized='table') }}

WITH previous_season_win_totals AS (
    SELECT
    season
    , team_id
    , SUM(team_win) AS total_wins
    , SUM(1-team_win) AS total_losses
    , SUM(team_win::FLOAT)/ (SUM(team_win) + SUM(1-team_win)) AS win_pct
    FROM {{ ref('int__games_by_team') }}
    WHERE gametype = 'R'
    GROUP BY season, team_id
)

, payrolls AS (
    SELECT
    season
    , payroll."Team" AS team_abbr
    , payroll."Total AAV"::BIGINT AS total_team_payroll
    , payroll."Avg Age"::FLOAT AS avg_team_age
    FROM {{ source('spotrac', 'payroll_tables') }} payroll
)

, final AS (
SELECT
payrolls.season
, team_ids.team_id
, team_ids.team_name
, team_ids.team_abbr
, payrolls.total_team_payroll
, (total_team_payroll - AVG(total_team_payroll) OVER(partition by payrolls.season))/
  stddev(total_team_payroll) OVER(partition by payrolls.season) AS z_score_payroll
, payrolls.avg_team_age
, CASE WHEN previous_season_win_totals.season = 2021 THEN (162 * win_pct)
    ELSE previous_season_win_totals.total_wins END AS team_total_wins_last_season

FROM {{ ref('team_ids') }}  team_ids
LEFT JOIN payrolls USING(team_abbr)
LEFT JOIN previous_season_win_totals
 ON team_ids.team_id = previous_season_win_totals.team_id
 AND payrolls.season = (previous_season_win_totals.season + 1)
)

SELECT * FROM final
