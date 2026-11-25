# Injury simulation (2026-11-25)

## What we tried

Team WAR as the mean over simulated seasons in which each player's availability is drawn and the
lineup and staff optimizers share the team's playing time out again. Our projections already
carry the average time a player loses; a single "average season" spreads that loss evenly over
everyone, so it cannot tell a deep roster (the backup plays when the starter is hurt) from a
top-heavy one. Code: `bucco.models.injury_sim`; opt-in with `load_marcel_data(injury_sims=N)`.

## Feasibility test (scratchpad, guessed injury rates)

150 draws per team for 2019, 2023, 2026 and 2027, with guessed injuries (30% of hitters and 45% of pitchers hurt, missing a uniform share of the
season), and talent draws (each player's rate drawn around his projection, with teams knowing
all or half of it on Opening Day):

| Simulated | Typical move vs the average season | Added to our forecasts, 2019/2023/2026 (RMSE 10.57) | Correlation with our errors |
| --- | --- | --- | --- |
| Injuries only | 0.42 wins | 10.48 | +0.23 |
| Injuries + talent, full knowledge | 0.84 | 10.55 | +0.07 |
| Injuries + talent, half knowledge | 0.79 | 10.54 | +0.08 |

Talent draws move teams twice as much but toward the middle (strong teams −1, weak +1) and do
not line up with what happened; dropped for expected wins (they belong in a season simulator
for ranges and odds). Injuries alone looked useful.

## Availability fitted from data

Delivered over projected playing time, rostered players 2012–2026 without 2020:

| Established group | Under half their projection | Bottom 10% delivered | Median |
| --- | --- | --- | --- |
| Hitters 450+ PA (32 and under / 33+) | 5% (2% to 5% / 10%) | 0.70 | 1.21 |
| Starters 120+ IP | 15% | 0.36 | 1.04 |
| Relievers 40+ IP | 19% | 0.28 | 1.02 |

Players with small projections were left out of the fit: their ratios reflect role decisions
(87% of fringe hitters do not play), not health. Availability A = min(1, delivered / projected
over the group's median): delivering at least the typical share counts as fully available.
Draws come from earlier seasons' established players, by group (hitters 32 and under, 33 and
over, starters, relievers; 100 samples needed, so 2012 has none and 2013 none for older
hitters), and apply to every player of that group. Healthy capacity = projection / the group's
mean A, so expected playing time is unchanged. Mean A for 2027: hitters 0.88 and 0.86,
starters 0.82, relievers 0.80.

## Walk-forward backtest (100 draws per team-season)

| | Wins RMSE | 2012–19 | 2021–26 | MAE | 80% cover |
| --- | --- | --- | --- | --- | --- |
| `marcel_staff_optimized` | 9.633 | 9.289 | 10.074 | 7.746 | 77.9% |
| + injury simulation | **9.611** | 9.259 | 10.061 | 7.740 | 78.6% |

Better in 10 of 13 seasons with draws (t −1.4); worst 2014 (+0.08), 2023 and 2025 (+0.06). The
three-season estimate (−0.09) was mostly the guessed rates and two favorable seasons. Each
team's spread over draws is kept (`PlayerData.sim_sd`) for team-specific ranges.

**Cost.** The backtest takes about 27 minutes instead of 3; a forecast about 2 minutes.

## Status

Built, tested and kept as an option; not adopted. A 0.02-win gain does not justify a tenfold
slower backtest while the model is still changing. It returns in the playing-time
streamlining ([../planning/playing_time_parameters.md](../planning/playing_time_parameters.md),
step 3), where the Opening Day factors and these draws become one availability distribution
and the fatigue curves are refitted with injuries on, since part of what they do overlaps.
