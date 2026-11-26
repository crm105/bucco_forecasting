{#
  Minor-league pitching lines from the MLB Stats API, typed. One row per season, level and pitcher.
#}

select
    cast(season as integer)      as season,
    cast(sport_id as integer)    as sport_id,
    level,
    cast(league_id as integer)   as league_id,
    league_name,
    cast(team_id as integer)     as team_id,
    cast(mlbam_id as bigint)     as mlbam_id,
    trim(player_name)            as player_name,
    cast(age as integer)         as age,
    cast(outs as integer)        as outs,
    cast(bf as integer)          as bf,
    cast(hr as integer)          as hr,
    cast(bb as integer)          as bb,
    cast(ibb as integer)         as ibb,
    cast(hbp as integer)         as hbp,
    cast(so as integer)          as so,
    cast(gs as integer)          as gs,
    cast(games as integer)       as games
from {{ source('mlb_api', 'minor_pitching') }}
