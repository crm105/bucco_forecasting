{#
  Minor-league pitching by pitcher, level and season, valued against his own league: FIP-based
  runs above that league's average, (league FIP - FIP) x IP / 9, the same scale as MLB
  pitching_runs. With each league's own average the FIP constant cancels and league environments
  (the Pacific Coast League's offense, for one) drop out. The unaffiliated Mexican League,
  classed Triple-A until 2020, is left out. The input to major-league equivalents for pitchers
  (bucco.models.milb).
#}

with lines as (

    select
        *,
        outs / 3.0                                     as ip,
        13.0 * hr + 3.0 * (bb + hbp) - 2.0 * so        as fip_num
    from {{ ref('stg_mlb__minor_pitching') }}
    where league_name <> 'MEX' and outs > 0

),

leagues as (

    select season, league_id, sum(fip_num) / sum(ip) as league_fip_core
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
    x.outs,
    x.ip,
    x.bf,
    x.gs,
    x.games,
    x.fip_num / x.ip - g.league_fip_core                          as fip_minus_league,
    (g.league_fip_core - x.fip_num / x.ip) * x.ip / 9.0           as pitching_runs
from lines x
join leagues g using (season, league_id)
