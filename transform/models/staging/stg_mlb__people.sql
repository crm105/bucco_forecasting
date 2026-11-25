{#
  Player details from the MLB Stats API /people endpoint, typed. One row per player who has a
  batting or pitching line since 2000.
#}

select
    cast(mlbam_id as bigint)                        as mlbam_id,
    trim(player_name)                               as player_name,
    cast(nullif(birth_date, '') as date)            as birth_date,
    upper(nullif(trim(bats), ''))                   as bats,
    upper(nullif(trim(throws), ''))                 as throws,
    upper(nullif(trim(primary_position), ''))       as primary_position,
    cast(nullif(mlb_debut_date, '') as date)        as mlb_debut_date,
    cast(nullif(last_played_date, '') as date)      as last_played_date
from {{ source('mlb_api', 'people') }}
