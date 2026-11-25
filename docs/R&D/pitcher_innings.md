# Pitcher innings: baseline innings and the staff optimizer (2026-11-25)

## What we tried

Marcel's pitchers get innings from a fixed formula (0.5 × last season + 0.1 × the season
before + 60 for a starter, 25 for a reliever), then the depth chart shares out each team's
innings. Two replacements:

1. **Baseline innings** from past innings, role and age (`bucco.models.innings`).
2. **A staff optimizer** (`bucco.models.staff_optimizer`), the pitching counterpart of the
   lineup optimizer: each team fills 830 rotation and 620 bullpen innings, a pitcher's rate
   gets worse as his innings rise past his baseline, and older arms get worse faster.

Model: `marcel_staff_optimized` (= `marcel_park_optimized` with both).

## Baseline innings

A least-squares line, refitted for every target season on earlier seasons' pitchers on
preseason rosters: next-season IP on the last three seasons' IP (scaled to 162 games), the
weighted share of games started, age (centered at 27) and age squared, with interactions of age
and of start share with last season's IP. Pitchers who threw no MLB innings count as 0 (32% of
rostered pitcher-seasons), so it is an expectation that includes injuries and lost jobs.

Walk-forward, 2013–2026 without 2020 (11,560 rostered pitcher-seasons):

| Innings | RMSE | Bias |
| --- | --- | --- |
| Marcel formula | 43.5 | +20.5 |
| Past IP only | 38.0 | +0.7 |
| + role | 37.5 | +1.0 |
| **+ role and age** | **37.2** | +0.4 |

Without age, starters 24 and under are under-projected by 9 IP and those 34+ over-projected by
14; with it, every age band is within 5.

## Age and room to grow

Actual innings over baseline innings, starters with a baseline of 100+ (relievers 40+):

| Age | Starters: 75th pct | 90th pct | Relievers: 90th pct |
| --- | --- | --- | --- |
| 24 and under | 1.40 | 1.60 | 1.87 |
| 25–26 | 1.34 | 1.62 | 1.78 |
| 27–28 | 1.30 | 1.50 | 1.57 |
| 29–30 | 1.31 | 1.51 | 1.50 |
| 31–32 | 1.29 | 1.41 | 1.52 |
| 33+ | about 1.32 | 1.46 | 1.55 |

Young arms have more room at the top (about +60% vs +45%) and also more downside (22% of
young starters threw under half their baseline, 16% at 29–32). The typical outcome barely
depends on age once the baseline has age in it. For a quadratic curve, that headroom means
c(age) about 1.4 times steeper at 32 than at 25: c(age) = c0 · exp(0.05 (age − 27)).

## The staff optimizer

rate(x) = r − c · ((x / B)² − 1) past the baseline B, half that gain below it. Replacement
level by pool (lower for relievers); starters can pitch in either pool, relievers only in
relief; at most 220 IP (100 in relief).

**First form: c the same for everyone (runs per inning).** An ace's edge over replacement is
so large that any c gentle enough to let young starters grow pushes him to the 220-IP cap
(Skenes 2027: 220); a c steep enough to stop him flattens everyone else.

**Kept form: proportional.** c is scaled by the pitcher's value over starter replacement, so
everyone loses the same share of his edge per inning past baseline. Quality decides who gets
the innings when the budget is tight; age decides how far anyone stretches.

**Innings error** (rostered pitchers, 2013–2026 without 2020):

| Allocation | RMSE | Established starters (150+ IP last season): bias | 26 and under | 31+ |
| --- | --- | --- | --- | --- |
| Depth chart on Marcel IP (current) | 41.2 | +18.5 | +20.7 | +15.9 |
| Depth chart on baseline IP | 38.0 | +2.1 | +6.2 | +0.7 |
| Proportional, c0 0.05, g 0 | 37.8 | +7.5 | +14.4 | +2.4 |
| **Proportional, c0 0.05, g 0.05** | 37.8 | +4.4 | +18.1 | −5.4 |
| Proportional, c0 0.1, g 0 | 37.7 | −2.9 | +3.5 | −6.4 |
| Proportional, c0 0.2, g 0.05 | 38.6 | −17.0 | −4.5 | −24.6 |

The age slope does not improve innings error: the baseline already expects young starters to
grow, so a steeper curve for older arms counts age twice. The extra room young arms show is
spread, not a higher mean, which a point forecast cannot use.

**Team wins** (RMSE, 420 team-seasons; better than `marcel_park_optimized` in):

| Model | 2012–2026 | 2022–2026 | Seasons better |
| --- | --- | --- | --- |
| `marcel_park_optimized` (depth chart on Marcel IP) | **9.809** | **9.874** | |
| Depth chart on baseline IP | 9.813 | 9.885 | 6 of 14 |
| Flat c, c0 0.05, g 0.05 | 9.808 | 9.960 | 5 of 14 |
| **`marcel_staff_optimized`** (proportional, c0 0.05, g 0.05) | 9.821 | 9.971 | 6 of 14 |
| Proportional, c0 0.1, g 0 | 9.830 | 9.970 | 6 of 14 |
| Flat c, c0 0.2, g 0.05 | 9.926 | 10.040 | 5 of 14 |

