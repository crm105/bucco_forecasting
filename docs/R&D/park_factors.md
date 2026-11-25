# Park factors (2026-11-25)

## What we tried

Put every player's history on a neutral-park footing before projecting from it, so a Rockies
hitter is not credited for Coors Field and a Mariners hitter is not penalized for T-Mobile Park.

## Why

Our player values had no park adjustment. Coors inflates singles and doubles most, which our
wOBA (and so batting runs) counts in full, while FIP only sees home runs, walks and strikeouts.
So Rockies hitters were overrated more than their pitchers were underrated, and Marcel had the
2027 Rockies at 78 wins. In the backtest, Marcel overrated the Rockies by 9 wins a season on
average.

## How it works

1. **Data.** `bucco extract mlb-park-splits`: each team's batting and pitching in home games and
   in road games, 2000 on. The schedule extract now also saves each game's ballpark, which tells
   when a team changed parks (Marlins 2012, Braves 2017, Rangers 2020, Rays at Steinbrenner and
   A's in Sacramento 2025, Rays back at Tropicana 2026, Blue Jays in Buffalo 2020-21).
2. **Factors** (`park_factors` mart), one per kind of event (singles, doubles, triples, home runs,
   unintentional walks, hit batters, strikeouts; runs for reference):
   - rate per PA in the team's home games (both teams batting) over the rate in its road games,
     on the log scale, centered each season, with half a count added to avoid zeros;
   - pooled over the season and up to two before it **at the same ballpark** (seasons with at
     least 75% of home games there), never a later season;
   - shrunk toward 1: weight = tau2 / (tau2 + noise), where tau2 is how strongly a park's
     single-season ratio carries over to its next season and noise is the rest, scaled by
     pooled PA. Both are set from 2000-2011 only, before the first backtest season. A three-season
     pool gets weight of about 0.8 for runs.
3. **Players.** A player gets about half of each park's effect (half his games at home), averaged
   over his teams by games in the field (batters) or innings (pitchers). His counts are divided
   by that, then wOBA, batting runs, FIP, pitching runs and WAR are recomputed (`*_neutral`
   columns) and rescaled each season so league totals are unchanged.
4. **Projections** (`marcel_park`, `marcel_park_optimized`: aging + fitted shrinkage + park)
   project from the neutral history; the age curves and shrinkage targets are fitted on it too.
   Nothing is re-applied for the forecast season: a park inflates a team's runs scored and
   allowed alike, so neutral values are the right ones for wins (as in FanGraphs WAR).

## Checks

- Coors Field: full runs factor about 1.3 before the humidor (2002), about 1.2 since (1.15 for
  2026), so about +10% for a Rockies player: in line with FanGraphs' halved factors.
- 2026 extremes: Coors, Sutter Health Park (A's), Citizens Bank Park high; T-Mobile Park,
  Globe Life Field, Wrigley, Busch low. Kauffman and Coors lead in triples.
- Rockies 2026 hitters lose 0.5-1.0 WAR (McCarthy 3.4 to 2.4); their pitchers gain about 0.1.

## What it yields

**Players**, scored against next season's park-neutral value (2012-2026 without 2020):

| | Batters (Off/600) | Changed teams | Rockies before or after | Pitchers (runs/700 BF) |
| --- | --- | --- | --- | --- |
| As played | 18.13 | 19.91 | 18.84, overrated by 4.3 | 16.81 |
| Park-neutral | **18.03** | **19.88** | **18.10, bias +0.1** | **16.77** |

**Teams** (RMSE in wins, 420 team-seasons):

| Model | RMSE | Before |
| --- | --- | --- |
| `marcel_park` | **9.89** | 9.98 (`marcel_shrunk`) |
| `marcel_park_optimized` | **9.89** | 10.02 (`marcel_shrunk_optimized`) |

- Better in 11 of 14 seasons for both (paired t 1.9 and 2.3).
- The Rockies' average error falls from -9.1 to -5.9 wins: still overrated, for reasons beyond
  the park (possibly the "Coors hangover" on the road, which a home/road factor does not model,
  or roster quality the projections miss).
- 2027: Rockies 78.0 to 73.8, A's 83.3 to 81.6, Mariners 80.7 to 82.0, Pirates 86.2 to 85.4.

## Not done

- Fence moves within a ballpark (Camden Yards 2022, Kauffman 2026) are only picked up as the
  three-season pool rolls forward; a list of reconfigurations could reset the pool.
- The outlook does not yet support `marcel_park_optimized`.

## By batter side (2026-11-25)

**What.** Separate factors for left- and right-side batters (`park_factors_by_side`), with each
player's park adjustment mixed by his own side: share of PA batting left for batters (switch
hitters in between), share of left-side batters faced for pitchers (`left_share` on the player
season tables).

**Data.** `bucco extract mlb-player-splits`: players' home and road lines, PA batting left and
right, and pitchers' batters faced by side, three league-wide requests per season. Team splits
cannot be crossed with batter side (the API's `combineSits` does not intersect them), so the
side difference is measured from each team's own hitters at home and on the road; visiting
hitters' lines at a park are not available. Switch hitters and traded players are left out.

**How.** For each team-season and side: log(home rate / road rate) for its left (or right)
handed hitters minus the same for all its hitters, centered each season, pooled over up to six
seasons at the same ballpark, shrunk toward 0, and applied on top of the all-batter factor.
The shrinkage's true spread comes from pairs of seasons 1-5 apart, 2000-2011 only.

**What the data says.** The true difference between sides at a typical park is small (home
runs about 3%, other events 1-3%), while one team's left-handed hitters give only 600-1,600
home PA a season (one-season noise about +/-23% for home runs). So after shrinkage the side
factors barely differ: at most 1.9% for home runs, 0.5% on average. Yankee Stadium's short
right field comes out at +0.4% for left-handed hitters.

**Backtest:** `marcel_park` 9.889 to 9.881, `marcel_park_optimized` 9.894 to 9.892, better in
9 of 14 seasons both: in the right direction but negligible.

**To do better** needs data that includes visiting hitters at each park, such as Baseball
Savant's Statcast park factors by batter side (manual download, recent seasons only), with the
all-batter factor kept for earlier seasons.

## Park fit for the forecast season (2026-11-25)

**Question.** Projections are park-neutral, which is right for team wins (a park inflates runs
scored and allowed alike). But parks change some events more than others (PNC Park 2026: home
runs -8%, doubles +19%, triples -24%), so a hitter's profile can suit his 2027 park better or
worse than a teammate's, which could change the optimal lineup and the free-agent order.

**How.** `marcel.batter_profiles`: each batter's event rates (Marcel-weighted, shrunk toward
league rates) and side mix. `park_runs_per_pa`: the runs per PA that profile gains or loses in
his team's park, at half the side-mixed factors through the season before (only if the team
plays in the same ballpark in the target season, from its schedule). `apply_park_fit`: minus
his team's PA-weighted average, so team totals are unchanged and only differences between
teammates remain; added to Off and WAR. Models `marcel_parkfit` and `marcel_parkfit_optimized`.

**Size.** 2027 fits have a spread of 0.6 runs per 600 PA (about 0.06 WAR), from -1.9 to +3.7.
They behave as expected: PNC favors doubles hitters (Mangum +1.2, Gonzales +0.9) over power
(Valdez -1.4, Henry Davis -1.1); Yankee Stadium favors power (Judge +1.9); Coors favors speed
(McCarthy +3.3). Among the Pirates' top free agents: Bohm +0.5, Arozarena 0.0, Suzuki -0.8,
Chisholm -1.1, Suárez -1.6 (about +/-0.15 WAR).

**Backtest:** `marcel_parkfit` 9.886 against `marcel_park` 9.881 (better in 6 of 14 seasons);
`marcel_parkfit_optimized` 9.901 against 9.892 (5 of 14). No gain: the fit changes little
within a team, and what it changes is within noise.

**Status:** built and registered, not adopted for the forecast.

## Status

Adopted for our own projections: `marcel_park` and `marcel_park_optimized` are the best
own-projection models (9.89). Steamer stays the model of record.
