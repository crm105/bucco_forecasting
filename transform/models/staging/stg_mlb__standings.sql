select
    cast(season as integer)                         as season,
    cast(team_id as integer)                        as team_id,
    team_name,
    cast(league_id as integer)                      as league_id,
    cast(division_id as integer)                    as division_id,
    cast(games_played as integer)                   as games_played,
    cast(wins as integer)                           as wins,
    cast(losses as integer)                         as losses,
    cast(runs_scored as integer)                    as runs_scored,
    cast(runs_allowed as integer)                   as runs_allowed,
    cast(division_rank as integer)                  as division_rank,
    nullif(trim(clinch_indicator), '')              as clinch_indicator,
    cast(fetched_at as timestamp)                   as fetched_at
from {{ source('mlb_api', 'standings') }}
