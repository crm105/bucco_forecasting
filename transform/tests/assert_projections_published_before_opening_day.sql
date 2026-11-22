-- A projection dated after Opening Day could contain information about actual results and
-- would make a model look better in the backtest than it can ever be in real use.
-- Same-day is allowed (Opening Day morning, before first pitch).

select
    season,
    source,
    as_of_date,
    opening_day
from {{ ref('external_projections') }}
where opening_day is not null
  and as_of_date > opening_day
