{#
  Each organization's minor-league depth going into a season: every player who played for one of
  its affiliates the season before (one row per target season and player), as a batter or a
  pitcher (whichever he did more of: batters faced against plate appearances). A player who
  played for several organizations' affiliates is listed with the one at his highest level
  (Triple-A first), then the one he played most for. Known before the season starts; misses
  winter moves (releases, minor-league free agents, trades, the Rule 5 draft). Our own
  projections add these players to the Opening Day 40-man rosters (marcel_rosters "mlb_org").
#}

with lines as (

    select season, mlbam_id, team_id, sport_id, pa as volume, 'batter' as kind
    from {{ ref('stg_mlb__minor_batting') }}
    union all
    select season, mlbam_id, team_id, sport_id, bf as volume, 'pitcher' as kind
    from {{ ref('stg_mlb__minor_pitching') }}

),

with_org as (

    select lines.*, aff.parent_org_id
    from lines
    inner join {{ ref('stg_mlb__minor_affiliates') }} as aff
        on aff.season = lines.season
        and aff.team_id = lines.team_id
    -- MLB organizations only (the Mexican League, classed Triple-A until 2020, is its own)
    where aff.parent_org_id in (select team_id from {{ ref('teams') }})

),

kinds as (

    select
        season,
        mlbam_id,
        case when sum(case when kind = 'pitcher' then volume else 0 end)
                  >= sum(case when kind = 'batter' then volume else 0 end)
             then 'pitcher' else 'batter' end                          as player_type
    from with_org
    group by 1, 2

),

orgs as (

    select
        season,
        mlbam_id,
        parent_org_id,
        min(sport_id)                                                   as top_sport_id,
        sum(volume)                                                     as volume,
        row_number() over (partition by season, mlbam_id
                           order by min(sport_id), sum(volume) desc, parent_org_id) as pick
    from with_org
    group by 1, 2, 3

)

select
    orgs.season + 1                                                     as season,
    orgs.mlbam_id,
    orgs.parent_org_id                                                  as team_id,
    kinds.player_type,
    orgs.top_sport_id                                                   as last_sport_id
from orgs
inner join kinds using (season, mlbam_id)
where orgs.pick = 1
