# Preseason projections (collected by hand)

Step 3 of the model ladder blends public preseason win projections and betting win totals. No free, reliable historical archive has been confirmed, so these files are collected by hand and kept in git. They can't be downloaded again later.

Put one or more CSV files in this folder, then run `bucco extract projections`. The command checks every file and stops with a list of problems if anything is off. Files starting with `_` are ignored.

## File format

One row per team per projection set.

| Column | Required | Notes |
| --- | --- | --- |
| `season` | yes | The season being projected, e.g. `2019` |
| `source` | yes | Short lowercase name for where it came from, e.g. `fangraphs_depth_charts`, `steamer`, `pecota`, `consensus_win_total` |
| `kind` | yes | `projection` (a model's forecast) or `market` (a betting win total) |
| `as_of_date` | yes | Date the numbers were published or captured, `YYYY-MM-DD`. Must be on or before Opening Day |
| `team_abbr` or `team_id` | yes | MLB team id, or an abbreviation. Current and older abbreviations both work (`ARI`/`AZ`, `CWS`/`CHW`, `OAK`/`ATH`, `WSH`/`WAS`). See `transform/seeds/teams.csv` |
| `projected_wins` | yes | Projected regular-season wins over a 162-game season. Betting totals like `81.5` are fine |
| `source_url` | no | Where the numbers came from |
| `notes` | no | Anything worth remembering, e.g. "captured from Wayback Machine" |

See [_template.csv](_template.csv) for an example.

## Rules the checks enforce

- Each combination of season, source and as-of date must include all 30 teams.
- No repeated rows for the same season, source, as-of date and team.
- `as_of_date` can't be after that season's Opening Day. A projection made after games start would leak results into the backtest.
- `projected_wins` must be between 40 and 125.
- You'll get a warning (not an error) if a set's team wins don't add up to between 2,300 and 2,550.

## Where to look (not yet checked)

None of these has been confirmed to work. Check each site's terms of use before copying data.

- Archived copies (Wayback Machine) of FanGraphs projected standings pages
- Baseball Prospectus PECOTA standings archives
- Sportsbook preseason win total archives
- Your own notes from past seasons

Keep the search short. If nothing usable turns up, that's a fine answer: skip step 3's backtest for the years without data, and start saving projections every preseason from 2027 on. Past years can't be reproduced later, so each year's snapshot should be saved in the preseason.

## Player-level projections (FanGraphs downloads)

Individual player projections (for example ZiPS) downloaded from FanGraphs go in this same folder, unchanged, with this file name:

```
<source>_<batters|pitchers>_individual_<season>.csv      e.g. zips_batters_individual_2024.csv
```

Then run `bucco extract player-projections` (also part of `bucco extract all`) and `bucco build`. Files named `streamer_...` are read as the source `steamer`. These files are skipped by the team-level checks above and have their own.

**Record the download date.** FanGraphs doesn't put it in the file. Add one line per file to [_player_downloads.csv](_player_downloads.csv) (`file, as_of_date, source_url, notes`). A blank date is allowed, but the file can't be checked against Opening Day, and models must not use it. `dbt build` shows a warning (`assert_player_projections_dated`) until every file has a date. If a download was made after Opening Day, the team on each row may be post-trade, so it is a leak risk and is rejected.

Checks that stop the extract with an error:

- Required columns present (`Name`, `Team`, `PlayerId`, `MLBAMID`, `WAR`, plus `PA` for batters or `IP` for pitchers).
- Each team abbreviation is recognised (FanGraphs' `KCR`, `SDP`, `SFG`, `TBR`, `WSN`, `CHW` and `ATH`/`OAK` all work).
- All 30 teams appear in every file.
- No player appears twice in the same file.
- WAR is between -10 and 20.
- The download date is on or before Opening Day.

A warning (not an error) appears when a season has batters but no pitchers, or the reverse.

**These are not rosters** (ZiPS; Steamer is different, see below). Players are not projected for a full season (in the 2026 batter file the median is about 400 plate appearances, and only 57 of 1,903 players reach 600), but each player's playing time is estimated on its own, not shared out within a team. Each team's rows include depth and minor-league players, so a team's batters add up to roughly 22,000 to 26,000 plate appearances (a real team has about 6,200) and hundreds of players have negative WAR. Adding up `WAR` by team does not give a team forecast. Turning these files into team totals needs playing time allocated per team, which is the job of the roster-based models (rung 5a). The team-level rungs (3 and 4) need a team-level export instead, such as FanGraphs Depth Charts team projections.

**Steamer is the exception.** From 2014 on its playing time is already shared out within each team (about 5,500 to 6,100 PA and 1,500 IP per team), so the `steamer` model sums its WAR as it is. Steamer 2013 is a raw list of every player and is run through the depth chart instead. See [docs/R&D/steamer.md](../../../docs/R&D/steamer.md).

## TODO: player positions

The player files above have no position column. The plan is to get positions from the MLB Stats API, keyed on `MLBAMID`, as a player × season table in which each player's listed position for a season is determined from the **prior** season, so nothing from the forecast year leaks in. Details and open questions are in the TODO under *Open questions* in the [planning doc](../../../docs/planning/img/Bucco%20Forecasting%20Season%20Win%20Model%20Plan.md). Nothing needs to be added to the CSV files for this.
