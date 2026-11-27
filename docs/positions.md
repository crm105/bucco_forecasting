# How we predict where players play

This covers our best model, `marcel_ml_hitter_pa`. Hitters are projected one way for the
forecast and another for the outlook page. Pitchers are placed the same way in both.

## Hitters

### In the forecast: no positions, just each player's projected defense

The forecast doesn't place hitters at positions. Each rostered hitter counts at his learned
playing time (`ml.hitters`) with his projected value:

- **Offense:** the learned offense rate (`ml.hitters`).
- **Defense:**
  - The positional adjustment comes from where he played over the last three seasons. Each
    season's adjustment is the FanGraphs scale (C +12.5, SS +7.5, 2B/3B/CF +2.5, LF/RF −7.5,
    1B −12.5, DH −17.5 runs per full season) weighted by his innings at each position (DH
    starts count as 9 innings). The three seasons are weighted 5:4:3, as in Marcel.
  - On top of that comes our fielding projection from Statcast fielding run value
    (docs/R&D/fielding.md). Where he has none, we use the average of Steamer's and ZiPS's
    projected Def.

So the forecast assumes each hitter plays his recent mix of positions. Team batting WAR is the
sum over the roster. Nothing checks that the team has exactly one shortstop's worth of playing
time.

### In the outlook: the lineup optimizer

The outlook's position tables and its "Projected leaders" use the lineup optimizer
(`lineup_optimizer`). It's a linear program run once for each team.

1. **Every position is filled exactly.** 640 PA at catcher and 700 at each other position, DH
   included (about 6,240 a team).
2. **No player exceeds his learned PA** (`pa_cap`), so time he's expected to miss goes to his
   backups. Nobody gets more than 700 PA.
3. **Replacement level fills the gaps.** A replacement-level player (0 WAR) is always
   available. Time no rostered player fills better goes to him.
4. **The goal is the most team WAR.** Each PA a player gets is worth his batting, baserunning
   and replacement credit plus his defense at that position. His batting rate falls as he plays
   more than his projected PA (fatigue, relative to his own projection) and improves slightly
   below it.

**Where he can play:**

- **His positions are taken from last season's games.** That's his most-played fielding
  position (his *anchor*), plus any other position with 20 or more games. A player who only
  DH'd can DH. A player with no MLB games last season gets the position group implied by his
  projected positional adjustment (for example SS, or 2B/3B/CF).
- **Only catchers catch.** Catching is open only to players with catcher among those positions.
  A player who mainly plays elsewhere but caught 20 or more games is treated as a
  below-average catcher (−5 runs per 700 PA).
- **Any other fielding position, and DH, is open to anyone, at a cost.** A player with no
  fielding position is treated as if his moves start from first base.

**His defense at each position** (runs per 700 PA):

- **At his anchor:** his projected Def, fielding plus that position's adjustment.
- **At another position he played:** his anchor fielding, plus the change in fielding fitted
  from Statcast Outs Above Average for players who made that move (`SwitchMatrix`,
  `scripts/fit_position_switch.py`), plus the new position's adjustment.
  - The change is capped so that moving to a harder position never adds defensive value.
- **At a position he hasn't played:** the same, minus a selection penalty of 2 runs plus half
  the rise in difficulty. That's because teams only move players they expect to cope.
  - Outfielders moving to first base pay 6 runs more, because the optimizer otherwise made
    that move twice as often as real teams.
- **A catcher playing elsewhere** fields like an average first baseman; none of his catching
  value carries over.
- **A DH-only player** fields like a below-average first baseman (−5).
- **At DH:** the DH adjustment (−17.5) for everyone.

The result is each player's PA at each position. The leaders table lists them all, most first,
for example "2B 211, 1B 114". The forecast doesn't use the optimizer for hitters because its
hitter playing time is the learned PA as given (docs/R&D/ml_playing_time.md). So the outlook's
batting WAR can differ a little from the forecast's.

## Pitchers (forecast and outlook alike)

The staff optimizer (`staff_optimizer`) shares each team's innings between the rotation and
the bullpen.

1. **Every team fills the same innings:** 830 by starters and 620 in relief. A
   replacement-level pitcher fills whatever is left.
2. **Who can start:** pitchers who started at least a tenth of their (weighted) games, which
   covers starters, swingmen and bulk relievers. Everyone else relieves only.
3. **Innings limits:**
   - A pitcher's relief innings are capped at 100 × (1 − his start share) + 10, so starters
     stay in rotations.
   - No pitcher throws more than 220 innings, or 100 for a pure reliever.
4. **Innings start from the learned model.** Each pitcher's innings start from the learned
   innings model (`ml.pitchers`). His rate gets worse the further past that he's pushed, and
   faster for older pitchers.
5. **Role penalty:** a pitcher who mostly relieves does worse when starting, and a starter does
   better in relief, by the same fitted penalty.
6. **Leverage:** after the innings are shared out, each team's best reliever (by relief WAR per
   inning, 20 or more relief innings) is its closer and the next three are setup men. Their
   relief WAR counts 2.0 and 1.5 times in team WAR (docs/R&D/leverage.md). It doesn't change
   anyone's innings.

The leaders table lists each pitcher's innings in each role, for example "SP 180, RP 10", and
marks closers and setup men.
