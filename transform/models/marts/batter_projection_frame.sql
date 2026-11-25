{#
  The table our own batter projections (rung 5b) are fitted and run on: one row per player per
  target season, for every player who batted in at least one of the three seasons before it.

  Inputs are columns prefixed y1_, y2_ and y3_: the player's line one, two and three seasons
  before the target season (null if he did not bat that season). Age is his age in the target
  season. Nothing from the target season is an input; this keeps the backtest honest (checked by
  assert_projection_frames_use_prior_seasons_only).

  Outcomes are columns prefixed target_: what he did in the target season. For a completed
  season, a player who did not bat gets 0 PA (that is a real outcome for a playing-time model:
  retired, hurt or in the minors). For the upcoming season (the one after the last completed
  season) the outcomes are null.

  Not included: players with no MLB batting in the previous three seasons (rookies, returnees
  after a long absence). A projection system has to handle them separately.
#}

{% set counts = ['games', 'pa', 'ab', 'h', 'singles', 'doubles', 'triples', 'hr', 'bb', 'ibb',
                 'hbp', 'so', 'sf', 'sb', 'cs'] %}
{% set values = ['woba', 'batting_runs', 'baserunning_runs', 'positional_runs', 'off_runs',
                 'war_approx', 'woba_neutral', 'off_runs_neutral', 'war_approx_neutral',
                 'left_share'] %}

with seasons as (

    select * from {{ ref('player_batting_seasons') }}

),

league as (

    select season, team_games from {{ ref('league_seasons') }}

),

last_completed as (

    select max(season) as season from league

),

spine as (

    select distinct seasons.season + lag.k as season, seasons.mlbam_id
    from seasons
    cross join (values (1), (2), (3)) as lag(k)
    where seasons.season + lag.k <= (select season + 1 from last_completed)
      and seasons.pa > 0

),

people as (

    select * from {{ ref('stg_mlb__people') }}

)

select
    spine.season,
    spine.mlbam_id,
    coalesce(people.player_name, y1.player_name, y2.player_name, y3.player_name) as player_name,
    spine.season > (select season from last_completed)                as is_upcoming_season,
    people.birth_date,
    spine.season - year(people.birth_date)
        - case when month(people.birth_date) > 6 then 1 else 0 end      as age,
    people.bats,
    coalesce(y1.last_team_id, y2.last_team_id, y3.last_team_id)        as last_team_id,
    coalesce(y1.primary_position, y2.primary_position, y3.primary_position) as last_primary_position,
    coalesce(y1.is_pitcher, y2.is_pitcher, y3.is_pitcher)              as is_pitcher,
    {% for k in [1, 2, 3] %}
    spine.season - {{ k }}                                              as y{{ k }}_season,
    league_y{{ k }}.team_games                                          as y{{ k }}_team_games,
    {% for c in counts %}
    coalesce(y{{ k }}.{{ c }}, 0)                                       as y{{ k }}_{{ c }},
    {% endfor %}
    {% for c in values %}
    y{{ k }}.{{ c }}                                                    as y{{ k }}_{{ c }},
    {% endfor %}
    {% endfor %}
    {% for c in counts %}
    case when spine.season <= (select season from last_completed)
         then coalesce(target.{{ c }}, 0) end                           as target_{{ c }},
    {% endfor %}
    {% for c in values %}
    target.{{ c }}                                                      as target_{{ c }},
    {% endfor %}
    target.primary_position                                             as target_primary_position
from spine
left join people
    on people.mlbam_id = spine.mlbam_id
{% for k in [1, 2, 3] %}
left join seasons as y{{ k }}
    on y{{ k }}.mlbam_id = spine.mlbam_id
    and y{{ k }}.season = spine.season - {{ k }}
left join league as league_y{{ k }}
    on league_y{{ k }}.season = spine.season - {{ k }}
{% endfor %}
left join seasons as target
    on target.mlbam_id = spine.mlbam_id
    and target.season = spine.season
where spine.season > {{ var('history_start_season') }}
