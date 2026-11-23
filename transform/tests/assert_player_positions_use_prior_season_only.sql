-- A position for season S must come from season S - 1, never from S itself or later. This is
-- what keeps the position data from leaking the forecast year into a backtest.

select
    season,
    prior_season,
    mlbam_id
from {{ ref('player_positions') }}
where prior_season <> season - 1
