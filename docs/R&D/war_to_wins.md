# Team WAR to wins: one line, separate slopes or Pythagorean (2026-11-27)

The player-projection models turn team WAR into a win percentage with one least-squares line,
fitted on earlier seasons only (`DepthChartModel.fit`):

    win% = intercept + slope × (team WAR − that season's league average)

then adjust for the schedule. With `marcel_ml_hitter_pa` the slope is about 1.26 wins per WAR,
above the textbook 1.0 because projected team WAR is more compressed than actual team WAR.

## What we tried

On `marcel_ml_hitter_pa`'s team batting and pitching WAR, 2014–2026 without 2020, each target
season fitted only on the seasons before it (from 2012), no schedule adjustment in any variant:

1. **Separate slopes**: win% = a + b × batting WAR + c × pitching WAR (each centered by season).
2. **Pythagorean**: runs scored = league runs + s_b × runs per win × batting WAR, runs allowed =
   league runs − s_p × runs per win × pitching WAR (last season's league runs per team and runs
   per win), win% = RS^x / (RS^x + RA^x), with s_b, s_p and x fitted by least squares.

| Conversion | Wins RMSE | Typical miss | Better than one line, by season | Top/bottom 3 teams, RMSE |
| --- | --- | --- | --- | --- |
| One line (current) | **9.51** | 7.69 | | 9.39 |
| Separate slopes | 9.52 | 7.68 | 7 of 12 (t +0.7) | 9.36 |
| Pythagorean | 9.52 | 7.69 | 7 of 12 (t +0.3) | 9.30 |

## Findings

- The separate slopes are not stably different: batting 1.33 wins per WAR in the 2014 fit and
  1.13 in 2026, pitching 1.03 and 1.38. The gap flips with the sample; one slope is enough.
- The Pythagorean fit sets its exponent at the lower bound (1.0, flatter than the usual 1.83) and
  scales WAR-implied runs by about 2: it undoes the projections' compression, as the line's slope
  does, and finds no curvature to use. Its small gain at the extremes (72 team-seasons) is noise.
- The conversion is not where the error is; projected team WAR is (rate error above all). Not
  adopted. Reliever leverage (FIP-based WAR weights every inning alike) is untested.
