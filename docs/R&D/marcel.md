# Marcel: our own player projections, first version (2026-11-24)

## What we tried

The barebones Marcel ("the monkey could do it") on our own player history
([player_history.md](player_history.md)), carried through to team wins with the same machinery
as the public projections (rung 5a), first with the depth chart and then with the lineup
optimizer.

## How it works

Code: `bucco.models.marcel` (projections), `bucco.models.player_inputs.load_marcel_data`
(rosters), models `marcel` and `marcel_optimized`.

1. **Rate.** Runs above league average per PA (batters: batting + stolen-base runs) or per
   batter faced (pitchers: FIP-based runs), averaged over the last three seasons with weights
   5/4/3 (batters) or 3/2/1 (pitchers) times playing time, with 1,200 weighted PA (or BF) of
   league average mixed in. Positional adjustment: weighted the same way, not regressed. No
   fielding runs, no aging.
2. **Playing time.** 0.5 × last season + 0.1 × the season before + 200 PA (60 IP for a starter,
   25 for a reliever); 2020 scaled to 162 games.
3. **Value.** Off, Def and WAR from the league constants of the season before the target season.
4. **Rosters.** Each team's players are the ones the Steamer file lists for it before Opening
   Day; only the team assignment is used, not Steamer's numbers. Players with no MLB history in
   the three prior seasons (rookies) get no projection, so their time goes to others or to
   replacement level.
5. **Team wins.** As for rung 5a: playing time shared out per team (depth chart; or the lineup
   optimizer for batters in `marcel_optimized`, pitchers always through the depth chart), team
   WAR centered on the league, a line from WAR to wins fitted on earlier seasons only, then the
   strength-of-schedule adjustment.

## What it yields

