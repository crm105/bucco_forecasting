{#
  Minor-league batting by player, level and season, valued against the player's own league:
  batting runs and stolen-base runs above that league's average, with that season's MLB run
  values (wOBA weights and scale, run values of a steal and a caught stealing). Taking each
  league's own average out removes league environments (the Pacific Coast League's offense, for
  one). The Mexican League, classed Triple-A until 2020 but not affiliated with MLB teams, is
  left out. A line whose PA are all bunts or catcher's interference has no wOBA: 0 batting runs.
  The input to major-league equivalents (bucco.models.milb).
#}

with lines as (

    select
        b.*,
        b.h - b.doubles - b.triples - b.hr                         as singles,
        b.ab + b.bb - b.ibb + b.sf + b.hbp                         as woba_pa,
        l.w_ubb * (b.bb - b.ibb) + l.w_hbp * b.hbp
            + l.w_single * (b.h - b.doubles - b.triples - b.hr)
            + l.w_double * b.doubles + l.w_triple * b.triples + l.w_hr * b.hr  as woba_num,
        l.woba_scale,
        b.sb * l.run_sb + b.cs * l.run_cs                          as sb_runs_raw,
        (b.h - b.doubles - b.triples - b.hr) + b.bb - b.ibb + b.hbp  as sb_opportunities
    from {{ ref('stg_mlb__minor_batting') }} b
    join {{ ref('league_seasons') }} l on l.season = b.season
    where b.league_name <> 'MEX'

),

leagues as (

    select
        season,
        league_id,
        sum(woba_num) / nullif(sum(woba_pa), 0)                    as league_woba,
        sum(sb_runs_raw) / nullif(sum(sb_opportunities), 0)        as league_sb_per_opportunity
    from lines
    group by season, league_id

)

select
    x.season,
    x.mlbam_id,
    x.player_name,
    x.age,
    x.sport_id,
    x.level,
    x.league_id,
    x.league_name,
    x.pa,
    x.woba_num / nullif(x.woba_pa, 0)                              as woba,
    g.league_woba,
    coalesce((x.woba_num / nullif(x.woba_pa, 0) - g.league_woba) / x.woba_scale * x.pa, 0)
                                                                   as batting_runs,
    x.sb_runs_raw - g.league_sb_per_opportunity * x.sb_opportunities          as sb_runs,
    coalesce((x.woba_num / nullif(x.woba_pa, 0) - g.league_woba) / x.woba_scale * x.pa, 0)
        + x.sb_runs_raw - g.league_sb_per_opportunity * x.sb_opportunities    as off_runs
from lines x
join leagues g using (season, league_id)
where x.pa > 0
