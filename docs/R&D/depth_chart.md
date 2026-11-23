# Depth chart: who plays, where, and how much

Code: [depth_chart.py](../../src/bucco/models/depth_chart.py) · Tests: [test_depth_chart.py](../../tests/test_depth_chart.py) · Replaces the position-blind rule in [proportional_fill.md](proportional_fill.md)

Status: the functions exist and are tested. They are not yet part of a registered forecasting model. The numbers below come from the 2023–2026 ZiPS files (120 team-seasons) checked against what players actually did. The batter allocation was reworked once (see "Does it work?" for how it compares with the first version).

## Why a depth chart

The ZiPS player files give each player's WAR for his own projected playing time, estimated without regard to the rest of the roster. A team's players add up to roughly four times a real team's playing time, so you can't just sum them. The earlier "regulars first" rule ranked the whole roster in one list. That mixes up players who would never compete for the same job: a glove-first shortstop and a first baseman with the same WAR/PA are not interchangeable, because a large part of WAR is defense plus the credit for playing a hard position (the ZiPS `Def` column holds both, and WAR is roughly (Off + Def + replacement credit) ÷ 10).

A depth chart fixes that by filling the actual jobs on a team: nine lineup slots, five rotation spots and a bullpen. The question for each job is who are the eligible players, in what order, and how much of the job does each one get?

## Batters

### 1. Eligibility: who can fill which slot

A player can have **several** slots, not just one. They come from the prior season's games by position (`player_position_games`), so nothing from the forecast year leaks in.

1. **Listed positions.** His main field position (most games) plus every field position with at least 20 games.
2. **Flex.** Each listed position also opens the slots in `FLEX_SLOTS`:

   | Listed at | Can also play |
   | --- | --- |
   | SS | 2B and 1B |
   | 2B or 3B | 1B |
   | LF, CF or RF | any outfield position (LF, CF, RF) |
   | everyone | DH |

   So any infielder other than a first baseman can play first base. A catcher or first baseman gets nothing extra beyond positions he actually played, and a player who only DHed (or only pitched) can only DH. Flex applies to every listed position, so a third baseman with 30 games in left field can play 3B, 1B, LF, CF, RF and DH.
3. **Override.** The map is a constant, and `eligible_slots(..., flex={...})` takes a different one, so a rule like "a second baseman can also play shortstop" is a one-line change.

Known-position players average 3.4 eligible slots (2026 file). About 38% of starters end up in a slot that is not their prior-season main position, most often 3B to 1B, 1B to DH and moves within the outfield.

### 2. Players with no known position: a guess from baserunning

A player with no MLB season last year (a rookie, an import from another league, a minor leaguer) has no prior position. His position is guessed from baserunning, using **BsR**, the baserunning runs column in the ZiPS files (stolen bases and advancement on the bases, in runs above average). Speed is a rough proxy for where a player fits, and BsR does order positions that way among players with known positions (runs per 600 PA, regulars with 200+ PA):

| C | DH | 1B | 3B | LF | RF | 2B | SS | CF |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| -0.93 | -0.76 | -0.72 | -0.55 | -0.18 | -0.03 | 0.00 | +0.38 | +0.49 |

**The rule.** BsR grows with playing time, so it is first converted to runs per 600 PA. Each player is ranked as a percentile against that season's batters projected for 200+ PA (the whole league, not one team), and the percentile picks the positions he is listed at (`BSR_BINS`):

| BsR percentile | Listed at | With flex, can play |
| --- | --- | --- |
| Slowest 20% (0 to 20) | 1B | 1B, DH |
| 20 to 40 | 3B, LF, RF | 3B, 1B, LF, CF, RF, DH |
| 40 to 60 | 2B | 2B, 1B, DH |
| 60 and up | CF, SS | CF, LF, RF, SS, 2B, 1B, DH |

The same flex rules apply as for any listed position, and everyone can DH. Players tagged this way have `position_source = "imputed_bsr"`. If a player has no BsR, he falls back to the outfield and DH (`default_outfield`).

**Does it help?** Checked on the 108 players in 2023–2026 who had no prior-season position and then got 200+ PA, by whether the position they actually played is in their eligible set:

| Rule | Hit rate | Average slots |
| --- | --- | --- |
| Outfield and DH for everyone (old default) | 40.7% | 4.0 |
| BsR guess, with flex | 64.8% | 5.5 |
| The same eligible sets handed out to players at random | 56.5% (95th percentile 61.1%) | 5.5 |

Larger sets hit more often, so the fair comparison is with the shuffled sets. BsR beats 99.9% of 2,000 shuffles, so the signal is real, but it is worth about 8 points over chance, not a precise position guess. Two things limit it:

