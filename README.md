# bucco_forecasting

A hobby project to forecast the Pittsburgh Pirates' regular season record before Opening Day.

The project started out predicting the outcome of individual Pirates games. That version is archived in [legacy/](legacy/). The current goal is a full-season forecast, starting with the 2027 season.

## What the forecast will look like

Each forecast gives a range, not just a single number. For example: "78 wins, 80% chance of finishing between 69 and 87, 14% playoff odds." (Those numbers are made up to show the format.)

Each preseason forecast will include:

- Expected wins and a likely range
- Odds of finishing in each spot in the division
- Playoff odds

The forecast can be re-run during the offseason as trades, signings and injuries happen. The version on Opening Day is the one that counts. Updating the forecast during the season is planned for a later phase.

## How it works

The plan is to start with a very simple model and add more involved ones over time. Every model is tested the same way: predict the record of every MLB team for each past season from 2001 to 2026, using only information that was available before that season started. A new model only replaces the current one if it does better on that test.

All 30 teams are used for testing because the Pirates alone only give about 25 seasons, which isn't enough to tell good models from lucky ones.

The planned models, roughly in order:

| Step | Model | Idea |
| --- | --- | --- |
| 0 | Constant | Every team wins 81 |
| 1 | Last year | Every team repeats last season's record |
| 2 | Blend of public forecasts | Weight preseason projections from established forecasters, plus betting win totals if historical data can be found |
| 3 | FanGraphs team WAR | Turn projected team WAR into wins |
| 4a | Roster, public player projections | Add up projected WAR for each player on the roster using systems like ZiPS, Steamer and PECOTA |
| 4b | Roster, own player projections | Same as 4a, but with player projections built here (recent seasons, aging, regression to average) |
| 5 | Season simulation | Simulate the actual schedule thousands of times to get the win range, division finish and playoff odds |
| 6 | In-season updates | Adjust the preseason forecast as games are played |
| 7 | Ensemble | Combine the best models |
| 8 | What-if scenarios | Estimate how a trade, injury or player slump changes the forecast |

### What counts as a good forecast

Even a perfect model would miss by about 6 wins in a typical season, just from the luck of 162 games. Roughly:

- Guessing 81 wins for every team misses by about 11 wins.
- The best public projection systems miss by about 7 to 8 wins.

So the room for improvement is small, and the testing has to be careful enough to tell real gains from noise. These figures are estimates and will be checked against this project's own backtests.

## Data

- **MLB Stats API:** the season calendar and final standings for every team, 2000 to now. This is the source for the first steps (checked: 30 teams every season, team IDs stay the same through moves and renames)
- **Public projections:** FanGraphs, ZiPS, Steamer, PECOTA, betting win totals. Collected by hand for now, since no free historical archive has been confirmed. See [data/manual/projections](data/manual/projections/README.md)
- **Player history (later):** needed for the roster models. The Lahman database was the plan, but the GitHub repository it was downloaded from no longer exists, so the source still needs picking
- **Retrosheet and the Chadwick Bureau register:** game logs, schedules and a player ID crosswalk, for the later steps

Data that can be downloaded again isn't stored in the repo. Instead, each source has a written description of how to fetch it. The exception is data that changes or disappears, such as preseason projections, betting lines and Opening Day rosters. Copies of those are kept so past forecasts can be reproduced.

## Tools

- DuckDB for storage, with raw downloads saved as Parquet files
- dbt for cleaning and joining data
- Python (pandas, NumPy, scikit-learn, statsmodels) for models and simulation
- A small command-line tool to run each step, with scheduled runs added once in-season updates start
- uv for managing the Python environment

## Status

- [x] Plan written
- [x] Old per-game model archived in [legacy/](legacy/)
- [ ] Set up the new project layout and load historical team records
- [ ] Build the testing setup and the first simple models
- [ ] Publish a first 2027 forecast before Opening Day

The full plan, including goals, data rules, risks and decisions made so far, is in [docs/planning](docs/planning/img/Bucco%20Forecasting%20Season%20Win%20Model%20Plan.md).
