{#
  Inputs for forecasting: one row per team per season to be forecast.

  Every column describes the PRIOR season only (season - 1), so a row is safe to use before
  the target season starts. Nothing from the target season appears here; this is what keeps
  the backtest honest.

  The spine is every team-season in team_seasons, plus one extra row per team for the season
  after the latest completed one. That extra row is the upcoming season (2027 once 2026 is
  complete), where the actual results do not exist yet.
#}

with seasons as (

    select * from {{ ref('team_seasons') }}

),

spine as (

    select season, team_id from seasons

    union

    select season + 1 as season, team_id
    from seasons
    where season = (select max(season) from seasons)

),

calendar as (

    select * from {{ ref('stg_mlb__seasons') }}

),

teams as (

    select team_id, team_abbr, team_name from {{ ref('teams') }}

)

select
    spine.season,
    spine.team_id,
    teams.team_abbr,
    teams.team_name,
    calendar.regular_season_start_date                  as opening_day,
    prior.season is not null                            as has_prior_season,
    prior.season                                        as prior_season,
    prior.wins                                          as prior_wins,
    prior.losses                                        as prior_losses,
    prior.games_played                                  as prior_games_played,
    prior.win_pct                                       as prior_win_pct,
    prior.runs_scored                                   as prior_runs_scored,
    prior.runs_allowed                                  as prior_runs_allowed,
    prior.run_diff                                      as prior_run_diff,
    prior.is_shortened_season                           as prior_season_shortened,
    prior.made_playoffs                                 as prior_made_playoffs
from spine
inner join teams
    on spine.team_id = teams.team_id
left join seasons as prior
    on prior.team_id = spine.team_id
   and prior.season = spine.season - 1
left join calendar
    on calendar.season = spine.season
