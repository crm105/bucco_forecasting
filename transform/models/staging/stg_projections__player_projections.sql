{#
  Hand-downloaded player projections (batters and pitchers), typed and with text trimmed.
  One row per player per file. Batter-only columns are null for pitchers and the reverse.
  Empty until player projection CSVs are added.
#}

select
    cast(season as integer)                         as season,
    lower(trim(source))                             as source,
    lower(trim(player_type))                        as player_type,
    cast(nullif(trim(as_of_date), '') as date)      as as_of_date,
    trim(fangraphs_id)                              as fangraphs_id,
    try_cast(trim(mlbam_id) as bigint)              as mlbam_id,
    trim(player_name)                               as player_name,
    upper(trim(team_abbr))                          as source_team_abbr,
    cast(team_id as integer)                        as team_id,
    cast(games as double)                           as games,
    cast(plate_appearances as double)               as plate_appearances,
    cast(games_started as double)                   as games_started,
    cast(innings_pitched as double)                 as innings_pitched,
    cast(war as double)                             as war,
    cast(home_runs as double)                       as home_runs,
    cast(stolen_bases as double)                    as stolen_bases,
    cast(avg as double)                             as avg,
    cast(obp as double)                             as obp,
    cast(slg as double)                             as slg,
    cast(woba as double)                            as woba,
    cast(wrc_plus as double)                        as wrc_plus,
    cast(off_runs as double)                        as off_runs,
    cast(def_runs as double)                        as def_runs,
    cast(bsr_runs as double)                        as bsr_runs,
    cast(fld_runs as double)                        as fld_runs,
    cast(era as double)                             as era,
    cast(fip as double)                             as fip,
    cast(strikeouts as double)                      as strikeouts,
    cast(walks as double)                           as walks,
    cast(saves as double)                           as saves,
    nullif(trim(source_url), '')                    as source_url,
    nullif(trim(notes), '')                         as notes,
    source_file
from {{ source('manual_projections', 'player_projections') }}