- **The bins don't split the group evenly.** Players with no prior season are young and fast. 53% of them fall at the 60th percentile or above, and only 15% in the slowest fifth. In the slowest fifth the guess is poor: 1B is the true position for 6% of them, and they play SS (29%) and RF (24%) more often.
- **Catchers are the slowest players.** Catchers have the lowest BsR of any position, so a slow no-prior player is as likely to be a catcher as a first baseman. No bin offers catcher.

**Playing time is the bigger problem, as with the old default.** The guessed players who win a starting slot (116 of 1,080 starter slots, 10.7%) average 180 real PA, 36% reach 200 PA and 33% play no PA for that team at all. Two switches on `build_batter_depth_chart` deal with it.

**`unknown_war_multiplier` (default 0.5).** Players whose position is a guess (`imputed_bsr` or `default_outfield`) have their projected WAR, and defense runs, multiplied by this factor before anyone is ranked. It changes how they rank as well as the WAR they are credited with. The clearest check is how much playing time guessed-position players are handed, because we know what they actually played: **536 PA per team** in 2023–2026. On the current allocation (120 team-seasons):

| Multiplier | PA given to guessed players (real: 536) | Guessed players who top a slot | Player error (PA) | Team WAR | Wins error |
| --- | --- | --- | --- | --- | --- |
| 1.00 (no trim) | 1,059 | 89 | 135.3 | 45.3 | 9.69 |
| 0.90 | 910 | 63 | 132.7 | 45.0 | 9.69 |
| 0.75 | 700 | 42 | 129.9 | 44.6 | 9.69 |
| 0.60 | 520 | 20 | 128.3 | 44.3 | 9.71 |
| **0.50** | **409** | **13** | **127.5** | 44.2 | 9.72 |
| 0.40 | 334 | 8 | 127.3 | 44.0 | 9.73 |
| 0.25 | 261 | 5 | 127.4 | 43.9 | 9.75 |

- **Without a trim, guessed-position players get about twice the playing time they really get.** They are unproven, but a rank-by-rate rule treats their projections as good as anyone's, and with replacement level in the ranking there are many of them to share time among. The trim corrects that.
- **0.5 is where the gain stops.** Player error falls from 135.3 to 127.5 and is flat below 0.5 (127.3 at 0.4). The wins error creeps up a little as the trim gets stronger (9.69 to 9.75), within noise but in one direction.
- **0.6 is the setting that matches the 536 PA** (520), and it costs 0.8 PA of error against 0.5. The two are close enough that I'd treat either as fine.
- **It moved from 0.75 because the allocation changed.** On the first version of the allocation (best starter at each slot, then backups), 0.75 was the sensible choice. The current allocation gives guessed players more time, so a stronger trim is needed.
- **Few guessed players are left at the top.** At 0.5 only 13 of 957 starters (top-ranked players at a slot) are guessed-position players, and they average 199 real PA (46% played 200 or more, 38% none). That is a small group, so those percentages are noisy.

**`unknown_can_start` (default True).** This controls how guessed-position players are ranked at a slot. With True they are ranked by WAR per PA like everyone else. With False they are ranked below every player whose position is known, at every slot, so they can only top a slot if no known player is eligible there. They are not removed: they still pick up backup PA. At the 0.5 trim it makes no difference (player error 127.5 either way, wins error 9.72 against 9.72), because the trim has already pushed them down the ranking. With the trim off, False does much better than True (126.8 against 135.3, wins error 9.63 against 9.69), but then gives guessed players only 271 PA per team against 536 real. The two switches overlap, and I left this one on.

### 3. Ranking a slot and sharing its plate appearances

**Rank.** At each slot, the eligible players are ranked from best to worst by projected WAR per plate appearance *at that slot*. Players below replacement level (negative WAR per PA) are left out.

