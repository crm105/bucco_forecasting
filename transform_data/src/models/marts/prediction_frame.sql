
{{ config(materialized='table') }}

SELECT 
gamepk
, gamedate::DATE
, gamedt::timestamptz AS game_timestamp 
, gametype
, home_id
, away_id
, home_wins
, home_losses
, home_pct
, away_wins
, away_losses
, away_pct
FROM {{ source('mlb_api', 'schedule_endpoint') }}
WHERE gamedt::timestamptz > CURRENT_TIMESTAMP

