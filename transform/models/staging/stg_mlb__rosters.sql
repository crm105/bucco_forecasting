{#
  Opening Day 40-man rosters from the MLB Stats API, typed. One row per season, team and player.
#}

select
    cast(season as integer)          as season,
    cast(team_id as integer)         as team_id,
    cast(snapshot_date as date)      as snapshot_date,
    cast(mlbam_id as bigint)         as mlbam_id,
    trim(player_name)                as player_name,
    upper(trim(position))            as position,
    upper(trim(status_code))         as status_code,
    trim(status_description)         as status_description
from {{ source('mlb_api', 'rosters') }}
