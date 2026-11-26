# Our own rosters and a longer backtest (2026-11-26)

## What we tried

Put our own projections on the MLB Stats API's Opening Day 40-man rosters instead of the team
assignments in Steamer's player files, which start in 2012. That removes the dependence on
Steamer's rosters and lets `marcel_staff_optimized` be scored on earlier seasons, so small
changes can be told from noise (most recent comparisons had t near 1.5).

## How far back the API goes

The plan was ten more seasons (2002–2011). The API's history does not support it: before 2009
its preseason rosters are incomplete, and so is every other roster source in it.

| Opening Day 40-man, six teams | Players | Pirates winter transactions |
| --- | --- | --- |
| 2002 (Pirates only) | 3 | 1 |
| 2005 (Pirates only) | 9 | 3 |
| 2006 | 17–25 | 8 |
| 2007 | 24–34 | 2 |
| 2008 | 29–36 | 3 |
| **2009** | **38–41** | 5 |
| 2010–2011 | 39–43 | 120+ |

Opening Day box scores list only the players who appeared, the depth-chart roster type ignores
its date (it returns today's), and `fullRoster` is inconsistent (95 players in 2002, 27 in 2005).
So rosters start in **2009** (`bucco extract mlb-rosters`, `FIRST_SEASON`), and minor-league
lines in 2006 (`bucco extract mlb-minor-batting`/`-pitching`), three seasons before. MLB season
stats already reach 2000. Going further back would need another roster source, such as
Retrosheet's transactions.

Fielding stays borrowed where it exists: ZiPS's projected Def from 2011, the Steamer and ZiPS
average from 2012, none (positional adjustment only) in 2009–2010.

## Rosters

`player_inputs.marcel_rosters("mlb")`: each team's 40-man on its first game
(`player_preseason_status`, with roster position: `P` pitchers, `TWP` both). The roster also
feeds the baseline-innings fit and the availability factors (`marcel_projections(...,
roster_source=)`). All snapshots are dated to the season's first game: dated by team, every team
opening after the first game (a day later, or a week after an opener abroad) was dropped from an
Opening Day forecast, which first gave 11.5 wins RMSE.

The 40-man is narrower than Steamer's lists, which carry the whole organization (2027 Pirates: 22
hitters and 17 pitchers against 99 and 105). Minor-leaguers off the 40-man (non-roster invitees,
prospects) are no longer projected; their playing time goes to replacement level.

## Results

Wins RMSE, without 2020:

| | 2012–26 | 2012–19 | 2021–26 | Better | t | 2009–26 |
| --- | --- | --- | --- | --- | --- | --- |
| Steamer's rosters | 9.537 | 9.175 | 10.001 | | | |
| **MLB 40-man rosters (kept)** | 9.577 | 9.254 | 9.992 | 6 of 14 | +1.0 | **9.455** |

The cost on the shared seasons (0.04) is within noise and comes from 2012–2017; since 2018 the
two are even. The new seasons are easy ones: 9.01 (2009), 8.88 (2010), 8.68 (2011). So
`marcel_staff_optimized`'s score over all its seasons (9.455) is not comparable with models that
start in 2012: the report now ranks models by RMSE over the seasons all of them cover
(`report.data.board`), where it is 9.58 (Steamer 9.50, the Steamer–ZiPS blend 9.54,
`steamer_optimized` 9.58). `bucco leaderboard --first-season 2012` gives the same comparison.

**2027**: teams move 0.8 wins on average; correlation with Steamer's forecast 0.851 to 0.861.
Pirates 84.7 to 83.5 (8th): November's 40-man has no minor-league depth, so Carmen Mlodzinski and
Lake Bachar fill the rotation (Wilber Dotel, 45 innings before, is off it) and the bullpen falls
from 1st to 9th. Rosters fill toward Opening Day; rerun then.

## Limits and next

- 2002–2008 need a roster source outside the API.
- Fielding in 2009–2010 is positional only, so those seasons are scored with a weaker model.
- Non-roster players: a prospect or veteran invitee who makes the team is missing until called
  up. Adding the organization's minor-leaguers from last season's affiliates would be the
  leak-free way to bring them back.

## Status

Adopted in `marcel_staff_optimized`: scored 2009–2026 (17 seasons), 9.58 on 2012–2026.
