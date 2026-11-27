{#
  Statcast season leaderboards from Baseball Savant, typed. One row per season, player and type
  (batter: his own plate appearances; pitcher: hitters' plate appearances against him). Rates
  are percentages as Savant gives them; speeds in miles per hour, sprint speed in feet per second.
#}

select
    cast(season as integer)                 as season,
    cast(mlbam_id as bigint)                as mlbam_id,
    player_type,
    cast(pa as integer)                     as pa,
    cast(k_percent as double)               as k_percent,
    cast(bb_percent as double)              as bb_percent,
    cast(xwoba as double)                   as xwoba,
    cast(exit_velocity_avg as double)       as exit_velocity_avg,
    cast(launch_angle_avg as double)        as launch_angle_avg,
    cast(barrel_batted_rate as double)      as barrel_batted_rate,
    cast(hard_hit_percent as double)        as hard_hit_percent,
    cast(sweet_spot_percent as double)      as sweet_spot_percent,
    cast(whiff_percent as double)           as whiff_percent,
    cast(oz_swing_percent as double)        as oz_swing_percent,
    cast(z_swing_percent as double)         as z_swing_percent,
    cast(iz_contact_percent as double)      as iz_contact_percent,
    cast(sprint_speed as double)            as sprint_speed,
    cast(ff_speed as double)                as ff_speed,
    cast(si_speed as double)                as si_speed,
    cast(fc_speed as double)                as fc_speed,
    cast(sl_speed as double)                as sl_speed
from {{ source('savant', 'players') }}
