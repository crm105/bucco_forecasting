WITH season_win_totals AS (
    SELECT
    season
    , team_id 
    , SUM(team_win) AS total_wins 
    FROM {{ ref('int__games_by_team') }}
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
, season_win_totals.total_wins AS team_total_wins_last_season

FROM {{ ref('team_ids') }}  team_ids
LEFT JOIN {{ source('spotrac', 'payroll_tables') }} payroll
ON team_abbr = payroll."Team"
LEFT JOIN season_win_totals 
 ON team_ids.team_id = season_win_totals.team_id
 AND payroll.season = (season_win_totals.season - 1)
)

SELECT * FROM final
--ToDo: Do salaries represent a leakage problem? I.E.- a 
