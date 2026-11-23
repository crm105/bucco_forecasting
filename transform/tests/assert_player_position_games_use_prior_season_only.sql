-- Games by position for season S must come from season S - 1, never S or later.

select
    season,
    prior_season,
    mlbam_id
from {{ ref('player_position_games') }}
where prior_season <> season - 1
