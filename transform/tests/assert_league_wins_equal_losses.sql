-- Every game has one winner and one loser, so league wins must equal league losses in a
-- complete season. A mismatch points to missing or corrupted team rows.

select
    season,
    sum(wins)   as total_wins,
    sum(losses) as total_losses
from {{ ref('team_seasons') }}
group by season
having sum(wins) <> sum(losses)
