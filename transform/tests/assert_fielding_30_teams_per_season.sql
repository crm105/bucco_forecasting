-- Each season of fielding data must cover all 30 teams. A partial league would quietly change
-- which players have a prior-season position.

select
    season,
    count(distinct team_id) as teams
from {{ ref('stg_mlb__fielding') }}
group by season
having count(distinct team_id) <> 30
