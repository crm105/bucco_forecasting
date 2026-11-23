{#
  Fielding splits from the MLB Stats API, typed. One row per season, team, player and position.
  Pitchers are position P and designated hitters are position DH.
#}

select
    cast(season as integer)         as season,
    cast(team_id as integer)        as team_id,
    cast(mlbam_id as bigint)        as mlbam_id,
    trim(player_name)               as player_name,
    upper(trim(position))           as position,
    cast(games as integer)          as games,
    cast(games_started as integer)  as games_started,
    cast(innings as double)         as innings
from {{ source('mlb_api', 'fielding') }}
