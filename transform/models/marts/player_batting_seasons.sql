{#
  What each batter did, one row per player per season from 2000 (all teams combined), with his
  age and position, rate stats and an approximate value in runs and wins. This is the history
  our own batter projections (rung 5b) learn from; to forecast, read batter_projection_frame,
  which only shows seasons before the one being forecast.

  Value is on the FanGraphs scale but approximate (see league_seasons for the constants):
    batting_runs     = (wOBA - league wOBA) / wOBA scale x PA, before park or league adjustments
    baserunning_runs = stolen-base runs (wSB) only; no extra bases taken or double plays
    positional_runs  = FanGraphs positional adjustment, by innings at each position (DH starts
                       count as 9 innings)
    fielding         = not included: the MLB API has no fielding runs, so def_runs is the
                       positional adjustment alone and players are treated as average fielders
    war_approx       = (batting + baserunning + positional + replacement runs) / runs per win

  Park-neutral versions (`*_neutral`): each count divided by how much his home parks inflated
  it (int__player_season_parks, from park_factors), then the same formulas, rescaled each
  season so league wOBA is unchanged (dividing by park multipliers does not average out
  exactly). Projections read these; the plain columns are as played.

  Age is baseball age: on June 30 of the season. Pitchers' batting lines are kept (pre-2022
  pitchers batted); `is_pitcher` marks them so models can drop them.
#}

{% set positional_runs_per_1458_innings = {
    'C': 12.5, 'SS': 7.5, '2B': 2.5, '3B': 2.5, 'CF': 2.5,
    'LF': -7.5, 'RF': -7.5, '1B': -12.5, 'DH': -17.5} %}

with bat as (

    select * from {{ ref('stg_mlb__batting') }}

),

league as (

    select * from {{ ref('league_seasons') }}

),

people as (

    select * from {{ ref('stg_mlb__people') }}

),

positions as (

    select * from {{ ref('int__player_season_positions') }}

),

parks as (

    select * from {{ ref('int__player_season_parks') }} where role = 'batter'

),

position_runs as (

    select
        season,
        mlbam_id,
        sum(
            case position
                {% for pos, runs in positional_runs_per_1458_innings.items() %}
                when '{{ pos }}' then {{ runs }}
                {% endfor %}
                else 0
            end
            * case when position = 'DH' then games_started * 9.0 else innings end
        ) / 1458.0                                                      as positional_runs
    from {{ ref('stg_mlb__fielding') }}
    group by season, mlbam_id

),

rated as (

    select
        bat.*,
        bat.ab + bat.bb - bat.ibb + bat.sf + bat.hbp                    as woba_pa,
        (league.w_ubb * (bat.bb - bat.ibb) + league.w_hbp * bat.hbp
            + league.w_single * bat.singles + league.w_double * bat.doubles
            + league.w_triple * bat.triples + league.w_hr * bat.hr)
            / nullif(bat.ab + bat.bb - bat.ibb + bat.sf + bat.hbp, 0)   as woba,
        league.run_sb * bat.sb + league.run_cs * bat.cs
            - league.wsb_per_opportunity
              * (bat.singles + bat.bb + bat.hbp - bat.ibb)              as baserunning_runs,
        league.batting_replacement_runs_per_pa * bat.pa                 as replacement_runs,
        (league.w_ubb * (bat.bb - bat.ibb) / coalesce(parks.m_ubb, 1)
            + league.w_hbp * bat.hbp / coalesce(parks.m_hbp, 1)
            + league.w_single * bat.singles / coalesce(parks.m_singles, 1)
            + league.w_double * bat.doubles / coalesce(parks.m_doubles, 1)
            + league.w_triple * bat.triples / coalesce(parks.m_triples, 1)
            + league.w_hr * bat.hr / coalesce(parks.m_hr, 1))
            / nullif(bat.ab + bat.bb - bat.ibb + bat.sf + bat.hbp, 0)   as woba_neutral,
        league.woba                                                     as league_woba,
        league.woba_scale,
        league.runs_per_win
    from bat
    inner join league on league.season = bat.season
    left join parks
        on parks.season = bat.season
        and parks.mlbam_id = bat.mlbam_id

),

