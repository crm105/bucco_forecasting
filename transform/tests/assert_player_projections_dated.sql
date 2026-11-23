{{ config(severity='warn') }}

-- Every player projection file needs a download date in data/manual/projections/_player_downloads.csv
-- so it can be checked against Opening Day. Models must not use files that fail this test.

select
    season,
    source,
    player_type,
    count(*) as undated_rows
from {{ ref('player_projections') }}
where as_of_date is null
group by season, source, player_type
