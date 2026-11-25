{#
  Park factors for left- and right-side batters, one row per team, season and side (`L`, `R`).

  Team splits cannot be crossed with batter side, so the difference between sides is measured
  from each team's own hitters (who bat at home and on the road; visiting hitters' lines at this
  park are not available): for left-handed (or right-handed) hitters who played the whole season
  for the team, the log of home rate over road rate, minus the same for all its hitters. Switch
  hitters and traded players are left out. That difference is centered each season, pooled over
  the season and up to {{ var('park_side_window') - 1 }} before it at the same ballpark (side
  differences come from fence geometry, which rarely changes, and one team's hitters give little
  data a season), shrunk toward 0 like park_factors, and applied on top of the all-batter factor:

      pf_side = pf (park_factors) x exp(shrunk, pooled side difference)

  The true spread of side differences (tau2) is the average product of a park's differences in
  seasons 1 to {{ var('park_side_window') - 1 }} apart, from seasons up to
  {{ var('park_prior_last_season') }} only: back-to-back seasons alone are too few to measure a
  spread this small (about 3% for home runs).
#}

{% set components = ['singles', 'doubles', 'triples', 'hr', 'ubb', 'hbp', 'so', 'runs'] %}

with splits as (

    select s.*, people.bats
    from {{ ref('stg_mlb__player_splits') }} as s
    left join {{ ref('stg_mlb__people') }} as people
        on people.mlbam_id = s.mlbam_id
    where s.player_group = 'batting'
      and s.split in ('home', 'road')
      and s.num_teams = 1

),

by_group as (

    select
        season,
        last_team_id                                                    as team_id,
        side,
        sum(case when split = 'home' then pa else 0 end)                as home_pa,
        sum(case when split = 'road' then pa else 0 end)                as road_pa,
        {% for c in components %}
        sum(case when split = 'home' then {{ c }} else 0 end)           as home_{{ c }},
        sum(case when split = 'road' then {{ c }} else 0 end)           as road_{{ c }}{{ ',' if not loop.last }}
        {% endfor %}
    from (
        select *, bats as side from splits where bats in ('L', 'R')
        union all
        select *, 'all' as side from splits
    )
    group by 1, 2, 3

),

ratios as (

    select
        season,
        team_id,
        side,
        home_pa,
        {% for c in components %}
        ln(((home_{{ c }} + 0.5) / home_pa) / ((road_{{ c }} + 0.5) / road_pa)) as lr_{{ c }}{{ ',' if not loop.last }}
        {% endfor %}
    from by_group
    where home_pa > 0 and road_pa > 0

),

diffs as (

    select
        side.season,
        side.team_id,
        side.side,
        side.home_pa,
        parks.venue_id,
        parks.venue_share >= {{ var('park_min_venue_share') }}             as poolable,
        {% for c in components %}
        (side.lr_{{ c }} - team.lr_{{ c }})
            - avg(side.lr_{{ c }} - team.lr_{{ c }}) over (partition by side.season, side.side)
                                                                        as d_{{ c }}{{ ',' if not loop.last }}
        {% endfor %}
    from ratios as side
    inner join ratios as team
        on team.season = side.season
        and team.team_id = side.team_id
        and team.side = 'all'
    inner join {{ ref('int__team_home_parks') }} as parks
        on parks.season = side.season
        and parks.team_id = side.team_id
    where side.side in ('L', 'R')

),

prior_seasons as (

    select * from diffs where season <= {{ var('park_prior_last_season') }} and poolable

),

prior as (

    select
        avg(cur.home_pa)                                                as pa_ref,
        {% for c in components %}
        greatest(avg(cur.d_{{ c }} * prev.d_{{ c }}), 0)                as tau2_{{ c }},
        var_samp(cur.d_{{ c }})                                         as v1_{{ c }}{{ ',' if not loop.last }}
        {% endfor %}
    from prior_seasons as cur
    inner join prior_seasons as prev
        on prev.team_id = cur.team_id
        and prev.side = cur.side
        and prev.season between cur.season - {{ var('park_side_window') - 1 }} and cur.season - 1
        and prev.venue_id = cur.venue_id

),

pooled as (

    select
        cur.season,
        cur.team_id,
        cur.side,
        count(past.season)                                              as seasons_pooled,
        coalesce(sum(past.home_pa), 0)                                  as home_pa_pooled,
        {% for c in components %}
        sum(past.d_{{ c }} * past.home_pa) / nullif(sum(past.home_pa), 0) as d_{{ c }}{{ ',' if not loop.last }}
        {% endfor %}
    from diffs as cur
    left join diffs as past
        on past.team_id = cur.team_id
        and past.side = cur.side
        and past.venue_id = cur.venue_id
        and past.season between cur.season - {{ var('park_side_window') - 1 }} and cur.season
        and past.poolable
    group by cur.season, cur.team_id, cur.side

),

shrunk as (

    select
        pooled.*,
        {% for c in components %}
        coalesce(pooled.d_{{ c }} * prior.tau2_{{ c }}
            / nullif(prior.tau2_{{ c }} + greatest(prior.v1_{{ c }} - prior.tau2_{{ c }}, 0)
                     * prior.pa_ref / nullif(pooled.home_pa_pooled, 0), 0), 0)
                                                                        as shift_{{ c }}{{ ',' if not loop.last }}
        {% endfor %}
    from pooled
    cross join prior

)

select
    pf.season,
    pf.team_id,
    sides.side,
    pf.venue_id,
    pf.venue_name,
    coalesce(shrunk.seasons_pooled, 0)                                  as seasons_pooled,
    {% for c in components %}
    pf.pf_{{ c }} * exp(coalesce(shrunk.shift_{{ c }}, 0))              as pf_{{ c }}{{ ',' if not loop.last }}
    {% endfor %}
from {{ ref('park_factors') }} as pf
cross join (values ('L'), ('R')) as sides(side)
left join shrunk
    on shrunk.season = pf.season
    and shrunk.team_id = pf.team_id
    and shrunk.side = sides.side