- **DH is valued on batting only.** A DH has no defense, and the positional adjustment is -17.5 runs per 162 games ([FanGraphs](https://library.fangraphs.com/misc/war/positional-adjustment/)). For the DH slot a player's WAR is rebuilt as (WAR minus his `Def` runs/10) plus the DH adjustment, so a glove-first player doesn't win the DH job on defense he won't be using.

**Share.** The slot's season of plate appearances (640 at catcher and 700 at every other slot, 6,240 in total, from FanGraphs) is shared down the ranking by weights. Each step down the ranking multiplies the weight by two things:

- **`rank_decay` (default 0.5)** stands for rest days and injuries. Even a clear starter doesn't play every inning, and the next man up gets the time. With two equal players and replacement level behind them, the shares are 57%, 29% and 14%.
- **A gap term, exp(-`decay_per_war600` × the rate the next player gives up)** with the rate measured in WAR per 600 PA (default 0.5). The bigger the drop from one player to the next, the faster the weights fall. A slot with a big gap between its best player and the next gives its best player most of the slot, up to `max_slot_share` (0.92, about 150 of 162 games), and a slot with equally good options splits the time.

**Replacement level is the last entry in every ranking.** Plate appearances that no good player absorbs go to replacement level, which is worth zero WAR by definition, so they are left out of the team total instead of going to a weak player. On average the chart allocates 6,209 of the 6,240 PA.

**Does the gap really matter?** I tested the premise on 1,079 team-slots from 2023–2026, by the real playing time of each slot's top-ranked player:

| Gap between best and next player (WAR per 600 PA) | Top player's projected PA | Top player's real PA | Played almost none |
| --- | --- | --- | --- |
| Smallest quarter (0.04) | 502 | 377 | 12% |
| Second (0.47) | 519 | 415 | 10% |
| Third (1.05) | 534 | 481 | 7% |
| Largest quarter (2.34) | 564 | 528 | 3% |

Where the gap is largest, the top player really does play far more, so the premise holds. But part of that is the top player simply being better. In a regression of his real PA on his projected PA, the gap and his own rate, the gap adds little (+5.7 PA per WAR/600, standard error 7.8) while his own rate adds a lot (+31.9, standard error 6.5). That fits the sweep below, where a small gap term (0.5) helps and a large one hurts.

### 4. Cleanup: players who can fill several slots

A player eligible at several slots could be ranked high at all of them and be handed far more plate appearances than he can play. A first version that simply scaled his shares back everywhere smeared a star shortstop with seven eligible slots across all seven. The cleanup concentrates him instead:

1. **Home slot.** Each player's home slot is the one where he would get the most PA if nobody had a limit. He keeps full weight there and `secondary_weight` (0.5) at every other slot.
2. **Limits.** A player's total can't pass his own projected PA (or 700), and no slot gives one player more than `max_slot_share` of its PA.
3. **Scale back, away from home first.** When a player is over his limit, his shares at his *other* slots are scaled back, and the freed plate appearances go to the next players at those slots. This repeats until nobody is over. His home slot is only reduced by the limits themselves.

On one 2026 team, a guessed-position player listed at CF and SS (eligible at seven slots) gets his full projected PA, about 65% of the SS slot and the rest at his other slots, and no one is over his projection.

## Pitchers

**Who is a starter.** A pitcher is a starter if ZiPS projects at least **15 starts** (`classify_pitcher_role`). I checked cutoffs against what pitchers actually did (pitchers with 30+ real IP, starter meaning they started at least half their games):

| Rule | Accuracy | Precision (called starters who really were) | Recall (real starters found) |
| --- | --- | --- | --- |
| 10+ projected starts | 85.8% | 76.4% | 97.7% |
| **15+ projected starts** | **88.0%** | 82.4% | 92.4% |
| 18+ projected starts | 86.7% | 85.1% | 84.6% |
| 20+ projected starts | 84.3% | 86.6% | 75.9% |
| Starts ÷ games at least 0.5 | 87.6% | 80.3% | 95.1% |
| Top 5 per team by projected starts | 76.0% | 92.4% | 49.3% |

The top-five rule looks tidy, but it finds half of real starters and captures only 55% of real starter innings, because teams use about seven starters a year. At 15 starts the label captures 93% of starter innings. The weakness is false positives: ZiPS projects many pitchers who never reach the majors for 15+ starts.

**How innings are shared** (`build_pitcher_depth_chart`). Team innings default to 1,500 (the FanGraphs figure). Starters share 57% of them, which matches the real split (starters throw 56.7% of a team's innings). The five best starters get a full slot (171 IP) or their projection if lower. Any shortfall goes to the next starters with a decay of 0.5. Relievers share the remaining 43% with a decay of 0.85, ranked by WAR per inning, and relievers projected for under 20 IP are not ranked.

## Does it work?

It does what it is built to do: it tracks real playing time better. It does not beat the simplest rule at predicting wins, and it overstates team WAR.

**Batters** (ZiPS 2023–2026, 120 team-seasons; "player error" is the RMSE of allocated against actual PA):

| Method | Player error (PA) | Mean batting WAR |
| --- | --- | --- |
| Regulars first, ranked by projected PA | 176.2 | 18.3 |
| Regulars first, ranked by WAR/PA | 135.4 | 28.5 |
| First depth chart (best starter at each slot, then backups) | 125.0 | 25.8 |
| **Depth chart now (rank, gap decay, cleanup)** | **127.5** | 27.1 |

**Whole team** (batters plus pitchers, wins error from team WAR with a line fitted leaving one season out; a typical team has about 33 WAR above replacement):

| Method | Mean team WAR | Wins error | Correlation with wins |
| --- | --- | --- | --- |
| Volume-ranked batters, regulars-first pitchers | 36.5 | **9.30** | **0.63** |
| WAR/PA-ranked batters, regulars-first pitchers | 46.7 | 9.66 | 0.60 |
| First depth chart | 42.9 | 9.74 | 0.59 |
| **Depth chart now** | 44.1 | 9.72 | 0.59 |

Pitcher innings are slightly closer to reality than the earlier rule (player error 33.9 IP against 34.9).

**The newer allocation matches real playing time a little worse than the first version** (player error 127.5 against 125.0) and shows more of the team-WAR inflation (44.1 against 42.9). The wins error is about the same (9.72 against 9.74). What it gives in return is structure: playing time that responds to the gap between a slot's players, replacement level in place of a forced fill, and a cleanup that keeps multi-position players concentrated and within their own projections.

**Sensitivity of the two decay settings** (everything else at its default):

| Setting | Player error (PA) | Typical starter's PA | Team WAR | Wins error |
| --- | --- | --- | --- | --- |
| `rank_decay` 0.25 | 133.2 | 505 | 44.5 | 9.69 |
| `rank_decay` 0.4 | 130.0 | 501 | 44.3 | 9.71 |
| **`rank_decay` 0.5 (default)** | **127.5** | **496** | 44.1 | 9.72 |
| `rank_decay` 0.6 | 124.8 | 490 | 43.8 | 9.71 |
| `rank_decay` 0.8 | 119.4 | 463 | 42.2 | 9.73 |
| `decay_per_war600` 0 (no gap term) | 128.5 | 485 | 42.9 | 9.72 |
| **`decay_per_war600` 0.5 (default)** | **127.5** | **496** | 44.1 | 9.72 |
| `decay_per_war600` 1 | 128.9 | 499 | 44.3 | 9.73 |
| `decay_per_war600` 2 | 132.1 | 503 | 44.3 | 9.67 |

- **A flatter decay always lowers the error against real PA**, but starters then play less than real starters do. The real top-nine hitters average about 505 PA. A value of 0.8 has the lowest error (119.4) but gives starters 463 PA and only a 41% share of the slot. The error rewards hedging against not knowing who will actually play. 0.5 splits the difference between realism (0.4, 501 PA) and hedging (0.6, 490 PA, error 124.8, now slightly below the first version's 125.0).
- **The gap term helps a little at small values** (0.5 is 1 PA better than none) and hurts at large ones. The wins error moves by 0.06 or less, which is noise.
- **`secondary_weight` (0.15 to 1.0) and `max_slot_share` (0.8 to 1.0) barely matter** (player error 133.0 to 134.1). The home-slot cleanup does the work, so these mostly affect how the chart looks, not how it scores.
- **The guessed-position trim matters most.** With no trim (`unknown_war_multiplier` 1.0) player error is 135.3 against 127.5 at the default 0.5. See the unknown-position section above for the full table.

**What this tells us.** Any rule that picks the *best-looking* players from noisy projections overstates team WAR, because the winners are partly lucky estimates. The more carefully a rule chooses, the more this shows up (36.5, then 42.9 to 44.7, then 46.7 mean team WAR). The wins error roughly follows the same ordering, and the simple volume rule is still best. The depth chart's advantage is that its output is realistic at the player level (who plays, where, how many PA), which the wins check can't show. If the goal is the team total, the depth chart needs its projected WAR shrunk toward replacement for uncertain players, mostly those with no MLB history. I haven't built that beyond the guessed-position trim.

Pitcher settings: starter IP share 0.5 to 0.65 and relief decay 0.7 to 0.95 barely moved the pitcher results.

## Limits

- **The prior-season position is only a guess about this season.** About 9% of real hitter PA belong to players with no prior position, who get the BsR guess above (a modest improvement over chance) and a 0.5 WAR trim. 91 to 94% of the others are covered. A player-position model is on the roadmap.
- **WAR is not re-based by slot, except at DH.** A player filling a different slot than his ZiPS position keeps his ZiPS WAR. For example, a shortstop playing second keeps shortstop credit.
- **Managers don't pick by WAR.** Contracts, service time and platoons matter. For example, a Pirates outfielder who got about 700 PA in 2026 is only a DH backup in the 2026 chart because ZiPS rates him at about 1 WAR.
- **Four seasons.** The checks use 2023–2026, the ZiPS download dates are not recorded yet, and the wins check uses only team WAR.
- **Not wired in.** There is no registered model that turns the depth chart into a win forecast yet.

## Using it

```python
from bucco.models import depth_chart as dc

pool = dc.build_batter_pool(zips_batters_for_a_team, player_position_games_for_the_season)
players, allocations = dc.build_batter_depth_chart(pool)     # PA and scaled WAR by player and slot
pitchers = dc.build_pitcher_depth_chart(zips_pitchers_for_a_team)
team_war = players["scaled_war"].sum() + pitchers["scaled_war"].sum()
```

`zips_batters_for_a_team` needs `mlbam_id`, `pa`, `war` and optionally `def_runs`. The pitcher frame needs `ip`, `war` and `gs`. `depth_chart_by_team` does the batter step for every team and season.

## Shrinking defense (`def_weight`)

ZiPS WAR includes `Def` (fielding plus the positional adjustment). Regressing allocation error
(allocated minus real PA) on batting and defense runs per 600 PA, for batters projected at 200+
PA in 2023-2026, gave +2.56 PA per defense run against +0.76 per batting run: the depth chart
gave glove-first players about 3.4 times too much credit. We keep only `def_weight` of each
player's `Def` before ranking: WAR is replaced by `WAR - (1 - def_weight) * Def / 10`, and the
shrunk WAR is used only to rank players and share PA. The WAR a player is credited with for the PA he gets is still his unshrunk ZiPS rate, so shrinking does not change how much WAR a played PA is worth (an earlier version credited the shrunk WAR, which raised wins error from 9.72 to 9.77-9.94).

| def_weight | PA error | Starter PA | Team WAR | Wins error |
| --- | --- | --- | --- | --- |
| 1.00 | 127.5 | 496 | 44.2 | 9.72 |
| 0.75 | 123.7 | 502 | 44.0 | 9.69 |
| 0.50 | 121.3 | 504 | 43.6 | 9.73 |
| **0.40** | **120.8** | 505 | 43.4 | 9.72 |
| 0.30 | 121.4 | 506 | 43.1 | 9.74 |
| 0.00 | 122.0 | 506 | 41.9 | 9.68 |

The default is 0.4, where the defense bias is zero and PA error is lowest. Wins error is flat (9.72 at 0.4). Caveat: `Def` includes the positional adjustment, so
this also shrinks the credit catchers and shortstops get for their position.

### Shrinking only the fielding part (`position_weight`)

`Def` is fielding plus a positional adjustment (C +12.5, SS +7.5, ... 1B -12.5, DH -17.5 runs
per 162 games). We split it using each player's prior-season primary position and kept the
two parts at separate weights. Splitting did not help:

| def_weight (fielding) | position_weight | PA error | Wins error |
| --- | --- | --- | --- |
| 0.4 | 0.4 (same as uniform) | 120.8 | 9.72 |
| 0.4 | 1.0 | 121.7 | 9.73 |
| 0.2 | 0.5 | 120.6 | 9.74 |

Keeping the full positional credit costs 0.9 PA of error, and the best split (0.2 / 0.5)
beats the uniform 0.4 by only 0.2 PA. Default stays at 0.4 for both. Only about a third of
projected players have a prior-season position, so the split can only apply to them.

## Slot position credit (`slot_position_credit`)

Outside DH the depth chart used to take a player's ZiPS WAR rate at every slot he can fill, so
a shortstop playing first base kept his shortstop positional credit. Now a player with a known
prior-season primary position who fills another slot has his positional adjustment swapped for
that slot's (shortstop +7.5 to first base -12.5 runs per 162 games, so -2 WAR per 700 PA). This
applies to ranking (at `position_weight`) and to the WAR credited (in full). His fielding runs
are assumed to carry over. Players with no known primary position are unchanged.

| slot credit | def_weight / position_weight | PA error | Team WAR | Wins error | Defense bias (PA per run) |
| --- | --- | --- | --- | --- | --- |
| off | 1.0 / 1.0 | 127.5 | 44.1 | 9.72 | +2.56 |
| on | 1.0 / 1.0 | 128.2 | 43.7 | 9.66 | +1.77 |
| off | 0.4 / 0.4 | 120.8 | 43.4 | 9.72 | +0.10 |
| **on** | **0.4 / 0.4** | 121.3 | 43.1 | 9.66 | -0.35 |
| on | 0.4 / 1.0 | 122.7 | 43.2 | 9.64 | -0.23 |
| on | 0.2 / 1.0 | 122.7 | 42.8 | 9.59 | -0.91 |

The credit alone cuts the defense bias from 2.56 to 1.77 and lowers wins error by about 0.06,
with PA error 0.5 higher. The wins gain is small next to the noise (even a perfect playing-time allocation only gets wins error to about 8.9),
so it is kept because it is the correct accounting, not because it is a measurable win.

## Off-position penalty (`off_position_penalty`)

A player at a non-DH slot other than his prior-season primary position has `off_position_penalty`
runs per 700 PA taken off his ranking rate. It affects ranking only; credited WAR is unchanged.
Players with no known primary position are never penalized. (This is separate from
`secondary_weight`, which halves weights at any slot that is not the player's home slot, meaning
where he would get the most PA, not his listed position.)

| Penalty (runs per 700 PA) | PA error | Starter PA | Team WAR | Wins error |
| --- | --- | --- | --- | --- |
| 0 | 121.3 | 504 | 43.1 | 9.66 |
| 2 | 121.5 | 497 | 43.1 | 9.68 |
| 5 | 120.6 | 498 | 43.0 | 9.67 |
| **8** | **119.9** | 498 | 42.9 | 9.66 |
| 12 | 120.5 | 497 | 42.7 | 9.65 |
| 20 | 121.3 | 495 | 42.4 | 9.64 |

The gain is small (1.4 PA at best) and not monotonic, so it is within noise; wins error does not
move. The constant penalty is now off by default (see below).

### As a multiplier (`off_position_multiplier`)

The same idea as a factor on the ranking rate instead of a fixed run cost, so it scales with
how good the player is. Applied only to positive rates at off-position slots, ranking only.

| Multiplier | PA error | Starter PA | Team WAR | Wins error |
| --- | --- | --- | --- | --- |
| 1.00 (off) | 121.3 | 504 | 43.1 | 9.66 |
| 0.90 | 121.5 | 499 | 43.0 | 9.67 |
| 0.80 | 120.3 | 499 | 43.0 | 9.67 |
| **0.70** | **119.7** | 499 | 42.9 | 9.66 |
| 0.60 | 120.1 | 499 | 42.8 | 9.67 |
| 0.50 | 120.3 | 499 | 42.7 | 9.65 |
| 0.30 | 121.5 | 495 | 42.3 | 9.65 |
| (8-run penalty) | 119.9 | 498 | 42.9 | 9.66 |

The multiplier at 0.7 is equivalent to the 8-run penalty (119.7 vs 119.9), with a wide flat
region from 0.5 to 0.8. Default is multiplier 0.7 and penalty 0.

## Recommended parameters

These are the current defaults in `src/bucco/models/depth_chart.py`, retuned on ZiPS 2011-2021
(see "Retuning on 2011-2021" at the end) and held out on 2022-2026. Earlier values, tuned one at a
time on 2023-2026, were rank_decay 0.5, decay_per_war600 0.5, secondary_weight 0.5,
unknown_war_multiplier 0.5, def_weight and position_weight 0.4.

| Group | Parameter | Value | What it does |
| --- | --- | --- | --- |
| PA sharing | `rank_decay` | 0.7 | Each rank's weight as a fraction of the rank above it, before gaps. Lower means the top player takes more of the slot. |
| | `decay_per_war600` | 0.25 | Extra drop in weight per 1.0 WAR/600 the next player gives up, so a slot with no viable backup gives its top player more. |
| | `secondary_weight` | 0.25 | Multiplier on a player's weight at every slot except his home slot (where he would get the most PA), so multi-position players mostly stay home. |
| | `max_slot_share` | 0.92 | The most of one slot's PA a single player can take. |
| | PA caps | 700 per player; slots 640 (C), 700 (others) | FanGraphs' team assumptions; the rest of a slot goes to replacement level. |
| Eligibility | `MIN_ELIGIBLE_GAMES` | 20 | Prior-season games at a position needed to count as able to play it. |
| | Flex rules | see `FLEX_SLOTS` | Which extra slots a listed position can fill (SS also 2B/1B, any infielder also 1B, outfielders any outfield spot, everyone DH). |
| Unknown positions | `unknown_war_multiplier` | 0.1 | Multiplies WAR and defense of players whose position is a guess (no prior MLB season), making them rank lower and count for less. |
| | `unknown_can_start` | on | If off, guessed-position players rank below every known player at each slot. Redundant at 0.5. |
| Defense | `def_weight` | 0.7 | Share of fielding runs kept when ranking; the rest is removed from WAR/PA for ranking only. |
| | `position_weight` | 0.7 | Same, for the positional adjustment of players with a known primary position. Equal to `def_weight`, so no split. |
| | `slot_position_credit` | on | A player at a slot other than his primary position has his positional adjustment swapped for the slot's, in ranking and credited WAR. |
| Off position | `off_position_multiplier` | 0.7 | Factor on a positive ranking rate at a non-DH slot other than his primary position. Ranking only. |
| | `off_position_penalty` | 0 | The same idea in runs per 700 PA; off so it is not stacked with the multiplier. |
| Credited WAR | (not a parameter) | unshrunk ZiPS | Team WAR always uses ZiPS WAR per PA played; only ranking uses shrunk values. |

## Baseline and how to re-evaluate

Tuned on ZiPS 2023-2026 (120 team-seasons), one parameter at a time, no holdout. Baseline at
the recommended defaults (as of 2026-11-22):

| Player PA error | Starter PA | Team WAR (batters + pitchers) | Wins error (leave-one-season-out) | Corr with wins |
| --- | --- | --- | --- | --- |
| 119.7 | 498.8 | 42.9 | 9.66 | 0.596 |

For reference: no defense shrink or position fixes gave 127.5 / 496 / 44.2 / 9.72; the simple
volume-ranked baseline predicts wins at about 9.30; a perfect playing-time allocation (ZiPS
rates times real PA) gives about 8.9, which bounds what PA allocation can do for wins.

To re-run after adding seasons:

1. Put the new `zips_batters_individual_<year>.csv` and `zips_pitchers_individual_<year>.csv`
   files in `data/manual/projections/` and list them in `_player_downloads.csv`.
2. `uv run bucco player-projections`, then `dbt build` (the mlb-positions cache already covers
   2000-2026, and real PA is cached for 2015-2026 under `data/cache/mlb_api/hitting_pa/`).
3. `uv run python scripts/eval_depth_chart.py` for the defaults, or a sweep such as
   `uv run python scripts/eval_depth_chart.py --grid def_weight=1,0.6,0.4,0.2`, or an override
   such as `... off_position_multiplier=0.8`.

What to check first with more seasons: (a) tune on all but one season and score the held-out one;
(b) whether `def_weight` stays near 0.4 and the defense bias stays near zero; (c) whether
`secondary_weight`, `off_position_multiplier` and `unknown_war_multiplier` (which overlap) are
all still pulling their weight; (d) whether wins error ever moves with PA error.

## Adding 2022 (holdout check, 2026-11-22)

2022 was added after the parameters were tuned on 2023-2026, so it is an out-of-sample test.
(One 2022 pitcher, Ervin Santana, has no team in the file and is dropped by the extractor.)

Player PA error by season, defaults against the original unshrunk depth chart:

| Season | Defaults | No defense shrink or position fixes |
| --- | --- | --- |
| **2022 (holdout)** | **129.0** | 132.9 |
| 2023 | 118.4 | 121.2 |
| 2024 | 126.3 | 134.1 |
| 2025 | 115.2 | 124.7 |
| 2026 | 119.3 | 129.8 |

The gain holds in 2022 but is smaller (3.9 PA, against 3 to 10 elsewhere), and 2022 is the
worst season for both. Wins error for 2022, using a line fit on 2023-2026 only, is 10.2 for
the defaults against 10.4 unshrunk.

All five seasons (150 team-seasons), leave-one-season-out wins error of team WAR (batters +
pitchers) from `scripts/eval_depth_chart.py --compare`:

| Method | Team WAR | Wins error | Corr | Batters only |
| --- | --- | --- | --- | --- |
| ZiPS WAR summed, no allocation | 48.4 | 10.83 | 0.51 | 11.74 |
| Volume-ranked, 6,240 PA budget | 32.2 | **9.56** | 0.65 | 10.37 |
| Rate-ranked regulars first | 45.3 | 9.82 | 0.63 | 10.91 |
| Depth chart (ours) | 42.5 | 9.79 | 0.63 | 10.70 |
| Oracle: ZiPS rates x real PA | 41.3 | 9.01 | 0.71 | 10.15 |

At the defaults on all five seasons: PA error 121.4, starter PA 497, team WAR 42.5, wins error
9.79, corr 0.631.

## Adding 2011-2021 (2026-11-22)

ZiPS files for 2010-2021 were added (2010 has no team on any row, so it is skipped; 2020 is left
out of scoring because it was a 60-game season). The defaults were not retuned. Data repairs in
the extractor: the Marlins' rows are blank in the 2011 and 2013 files and are assigned to MIA
(the only team missing); 3 rows with no name or MLB id are dropped; free agents (no team) are
dropped. None of the files has a download date, so the no-peeking check cannot confirm they are
true preseason projections.

Team WAR drifts a lot between seasons (league average about 20 in 2011-2013, 35 in 2014-2019, 41-45
in 2022-2026), so wins error now centers each season's team WAR on that season's league mean
before fitting the line. With 15 seasons (450 team-seasons), leave-one-season-out:

| Method | Wins error 2011-2026 | 2011-2021 | 2022-2026 |
| --- | --- | --- | --- |
| ZiPS WAR summed, no allocation | 10.51 | 10.48 | 10.67 |
| Volume-ranked, 6,240 PA budget | 10.00 | 10.33 | **9.44** |
| Rate-ranked regulars first | 9.70 | 9.81 | 9.55 |
| Depth chart (ours) | **9.69** | **9.78** | 9.59 |
| Oracle: ZiPS rates x real PA | 8.92 | 9.10 | 8.62 |

At the defaults, PA error is 137.7 over all seasons, 149.1 for 2011-2021 and 121.4 for 2022-2026
(about 150 in every season before 2022). The older files have about 15,800 projected batter PA
per team against 25,000 now, so older ZiPS already spread playing time more realistically and
the volume-ranked rule does worse there. The depth chart is steadier across eras; the
volume-ranked rule is best in the recent era only.

## Retuning on 2011-2021 (2026-11-22)

Search: coordinate descent on 2011-2021 (10 seasons, 300 team-seasons) minimizing player PA
error, accepting a change only if it cut error by more than 0.3 PA. Held out: 2022-2026.
Fixed rather than tuned: `max_slot_share` 0.92 (no effect), `slot_position_credit` on,
`off_position_penalty` 0, `position_weight` tied to `def_weight`, `unknown_can_start` on (off
gained under 0.2 PA), `off_position_multiplier` 0.7 (never moved; every value from 0.5 to 0.9
was within 0.6 PA).

| Parameter | Before | After |
| --- | --- | --- |
| `rank_decay` | 0.5 | 0.7 (top of the grid; 0.6 also beat 0.5) |
| `decay_per_war600` | 0.5 | 0.25 |
| `secondary_weight` | 0.5 | 0.25 |
| `unknown_war_multiplier` | 0.5 | 0.1 (bottom of the grid except 0.1; 0.2 was within 0.5 PA) |
| `def_weight` = `position_weight` | 0.4 | 0.7 |

| Set | Seasons | PA error | Starter PA | Team WAR | Wins error |
| --- | --- | --- | --- | --- | --- |
| Before | 2011-2021 (train) | 149.1 | 509 | 32.2 | 9.78 |
| After | 2011-2021 (train) | 138.7 | 470 | 30.5 | 9.80 |
| Before | 2022-2026 (holdout) | 121.4 | 497 | 42.5 | 9.59 |
| After | 2022-2026 (holdout) | 117.4 | 459 | 40.6 | 9.61 |
| Before | all 15 seasons | 137.7 | 505 | 35.6 | 9.69 |
| After | all 15 seasons | 129.8 | 466 | 33.9 | 9.72 |

PA error falls on the holdout too (4 PA), but wins error does not move. The tuned allocation is
flatter, so a starter gets about 460 PA against about 500 for real starters: the error falls by
hedging.

## Pitchers: first look across 2011-2026 (2026-11-22)

Real innings and starts come from the MLB fielding cache (position P). 15 seasons, 450
team-seasons, defaults unchanged since the original pitcher depth chart.

* Coverage: ZiPS has about 47 pitchers per team and 3,766 projected IP per team (real teams
  throw about 1,442); the pitchers in the ZiPS file account for 90.6% of real innings.
* Innings error per pitcher: 44.2 (raw ZiPS IP: 66.8).
* Roles (ZiPS GS >= 15 means starter): finds 94.4% of real starters (15+ real starts, 30+ IP)
  and 95.1% of their innings.
* Team pitching WAR to wins (centered, leave-one-season-out):

| Method | Team pitching WAR | Pitching only | Plus tuned batter depth chart |
| --- | --- | --- | --- |
| Raw ZiPS WAR summed | 13.4 | 11.26 | 10.03 |
| Volume-ranked, 1,500 IP | 9.6 | 11.16 | 9.79 |
| Pitcher depth chart | 13.4 | 10.84 | **9.72** |
| Oracle: ZiPS rate x real IP | 10.3 | 10.30 | 9.38 |

Batters alone (tuned depth chart): 10.07, so pitching improves the total by about 0.35 wins.
Pitching-only error is 10.84, worse than batting-only (10.07).

Pitcher parameters (starter share of IP 0.45-0.65, rp_decay, sp_decay, min_starts 8-20,
rotation size 4-6, min_rp_ip) move IP error by under 2 and total wins error by under 0.02, so
they are left alone. Open items: no pitcher-specific injury or innings forecast (roadmap TODO),
relievers are ranked by WAR/IP with no leverage, and team pitching WAR (13.4) is about 3
above what real innings at ZiPS rates give (10.3).

## As a registered model: `depth_chart` (rung 5a)

`src/bucco/models/depth_chart_model.py` wraps the depth chart as a model the backtest and
forecast commands can run. For a target season it runs every team's ZiPS batters and pitchers
through the depth chart (all current defaults), sums team WAR, subtracts that season's league
average, and maps it to win percentage with a least-squares line fit on earlier seasons only
(about 1.1 wins per WAR). With under two earlier seasons of projections it uses one win per
WAR. The spread is the residual SD of earlier forecasts, never below the 6.4-win luck floor.
Projections dated after the forecast's as-of date are ignored. The database read is in
`src/bucco/models/player_inputs.py`, so the model class itself reads nothing.

Walk-forward backtest, 2011-2026 without 2020 (450 team-seasons, every model trained on earlier
seasons only):

| Model | MAE | RMSE (wins) | 80% coverage |
| --- | --- | --- | --- |
| **depth_chart** | **7.91** | **9.75** | 0.78 |
| holt | 8.75 | 11.04 | 0.78 |
| last_year | 9.49 | 11.79 | 0.78 |
| constant | 10.04 | 12.30 | 0.77 |

Pirates error (predicted minus actual wins): 2022 +6.0, 2023 -4.5, 2024 +0.7, 2025 +5.9,
2026 -4.0. The 2027 forecast needs the 2027 ZiPS files, which are not out yet.
