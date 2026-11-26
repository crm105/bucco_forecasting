{#
  The table our own pitcher projections (rung 5b) are fitted and run on: one row per player per
  target season, for every player who pitched in at least one of the three seasons before it.
  Same layout and rules as batter_projection_frame: y1_, y2_, y3_ inputs from the three prior
  seasons only, target_ outcomes (0 innings for a completed season he did not pitch in, null
  for the upcoming season). Position players who pitched in a blowout are included; filter on
  the y*_bf columns.
#}

{% set counts = ['games', 'gs', 'outs', 'bf', 'h', 'hr', 'bb', 'ibb', 'hbp', 'so', 'sh', 'runs',
                 'er', 'ground_outs', 'air_outs'] %}
{% set values = ['ip', 'fip', 'pitching_runs', 'war_approx', 'fip_neutral',
                 'pitching_runs_neutral', 'war_approx_neutral',
                 'k_runs', 'bb_runs', 'hr_runs', 'other_runs', 'k_runs_neutral',
                 'bb_runs_neutral', 'hr_runs_neutral', 'other_runs_neutral'] %}

with seasons as (

    select * from {{ ref('player_pitching_seasons') }}

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
      and seasons.bf > 0

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
    people.throws,
    coalesce(y1.last_team_id, y2.last_team_id, y3.last_team_id)        as last_team_id,
    coalesce(y1.role, y2.role, y3.role)                                 as last_role,
    {% for k in [1, 2, 3] %}
    spine.season - {{ k }}                                              as y{{ k }}_season,
    league_y{{ k }}.team_games                                          as y{{ k }}_team_games,
    y{{ k }}.role                                                       as y{{ k }}_role,
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
    target.role                                                         as target_role
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
