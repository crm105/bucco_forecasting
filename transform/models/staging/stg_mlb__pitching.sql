{#
  Pitching lines from the MLB Stats API, typed. One row per player per season (full-season
  totals across teams). `ip` is true innings (outs / 3), not the 69.2-style display value.
#}

select
    cast(season as integer)         as season,
    cast(mlbam_id as bigint)        as mlbam_id,
    trim(player_name)               as player_name,
    cast(last_team_id as integer)   as last_team_id,
    cast(num_teams as integer)      as num_teams,
    cast(games as integer)          as games,
    cast(gs as integer)             as gs,
    cast(games_finished as integer) as games_finished,
    cast(complete_games as integer) as complete_games,
    cast(saves as integer)          as saves,
    cast(holds as integer)          as holds,
    cast(wins as integer)           as wins,
    cast(losses as integer)         as losses,
    cast(outs as integer)           as outs,
    outs / 3.0                      as ip,
    cast(bf as integer)             as bf,
    cast(h as integer)              as h,
    cast(doubles as integer)        as doubles,
    cast(triples as integer)        as triples,
    cast(hr as integer)             as hr,
    cast(bb as integer)             as bb,
    cast(ibb as integer)            as ibb,
    cast(hbp as integer)            as hbp,
    cast(so as integer)             as so,
    cast(sf as integer)             as sf,
    cast(sh as integer)             as sh,
    cast(runs as integer)           as runs,
    cast(er as integer)             as er,
    cast(wp as integer)             as wp,
    cast(balks as integer)          as balks,
    cast(ground_outs as integer)    as ground_outs,
    cast(air_outs as integer)       as air_outs
from {{ source('mlb_api', 'pitching') }}
