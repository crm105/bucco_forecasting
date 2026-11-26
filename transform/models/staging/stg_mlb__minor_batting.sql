{#
  Minor-league batting lines from the MLB Stats API, typed. One row per season, level and player.
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
    cast(pa as integer)          as pa,
    cast(ab as integer)          as ab,
    cast(h as integer)           as h,
    cast(doubles as integer)     as doubles,
    cast(triples as integer)     as triples,
    cast(hr as integer)          as hr,
    cast(bb as integer)          as bb,
    cast(ibb as integer)         as ibb,
    cast(hbp as integer)         as hbp,
    cast(so as integer)          as so,
    cast(sf as integer)          as sf,
    cast(sh as integer)          as sh,
    cast(sb as integer)          as sb,
    cast(cs as integer)          as cs
from {{ source('mlb_api', 'minor_batting') }}
