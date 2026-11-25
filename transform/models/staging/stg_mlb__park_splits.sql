{#
  Team lines in home and road games, typed. One row per season, team, site and side.
  `ubb` is unintentional walks and `singles` hits minus extra-base hits.
#}

select
    cast(season as integer)                         as season,
    cast(team_id as integer)                        as team_id,
    site,
    side,
    cast(games as integer)                          as games,
    cast(pa as integer)                             as pa,
    cast(runs as integer)                           as runs,
    cast(h - doubles - triples - hr as integer)     as singles,
    cast(doubles as integer)                        as doubles,
    cast(triples as integer)                        as triples,
    cast(hr as integer)                             as hr,
    cast(bb - ibb as integer)                       as ubb,
    cast(hbp as integer)                            as hbp,
    cast(so as integer)                             as so
from {{ source('mlb_api', 'park_splits') }}
