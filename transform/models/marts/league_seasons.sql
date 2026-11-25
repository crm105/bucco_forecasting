{#
  League run environment and value constants, one row per season. These turn a player's counts
  into runs and wins (player_batting_seasons, player_pitching_seasons) on a scale close to
  FanGraphs', from MLB Stats API counts alone.

  wOBA: the relative run values of each event are held fixed (FanGraphs' 2019 weights divided by
  that year's wOBA scale); each season they are rescaled so league wOBA equals league OBP, which
  is how FanGraphs scales them. Holding the relative values fixed costs little accuracy: they move
  by a few percent across run environments.

  Replacement level: as at FanGraphs, the league's WAR adds up to 1,000 per 2,430 games, 570 for
  batters and 430 for pitchers. Each season's replacement runs per PA and per inning are set so
  that this holds. 2020 (60 games) gets 1,000 x 898 / 2,430.

  Pitchers, as at FanGraphs, have a lower replacement level as starters than as relievers:
  {{ sp_replacement_wins }} wins per 9 innings below average for a pure starter and
  {{ rp_replacement_wins }} for a pure reliever, mixed by the share of his games he started, all
  scaled each season so pitchers still add up to 430 WAR (`pitching_replacement_scale`). The
  single `pitching_replacement_runs_per_ip` (all pitchers alike) is kept for reference.

  Runs per win follows FanGraphs: 9 x (league runs per inning) x 1.5 + 3.
#}

{% set rv = {'ubb': 0.596, 'hbp': 0.621, 'single': 0.752, 'double': 1.052,
             'triple': 1.322, 'hr': 1.677} %}
{% set run_sb = 0.2 %}
{% set batting_war_per_game = 570 / 2430 %}
{% set pitching_war_per_game = 430 / 2430 %}
{% set sp_replacement_wins = 0.12 %}
{% set rp_replacement_wins = 0.03 %}

with bat as (

    select
        season,
        sum(pa) as pa, sum(ab) as ab, sum(h) as h, sum(singles) as singles,
        sum(doubles) as doubles, sum(triples) as triples, sum(hr) as hr, sum(bb) as bb,
        sum(ibb) as ibb, sum(hbp) as hbp, sum(so) as so, sum(sf) as sf, sum(sb) as sb,
        sum(cs) as cs, sum(runs) as runs
    from {{ ref('stg_mlb__batting') }}
    group by season

),

pit as (

    select
        season,
        sum(gs) / 2         as games,
        sum(outs)           as outs,
        sum(outs) / 3.0     as ip,
        sum(er)             as er,
        sum(runs)           as runs,
        sum(hr)             as hr,
        sum(bb)             as bb,
        sum(hbp)            as hbp,
        sum(so)             as so,
        -- replacement wins per 9 innings, by role mix, times innings / 9
        sum(({{ rp_replacement_wins }} + ({{ sp_replacement_wins }} - {{ rp_replacement_wins }})
             * gs * 1.0 / nullif(games, 0)) * outs / 27.0)              as replacement_units
    from {{ ref('stg_mlb__pitching') }}
    group by season

),

base as (

    select
        bat.season,
        pit.games,
        pit.games * 2.0 / 30                                            as team_games,
        bat.pa, bat.ab, bat.h, bat.singles, bat.doubles, bat.triples, bat.hr, bat.bb,
        bat.ibb, bat.hbp, bat.so, bat.sf, bat.sb, bat.cs, bat.runs,
        pit.ip,
        pit.outs,
        pit.replacement_units,
        (bat.h + bat.bb + bat.hbp) * 1.0
            / nullif(bat.ab + bat.bb + bat.hbp + bat.sf, 0)             as obp,
        ({{ rv.ubb }} * (bat.bb - bat.ibb) + {{ rv.hbp }} * bat.hbp
            + {{ rv.single }} * bat.singles + {{ rv.double }} * bat.doubles
            + {{ rv.triple }} * bat.triples + {{ rv.hr }} * bat.hr)
            / nullif(bat.ab + bat.bb - bat.ibb + bat.sf + bat.hbp, 0)   as woba_unscaled,
        9.0 * pit.er / pit.ip                                           as era,
        9.0 * pit.runs / pit.ip                                         as ra9,
        (13.0 * pit.hr + 3 * (pit.bb + pit.hbp) - 2 * pit.so) / pit.ip  as fip_core,
        pit.runs * 1.0 / pit.outs                                       as runs_per_out,
        9.0 * pit.runs / pit.ip * 1.5 + 3                               as runs_per_win
    from bat
    inner join pit on pit.season = bat.season

),

scaled as (

    select
        *,
        obp / woba_unscaled                                             as woba_scale,
        -(2 * runs_per_out + 0.075)                                     as run_cs
    from base

)

select
    season,
    games,
    team_games,
    games < {{ var('full_season_min_games') }} * 15                     as is_shortened_season,
    pa,
    ip,
    runs * 1.0 / pa                                                     as runs_per_pa,
    runs_per_out,
    runs_per_win,
    obp,
    obp                                                                 as woba,
    woba_scale,
    {{ rv.ubb }} * woba_scale                                           as w_ubb,
    {{ rv.hbp }} * woba_scale                                           as w_hbp,
    {{ rv.single }} * woba_scale                                        as w_single,
    {{ rv.double }} * woba_scale                                        as w_double,
    {{ rv.triple }} * woba_scale                                        as w_triple,
    {{ rv.hr }} * woba_scale                                            as w_hr,
    {{ run_sb }}                                                        as run_sb,
    run_cs,
    ({{ run_sb }} * sb + run_cs * cs) / nullif(singles + bb + hbp - ibb, 0) as wsb_per_opportunity,
    singles * 1.0 / pa                                                  as singles_rate,
    doubles * 1.0 / pa                                                  as doubles_rate,
    triples * 1.0 / pa                                                  as triples_rate,
    hbp * 1.0 / pa                                                      as hbp_rate,
    so * 1.0 / pa                                                       as k_rate,
    (bb - ibb) * 1.0 / pa                                               as ubb_rate,
    hr * 1.0 / pa                                                       as hr_rate,
    (h - hr) * 1.0 / nullif(ab - so - hr + sf, 0)                       as babip,
    era,
    ra9,
    era - fip_core                                                      as fip_constant,
    {{ batting_war_per_game }} * games * runs_per_win / pa              as batting_replacement_runs_per_pa,
    {{ pitching_war_per_game }} * games * runs_per_win / ip             as pitching_replacement_runs_per_ip,
    {{ pitching_war_per_game }} * games / replacement_units             as pitching_replacement_scale,
    {{ pitching_war_per_game }} * games / replacement_units
        * {{ sp_replacement_wins }} * runs_per_win / 9                  as sp_replacement_runs_per_ip,
    {{ pitching_war_per_game }} * games / replacement_units
        * {{ rp_replacement_wins }} * runs_per_win / 9                  as rp_replacement_runs_per_ip
from scaled
