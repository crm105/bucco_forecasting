{#
  Each team's actual WAR per season, split into batting and pitching, from our own approximate
  player WAR (park-neutral, `war_approx_neutral`: the same footing as our projections). A player
  who played for several teams has his season split by his share of games in the field (batters,
  DH included) or innings pitched (pitchers) with each; one with no fielding rows goes to his last
  team. The target of the backtest's intermediate check: projected team WAR against what the team
  produced, without the game-to-game luck that turns WAR into wins (bucco.evaluate.team_war).
#}

select
    season,
    team_id,
    sum(case when part = 'batting' then war else 0 end)                        as batting_war,
    sum(case when part = 'pitching' then war else 0 end)                       as pitching_war,
    sum(war)                                                                   as war
from {{ ref('player_team_seasons') }}
group by season, team_id
