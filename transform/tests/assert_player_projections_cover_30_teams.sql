-- Each projection file must include players from all 30 teams. A partial league would
-- quietly change which teams are being compared.

select
    season,
    source,
    player_type,
    count(distinct team_id) as teams
from {{ ref('player_projections') }}
group by season, source, player_type
having count(distinct team_id) <> 30
