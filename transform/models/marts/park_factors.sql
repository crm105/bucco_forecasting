{#
  Park factors: how much each team's home park raises (> 1) or lowers (< 1) each kind of event
  per plate appearance, one row per team per season from 2000. Used to put players' seasons on a
  neutral-park footing (player_batting_seasons, player_pitching_seasons).

  1. Raw, per season: the rate in the team's home games (both teams batting) over the rate in its
     road games, on the log scale, centered each season so the average park is neutral.
  2. Trailing pool: the season and the {{ var('park_window') - 1 }} before it, at the same
     ballpark (int__team_home_parks), counting only seasons with at least
     {{ var('park_min_venue_share') }} of home games there, weighted by home PA. Never a later
     season, so a factor can be used for any forecast after its season.
  3. Shrunk toward neutral by how much of the pooled ratio is signal: weight = tau2 /
     (tau2 + noise). tau2 (the true spread of parks) is how strongly a park's single-season
     ratios carry over to its next season; noise is the rest of the single-season variance,
     scaled down by the pooled PA. Both come from seasons up to {{ var('park_prior_last_season') }}
     only, before the first backtest season.

  The factor is the full home-versus-road effect; a player gets about half of it, since about
  half his games are at home.
#}

{% set components = ['singles', 'doubles', 'triples', 'hr', 'ubb', 'hbp', 'so', 'runs'] %}

with splits as (

    select * from {{ ref('stg_mlb__park_splits') }}

),

parks as (

    select * from {{ ref('int__team_home_parks') }}

),

by_site as (

    select
        season,
        team_id,
        sum(case when site = 'home' then pa else 0 end)                 as home_pa,
        sum(case when site = 'road' then pa else 0 end)                as road_pa,
        {% for c in components %}
        sum(case when site = 'home' then {{ c }} else 0 end)            as home_{{ c }},
        sum(case when site = 'road' then {{ c }} else 0 end)            as road_{{ c }}{{ ',' if not loop.last }}
        {% endfor %}
    from splits
    group by season, team_id

),

raw as (

    select
        season,
        team_id,
        home_pa,
        {% for c in components %}
        ln(((home_{{ c }} + 0.5) / home_pa) / ((road_{{ c }} + 0.5) / road_pa))
            as lr_{{ c }}{{ ',' if not loop.last }}
        {% endfor %}
    from by_site
    where home_pa > 0 and road_pa > 0

),

centered as (

    select
        raw.season,
        raw.team_id,
        raw.home_pa,
        parks.venue_id,
        parks.venue_name,
        parks.venue_share,
        parks.venue_share >= {{ var('park_min_venue_share') }}             as poolable,
        {% for c in components %}
        raw.lr_{{ c }} - avg(raw.lr_{{ c }}) over (partition by raw.season) as lr_{{ c }}{{ ',' if not loop.last }}
        {% endfor %}
    from raw
    inner join parks
        on parks.season = raw.season
        and parks.team_id = raw.team_id

),

prior_seasons as (

    select * from centered
    where season <= {{ var('park_prior_last_season') }} and poolable

),

prior as (

    select
        avg(cur.home_pa)                                                as pa_ref,
        {% for c in components %}
        greatest(avg(cur.lr_{{ c }} * prev.lr_{{ c }}), 0)              as tau2_{{ c }},
        var_samp(cur.lr_{{ c }})                                        as v1_{{ c }}{{ ',' if not loop.last }}
        {% endfor %}
    from prior_seasons as cur
    inner join prior_seasons as prev
        on prev.team_id = cur.team_id
        and prev.season = cur.season - 1
        and prev.venue_id = cur.venue_id

),

pooled as (

    select
        cur.season,
        cur.team_id,
        count(past.season)                                              as seasons_pooled,
        coalesce(sum(past.home_pa), 0)                                  as home_pa_pooled,
        {% for c in components %}
        sum(past.lr_{{ c }} * past.home_pa) / nullif(sum(past.home_pa), 0) as lr_{{ c }}{{ ',' if not loop.last }}
        {% endfor %}
    from centered as cur
    left join centered as past
        on past.team_id = cur.team_id
        and past.venue_id = cur.venue_id
        and past.season between cur.season - {{ var('park_window') - 1 }} and cur.season
        and past.poolable
    group by cur.season, cur.team_id

)

select
    centered.season,
    centered.team_id,
    centered.venue_id,
    centered.venue_name,
    centered.venue_share,
    pooled.seasons_pooled,
    pooled.home_pa_pooled,
    {% for c in components %}
    exp(centered.lr_{{ c }})                                            as raw_{{ c }},
    prior.tau2_{{ c }} / nullif(prior.tau2_{{ c }} + greatest(prior.v1_{{ c }} - prior.tau2_{{ c }}, 0)
        * prior.pa_ref / nullif(pooled.home_pa_pooled, 0), 0)          as weight_{{ c }},
    coalesce(exp(pooled.lr_{{ c }} * prior.tau2_{{ c }}
        / nullif(prior.tau2_{{ c }} + greatest(prior.v1_{{ c }} - prior.tau2_{{ c }}, 0)
                 * prior.pa_ref / nullif(pooled.home_pa_pooled, 0), 0)), 1.0)
                                                                        as pf_{{ c }}{{ ',' if not loop.last }}
    {% endfor %}
from centered
inner join pooled
    on pooled.season = centered.season
    and pooled.team_id = centered.team_id
cross join prior
