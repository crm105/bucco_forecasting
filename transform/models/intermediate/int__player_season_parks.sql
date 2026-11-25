{#
  How much a player's home parks inflated his stats, one row per player, season and role
  (`batter`, `pitcher`): for each kind of event, the average over the teams he played for of
  (1 + the park factor for his side mix) / 2, since about half his games were at home. The side
  mix is his share of plate appearances batting left (batters) or of batters faced who batted
  left (pitchers), from int__player_sides, applied to park_factors_by_side. Teams are weighted by
  games in the field (DH included) for batters and innings pitched for pitchers; a player with
  no fielding rows (pinch hitters) gets his last team. Dividing his counts by these gives his
  season in a neutral park.
#}

{% set components = ['singles', 'doubles', 'triples', 'hr', 'ubb', 'hbp', 'so'] %}

with fielding as (

    select
        season,
        mlbam_id,
        team_id,
        case when position = 'P' then 'pitcher' else 'batter' end      as role,
        sum(case when position = 'P' then innings else games end)       as weight
    from {{ ref('stg_mlb__fielding') }}
    group by 1, 2, 3, 4

),

players as (

    select season, mlbam_id, 'batter' as role, last_team_id from {{ ref('stg_mlb__batting') }}
    union all
    select season, mlbam_id, 'pitcher' as role, last_team_id from {{ ref('stg_mlb__pitching') }}

),

shares as (

    -- teams from the field where he has any; otherwise his last team
    select players.season, players.mlbam_id, players.role,
           coalesce(fielding.team_id, players.last_team_id)                      as team_id,
           coalesce(fielding.weight / nullif(sum(fielding.weight) over (
               partition by players.season, players.mlbam_id, players.role), 0), 1.0) as share
    from players
    left join fielding
        on fielding.season = players.season
        and fielding.mlbam_id = players.mlbam_id
        and fielding.role = players.role
        and fielding.weight > 0

),

sided as (

    select
        shares.*,
        coalesce(sides.left_share, 0.5)                                 as left_share
    from shares
    left join {{ ref('int__player_sides') }} as sides
        on sides.season = shares.season
        and sides.mlbam_id = shares.mlbam_id
        and sides.role = shares.role

)

select
    sided.season,
    sided.mlbam_id,
    sided.role,
    count(*)                                                            as teams,
    max(sided.left_share)                                               as left_share,
    {% for c in components %}
    sum(sided.share * (1 + coalesce(
            sided.left_share * pf_l.pf_{{ c }} + (1 - sided.left_share) * pf_r.pf_{{ c }}, 1.0)) / 2)
        / sum(sided.share)                                              as m_{{ c }}{{ ',' if not loop.last }}
    {% endfor %}
from sided
left join {{ ref('park_factors_by_side') }} as pf_l
    on pf_l.season = sided.season
    and pf_l.team_id = sided.team_id
    and pf_l.side = 'L'
left join {{ ref('park_factors_by_side') }} as pf_r
    on pf_r.season = sided.season
    and pf_r.team_id = sided.team_id
    and pf_r.side = 'R'
group by sided.season, sided.mlbam_id, sided.role
