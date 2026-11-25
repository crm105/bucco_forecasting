{#
  Each player's batter-side mix per season: for batters, the share of his plate appearances
  batting left (switch hitters fall in between); for pitchers, the share of the batters he faced
  who batted left. From the batter-side splits, falling back to how he bats (L = 1, R = 0,
  S = 0.5) or 0.5 when the splits are missing.
#}

with sides as (

    select
        season,
        mlbam_id,
        player_group,
        sum(case when split in ('bat_left', 'vs_left') then pa else 0 end) * 1.0
            / nullif(sum(case when split in ('bat_left', 'bat_right', 'vs_left', 'vs_right')
                              then pa else 0 end), 0)                       as left_share
    from {{ ref('stg_mlb__player_splits') }}
    where split in ('bat_left', 'bat_right', 'vs_left', 'vs_right')
    group by 1, 2, 3

),

players as (

    select season, mlbam_id, 'batting' as player_group from {{ ref('stg_mlb__batting') }}
    union all
    select season, mlbam_id, 'pitching' as player_group from {{ ref('stg_mlb__pitching') }}

)

select
    players.season,
    players.mlbam_id,
    case players.player_group when 'batting' then 'batter' else 'pitcher' end as role,
    coalesce(sides.left_share,
             case when players.player_group = 'batting' then
                 case people.bats when 'L' then 1.0 when 'R' then 0.0 else 0.5 end
             end, 0.5)                                                       as left_share
from players
left join sides
    on sides.season = players.season
    and sides.mlbam_id = players.mlbam_id
    and sides.player_group = players.player_group
left join {{ ref('stg_mlb__people') }} as people
    on people.mlbam_id = players.mlbam_id
