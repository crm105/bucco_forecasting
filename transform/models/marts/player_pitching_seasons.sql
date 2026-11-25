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
        )
    from rated

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
    coalesce((balanced.league_ra9 - (balanced.fip + balanced.ra9_minus_era)) * balanced.ip / 9, 0)
                                                                        as pitching_runs,
    balanced.replacement_runs,
    (coalesce((balanced.league_ra9 - (balanced.fip + balanced.ra9_minus_era)) * balanced.ip / 9, 0)
        + balanced.replacement_runs) / balanced.runs_per_win                  as war_approx,
    balanced.fip_neutral,
    coalesce((balanced.league_ra9 - (balanced.fip_neutral + balanced.ra9_minus_era)) * balanced.ip / 9, 0)
                                                                        as pitching_runs_neutral,
    (coalesce((balanced.league_ra9 - (balanced.fip_neutral + balanced.ra9_minus_era)) * balanced.ip / 9, 0)
        + balanced.replacement_runs) / balanced.runs_per_win                  as war_approx_neutral
from balanced
left join people
    on people.mlbam_id = balanced.mlbam_id
left join {{ ref('int__player_sides') }} as sides
    on sides.season = balanced.season
    and sides.mlbam_id = balanced.mlbam_id
    and sides.role = 'pitcher'
