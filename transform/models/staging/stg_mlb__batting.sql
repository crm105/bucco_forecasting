{#
  Batting lines from the MLB Stats API, typed. One row per player per season (full-season
  totals across teams). Rates are computed later from these counts.
#}

select
    cast(season as integer)         as season,
    cast(mlbam_id as bigint)        as mlbam_id,
    trim(player_name)               as player_name,
    cast(last_team_id as integer)   as last_team_id,
    cast(num_teams as integer)      as num_teams,
    cast(games as integer)          as games,
    cast(pa as integer)             as pa,
    cast(ab as integer)             as ab,
    cast(h as integer)              as h,
    cast(h - doubles - triples - hr as integer) as singles,
    cast(doubles as integer)        as doubles,
    cast(triples as integer)        as triples,
    cast(hr as integer)             as hr,
    cast(bb as integer)             as bb,
    cast(ibb as integer)            as ibb,
    cast(hbp as integer)            as hbp,
    cast(so as integer)             as so,
    cast(sf as integer)             as sf,
    cast(sh as integer)             as sh,
    cast(ci as integer)             as ci,
    cast(sb as integer)             as sb,
    cast(cs as integer)             as cs,
    cast(gidp as integer)           as gidp,
    cast(ground_outs as integer)    as ground_outs,
    cast(air_outs as integer)       as air_outs,
    cast(runs as integer)           as runs,
    cast(rbi as integer)            as rbi
from {{ source('mlb_api', 'batting') }}
