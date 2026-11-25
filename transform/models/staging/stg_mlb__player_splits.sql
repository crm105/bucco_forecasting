{#
  Players' home/road and batter-side splits, typed. One row per season, player, group and
  split, with singles and unintentional walks.
#}

select
    cast(season as integer)                         as season,
    cast(mlbam_id as bigint)                        as mlbam_id,
    "group"                                         as player_group,
    split,
    cast(last_team_id as integer)                   as last_team_id,
    cast(num_teams as integer)                      as num_teams,
    cast(pa as integer)                             as pa,
    cast(runs as integer)                           as runs,
    cast(h - doubles - triples - hr as integer)     as singles,
    cast(doubles as integer)                        as doubles,
    cast(triples as integer)                        as triples,
    cast(hr as integer)                             as hr,
    cast(bb - ibb as integer)                       as ubb,
    cast(hbp as integer)                            as hbp,
    cast(so as integer)                             as so
from {{ source('mlb_api', 'player_splits') }}
