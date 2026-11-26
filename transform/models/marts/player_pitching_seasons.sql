{#
  What each pitcher did, one row per player per season from 2000 (all teams combined), with his
  age and role, rate stats and an approximate value in runs and wins. This is the history our own
  pitcher projections (rung 5b) learn from; to forecast, read pitcher_projection_frame.

  Value is FIP-based, like FanGraphs WAR, but approximate (see league_seasons):
    fip           = (13 HR + 3 (BB + HBP) - 2 K) / IP + the season's FIP constant
    pitching_runs = (league RA9 - FIP on the RA9 scale) x IP / 9, so the league sums to zero
    war_approx    = (pitching_runs + replacement runs) / runs per win
  Replacement level depends on role, as at FanGraphs: lower for starters than relievers, mixed
  by the share of his games he started (league_seasons). Unlike FanGraphs there is no
  infield-fly adjustment and no leverage credit for relievers.

  Park-neutral versions (`*_neutral`): home runs, walks, hit batters and strikeouts divided by
  how much his home parks inflated them (int__player_season_parks), then the same formulas,
  shifted each season so league FIP is unchanged. Projections read these.

  Components (`k_runs`, `bb_runs`, `hr_runs`, `other_runs`, and `*_neutral`): pitching runs
  split by FIP's parts, each against the season's league rate per batter faced:
    k_runs  = 2/9 x (K - league K rate x BF)
    bb_runs = -3/9 x (BB + HBP - league rate x BF)
    hr_runs = -13/9 x (HR - league rate x BF)
    other_runs = pitching runs - the three: innings per batter faced against the league (more
                 outs per batter faced, from balls in play and double plays, means more innings
                 for the same events). Each sums to zero over the league.
  Our projections regress each part separately (bucco.models.marcel).

  Role: a starter (SP) started at least half of the games he pitched. Age is on June 30.
#}

{% set starter_share_cutoff = 0.5 %}

with pit as (

    select * from {{ ref('stg_mlb__pitching') }}

),

league as (

    select * from {{ ref('league_seasons') }}

),

people as (

    select * from {{ ref('stg_mlb__people') }}

),

parks as (

    select * from {{ ref('int__player_season_parks') }} where role = 'pitcher'

),

rated as (

    select
        pit.*,
        (13.0 * pit.hr + 3 * (pit.bb + pit.hbp) - 2 * pit.so) / nullif(pit.ip, 0)
            + league.fip_constant                                       as fip,
        (13.0 * pit.hr / coalesce(parks.m_hr, 1)
            + 3 * ((pit.bb - pit.ibb) / coalesce(parks.m_ubb, 1) + pit.ibb
                   + pit.hbp / coalesce(parks.m_hbp, 1))
            - 2 * pit.so / coalesce(parks.m_so, 1)) / nullif(pit.ip, 0)
            + league.fip_constant                                       as fip_neutral,
        pit.so / coalesce(parks.m_so, 1)                                as so_neutral,
        (pit.bb - pit.ibb) / coalesce(parks.m_ubb, 1) + pit.ibb
            + pit.hbp / coalesce(parks.m_hbp, 1)                        as bbh_neutral,
        pit.hr / coalesce(parks.m_hr, 1)                                as hr_neutral,
        league.ra9 - league.era                                         as ra9_minus_era,
        league.ra9                                                      as league_ra9,
        (league.rp_replacement_runs_per_ip
            + (league.sp_replacement_runs_per_ip - league.rp_replacement_runs_per_ip)
              * pit.gs * 1.0 / nullif(pit.games, 0)) * pit.ip             as replacement_runs,
        league.runs_per_win
    from pit
    inner join league on league.season = pit.season
    left join parks
        on parks.season = pit.season
        and parks.mlbam_id = pit.mlbam_id

),

balanced as (

    select
        * replace (
            fip_neutral + sum((fip - fip_neutral) * ip) over (partition by season)
                / sum(ip) over (partition by season) as fip_neutral
        ),
        sum(so) over (partition by season) / sum(bf) over (partition by season)      as lg_k,
        sum(bb + hbp) over (partition by season) / sum(bf) over (partition by season) as lg_bbh,
        sum(hr) over (partition by season) / sum(bf) over (partition by season)      as lg_hr,
        sum(so_neutral) over (partition by season) / sum(bf) over (partition by season)
                                                                        as lg_k_neutral,
        sum(bbh_neutral) over (partition by season) / sum(bf) over (partition by season)
                                                                        as lg_bbh_neutral,
        sum(hr_neutral) over (partition by season) / sum(bf) over (partition by season)
                                                                        as lg_hr_neutral
    from rated

),

valued as (

    select
        *,
        coalesce((league_ra9 - (fip + ra9_minus_era)) * ip / 9, 0)       as pitching_runs,
        coalesce((league_ra9 - (fip_neutral + ra9_minus_era)) * ip / 9, 0)
                                                                        as pitching_runs_neutral,
        2.0 / 9 * (so - lg_k * bf)                                      as k_runs,
        -3.0 / 9 * (bb + hbp - lg_bbh * bf)                             as bb_runs,
        -13.0 / 9 * (hr - lg_hr * bf)                                   as hr_runs,
        2.0 / 9 * (so_neutral - lg_k_neutral * bf)                      as k_runs_neutral,
        -3.0 / 9 * (bbh_neutral - lg_bbh_neutral * bf)                  as bb_runs_neutral,
        -13.0 / 9 * (hr_neutral - lg_hr_neutral * bf)                   as hr_runs_neutral
    from balanced

)

select
    balanced.season,
    balanced.mlbam_id,
    coalesce(people.player_name, balanced.player_name)                     as player_name,
    balanced.last_team_id,
    balanced.num_teams,
    people.birth_date,
    balanced.season - year(people.birth_date)
        - case when month(people.birth_date) > 6 then 1 else 0 end      as age,
    people.throws,
    sides.left_share,
    case when balanced.gs >= {{ starter_share_cutoff }} * balanced.games
         and balanced.gs > 0 then 'SP' else 'RP' end                       as role,
    balanced.games,
    balanced.gs,
    balanced.games_finished,
    balanced.saves,
    balanced.holds,
    balanced.outs,
    balanced.ip,
    balanced.bf,
    balanced.h,
    balanced.doubles,
    balanced.triples,
    balanced.hr,
    balanced.bb,
    balanced.ibb,
    balanced.hbp,
    balanced.so,
    balanced.sf,
    balanced.sh,
    balanced.runs,
    balanced.er,
    balanced.ground_outs,
    balanced.air_outs,
    balanced.so * 1.0 / nullif(balanced.bf, 0)                                as k_rate,
    balanced.bb * 1.0 / nullif(balanced.bf, 0)                                as bb_rate,
    balanced.hr * 1.0 / nullif(balanced.bf, 0)                                as hr_rate,
    (balanced.h - balanced.hr) * 1.0 / nullif(balanced.bf - balanced.bb - balanced.hbp - balanced.so
                                        - balanced.hr - balanced.sh, 0)       as babip,
    balanced.ground_outs * 1.0 / nullif(balanced.ground_outs + balanced.air_outs, 0)
                                                                        as ground_out_share,
    9.0 * balanced.er / nullif(balanced.ip, 0)                                as era,
    9.0 * balanced.runs / nullif(balanced.ip, 0)                              as ra9,
    balanced.fip,
    balanced.pitching_runs,
    balanced.replacement_runs,
    (coalesce((balanced.league_ra9 - (balanced.fip + balanced.ra9_minus_era)) * balanced.ip / 9, 0)
        + balanced.replacement_runs) / balanced.runs_per_win                  as war_approx,
    balanced.fip_neutral,
    balanced.pitching_runs_neutral,
    (coalesce((balanced.league_ra9 - (balanced.fip_neutral + balanced.ra9_minus_era)) * balanced.ip / 9, 0)
        + balanced.replacement_runs) / balanced.runs_per_win                  as war_approx_neutral,
    balanced.k_runs,
    balanced.bb_runs,
    balanced.hr_runs,
    balanced.pitching_runs - balanced.k_runs - balanced.bb_runs - balanced.hr_runs
                                                                        as other_runs,
    balanced.k_runs_neutral,
    balanced.bb_runs_neutral,
    balanced.hr_runs_neutral,
    balanced.pitching_runs_neutral - balanced.k_runs_neutral - balanced.bb_runs_neutral
        - balanced.hr_runs_neutral                                      as other_runs_neutral
from valued as balanced
left join people
    on people.mlbam_id = balanced.mlbam_id
left join {{ ref('int__player_sides') }} as sides
    on sides.season = balanced.season
    and sides.mlbam_id = balanced.mlbam_id
    and sides.role = 'pitcher'
