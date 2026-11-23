{#
  Hand-downloaded player projections with the current team abbreviation and Opening Day
  attached. One row per player per source, player type and season.

  These are independent player projections, not a roster. Each team's rows add up to roughly
  four times a real team's plate appearances and include many minor leaguers with negative WAR,
  so do NOT sum war by team and treat it as a team forecast. Allocating playing time per team
  is the job of the roster-based models (rung 5a).

  as_of_date is null until the download date is entered in _player_downloads.csv. Models must
  not use rows with a null date, because they cannot be shown to pre-date Opening Day.
#}

with players as (

    select * from {{ ref('stg_projections__player_projections') }}

),

calendar as (

    select * from {{ ref('stg_mlb__seasons') }}

),

teams as (

    select team_id, team_abbr from {{ ref('teams') }}

)

select
    players.season,
    players.source,
    players.player_type,
    players.as_of_date,
    calendar.regular_season_start_date                              as opening_day,
    calendar.regular_season_start_date - players.as_of_date         as days_before_opening_day,
    players.fangraphs_id,
    players.mlbam_id,
    players.player_name,
    players.team_id,
    teams.team_abbr,
    players.source_team_abbr,
    players.games,
    players.plate_appearances,
    players.games_started,
    players.innings_pitched,
    players.war,
    players.home_runs,
    players.stolen_bases,
    players.avg,
    players.obp,
    players.slg,
    players.woba,
    players.wrc_plus,
    players.off_runs,
    players.def_runs,
    players.bsr_runs,
    players.fld_runs,
    players.era,
    players.fip,
    players.strikeouts,
    players.walks,
    players.saves,
    players.source_url,
    players.notes
from players
inner join teams
    on players.team_id = teams.team_id
left join calendar
    on calendar.season = players.season
