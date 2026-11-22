{#
  Hand-collected preseason projections and betting win totals, with Opening Day attached.

  Projections are for a full 162-game schedule, so projected_win_pct divides by 162 for every
  season. For 2020 these are the pre-pandemic projections for the season that never happened;
  compare them with 2020 results with care.
#}

with projections as (

    select * from {{ ref('stg_projections__preseason_wins') }}

),

calendar as (

    select * from {{ ref('stg_mlb__seasons') }}

),

teams as (

    select team_id, team_abbr, team_name from {{ ref('teams') }}

)

select
    projections.season,
    projections.team_id,
    teams.team_abbr,
    projections.source,
    projections.kind,
    projections.as_of_date,
    calendar.regular_season_start_date                              as opening_day,
    calendar.regular_season_start_date - projections.as_of_date     as days_before_opening_day,
    projections.projected_wins,
    projections.projected_wins / 162.0                              as projected_win_pct,
    projections.source_url,
    projections.notes
from projections
inner join teams
    on projections.team_id = teams.team_id
left join calendar
    on calendar.season = projections.season
