
{{ config(materialized='table') }}

SELECT 
gamepk
, home_win
, home_wins
, home_losses
, home_pct
, away_wins
, away_losses
, away_pct
, CASE WHEN winner = 134 THEN 1 ELSE 0 END AS pirates_win
FROM {{ source('mlb_api', 'schedule_endpoint') }}
