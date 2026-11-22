-- Every team has played since 1998, so after the first season in the window every
-- forecast row should have a prior season. A gap means a missing season file.

select
    season,
    team_id
from {{ ref('team_season_features') }}
where season > (select min(season) from {{ ref('team_seasons') }})
  and not has_prior_season
