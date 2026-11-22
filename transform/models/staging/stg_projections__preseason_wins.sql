select
    cast(season as integer)                         as season,
    lower(trim(source))                             as source,
    lower(trim(kind))                               as kind,
    cast(as_of_date as date)                        as as_of_date,
    cast(team_id as integer)                        as team_id,
    cast(projected_wins as double)                  as projected_wins,
    nullif(trim(source_url), '')                    as source_url,
    nullif(trim(notes), '')                         as notes,
    source_file
from {{ source('manual_projections', 'preseason_projections') }}