No setting improves team wins; all are within noise overall, and every optimizer setting is
about 0.1 worse in 2022–2026.

## 2027 Pirates

Innings (2026 actual in brackets):

| | Skenes (174) | Chandler (154) | Jones (102) | Keller (116) | B. Ashcraft (165) |
| --- | --- | --- | --- | --- | --- |
| Depth chart on Marcel IP (current) | 166 | 140 | 111 | 135 | 150 |
| Baseline | 148 | 124 | 101 | 105 | 122 |
| Flat c, c0 0.05, g 0.05 | 220 (cap) | 160 | 135 | 105 | 160 |
| **`marcel_staff_optimized`** | 180 | 150 | 120 | 115 | 140 |

The kept form holds Skenes steady, lifts Jones (+18) and lowers Keller below the 135 he gets
now. Chandler stays about level rather than jumping. Pirates pitching: 15.7 WAR, 5th.

## Follow-up: seasons, history and the innings trend (2026-11-25)

**Season by season** (RMSE in wins; `marcel_staff_optimized` minus `marcel_park_optimized`):
better in 2012 (−0.01), 2013 (−0.19), 2016 (−0.26), 2018 (−0.10) and 2022 (−0.25); tied in
2017; worse in 2014, 2015, 2019, 2021, 2026 (+0.03 to +0.06), 2024 (+0.14), 2023 and 2025
(+0.30). Through 2019 it is better (9.376 vs 9.424); from 2021 worse (10.385 vs 10.299).

**How history is used.** The baseline line is refitted for every target season on all
earlier seasons, weighted equally. The optimizer's rotation and bullpen budgets (830/620) are
constants for every season. c0 and g were chosen on 2013–2026 at once, not walk-forward; with
two parameters, neither of which improved wins, the leak is small but it is there.

**The trend.** Total innings per team are flat (1,445 in 2012, 1,436 in 2026); who throws
them is not:

| | 2012 | 2026 |
| --- | --- | --- |
| Pitchers with 180+ IP | 62 | 13 |
| Pitchers with 200+ IP | 31 | 3 |
| IP per start, regular starters | 6.06 | 5.48 |
| Pitchers used per team | 22 | 29 |
| Rotation innings per team (estimated) | 988 | 892 |

Most of the change came between 2015 and 2021; it has been flat since. Rotation innings are
estimated per season from IP = a × starts + b × relief games across pitchers (there is no
starter/reliever split in our data); every team-game has one start.

Three ways to follow it, all walk-forward:

| | Innings RMSE | Established SP bias 2013–19 / 2021–26 | Wins 2012–26 |
| --- | --- | --- | --- |
| Baseline as built | 37.2 | +0.3 / +7.4 | 9.821 (staff) |
| Recency-weighted fit, half-life 2 years | 37.2 | +0.4 / +6.5 | 9.820 (staff) |
| Past innings scaled to the current era's rotation innings | 37.2 | 0.0 / +7.7 | |
| Rotation and bullpen budgets from the season before | | | 9.848 (staff) |

None helps. The baseline already follows the trend through each pitcher's own recent innings.
The recent over-projection of established starters is noisy, not a trend (2022 −2, 2023 +8,
2024 +19, the year of the ace-injury wave, 2025 +7, 2026 +6). Not kept in the code.

**Without the Pirates guidance.** Two choices followed it: proportional fatigue (to keep
Skenes off the cap) and keeping the age slope (g = 0.05). The best setting on the backtest,
ignoring the guidance, is flat c with c0 0.05 (9.808, against 9.821), a tie with the current
model (9.809), and it puts Skenes at 220. g = 0 and g = 0.05 score the same. The guidance cost
about 0.01 wins, within noise.

## Swingmen can start (2026-11-25)

**Problem.** Only pitchers who started at least half their weighted games could pitch in the
rotation. Swingmen (bulk relievers, spot starters: some starts but under half) were bullpen
only, so a thin rotation went to replacement level while its swingman sat in the bullpen:
52 rotation innings a team on average, 125 for the 2027 Pirates while Carmen Mlodzinski
(start share 0.29, FIP 3.8) threw 90 in relief. Swingmen throw about 14% of all innings
(2021–2026), and rostered ones start 23% of their games the next season.

**Fix.** Anyone with a weighted start share of at least `ROTATION_MIN_SHARE` can pitch in
either pool; his fatigue curve still limits his total.

| Cutoff | Wins 2012–26 | 2021–26 | Better than `marcel_park_optimized` | t | Swingmen IP bias | Replacement rotation IP/team |
| --- | --- | --- | --- | --- | --- | --- |
| 0.5 (before) | 9.821 | 10.385 | 6 of 14 | | −16.0 | 52 |
| 0.3 | 9.785 | 10.257 | 9 of 14 | | −8.5 | 28 |
| 0.2 | 9.762 | 10.224 | 9 of 14 | −0.8 | −6.0 | 18 |
| **0.1 (kept)** | **9.734** | 10.193 | 9 of 14 | −1.5 | −3.8 | 11 |
| 0.05 | 9.726 | 10.156 | 9 of 14 | −1.4 | | |
| 0 (anyone) | 9.729 | 10.162 | 9 of 14 | −0.8 | | |
| `marcel_park_optimized` | 9.809 | 10.299 | | | | |

