# Availability: Opening Day injured list and 40-man status (2026-11-25)

## What we tried

Scale each player's projected playing time by his status on his team's Opening Day 40-man
roster: what a forecaster knows about injuries when the season starts, and what Steamer's own
files (made just before Opening Day) know. Our model knew nothing about injuries: it gave Cole
Ragans, Luinder Avila and Stephen Kolek, all on the 60-day injured list, 50 to 60 innings each
in 2027, where Steamer gives them about 1.

## The data

The MLB Stats API gives a team's 40-man roster on any date, with each player's status (`A`
active, `D60`/`D15`/`D10`/`D7` injured list, `RM` and others in the minors). `bucco extract
mlb-rosters` takes it on each team's first regular-season game (teams opening abroad on their
own date), 2012 on; mart `player_preseason_status`. 23 to 61 players a season start on the 60-day
list (more in recent seasons) and 74 to 116 on a shorter one.

The injured list is cleared after the World Series, so a November snapshot shows almost no one:
none on 2025-11-25, four on 2026-11-25 (Ragans, Avila, Kolek and Spencer Strider, kept on the
60-day list). The transactions feed has every injured-list move with the injury (for example
"Left elbow impingement") and would be the way to know about injuries in the offseason; not
used yet.

## What players delivered

Projected playing time delivered (actual over projected), rostered players, 2012–2026 without
2020. Projected is Marcel's PA formula for batters and baseline innings for pitchers.

| Opening Day status | Batters | Pitchers | Pitcher-seasons |
| --- | --- | --- | --- |
| 60-day injured list | 0.19 | 0.20 | 421 |
| 7-, 10- or 15-day injured list | 0.56 | 0.67 | 849 |
| Active 40-man (incl. optioned) | 0.86 | 1.15 | 6,609 |
| Not on the 40-man roster | 0.11 | 0.41 | 4,208 |

Both eras look alike (60-day list 0.19 batters, 0.15–0.23 pitchers). A surprise: Steamer's
preseason team lists, which we use as rosters, include non-roster invitees and minor leaguers,
who deliver very little; we were projecting them as if they would play.

## How

`bucco.models.availability`: for each target season, batters and pitchers separately, each
group's factor is delivered over projected on earlier seasons only (2020 targets left out); a
group needs 30 earlier rows (2012 gets none). Applied to rostered players' projected PA or
innings (and the WAR, runs and so on that scale with them) before the lineup and staff
optimizers. Unsigned players get none, so free agents are not marked down for being off a
40-man roster. Loader option `availability` ("none", "relative" to active players, "absolute").

## What it yields

Wins RMSE, 2012–2026 without 2020:

| | 2012–26 | 2012–19 | 2021–26 | Better than without | t |
| --- | --- | --- | --- | --- | --- |
| `marcel_staff_optimized` before | 9.745 | 9.378 | 10.215 | | |
| Injured-list factors only (relative) | 9.714 | | 10.186 | | |
| Off-40-man factor only (relative) | 9.738 | | 10.200 | | |
| Both, relative to active players | 9.703 | 9.330 | 10.178 | 8 of 14 | −0.6 |
| **Both, absolute (kept)** | **9.691** | 9.331 | 10.152 | 8 of 14 | −0.8 |

Most of the gain is the injured list. "Absolute" also recalibrates active 40-man players (0.86 of
Marcel's PA, 1.15 of baseline innings); it is measured, not tuned. A modest gain, consistent
across eras, weak season by season.

**2027** (snapshot 2026-11-25): Ragans, Kolek, Strider and Avila drop to about 10 innings each;
50 batters and 104 pitchers on preseason lists are off their 40-man rosters. Royals 79.4 to
77.4 wins; Pirates 85.4 to 86.3 (5th).

## Status

Adopted in `marcel_staff_optimized` (9.69; Steamer 9.50).

## Next

- Rerun `bucco extract mlb-rosters` just before Opening Day: the forecast of record should use
  that snapshot, as the backtest does.
- Offseason injuries from the transactions feed (who ended the season on the 60-day list, and
  with what), for November forecasts.
- By injury type and timing (an elbow surgery in August is not a hamstring in March).
