# Lineup optimizer: best PA by player and position (first pass, 2026-11-23)

Code: `src/bucco/models/lineup_optimizer.py`. Tests: `tests/test_lineup_optimizer.py`.

The depth chart (and Steamer's own playing time) estimates how a team *will* use its batters.
This asks a different question: given each player's projected hitting and defense, how *should*
a team spread its plate appearances over positions to get the most batting WAR?

## Rules

- **Same PA for every team.** 640 at C and 700 at each other position, DH included (6,240).
- **Replacement level is always available**, at 0 WAR, for any position.
- **In-season additions** (optional, off by default). `RESERVE_PA` per team, spread over
  positions in proportion to their PA, goes to players not on the preseason list (trades,
  call-ups), valued at replacement level. It made wins error slightly worse (step 5).
- **Most PA for one player:** 700 (`MAX_PA`).
- **Batting** is the projection's `Off` (batting + baserunning) per PA, plus replacement-level
  credit (20.3 runs per 600 PA for Steamer 2027). WAR = runs / runs-per-win (9.76), both fit to
  the projection's own WAR, which they reproduce within about 0.13 WAR per player.
- **Fatigue.** The batting rate falls as PA rise, faster and faster:
  `rate(x) = Off/PA - c * ((x/600)^k - (projected PA/600)^k)` above the projected PA, and half
  that change (`REST_BONUS` 0.5) below it. At the projection's own PA the rate is the
  projection's. Fewer PA give a slightly better rate (rest, platoon use), more PA a worse one.
  This is meant to stand in for rest days, platooning and wear. Defaults: c = 0.015, k = 2.
- **Defense.** The projection's `Def` (fielding + positional adjustment) is taken to be at the
  player's most-played position last season (or, with no MLB games, the position its adjustment
  implies). Because every team fills every position with the same PA, the positional adjustments
  add up to the same total whatever the alignment; what decides who plays where is fielding
  relative to the average player at each position (and, for DH, the DH adjustment). At another
  position a player's fielding changes by the amount fitted from Statcast OAA (below). At a
  position he did **not** play last season he also pays a selection penalty. Only catchers catch;
  a catcher elsewhere fields like an average first baseman, a DH-only player like a
  below-average one (−5), and a part-time catcher catches at −5. DH is −17.5 for everyone. A
  0.05-run tie-break prefers a player's own position.

**Method.** A linear program per team (scipy HiGHS). The fatigue curve is concave, so it is cut
into 25-PA steps that fill in order, which makes the problem an exact LP. Players are capped at
750 PA. All 30 teams take about 2 seconds.

## What we tried

1. **First version** used Steamer's fielding at every position a player had played. A first
   baseman with 20+ games in right field then gained RF's milder adjustment (−7.5 vs −12.5) for
   free and was moved to right field. Fixed by anchoring `Def` at the main position (above).
   The switching penalties were hand-set at first (half the drop in positional adjustment kept
   when moving down, plus guessed costs); they are now fitted (next section).
2. **Fatigue with k = 2, calibrated on 2012–2026 Steamer** (2020 left out) against real PA:

   | c | k | PA error | 650+ PA seasons/year (real 38) | Wins error | 2022–26 |
   | --- | --- | --- | --- | --- | --- |
   | 0.005 | 2 | 111.2 | 132 | 9.76 | 9.58 |
   | 0.01 | 2 | 97.0 | 82 | 9.73 | 9.56 |
   | **0.02** | **2** | **85.6** | **29** | **9.69** | **9.54** |
   | 0.03 | 2 | 81.7 | 9 | 9.66 | 9.52 |
   | 0.08 | 2 | 79.8 | 0 | 9.60 | 9.54 |
   | 0.02 | 4 | 92.7 | 1 | 9.66 | 9.49 |
   | 0.02 | 6 | 97.6 | 0 | 9.64 | 9.46 |

   PA error is over every projected player; Steamer's own PA score 77.5 on the same players and
   give 19 seasons of 650+. Wins error is leave-one-season-out with optimized batting WAR plus
   Steamer pitching WAR as given. The anchor at projected PA means a player given fewer PA than
   projected gets a better rate, and with a strong curve the optimizer exploits that by spreading
   PA thin (average team batting WAR rose to 28.6 at c = 0.08). c = 0.02 was chosen at first
   because it came closest to the real number of 650+ PA seasons. That was the wrong target: a
   preseason allocation is an expected value and cannot know which regulars stay healthy, so it
   should give out fewer 650+ seasons than happen (Steamer gives 19). See step 3.
