# Proportional fill: turning player projections into a team

Update: the position-blind rules below have been superseded by the slot-by-slot [depth chart](depth_chart.md), which is what to use for rung 5a. This note remains as the reasoning behind them.

Status: the "regulars first" version is implemented in [playing_time.py](../../src/bucco/models/playing_time.py) as the first way to build a team from ZiPS player projections (rung 5a). Plain uniform proportional fill (described first, below) is not implemented; it is here to explain why. Pitcher defaults and position rules are still to do.

## The problem

The ZiPS player files give each player's projected WAR for his own projected playing time. Each player's playing time is estimated on his own, without regard to the rest of the roster. In the 2026 batter file the median player has about 400 plate appearances (PA), and a team's batters add up to roughly 22,000 to 26,000 PA. A real team gets about 6,200.

So adding up WAR by team gives a number that is too big and means nothing. A team projection needs two things the files don't give us:

1. A **team budget**: how much playing time a team has in total.
2. A rule for **sharing that budget** among the players on the roster.

## What FanGraphs does

FanGraphs Depth Charts do this by hand. Staff estimate each player's playing time from how they expect teams to use their lineups and injuries ([Depth Charts](https://library.fangraphs.com/depth-charts/)). The team totals they assume are 640 PA from catchers, 700 PA from each of the other offensive positions, and about 1,500 innings pitched. In the same description, their rates are a 50/50 blend of Steamer and ZiPS. Their rule for missing time is that it moves to the next players on the depth chart, not to replacement-level fill-ins ([2025 post](https://blogs.fangraphs.com/an-even-newer-way-of-looking-at-depth/)).

We can't replicate staff judgment, and past depth charts probably can't be downloaded. We need a mechanical rule that a computer can apply to every team in every past season.

## The idea

Think of a team's playing time as a fixed pie: about **6,240 PA** and **1,500 IP**. (6,240 is my reading of FanGraphs' rule: 640 for the catcher slot plus 700 for each of seven other slots, including DH. That sum is my inference, not a FanGraphs quote.)

ZiPS has handed out far more than one pie's worth of playing time. **Proportional fill** shrinks every player's playing time by the same factor, so the team's total comes out to exactly one pie:

> factor = team budget ÷ sum of the team's projected PA
>
> scaled PA = PA × factor
>
> scaled WAR = WAR × factor

Pitchers work the same way, with innings pitched in place of PA.

WAR can be scaled this way because it accumulates in proportion to playing time. A player worth 3 WAR over 600 PA is worth about 1.5 WAR over 300 PA. FanGraphs itself estimates lost WAR from a player's projected WAR per PA or per IP ([2025 post](https://blogs.fangraphs.com/an-even-newer-way-of-looking-at-depth/)). The team's WAR is the sum of the scaled player WARs.

