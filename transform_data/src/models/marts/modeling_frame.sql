/*
ToDo: Modify extract to produce all lower cols
*/

{{ config(materialized='table') }}

SELECT 
"gamePk"
, home_win
, home_wins
, home_losses
, home_pct
, away_wins
, away_losses
, away_pct
, CASE WHEN winner = 134 THEN 1 ELSE 0 END AS pirates_win
FROM staging.game_results
