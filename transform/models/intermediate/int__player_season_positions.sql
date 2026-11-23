{#
  One row per player per season: the position he played most that season, plus the context
  needed to judge how settled it is. Summed across teams, so a player traded mid-season is
  one row.

  Primary position = the position with the most games (DH counts as a position, pitching
  as P). Ties go to innings, then games started, then the position code, so the answer
  never changes between runs.

  Pitchers are split into starters and relievers by how many of their games they started
  (a starter started at least `starter_share_cutoff` of them).
#}

{% set starter_share_cutoff = 0.5 %}

with by_position as (

    select
        season,
        mlbam_id,
        position,
        sum(games)          as games,
        sum(games_started)  as games_started,
        sum(innings)        as innings,
        max(player_name)    as player_name
    from {{ ref('stg_mlb__fielding') }}
    group by season, mlbam_id, position

),

ranked as (

    select
        *,
        row_number() over (
            partition by season, mlbam_id
            order by games desc, innings desc, games_started desc, position
        ) as position_rank
    from by_position

),

totals as (

    select
        season,
        mlbam_id,
        sum(games)                                              as total_position_games,
        count(*)                                                as positions_played,
        sum(case when position = 'P' then games else 0 end)     as pitching_games,
        sum(case when position = 'P' then games_started else 0 end) as pitching_starts,
        sum(case when position <> 'P' then games else 0 end)    as non_pitching_games
    from by_position
    group by season, mlbam_id

)

select
    ranked.season,
    ranked.mlbam_id,
    ranked.player_name,
    ranked.position                                             as primary_position,
    case
        when ranked.position = 'C'                      then 'C'
        when ranked.position in ('1B', '2B', '3B', 'SS') then 'IF'
        when ranked.position in ('LF', 'CF', 'RF')      then 'OF'
        when ranked.position = 'DH'                     then 'DH'
        when totals.pitching_games > 0
             and totals.pitching_starts * 1.0 / totals.pitching_games >= {{ starter_share_cutoff }}
                                                        then 'SP'
        else 'RP'
    end                                                         as position_group,
    ranked.games                                                as primary_games,
    totals.total_position_games,
    ranked.games * 1.0 / nullif(totals.total_position_games, 0) as primary_share,
    totals.positions_played,
    totals.pitching_games,
    totals.pitching_starts,
    totals.non_pitching_games,
    -- both pitched and hit/fielded a meaningful amount (Ohtani-type players)
    (totals.pitching_games >= 10 and totals.non_pitching_games >= 30) as is_two_way
from ranked
inner join totals
    on ranked.season = totals.season
    and ranked.mlbam_id = totals.mlbam_id
where ranked.position_rank = 1