The attractions are that the rule is simple, takes no judgment calls, and uses only information in the projection file, so it carries no leakage risk. It is related to what Szymborski describes in his ZiPS standings post, where ZiPS "automatically and proportionally 'fills in' playing time from the next players on the list" ([2026 ZiPS standings](https://blogs.fangraphs.com/the-official-and-hopefully-not-too-erroneous-2026-zips-projected-standings/)). That is a different, injury-driven step, so the match is loose.

## A worked example: the 2023 Pirates (prototype)

- Pirates batters in the file are projected for 21,766 PA in total. The factor is 6,240 ÷ 21,766 ≈ **0.287**.
- A regular projected for 625 PA and 3.9 WAR becomes about 179 PA and 1.1 WAR.
- The team's total WAR (batters and pitchers) goes from 39.9 (raw sum) to 12.2.

## The weakness we found

The prototype shows a problem. Uniform shrinking treats a regular the same as a bench player. That regular loses 71% of his playing time, but a real team's regulars keep nearly all of theirs, and the bench plays little. Because the shrinking is the same for everybody, the team's WAR comes out far too low.

Across all 30 teams in the 2023 files:

| Method | Mean team WAR | Spread (SD) | Team WAR vs. 2023 wins (correlation) | Pirates |
| --- | --- | --- | --- | --- |
| Raw sum (no fill) | 55.1 | 13.0 | 0.51 | 39.9 |
| Uniform proportional fill | 16.5 | 4.0 | 0.55 | 12.2 |
| Regulars first (see below) | 38.0 | 8.5 | 0.56 | 30.6 |

A team that is average in the league wins 81 games, and with a replacement level near 48 wins, an average team has about 33 WAR above replacement. Uniform fill's mean of 16.5 is about half of that. This matters mostly for interpretation: if the rung 4 and 5a models fit a line from team WAR to wins, the fitted line can undo the rescaling, and the uniform version's correlation is as good as the others. But its "team WAR" would not be a number you can read as WAR, and its spread is squeezed to about a third of the raw spread. It also depends on how many depth players a source includes: each extra minor leaguer dilutes everyone else.

The correlation figures come from 30 teams in one season, so they say nothing about which version forecasts better.

## Regulars first, with a bench set-aside (implemented)

Instead of shrinking everybody equally, the team's budget goes to its regulars first. Per team:

1. **Rank** the team's players by projected WAR per plate appearance (WAR/IP for pitchers), highest first. Players projected for fewer than `min_volume` (200) PA rank below everyone who reaches it, so a handful of plate appearances can't make a regular. The top `n_regulars` (12) are the regulars. Ranking by projected playing time instead is available as `rank_by="volume"`.
2. **Regulars** share `1 − bench_share` of the budget, pro rata to their own projections. No one gets more than his projection (or `cap`, once positions are known).
3. **Bench:** the set-aside, `bench_share` of the budget, goes to the next players in the ranking with an exponential decay. Each gets `decay` times the share of the player ranked just above him, so `decay = 0.8` gives 100, 80, 64, 51, ... before caps. A bench player can't receive more than his own projection, and the excess moves down the list.
4. **WAR** is scaled by the fraction of his projection each player receives, as before.

If the regulars' projections add up to less than their share, the unused part also goes to the bench. If the whole roster can't absorb the budget, everyone gets his projection and the team falls short of the budget, rather than any player being given more than he was projected for.

This differs from the prototype in the table above, where the regulars took their full projection until the budget ran out. Letting the regulars share a fixed fraction is what makes a bench set-aside possible.

| Argument | Default | Meaning |
| --- | --- | --- |
| `budget` | 6,240 PA (batters), 1,500 IP | The team's total playing time |
| `rank_by` | `"rate"` | `"rate"` ranks by WAR per PA, `"volume"` by projected PA |
| `min_volume` | 200 | Players projected below this rank last (with `rank_by="rate"`) |
| `n_regulars` | 12 | How many top-ranked players are regulars |
| `bench_share` | 0.15 | Fraction of the budget set aside for everyone else |
| `decay` | 0.8 | Bench share ratio from one rank to the next |
| `cap` | none | Most playing time one player can get (700 PA for a non-catcher once positions exist) |

Ranking by projected playing time was the first version, and it picked the wrong regulars: ZiPS projects prospects for big playing time too, so three prospects projected for 500 to 550 PA at about 0 WAR ranked 6th, 10th and 12th on one team in the 2026 file. Ranking by WAR per PA removes them. It still can't know who is actually on the roster: players who are regulars in the new ranking may never play for the team that year, and a player with a big real season can sit on the bench. The rule also ignores everything ZiPS can't know about a lineup, and knows about injuries only as far as they are in each projection.

### Which ranking? The evidence is mixed

Same data as below (ZiPS batters 2023–2026, 120 team-seasons, bench share 0.15, decay 0.8, cap 700). "Regulars' real PA share" is the share of the team's actual PA that went to the 12 players the rule chose.

| Ranking | Regulars' real PA share | Player error (PA) | Mean batting WAR | Wins error |
| --- | --- | --- | --- | --- |
| Projected PA | 52.8% | 176.2 | 18.3 | 10.20 |
| WAR/PA, no floor | 65.2% | 135.3 | 28.6 | 10.67 |
| WAR/PA, floor 200 PA | 65.5% | 135.4 | 28.5 | 10.67 |
| WAR/PA, floor 300 PA | 66.0% | 136.0 | 28.0 | 10.74 |
| WAR/PA, floor 400 PA | 65.2% | 143.8 | 25.3 | 10.88 |

WAR/PA is much better at finding the players who actually play (65% of real PA against 53%, and a lower player error). But it does worse on the wins check, and it pushes mean batting WAR from 18 to 28, which is too high once pitchers are added (a typical team has about 33 WAR above replacement in total). One likely reason is a selection effect: picking the highest projected rates out of about 57 players per team favors players whose projections are optimistic. The floor makes little difference between 0 and 250 PA, so 200 is a guard rather than a tuned value.

I made WAR/PA the default as requested, but the wins check does not support it. Both rankings are one argument apart, so the backtest can settle this once there is a full team model.

## Choosing the defaults

How much should go to the bench? I checked against real playing time from the MLB Stats API (per-team season hitting splits, regular season) and against the ZiPS files.

**What real teams do (2015–2026, excluding 2020; 330 team-seasons).** Ranking each team's hitters by the PA they actually got:

| Top N hitters | Share of team PA |
| --- | --- |
| 9 | 72.8% |
| 10 | 77.3% |
| 12 | 84.5% |
| 14 | 89.8% |

So the real bench share, everyone outside the top 12, is about **15.5%**. Beyond rank 12, real playing time falls off in a very regular way: the shares for ranks 13 to 20 are 2.87, 2.40, 2.00, 1.65, 1.35, 1.10, 0.90 and 0.71 percent of team PA. That is a ratio of about **0.8** from one rank to the next, for every step. I set the defaults (0.15 and 0.8) from these numbers before running the comparison below.

**The catch.** Those shares rank players by what they actually played, which nobody knows in advance. Ranking by ZiPS projected PA instead (2023–2026, 120 team-seasons), the top 12 got only **52.8%** of their team's real PA, because the projections include prospects who never play and regulars who get hurt. (About 95% of real team PA went to players ZiPS listed on that team, so coverage is not the problem.) A larger bench share hedges against that noisy ranking.

**Trying the settings (ZiPS batters, 2023–2026, decay 0.8, ranked by projected PA).** These numbers were computed with the volume ranking. With the WAR/PA ranking the picture is the same: a larger bench fits individual playing time better (best at about 0.2) and predicts wins worse (wins error 10.52 at 0, 10.74 at 0.15, 10.86 at 0.30). "Player error" is the RMSE of allocated PA against the PA each player actually got. "Wins error" is the RMSE of a line from batting WAR to wins, fitted leaving one season out. Batting WAR alone is a weak predictor of wins, so only the differences matter.

| `bench_share` | Player error (PA) | Mean batting WAR | Wins error |
| --- | --- | --- | --- |
| 0.00 | 197.6 | 19.9 | 10.12 |
| 0.15 | 176.2 | 18.3 | 10.20 |
| 0.30 | 169.0 | 16.7 | 10.40 |
| 0.40 | 172.9 | 15.5 | 10.62 |

Two goals pull in different directions. Matching individual playing time improves as the bench grows (best near 0.4, with a slower decay of 0.9), but predicting wins gets steadily worse and the team WAR scale shrinks, because a larger share of playing time goes to players with little WAR.

**Why 0.15.** It matches the real structure of a team, and its cost in wins accuracy against no bench (0.08 wins RMSE) is within the noise of 120 team-seasons. The data cannot separate any value from 0 to about 0.2 on wins. Going above 0.2 clearly costs accuracy. I'd treat 0.15 and 0.8 as a starting point and tune them in the walk-forward backtest once there is a full team model, never on the full history.

Caveats: four seasons, batters only, and the ZiPS download dates are not recorded yet. The real-PA data was pulled for this check and isn't stored in the repo.

## What the rule needs and doesn't do yet

- **Positions.** The 640-PA catcher and 700-PA caps need a position for each player, and the files don't have one. The plan for getting positions is in the TODO in the [planning doc](../planning/img/Bucco%20Forecasting%20Season%20Win%20Model%20Plan.md). Until then the default `cap` is none, and the regulars-first rule only limits each player to his own projection.
- **Pitchers.** The function works on innings pitched too (`volume="ip"`, `budget=1500`), but `n_regulars`, the bench share and the decay for pitchers haven't been chosen, and FanGraphs gives no starter and reliever split beyond the 1,500 IP total. The batter defaults should not be reused for pitchers.
- **Rate stats.** FanGraphs blends Steamer and ZiPS. We only have ZiPS so far.
- **Which teams.** The ZiPS team column reflects the roster when the file was downloaded. A download after a trade puts the player on his new team, so download dates matter (see `_player_downloads.csv`).

## How the prototype was run

The comparison table in "The weakness we found" came from a throwaway calculation. I ran both versions on the 2023 ZiPS batter and pitcher files, with budgets of 6,240 PA and 1,500 IP per team, and compared team WAR with 2023 actual wins. This was a throwaway calculation, not the final function, and the files have no recorded download date yet.