3. **Where the PA error comes from** (c = 0.02). Allocated minus real PA, per player: the
   optimizer's top 9 per team got +52 (Steamer's own PA give the same players +57), its 10th to
   13th men +80 (Steamer −2). Both methods also hand out more PA than projected players really
   get (6,059 and 5,958 per team vs 5,638), because about 600 real PA per team go to players who
   join during the season. So starters are not over-allocated by the optimizer; the bench is.
4. **Reserve and rest bonus.** Holding 600 PA per team for in-season additions cut starter bias
   by 5–25 PA and bench bias by 15–55 PA. Removing the rest bonus did not fix the bench (it comes
   mostly from choosing bench players by projected rate) and pushed more PA to starters; half a
   bonus worked best. Sweep (hand-set position penalties at the time):

   | c | Rest bonus | Reserve | PA error | Starter bias | Bench bias | Wins error | 2022–26 |
   | --- | --- | --- | --- | --- | --- | --- | --- |
   | 0.02 | 1.0 | 0 | 85.9 | +52 | +80 | 9.69 | 9.54 |
   | 0.02 | 1.0 | 600 | 84.0 | +38 | +49 | 9.72 | 9.54 |
   | 0.02 | 0.0 | 600 | 88.8 | +83 | +41 | 9.73 | 9.56 |
   | **0.04** | **0.5** | **600** | **78.7** | **+17** | **+27** | 9.68 | 9.52 |
   | 0.04 | 1.0 | 0 | 80.5 | −20 | +49 | 9.64 | 9.51 |

   These were the defaults for a while (c = 0.04, rest bonus 0.5, reserve 600; with the fitted
   position matrix: PA error 79.2, wins error 9.69, 9.52 on 2022–2026).
