-- A park factor for season S may pool S and earlier seasons only. Recompute the latest season
-- each factor could have pooled and fail if it is after S. (The pool joins on
-- past.season between S - window + 1 and S; this guards against that being loosened.)

select pf.season, pf.team_id
from {{ ref('park_factors') }} as pf
where pf.seasons_pooled > (
    select count(*)
    from {{ ref('int__team_home_parks') }} as hp
    where hp.team_id = pf.team_id
      and hp.venue_id = pf.venue_id
      and hp.season between pf.season - {{ var('park_window') - 1 }} and pf.season
      and hp.venue_share >= {{ var('park_min_venue_share') }}
)
