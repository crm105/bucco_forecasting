{#
  Statcast fielding run value from Baseball Savant, typed. One row per season and fielder: runs
  saved (positive) or cost, total and by part, and the outs he was on the field for at each
  position (catcher outs_2 to right field outs_9). Framing for 2016-2017 comes from Savant's
  older framing leaderboard (framing_source).
#}

select
    cast(season as integer)                             as season,
    cast(mlbam_id as bigint)                            as mlbam_id,
    cast(total_runs as double)                          as fielding_runs,
    cast(inf_of_runs as double)                         as inf_of_runs,
    cast(range_runs as double)                          as range_runs,
    cast(arm_runs as double)                            as arm_runs,
    cast(dp_runs as double)                             as dp_runs,
    cast(fielding_runs_prevented_on_rec1b as double)    as receiving_1b_runs,
    cast(catching_runs as double)                       as catching_runs,
    cast(framing_runs as double)                        as framing_runs,
    cast(throwing_runs as double)                       as throwing_runs,
    cast(blocking_runs as double)                       as blocking_runs,
    cast(outs_total as integer)                         as outs_total,
    cast(outs_2 as integer)                             as outs_c,
    cast(outs_3 as integer)                             as outs_1b,
    cast(outs_4 as integer)                             as outs_2b,
    cast(outs_5 as integer)                             as outs_3b,
    cast(outs_6 as integer)                             as outs_ss,
    cast(outs_7 as integer)                             as outs_lf,
    cast(outs_8 as integer)                             as outs_cf,
    cast(outs_9 as integer)                             as outs_rf,
    framing_source
from {{ source('savant', 'fielding') }}