5. **The fatigue curve was standing in for everything that keeps players off the field.**
   Tuning c to real PA made it absorb injuries, slumps, platoons and managers' choices, so the
   optimizer copied real usage (roughly Steamer's playing time) instead of optimizing. At
   c = 0.04 a Pirates DH plate appearance from Ryan O'Hearn (+9 runs per 600 over replacement
   before fatigue) was worth less than a replacement player's after 400 PA, and 227 DH PA went
   to replacement level; no Pirate reached 600 PA. Settings were re-chosen by **wins error**
   (the forecast goal), with realistic lineups as the tie-break. Leave-one-season-out, 2012–2026
   (2020 left out), cap 700:

   | c | Rest bonus | Reserve | Wins error | 2012–21 | 2022–26 | 600+ / 650+ PA seasons per year |
   | --- | --- | --- | --- | --- | --- | --- |
   | 0.04 (cap 750) | 0.5 | 600 | 9.691 | 9.826 | 9.519 | 34 / 10 |
   | 0.03 | 0.5 | 600 | 9.703 | 9.843 | 9.520 | 46 / 18 |
   | 0.02 | 0.5 | 0 | 9.697 | 9.833 | 9.523 | 72 / 37 |
   | **0.015** | **0.5** | **0** | **9.709** | **9.851** | **9.523** | **89 / 53** |
   | 0.015 | 0.5 | 600 | 9.734 | 9.882 | 9.531 | 79 / 44 |
   | 0.01 | 0.5 | 600 | 9.753 | 9.905 | 9.542 | 98 / 66 |
   | 0.005 | 0.5 | 600 | 9.776 | 9.932 | 9.552 | 131 / 105 |

   Real seasons: 74 with 600+ PA and 40 with 650+ per year. Stronger fatigue predicts slightly
   better, but everything from c = 0.015 to 0.04 without the reserve is within 0.02 wins, well
   inside the noise. The reserve cost 0.02–0.03 at every c and was dropped. Rest bonus barely
   matters (0.004). **Defaults: c = 0.015, rest bonus 0.5, no reserve, 700-PA cap.** c = 0.02
   predicted 0.012 better but sent 140 Pirates DH PA to replacement level; c = 0.015 gives a
   believable Pirates lineup (Griffin 650, Cruz 625, Reynolds 600, O'Hearn 475 at DH) with no
   replacement DH. PA error is 91 (Steamer's own PA: 72.8), which is no longer the target.

## Fitting the position-switch matrix (Statcast OAA)

`scripts/fit_position_switch.py` fits how fielding changes when a player moves, from Baseball
Savant OAA by player, position and season (2016–2026; 7 positions, C not covered), with innings
from the MLB fielding data. The output, `data/derived/position_switch.csv`, is what the
optimizer reads.

- **Centering.** OAA is not centered at each position: outfielders are judged on the same plays,
  so the average center fielder is about +5 runs a season and the average left fielder −3. Each
  position-season is centered on its innings-weighted average first.
- **Delta method.** 2,123 same-season pairs: a player's fielding runs per full season (1,350
  innings) at a second position minus at his main one, weighted by the harmonic mean of innings.
- **Additive fit.** change(p → q) = difficulty(p) − difficulty(q), by weighted least squares.
  Difficulty, in fielding runs per full season: 1B 0, 3B 4.1, LF 4.8, RF 5.0, 2B 6.0, SS 10.0,
  CF 13.2. Only the additive part is used: the per-move averages are noisy and not additive, and
  the optimizer exploited that through loops of moves (RF → 1B → CF → RF came to +6 runs, and
  3,900 of 6,240 PA per team went to unplayed positions).
- **First season at a new position:** no extra cost beyond the fitted change (about −1 run, 178
  moves), so none is added.
- **Selection penalty** (a judgment call, not fitted: the switchers in the data were chosen
  because teams expected them to cope). At a position the player did not play last season:
  `SELECTION_BASE` (2 runs per 700 PA) + `SELECTION_UP` (0.5) × any rise in difficulty.

Fielding change at a position he did not play, after the selection penalty (runs per 700 PA,
relative to the average player there; rows from, columns to):

| From \ To | 1B | 2B | 3B | SS | LF | CF | RF |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 1B | 0 | −10.9 | −8.1 | −17.0 | −9.2 | −21.8 | −9.5 |
| 2B | +4.0 | 0 | −0.1 | −8.1 | −0.9 | −12.9 | −1.1 |
| 3B | +2.1 | −4.8 | 0 | −10.9 | −3.1 | −15.7 | −3.4 |
| SS | +8.0 | +2.1 | +3.9 | 0 | +3.2 | −6.8 | +3.0 |
| LF | +2.8 | −3.7 | −1.3 | −9.8 | 0 | −14.6 | −2.3 |
| CF | +11.2 | +5.2 | +7.1 | +1.2 | +6.4 | 0 | +6.2 |
| RF | +3.0 | −3.4 | −1.1 | −9.5 | −1.8 | −14.3 | 0 |

Selection penalty check (2012–2026 Steamer, 2020 left out; c = 0.02, full rest bonus, no
reserve, i.e. the fatigue settings before step 4):

| Selection | PA error | Wins error | 2022–26 | Unplayed-position PA per team (2027) |
| --- | --- | --- | --- | --- |
| none | 87.2 | 9.70 | 9.53 | 852 |
| **2 + 0.5 × rise (default)** | 86.4 | 9.70 | 9.54 | 346 |
| 4 + 1.0 × rise | 86.0 | 9.70 | 9.54 | 222 |

Forecast accuracy barely moves; the penalty mainly stops the optimizer from inventing value by
moving players. With the default, the common moves are the ones teams make: catchers to first,
corner outfielders and shortstops to third.

Caveats: OAA measures range and (for infielders) throws, not outfield arms, so it rates 3B as
easier than the corner outfield spots; FanGraphs' adjustments rank them the other way. Catchers
and DH-only players are placed by assumption.

## Results so far

With the current defaults (fitted position matrix, c = 0.015, rest bonus 0.5, no reserve, cap 700):

- **It does not beat Steamer's own playing time** at predicting wins (9.71 leave-one-season-out
  vs 9.58 for the `steamer` model; 9.52 vs 9.45 on 2022–2026), though the gap is small. Real
  teams don't play optimal lineups, and optimizing on projections favors players whose
  projections run high.
