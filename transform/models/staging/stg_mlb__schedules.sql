{#
  Regular-season schedules from the MLB Stats API, typed. One row per game; cancelled listings
  (games moved to a new id, or never made up) are dropped.
#}

select
    cast(season as integer)         as season,
    cast(game_pk as bigint)         as game_pk,
    cast(game_date as date)         as game_date,
    cast(home_team_id as integer)   as home_team_id,
    cast(away_team_id as integer)   as away_team_id,
    status
from {{ source('mlb_api', 'schedules') }}
where status <> 'Cancelled'