The gain levels off from 0.1 down; 0.1 has the steadiest season-by-season gain and still keeps
out relievers with an opener start or two. Innings RMSE 37.7 (37.8 before). The cutoff was
picked on the same backtest, but the plateau from 0.1 to 0 makes that matter little. This is
the first innings change that beats the current model: suggestive (t −1.5), not conclusive.

**2027 Pirates** (rotation + relief innings): Skenes 170, Chandler 135, B. Ashcraft 130, Jones
110, Keller 105, Mlodzinski 95 + 0; no replacement-level rotation innings (was 125). Pitching
WAR 15.7 to 17.5. With swingmen able to start, the fixed 830-inning rotation is filled, so the
top starters are pushed less than before (Skenes 180 to 170, Chandler 150 to 135). The
rotation budget is below the estimated 2021–2026 level (about 890), which squeezes them;
season budgets were tested only with the 0.5 cutoff.

## Starting penalty for relievers (2026-11-25)

**Why.** Relievers' numbers flatter them as starters: shorter outings at full effort, and no
third time through the order. With swingmen able to start, Mlodzinski and Bachar were
credited with their mixed-role rate in the rotation.

**Measured** with the delta method on pairs of consecutive seasons (age and age squared as
controls, weighted by the harmonic mean of batters faced; park-neutral FIP-based runs): the
same pitcher gives up about **0.27 runs per 9 innings more** per unit of start share (0.29 on
2012+ targets; 0.38 among role changes of half or more). By component, as a starter: 2.3
points fewer strikeouts, 0.9 points fewer walks, 0.3 points more home runs. Relievers moved to
the rotation are usually the ones pitching well, so this is likely a little low. Refitted for
each target season on earlier seasons only (`innings.fit_start_penalty`): 0.22 to 0.32 runs per
9, 0.27 for 2027.

**How.** A pitcher's projected rate reflects his past mix (start share s): in the rotation he
loses penalty × (1 − s) per inning, in relief he gains penalty × s.

| | Wins 2012–26 | 2021–26 | Better than without | t |
| --- | --- | --- | --- | --- |
| No penalty | **9.734** | 10.193 | | |
| **Fitted penalty (kept)** | 9.745 | 10.214 | 8 of 14 | +1.0 |
| Fixed 0.045 (0.4 per 9) | 9.758 | 10.229 | 7 of 14 | +1.2 |
| `marcel_park_optimized` | 9.809 | 10.299 | | |

Within noise, slightly worse. Kept because it is measured, not tuned, and makes the value of
relievers who start more accurate (as for replacement level by role).

**2027 Pirates.** Innings barely move: Mlodzinski and Bachar still start, because the
alternative is a replacement-level starter, far worse even after the penalty. Their credit
falls (Mlodzinski 1.8 to 1.6 WAR, Bachar 0.8 to 0.6); pitching 17.5 to 17.0 WAR, still 1st;
85.7 to 85.4 wins (6th). The FIP shown in the outlook is the projection's, without the penalty.

### Relative to the pitcher's quality? (2026-11-25)

**Data.** Adding an interaction of the change in start share with the pitcher's quality (his
rate the season before the pair, to avoid regression to the mean): each run per 9 of better
quality adds 0.09 ± 0.06 runs per 9 of penalty (relievers alone: 0.04 ± 0.09). The direction
fits "elite relievers lose more", but it is not distinguishable from zero. A penalty
proportional to value over replacement implies about 0.21, steeper than that.

**Backtest**, penalty = fitted × (1 + slope × (v − 0.15) / 0.15), v his value over starter
replacement per inning:

| Slope | Wins 2012–26 | Better than uniform |
| --- | --- | --- |
| 0 (uniform, kept) | **9.745** | |
| 0.4 (the measured interaction) | 9.748 | 4 of 14 |
| 1 (proportional) | 9.754 | 4 of 14 |
| 2 | 9.765 | 4 of 14 |

Worse the more relative; the 2027 Pirates do not change (Mlodzinski and Bachar are mid-quality).
Not kept in the code.

## Status

Built, registered and backtested. With swingmen able to start and the starting penalty,
`marcel_staff_optimized` (9.74; 9.69 since Opening Day injury status was added, see
[availability.md](availability.md)) is our best own-projection model, ahead of `marcel_park_optimized` (9.81). Not yet
used by the outlook (which shows depth-chart innings) or adopted; Steamer (9.50) stays the
model of record.

## Next

- Why every optimizer setting is about 0.1 worse in 2022–2026 (replacement-level innings for
  thin November-style rosters are one suspect: 300+ per team vs about 180 really thrown by
  pitchers not on the preseason roster).
- Rotation and bullpen budgets again, now that swingmen can start (the 830-inning rotation
  now binds and squeezes the top starters).
- Leverage: a value multiplier for each team's best relievers.
- Show the role-adjusted FIP for pitchers who change role in the outlook.
