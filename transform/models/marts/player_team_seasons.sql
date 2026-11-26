{#
  What each player actually did for each team in a season, as batter and as pitcher: playing time
  (PA or innings) and our approximate park-neutral WAR (`war_approx_neutral`), with the off_runs
  or pitching runs behind it. A player who played for several teams has his season split by his
  share of games in the field (batters, DH included) or innings pitched (pitchers) with each; one
  with no fielding rows goes to his last team. The actual side of the projection evaluation
  (bucco.evaluate.projection_report) and of team_war_seasons.
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

    select season, mlbam_id, last_team_id, 'batting' as part, pa as playing_time,
           war_approx_neutral as war, off_runs_neutral as runs
    from {{ ref('player_batting_seasons') }}
    where not is_pitcher
    union all
    select season, mlbam_id, last_team_id, 'pitching' as part, outs / 3.0 as playing_time,
           war_approx_neutral as war, pitching_runs_neutral as runs
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
        players.runs
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
    runs * share                                                               as runs
from shared
where team_id is not null
