{#
  Games scheduled between each pair of teams in each season, from each team's side (both
  orders appear). Known before the season starts, so models may use it for the season they
  forecast.
#}

with sides as (
    select season, home_team_id as team_id, away_team_id as opponent_id from {{ ref('stg_mlb__schedules') }}
    union all
    select season, away_team_id as team_id, home_team_id as opponent_id from {{ ref('stg_mlb__schedules') }}
)

select season, team_id, opponent_id, count(*) as games
from sides
group by season, team_id, opponent_id
