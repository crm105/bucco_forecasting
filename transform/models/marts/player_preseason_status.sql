{#
  Each player's status on his team's Opening Day 40-man roster, one row per season and player:
  what a forecaster knows about injuries when the season starts. il_group is `il_60` (60-day
  injured list), `il_short` (7-, 10- or 15-day) or `none` (active, in the minors, anything else).
  A player on two teams' snapshots (moved between their Opening Days) keeps the injured-list row,
  else the later snapshot. `position` is his roster position (`P` pitcher, `TWP` two-way), which
  our own projections use as the preseason rosters (bucco.models.player_inputs.marcel_rosters).
#}

with ranked as (

    select
        season,
        mlbam_id,
        team_id,
        snapshot_date,
        position,
        status_code,
        status_description,
        case
            when status_code = 'D60' then 'il_60'
            when status_code in ('D7', 'D10', 'D15') then 'il_short'
            else 'none'
        end as il_group,
        row_number() over (
            partition by season, mlbam_id
            order by (status_code like 'D%') desc, snapshot_date desc, team_id
        ) as pick
    from {{ ref('stg_mlb__rosters') }}

)

select season, mlbam_id, team_id, snapshot_date, position, status_code, status_description,
    il_group
from ranked
where pick = 1
