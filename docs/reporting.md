# Reporting design

Status: implemented (`bucco report`). See [cli.md](cli.md) for usage.

## Purpose

Turn a saved forecast into a web page that a Pirates fan can read without knowing anything about the model, and that you can publish and share. The page leads with the Pirates, then shows the league, then explains how much to trust the numbers.

## Decisions

| Question | Decision |
| --- | --- |
| Audience | You, plus public readers |
| Depth | Fan-friendly. Headline forecast and plain-language text first, methods and scores lower down |
| Model shown | The best model on the leaderboard (lowest RMSE, 2020 excluded). The baselines are shown for comparison |
| Cadence | On demand. Each report is stamped with its as-of date and kept. The Opening Day report is the forecast of record |
| Format | One self-contained HTML file, built by a Python script, with inline SVG charts. No JavaScript libraries, works offline |
| Location | `reports/<season>/<model>_<as-of>.html`, committed to git |
| Missing odds | Playoff and division odds are hidden until the season simulator exists |
| Extras | A "What changed" note. Not included: downloadable CSV, NL Central view, change-vs-last-season, Pirates-voice tone, data and methods footer (see Open items) |

## Command

```
bucco report                          # best model, latest forecast for the upcoming season
bucco report --model last_year        # override the model
bucco report --as-of 2027-03-15       # use the saved forecast with this as-of date
```

The report reads only saved results (`forecasts.season_forecasts` and `evaluate.backtest_results`), never recomputes a model. If there is no saved forecast for the requested model, season and as-of date, it stops and says to run `bucco forecast` first. If the model is missing from the leaderboard it stops and says to run `bucco backtest`.

## Page layout

Top to bottom:

### 1. Pirates headline

- Season, model name, as-of date, and a badge if this is the Opening Day forecast of record ("Forecast of record") or an earlier one ("Preliminary").
- Expected wins and the 80% range, for example "78 wins, 80% range 69 to 87".
- Two probability lines from the same distribution:
  - Chance of finishing above .500 (82 or more wins).
  - Chance of winning more games than last season.
- A sentence of plain-language explanation of what the range means.

### 2. What changed

A short note comparing this report with the previous saved report for the same season: the change in the Pirates' expected wins, and any difference in model or inputs. For the first report of a season, it says so.

### 3. Pirates over time

A small chart of the Pirates' expected wins by as-of date, with the 80% range as a band and the Opening Day version flagged. This section is hidden until there are at least two saved as-of dates.

### 4. League range chart

One row per team, sorted by expected wins: a dot for expected wins and a bar for the 80% range. The Pirates row is highlighted. A vertical line marks 81 wins.

### 5. How much to trust this

- **Leaderboard:** the model against the baselines (constant 81 wins and last year's record). Columns: MAE, RMSE, 80% interval coverage. Scored on 2001 to the latest complete season.
- **Pirates' past errors:** predicted against actual wins for each season, as a small chart or table. Labeled as interesting, not used to choose models.
- **Plain-language caveats:**
  - Even a perfect model would miss by about 6 wins in a typical season from luck alone.
  - What the forecast does not know: trades, signings and injuries after the as-of date, and anything about individual players for the current baseline models.

### 6. Footer

Short: report generated date, as-of date, git commit, and a data credit for the MLB Stats API. Details are kept to what the licence and honest reporting require.

## Data the report needs

| Item | Source |
| --- | --- |
| Forecast rows (team, mean, sd, as-of date) | `forecasts.season_forecasts` |
| Previous report's forecast, for "What changed" | Same table, earlier as-of date |
| Leaderboard and Pirates past errors | `evaluate.backtest_results`, through the existing `evaluate` functions |
| Last season's wins, for "beat last year" | `marts.team_seasons` |
| Opening Day, for the forecast-of-record badge | `marts.team_season_features.opening_day` |

## How the probabilities are computed

Each team's forecast is a normal distribution on win percentage (mean and sd from the model). The Pirates probability lines convert it to wins (times 162) and take the area above a threshold, using a continuity correction since wins are whole numbers: the chance of 82 or more wins is the area above 81.5.

Because the spread comes from past errors and 80% coverage is close to 0.80, this is reasonable. It is stated on the page as an estimate, not a guarantee.

## Build plan

1. `src/bucco/report/data.py`: load and assemble the inputs above into one plain dictionary. No HTML here.
2. `src/bucco/report/charts.py`: functions that return SVG strings for the range chart and the timeline, with light and dark colours.
3. `src/bucco/report/render.py`: builds the HTML from the dictionary and writes `reports/<season>/<model>_<as-of>.html`.
4. `bucco report` in the CLI, plus a section in `docs/cli.md`.
5. Tests: probabilities against known values, "What changed" for the first report and for a later one, chart functions return valid SVG for a full league, and the report refuses to run with no saved forecast.

## Open items

- **Footer and methods detail:** you did not select the data-and-methods footer. The design keeps a minimal footer (generated date, as-of date, git commit, MLB data credit) because MLB's terms call for acknowledgement. Confirm or trim this.
- **2020:** the leaderboard excludes 2020 by default. The report needs a one-line note saying so, or the scores will look unexplained.
- **Test forecast in the database:** a trial `bucco forecast` run with `--as-of 2027-02-01` was saved to `forecasts.season_forecasts`. Delete it before building the report, or the "What changed" and timeline sections will treat it as real history.
- **Playoff and division odds:** when the simulator exists, add them to section 1 and a division-finish table to section 4.
- **Publishing:** reports are committed to git. Publishing them (for example GitHub Pages) is a later decision.
- **Opening Day lock:** "forecast of record" means the latest forecast made on or before Opening Day. The report should compute that, not rely on a manual label.

## Editing the written content

All prose in the report lives in `config/report_text.yml`, not in code. Edit it and re-run `bucco report` to rebuild. Generated files in `reports/` are overwritten on every build, so they should never be edited by hand. The project skill `.claude/skills/update-report-text/SKILL.md` lets an agent apply forecaster feedback this way: it edits the text file, rebuilds with the same model, season and as-of date, and reports what changed.