**Players**, 2012–2026 without 2020, against Steamer on the same player-seasons (relative to the
season average, so the difference between our scale and FanGraphs' drops out):

| | Batters (300+ PA): Off runs per 600 PA | | Pitchers (50+ IP): FIP | |
| --- | --- | --- | --- | --- |
| | r | RMSE | r | RMSE |
| Marcel | 0.493 | 15.2 | 0.381 | 0.747 |
| Steamer | 0.515 | 14.7 | 0.485 | 0.694 |

**Teams**, backtest RMSE in wins, 2012–2026 without 2020 (420 team-seasons):

| Model | RMSE | MAE | 80% cover |
| --- | --- | --- | --- |
| `steamer` | 9.50 | 7.64 | 0.78 |
| `steamer_optimized` | 9.58 | 7.71 | 0.78 |
| `zips_optimized` | 9.72 | 7.84 | 0.79 |
| `depth_chart` (ZiPS) | 9.79 | 7.91 | 0.80 |
| **`marcel`** | **10.21** | 8.21 | 0.77 |
| **`marcel_optimized`** | **10.27** | 8.24 | 0.76 |
| `holt` | 11.08 | 8.81 | 0.77 |
| `last_year` | 11.77 | 9.50 | 0.78 |

- Our own projections beat every team-history model by about 0.9 wins, and trail ZiPS by 0.4
  and Steamer by 0.7.
- The lineup optimizer does not help Marcel (10.27 vs 10.21). It helped ZiPS and hurt Steamer
  slightly, so it is not a sure gain; Marcel's crude playing time (everyone gets 200 PA on top)
  is a likely reason, since the optimizer anchors each player's fatigue curve at his projected PA.
- Marcel beat Steamer in only 1 of 14 seasons (2025).

## Where it falls short

- **Aging.** Team errors track roster age: Marcel overrates older lineups by about 1.2 wins per
  year of average batter age above the league (correlation -0.13; Steamer -0.10). On the 2027
  Pirates, veterans with no decline (Reynolds, O'Hearn, Mangum) make Marcel 4 wins more
  optimistic than Steamer (85.5 vs 81.5).
- **Pitchers.** One replacement level for starters and relievers, and FIP regressed as one
  number rather than by component (K, BB, HR), leave starters low (Skenes 2027: 3.5 WAR vs
  Steamer's 4.7).
- **Rookies** are treated as replacement level.

## Adding aging (2026-11-24)

**How.** The delta method, refitted for every target season on pairs of consecutive seasons that
both finished before it: for each player, the change in runs per PA (batters: Off) or per batter
faced (pitchers: FIP-based runs) from one season to the next at his age, weighted by the harmonic
mean of the two seasons' playing time, smoothed with a weighted quadratic in age (fitted on ages
20 to 40, flat outside). The curve is the running sum of those changes. Each of a player's three
past seasons is aged forward to his age in the target season before the Marcel weighting
(`marcel.fit_age_curve`, `age_curves`; models `marcel_aging`, `marcel_aging_optimized`).

**The curves** are stable from the 2012 fit to the 2027 fit: batters peak at 25, pitchers at 24.
From age 27, batters lose about 5 runs per 600 PA by 29, 12 by 31 and 21 by 33. The delta
method only sees players who kept playing, which pulls every change down; a version with the
average change removed (shape only) did no better, so the full curve was kept, as planned before
testing.

**Players** (same samples as above):

| | Batters: r | RMSE | Error trend with age | Pitchers: r | RMSE |
| --- | --- | --- | --- | --- | --- |
| Marcel | 0.493 | 15.16 | -0.73 runs per 600 PA per year | 0.381 | 0.747 |
| Marcel + aging | 0.508 | 14.88 | +0.03 | 0.396 | 0.739 |
| Marcel + aging, shape only | 0.509 | 14.91 | -0.12 | 0.391 | 0.741 |
| Steamer | 0.515 | 14.68 | -0.11 | 0.485 | 0.694 |

**Teams:**

| Model | RMSE | MAE | 80% cover |
| --- | --- | --- | --- |
| `marcel_aging` | **10.06** | 8.13 | 0.78 |
| `marcel_aging_optimized` | 10.13 | 8.12 | 0.77 |
| `marcel` | 10.21 | 8.21 | 0.77 |
| `marcel_optimized` | 10.27 | 8.24 | 0.76 |

- Aging gains 0.15 wins and beats no aging in 11 of 14 seasons (paired t 3.0): a real gain.
- The team-age bias falls from a correlation of -0.13 to -0.06 (Steamer: -0.10).
- Gap to Steamer: 0.56 wins (was 0.71); to ZiPS through the depth chart: 0.27 (was 0.42).
- The optimizer still does not help.
- 2027 Pirates: 86.1 (`marcel_aging`). Aging takes 2.8 WAR off their batters (Reynolds -0.7,
  O'Hearn -0.6) and 1.0 off their pitchers, but every team ages, so their edge over the league
  is unchanged (+3.9 WAR). The 4.5-win gap to Steamer (81.5) is not about age.

## Shrinking toward what players with that much history did (2026-11-24)

**Why.** Marcel mixes 1,200 PA (or BF) of league-average performance into every player. Players
with little MLB history went on to do much worse than that: batters with under 300 weighted PA
(5/4/3) produced -9.4 Off per 600 PA the next season against Marcel's -2.5. The same showed up in
the Pirates outlook, where fringe free agents with almost no MLB time ranked as top-10 targets.
They did not do as badly as replacement level, though (-9 runs per 600 PA for Off plus position,
against replacement at -18), so shrinking everyone toward replacement level overshoots.

**How.** Three targets, all walk-forward (`project_batters(..., prior=...)`, same for pitchers):

- `league`: the original (league average).
- `replacement`: replacement level (Off + positional at replacement; pitchers' replacement runs
  per batter faced).
- `fitted`: mu = a + b log(1 + weighted volume / scale), with a and b refitted for each target
  season on earlier player-seasons so that projections match what players with that much
  history went on to do (`fitted_prior_means`). Models `marcel_shrunk` and
  `marcel_shrunk_optimized` (with aging).

**Players**, everyone who played the next season, weighted by playing time (2012–2026 without
2020). Bias is actual minus projected, by weighted recent PA (batters: under 300, 300–750,
750–1,500, 1,500–3,000, 3,000–5,000, over 5,000):

| Target | Batters RMSE (Off/600) | Batter bias by history | Pitchers RMSE (runs/700 BF) |
| --- | --- | --- | --- |
| league | 18.12 | -7.1 -2.3 -1.9 +0.2 0.0 +2.1 | 16.64 |
| replacement | 18.90 | +8.8 +10.8 +7.8 +6.7 +4.2 +4.6 | 18.58 |
| **fitted** | **18.01** | **0.0 +1.2 -1.0 -0.5 -1.3 +0.7** | **16.56** |
| Steamer | 17.77 | +0.7 +0.8 -0.2 +0.3 -1.2 +0.2 | |

**Teams:**

| Model | RMSE | Before (aging only) |
| --- | --- | --- |
| `marcel_shrunk` | **9.98** | 10.06 |
| `marcel_shrunk_optimized` | 10.02 | 10.13 |
| replacement target, depth chart (not registered) | 9.98 | |
| replacement target, optimized (not registered) | 10.00 | |

- The fitted target beats aging-only in 8 of 14 seasons (paired t 2.6) through the depth chart
  and 9 of 14 (t 2.9) through the optimizer.
- At team level the replacement target ties it: forecasts are centered on the league, so its
  uniform underrating of everyone cancels. It is kept out because player values are used
  directly (free-agent gains, the outlook's WAR), where it is biased by 4 to 11 runs per 600 PA.
- The fringe free agents left the Pirates outlook's top 10, replaced by MLB regulars.
- The 2027 Pirates barely moved (86.4 to 86.2): their young hitters have real 2026 MLB time
  (Valdez: about 340 PA at a 120 wRC+), which Marcel takes largely at face value. That, not
  shrinkage, is most of the gap to Steamer's 81.5 and 27th-ranked lineup; Steamer also uses
  minor-league and Statcast data.

## Park adjustment (2026-11-25)

History put on a neutral-park footing before projecting; see [park_factors.md](park_factors.md).
`marcel_park` and `marcel_park_optimized` score 9.89 (from 9.98 and 10.02), better in 11 of 14
seasons.

## Replacement level by role (2026-11-25)

**What.** Pitchers' replacement level now depends on role, as at FanGraphs: 0.12 wins per 9
innings below average for a pure starter, 0.03 for a pure reliever, mixed by the share of his
games he started, scaled each season so pitchers still add up to 430 WAR (`league_seasons`:
`sp_replacement_runs_per_ip`, `rp_replacement_runs_per_ip`). Used for history
(`player_pitching_seasons`) and Marcel's projections (by the weighted share of starts).

**Players.** 2026: starters 355 WAR, relievers 75. 2024 leaders move toward FanGraphs: Sale 5.8
to 6.7 (FanGraphs 6.4), Skubal 5.4 to 6.3 (6.0). Skenes 2027: 3.7 to 4.6 (Steamer 4.7).

**Teams.** Slightly worse in every variant, within noise (`marcel_park` 9.881 to 9.905,
`marcel_park_optimized` 9.892 to 9.912; better in 5-7 of 14 seasons), with single teams moving
up to 3 wins. The cause is the depth chart, which gives innings only to pitchers projected above
replacement: with the lower reliever level, 49 rostered 2027 pitchers fall to 0 WAR or below
(4 before), so bullpen innings shift. Teams with deep bullpens gain (MIN +2.2, KC +1.9) and those
relying on marginal relievers lose (SD -2.3). Kept for the more accurate player values; the
depth chart's handling of sub-replacement relievers is a follow-up.

**2027 Pirates:** 85.3 to 84.5 wins; rotation 5th (13.6 WAR), bullpen 16th (4.2).

## Diagnostic: rates or playing time? (2026-11-25)

Rates and playing time swapped between Marcel (`marcel_park`) and Steamer, everything else the
same machinery (RMSE in wins, 2012-2026 without 2020):

| | Rates | Playing time | Players without MLB history | RMSE |
| --- | --- | --- | --- | --- |
| A | Steamer | Steamer (as given) | Steamer's | **9.501** |
| B | Marcel | Steamer (as given) | Steamer's | 9.640 |
| C | Marcel | Steamer (as given) | replacement level | 9.743 |
| D | Steamer | Marcel (depth chart) | none | 9.810 |
| E | Marcel | Marcel (depth chart) | none | 9.905 |

Pieces of the 0.40-win gap (RMSE is not additive, so ranges):

- **Playing time: 0.16 to 0.31**, the largest (E to C with our rates; D to A with Steamer's).
  Steamer's playing time is shared out per team by hand and updated through spring training.
- **Rates for players with history: 0.10 to 0.14** (E to D; B to A).
- **Rookies and players without MLB history: about 0.10** (C to B).

Script: run from the scratchpad (not in the repo), using `load_player_data("steamer")` and
`marcel_projections(True, "fitted", True)`.

## Fielding borrowed from Steamer and ZiPS (2026-11-25)

**Why.** Marcel's Def is the positional adjustment only: our history has no fielding runs. How
much does that cost?

**How.** Each batter's Def rate is replaced by the mean of Steamer's and ZiPS's projected Def per
PA (fielding + positional) for the target season, over whichever of the two lists him; the
difference from his positional rate is credited as fielding runs (`marcel.apply_external_def`,
`player_inputs.external_def_rates`). Batters neither lists keep their own Def. Both files are
made before Opening Day. Applied to `marcel_park_optimized` only.

**Teams** (RMSE in wins, 2012-2026 without 2020; seasons better than positional only):

| Def | `marcel_park` | `marcel_park_optimized` | Better (optimized) |
| --- | --- | --- | --- |
| Positional only | 9.905 | 9.912 | |
| Steamer | 9.913 | 9.869 | 9 of 14 |
| ZiPS | **9.828** | **9.808** | 11 of 14 (t -2.0) |
| Mean of Steamer and ZiPS (adopted) | 9.850 | **9.809** | 11 of 14 (t -1.9) |
| `steamer` / with its own fielding removed | 9.501 / 9.556 | | |

- Defense is worth 0.05 to 0.10 wins of the 0.40-win gap to Steamer, less than playing time or
  rates (see the diagnostic above). Steamer loses 0.055 when its fielding is removed (worse in
  12 of 14 seasons).
- Steamer's Def alone barely helps Marcel; ZiPS's or the mean does. Untested guess: Steamer's
  Def follows the positions it projects, which can disagree with Marcel's position history.
- "Fielding" here is the outside Def minus our positional rate, so it includes disagreements
  about position, not only about glove.
- **2027 caveat:** there are no ZiPS 2027 files yet, so the 2027 forecast uses Steamer's Def
  alone, the weaker variant. Rerun once ZiPS 2027 is out.

**2027 Pirates** (`marcel_park_optimized`): 84.5 to 83.7 wins, still 7th. Lineup 17th to 18th;
defense (fielding + positional) 20th to 30th, as Steamer rates most of their regulars below
average in the field (Reynolds, Horwitz, O'Hearn, Gonzales, Mangum, Valdez: -2.5 to -4 runs per
600 PA). Biggest team moves: MIN -2.5, CHC +1.6, STL +1.5, CLE +1.5.

## Next

1. Fielding of our own (FanGraphs Fld or Statcast OAA in the history), to replace the borrowed
   Def.
2. Pitchers: by component (K, BB, HR), with separate starter and reliever replacement levels.
   This is now the biggest player-level gap (FIP RMSE 0.739 vs Steamer's 0.694).
3. Rookies with no MLB history at all still get no projection (the fitted target covers players
   with some history). Minor-league data would help both them and young players like Valdez.
4. Playing time beyond the Marcel formula, then a second look at the optimizer.
5. Where the 2027 Pirates gap to Steamer comes from (batting depth and playing time).

## Status

Registered (`marcel`, `marcel_optimized`, `marcel_aging`, `marcel_aging_optimized`) and
backtested, plus `marcel_shrunk`, `marcel_shrunk_optimized`, `marcel_park` and
`marcel_park_optimized`. `marcel_park_optimized`, with fielding from Steamer and ZiPS, is our best own-projection model (9.81). Not adopted: Steamer stays the
model of record.
