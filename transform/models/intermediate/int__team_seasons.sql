{#
  One row per team per completed season, from the history start season on.

  A season counts as complete once its regular season ended at least
  `season_complete_buffer_days` ago, so a half-played season can never appear as a result.
#}

with standings as (

    select * from {{ ref('stg_mlb__standings') }}

),

calendar as (

    select * from {{ ref('stg_mlb__seasons') }}

),

teams as (

    select team_id, team_abbr, team_name from {{ ref('teams') }}

)

select
    standings.season,
    standings.team_id,
    teams.team_abbr,
    teams.team_name,
    standings.league_id,
    standings.division_id,
    standings.games_played,
    standings.wins,
    standings.losses,
    standings.wins::double / nullif(standings.wins + standings.losses, 0) as win_pct,
    standings.runs_scored,
    standings.runs_allowed,
    standings.runs_scored - standings.runs_allowed                        as run_diff,
    standings.games_played < {{ var('full_season_min_games') }}           as is_shortened_season,
    standings.clinch_indicator is not null                                as made_playoffs,
    coalesce(standings.clinch_indicator in ('y', 'z'), false)             as won_division
from standings
inner join calendar
    on standings.season = calendar.season
inner join teams
    on standings.team_id = teams.team_id
where standings.season >= {{ var('history_start_season') }}
  and calendar.regular_season_end_date
      + interval '{{ var("season_complete_buffer_days") }} days' <= current_date
