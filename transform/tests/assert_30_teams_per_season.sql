-- Every season since the league reached 30 teams (1998) must have all 30. A smaller count
-- means a partial or failed download. Returns the bad seasons; the test passes when empty.

select
    season,
    count(*) as teams
from {{ ref('team_seasons') }}
where season >= 1998
group by season
having count(*) <> 30
