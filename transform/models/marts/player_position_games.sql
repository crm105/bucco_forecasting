{#
  Games at each position in the PRIOR season, one row per player per position. A row for
  season S describes season S - 1, so it can be used to forecast S without peeking at S.

  This is the detail behind player_positions: it shows which positions a player can cover, not
  just his main one. Games are summed across teams. A player who played two positions in the same
  game counts for both, so shares are of position games, not of games played.
#}

with by_position as (

    select
        season,
        mlbam_id,
        position,
        sum(games)          as games,
        sum(games_started)  as games_started,
        sum(innings)        as innings
    from {{ ref('stg_mlb__fielding') }}
    group by season, mlbam_id, position

)

select
    season + 1                                                          as season,
    season                                                              as prior_season,
    mlbam_id,
    position,
    games,
    games_started,
    innings,
    games * 1.0 / nullif(sum(games) over (partition by season, mlbam_id), 0) as share_of_position_games
from by_position
where season + 1 > {{ var('history_start_season') }}
