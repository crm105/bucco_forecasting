select
    cast(season_id as integer)                      as season,
    cast(regular_season_start_date as date)         as regular_season_start_date,
    cast(regular_season_end_date as date)           as regular_season_end_date,
    cast(post_season_start_date as date)            as post_season_start_date,
    cast(post_season_end_date as date)              as post_season_end_date,
    cast(has_wildcard as boolean)                   as has_wildcard
from {{ source('mlb_api', 'seasons') }}
