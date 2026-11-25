-- Every input in a projection frame must come from the three seasons before the target season,
-- never the target season itself or later. y1_ is season - 1, y2_ is season - 2, y3_ is
-- season - 3. This is what keeps our own player projections from leaking into a backtest.

select 'batter' as frame, season, mlbam_id
from {{ ref('batter_projection_frame') }}
where y1_season <> season - 1 or y2_season <> season - 2 or y3_season <> season - 3
   or (y1_pa = 0 and y2_pa = 0 and y3_pa = 0)

union all

select 'pitcher' as frame, season, mlbam_id
from {{ ref('pitcher_projection_frame') }}
where y1_season <> season - 1 or y2_season <> season - 2 or y3_season <> season - 3
   or (y1_bf = 0 and y2_bf = 0 and y3_bf = 0)
