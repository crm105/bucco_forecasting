/*
ToDo: Modify extract to produce all lower cols
*/

{{ config(materialized='table') }}

SELECT 
"gamePk"
, CASE WHEN winner = 134 THEN 1 ELSE 0 END AS pirates_win
FROM staging.game_results
