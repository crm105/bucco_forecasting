{#
  Each player's listed position for a season, determined from the PRIOR season.

  A row for season S describes where a player played in season S - 1, so it can be used when
  forecasting S without peeking at S itself. There is one row per player who played in the
  majors in S - 1; a player with no row (a rookie or minor leaguer) has no prior-season
  position yet. The newest row is for the season after the latest completed one, which is the
  season being forecast.

  position_group is C, IF, OF, DH, SP or RP. DH is its own group. See int__player_season_positions
  for how the primary position and the starter/reliever split are chosen.
#}

select
    season + 1                  as season,
    season                      as prior_season,
    mlbam_id,
    player_name,
    primary_position,
    position_group,
    primary_games,
    total_position_games,
    primary_share,
    positions_played,
    pitching_games,
    pitching_starts,
    is_two_way
from {{ ref('int__player_season_positions') }}
where season + 1 > {{ var('history_start_season') }}
