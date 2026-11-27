{#
  What each player actually did for each team in a season, as batter and as pitcher: playing time
  (PA or innings) and our approximate park-neutral WAR (`war_approx_neutral`), with the off_runs
  or pitching runs behind it. A player who played for several teams has his season split by his
  share of games in the field (batters, DH included) or innings pitched (pitchers) with each; one
  with no fielding rows goes to his last team. The actual side of the projection evaluation
  (bucco.evaluate.projection_report) and of team_war_seasons.

  From 2016 a batter's WAR includes his measured fielding: Statcast fielding run value
  (stg_savant__fielding, framing included) over the season's runs per win, split like the rest.
  Before 2016 there is no measured fielding (fielding_runs is null) and WAR is offense plus
  positional adjustment only.
#}

with fielding as (

    select
        season,
        mlbam_id,
        team_id,
        case when position = 'P' then 'pitching' else 'batting' end           as part,
        sum(case when position = 'P' then innings else games end)             as weight
    from {{ ref('stg_mlb__fielding') }}
    group by 1, 2, 3, 4

),

players as (

    select b.season, b.mlbam_id, b.last_team_id, 'batting' as part, b.pa as playing_time,
           b.war_approx_neutral + coalesce(f.fielding_runs / lg.runs_per_win, 0)  as war,
           b.off_runs_neutral as runs, f.fielding_runs
    from {{ ref('player_batting_seasons') }} as b
    inner join {{ ref('league_seasons') }} as lg on lg.season = b.season
    left join {{ ref('stg_savant__fielding') }} as f
        on f.season = b.season and f.mlbam_id = b.mlbam_id
    where not b.is_pitcher
    union all
    select season, mlbam_id, last_team_id, 'pitching' as part, outs / 3.0 as playing_time,
           war_approx_neutral as war, pitching_runs_neutral as runs,
           cast(null as double) as fielding_runs
    from {{ ref('player_pitching_seasons') }}

),

shared as (

    select
        players.season,
        players.mlbam_id,
        players.part,
        coalesce(fielding.team_id, players.last_team_id)                       as team_id,
        coalesce(fielding.weight / nullif(sum(fielding.weight) over (
            partition by players.season, players.mlbam_id, players.part), 0), 1.0) as share,
        players.playing_time,
        players.war,
        players.runs,
        players.fielding_runs
    from players
    left join fielding
        on fielding.season = players.season
        and fielding.mlbam_id = players.mlbam_id
        and fielding.part = players.part
        and fielding.weight > 0

)

select
    season,
    mlbam_id,
    team_id,
    part,
    share,
    playing_time * share                                                       as playing_time,
    war * share                                                                as war,
    runs * share                                                               as runs,
    fielding_runs * share                                                      as fielding_runs
from shared
where team_id is not null
