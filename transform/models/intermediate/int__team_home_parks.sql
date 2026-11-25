{#
  Each team's home ballpark per season: the venue where it played the most home games, and the
  share of its home games played there. Games abroad (Tokyo, London, Mexico City) and moves
  (the 2020-21 Blue Jays in Buffalo and Dunedin) lower the share.
#}

with games as (

    select season, home_team_id as team_id, venue_id, max(venue_name) as venue_name,
           count(*) as games
    from {{ ref('stg_mlb__schedules') }}
    where status not in ('Postponed', 'Cancelled')
      and venue_id is not null
    group by 1, 2, 3

),

ranked as (

    select
        *,
        sum(games) over (partition by season, team_id)                      as home_games,
        row_number() over (partition by season, team_id
                           order by games desc, venue_id)                   as venue_rank
    from games

)

select
    season,
    team_id,
    venue_id,
    venue_name,
    games                                   as games_at_venue,
    home_games,
    games * 1.0 / home_games                as venue_share
from ranked
where venue_rank = 1
