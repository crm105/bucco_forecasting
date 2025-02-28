
{{ config(materialized='table') }}

SELECT 
gamepk
, gamedate
, gametype
, home_id
, away_id
, home_wins
, home_losses
, home_pct
, away_wins
, away_losses
, away_pct
FROM staging.scheduled_games
