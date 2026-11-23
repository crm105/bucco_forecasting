-- A player projection downloaded after Opening Day could contain information about actual
-- results. Rows with no recorded download date are not caught here (they cannot be shown to be
-- late); see assert_player_projections_dated, which warns about them.

select
    season,
    source,
    player_type,
    as_of_date,
    opening_day
from {{ ref('player_projections') }}
where opening_day is not null
  and as_of_date > opening_day
group by season, source, player_type, as_of_date, opening_day