- **2027 (Steamer, November file).** Pirates 18.3 batting WAR (27th, league average 22.7):
  Griffin at short (650 PA), Cruz in center (625), Reynolds in left (600), Valdez in right,
  Gonzales at third, Horwitz at first, O'Hearn at DH (475).

## As a registered model: `steamer_optimized` (rung 5a)

`PlayerData(..., playing_time="optimized")` runs each season's Steamer batters through the
optimizer and takes Steamer's pitchers as given (with the depth-chart fallback for a raw-list
file, as in `steamer`). The rest is the same `DepthChartModel`: team WAR centered on the league
average, a least-squares line to wins fit on earlier seasons only. Registered as
`steamer_optimized`.

Walk-forward backtest (every model trained on earlier seasons only, 2020 left out):

| Seasons | steamer | steamer_optimized | depth_chart | holt |
| --- | --- | --- | --- | --- |
| 2012–2026 (420 team-seasons) | **9.58** | 9.67 | 9.78 | 11.08 |
| 2022–2026 (150) | **9.45** | 9.46 | 9.57 | 10.80 |

(With the earlier settings, c = 0.04 and a 600-PA reserve: 9.65 and 9.45.)

Pirates error (predicted minus actual wins), `steamer_optimized` / `steamer`: 2022 +6.9 / +5.7,
2023 −3.1 / −2.7, 2024 −1.4 / −1.9, 2025 +3.5 / +4.6, 2026 −3.2 / −4.7.

2027 forecast (November Steamer file): Pirates 81.1 wins (80% range 68.8–93.5), 13th; Brewers
88.7. Re-optimizing with each unsigned batter added gives a free agent's value to the Pirates:
the corner bats Suzuki +2.0 and Arozarena +1.8 WAR, second basemen Arraez +1.6, Chisholm +1.4,
Lowe +1.3; close to additive in pairs (Suzuki and Arraez +3.5). The optimizer put Suzuki at
third base, an artifact of OAA not counting outfield arms.

## Adjustment floor on position switches (2026-11-23)

The outlook kept moving outfielders to the infield (Suzuki to 3B, Grisham to 2B). Cause: the
OAA difficulties put 2B/3B/SS at a third to a half of what the positional adjustments give
them (relative to 1B: OAA 3B 4.1, 2B 6.0, SS 10.0; adjustments 15, 15, 20), while LF/RF agree
(about 5). We charged the small OAA fielding cost but credited the full adjustment, so LF/RF to
3B netted about +9 runs per 700 PA and CF to 2B/3B +5 to +7, before any bat. The raw per-move
averages agree with the fit (LF to 3B +0.3), so it is not smoothing: the few players who made
these moves (8 to 19 player-seasons per move) were mostly infielders by trade.

Fix (`ADJ_FLOOR`): a move's fielding change is the lower of the OAA change and the adjustment
gap adj(p) - adj(q), so moving up the spectrum never adds defense. Moves down the spectrum and
those where OAA is stricter (into CF) are unchanged.

| | without floor | with floor |
| --- | --- | --- |
| RMSE 2012–2026 | 9.67 | 9.68 |
| RMSE 2022–2026 | 9.46 | 9.49 |
| Outfielders' PA at 2B/3B/SS, per team (2016–2027 mean) | 169 | 8.5 |
| PA at positions not played last season, per team | 447 | 359 |
| Replacement-level PA, per team | 136 | 101 |

Kept for realism: the error cost is within noise. 2027: Pirates 81.2 wins (was 81.1); Suzuki
now goes to 1B (+2.0), Grisham stays in CF (+1.4), Robert drops off the free-agent list.

Next idea: observed move frequencies (outfield spots trade 30–38% of the time, OF to 2B/3B
2–7%, C to anywhere but 1B 0–2%) carry information OAA cannot. Rarity mixes "cannot do it" with
"too valuable where he is", so rather than reading it directly, fit a few group penalties
(OF to IF, IF to OF, within IF, within OF, off C) so the optimizer's move rates on past seasons
match the observed rates of regulars, and keep it only if backtest error holds.

## Open questions

- The selection penalty is a judgment call; nothing in the data can measure it directly.
- Fatigue is the same for everyone. Catchers and older players may need more rest.
- Pitchers are not done yet (taken as Steamer projects them).
- Calibrate the switch penalties to how often teams make each move (see below).
