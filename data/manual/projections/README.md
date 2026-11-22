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
