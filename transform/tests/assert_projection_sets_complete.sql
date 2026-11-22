-- A projection set (one source, one date, one season) must cover all 30 teams. Scoring a
-- model on a partial league would quietly change which teams are being compared.

select
    season,
    source,
    as_of_date,
    count(distinct team_id) as teams
from {{ ref('external_projections') }}
group by season, source, as_of_date
having count(distinct team_id) <> 30