balanced as (

    select
        * replace (
            woba_neutral * sum(woba * woba_pa) over (partition by season)
                / sum(woba_neutral * woba_pa) over (partition by season) as woba_neutral
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
    people.bats,
    sides.left_share,
    positions.primary_position,
    positions.position_group,
    coalesce(positions.position_group in ('SP', 'RP')
             and not positions.is_two_way, false)                       as is_pitcher,
    balanced.games,
    balanced.pa,
    balanced.ab,
    balanced.h,
    balanced.singles,
    balanced.doubles,
    balanced.triples,
    balanced.hr,
    balanced.bb,
    balanced.ibb,
    balanced.hbp,
    balanced.so,
    balanced.sf,
    balanced.sh,
    balanced.sb,
    balanced.cs,
    balanced.gidp,
    balanced.ground_outs,
    balanced.air_outs,
    balanced.runs,
    balanced.rbi,
    balanced.h * 1.0 / nullif(balanced.ab, 0)                                 as avg,
    (balanced.h + balanced.bb + balanced.hbp) * 1.0
        / nullif(balanced.ab + balanced.bb + balanced.hbp + balanced.sf, 0)         as obp,
    (balanced.singles + 2 * balanced.doubles + 3 * balanced.triples + 4 * balanced.hr) * 1.0
        / nullif(balanced.ab, 0)                                           as slg,
    (balanced.doubles + 2 * balanced.triples + 3 * balanced.hr) * 1.0
        / nullif(balanced.ab, 0)                                           as iso,
    (balanced.h - balanced.hr) * 1.0
        / nullif(balanced.ab - balanced.so - balanced.hr + balanced.sf, 0)          as babip,
    balanced.so * 1.0 / nullif(balanced.pa, 0)                                as k_rate,
    balanced.bb * 1.0 / nullif(balanced.pa, 0)                                as bb_rate,
    balanced.hr * 1.0 / nullif(balanced.pa, 0)                                as hr_rate,
    balanced.woba,
    coalesce((balanced.woba - balanced.league_woba) / balanced.woba_scale * balanced.woba_pa, 0)
                                                                        as batting_runs,
    balanced.baserunning_runs,
    coalesce(position_runs.positional_runs, 0)                             as positional_runs,
    balanced.replacement_runs,
    coalesce((balanced.woba - balanced.league_woba) / balanced.woba_scale * balanced.woba_pa, 0)
        + balanced.baserunning_runs                                        as off_runs,
    coalesce(position_runs.positional_runs, 0)                             as def_runs,
    (coalesce((balanced.woba - balanced.league_woba) / balanced.woba_scale * balanced.woba_pa, 0)
        + balanced.baserunning_runs
        + coalesce(position_runs.positional_runs, 0)
        + balanced.replacement_runs) / balanced.runs_per_win                  as war_approx,
    balanced.woba_neutral,
    coalesce((balanced.woba_neutral - balanced.league_woba) / balanced.woba_scale * balanced.woba_pa, 0)
                                                                        as batting_runs_neutral,
    coalesce((balanced.woba_neutral - balanced.league_woba) / balanced.woba_scale * balanced.woba_pa, 0)
        + balanced.baserunning_runs                                        as off_runs_neutral,
    (coalesce((balanced.woba_neutral - balanced.league_woba) / balanced.woba_scale * balanced.woba_pa, 0)
        + balanced.baserunning_runs
        + coalesce(position_runs.positional_runs, 0)
        + balanced.replacement_runs) / balanced.runs_per_win                  as war_approx_neutral
from balanced
left join people
    on people.mlbam_id = balanced.mlbam_id
left join {{ ref('int__player_sides') }} as sides
    on sides.season = balanced.season
    and sides.mlbam_id = balanced.mlbam_id
    and sides.role = 'batter'
left join positions
    on positions.season = balanced.season
    and positions.mlbam_id = balanced.mlbam_id
left join position_runs
    on position_runs.season = balanced.season
    and position_runs.mlbam_id = balanced.mlbam_id
