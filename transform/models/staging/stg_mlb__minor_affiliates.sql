{#
  Minor-league teams by season with the major-league organization each belonged to, typed.
#}

select
    cast(season as integer)          as season,
    cast(team_id as integer)         as team_id,
    team_name,
    cast(sport_id as integer)        as sport_id,
    level,
    cast(parent_org_id as integer)   as parent_org_id
from {{ source('mlb_api', 'minor_affiliates') }}
where parent_org_id is not null
