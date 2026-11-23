"""Score the batter depth chart against real playing time and wins, for every projection season on disk.

    uv run python scripts/eval_depth_chart.py                      # the defaults
    uv run python scripts/eval_depth_chart.py def_weight=0.3 rank_decay=0.4   # one setting
    uv run python scripts/eval_depth_chart.py --grid def_weight=1,0.6,0.4     # a sweep
    uv run python scripts/eval_depth_chart.py --source steamer --compare      # another system

Reports, per setting: player PA error (RMSE of allocated vs real PA, players on rosters with
projections), average starter PA, average team WAR (batters + pitchers) and leave-one-season-out
wins error (a line from team WAR, minus that season's league average, to wins, fit on the
other seasons). See docs/R&D/depth_chart.md.

Needs: the player-projections and mlb-positions extracts, `dbt build` (marts.player_position_games,
marts.team_seasons), and one MLB API call per team-season for real PA, cached in
data/cache/mlb_api/hitting_pa/. A season with no completed games gets no wins and is skipped.
"""

from __future__ import annotations

import argparse
import sys

import duckdb
import numpy as np
import pandas as pd

from bucco.config import CACHE_DIR, DUCKDB_PATH, TEAMS_SEED
from bucco.extract._io import get_json
from bucco.extract.mlb_api import BASE_URL
from bucco.models import depth_chart as dc

PA_DIR = CACHE_DIR / "mlb_api" / "hitting_pa"
SHORT_SEASONS = {2020}  # 60 games: real PA and wins are not comparable with a full-season projection


def seasons_on_disk(con, source: str = "zips") -> list[int]:
    """Seasons with both batter and pitcher rows for `source` in the player_projections mart."""
    rows = con.execute("select season from marts.player_projections where source = ? "
                       "group by 1 having count(distinct player_type) = 2 order by 1",
                       [source]).fetchall()
    return [r[0] for r in rows if r[0] not in SHORT_SEASONS]


def real_pa(season: int) -> pd.DataFrame:
    """Every player's real PA per team for one season (cached after the first fetch)."""
    path = PA_DIR / f"season={season}.parquet"
    if path.exists():
        return pd.read_parquet(path)
    rows = []
    for team in pd.read_csv(TEAMS_SEED, dtype=str)["team_id"]:
        payload = get_json(f"{BASE_URL}/stats", params={
            "stats": "season", "group": "hitting", "season": season, "sportId": 1,
            "playerPool": "ALL", "teamId": int(team), "limit": 300, "gameType": "R"})
        for split in payload["stats"][0]["splits"] if payload.get("stats") else []:
            rows.append({"season": season, "team_id": int(team), "mlbam_id": split["player"]["id"],
                         "pa": split["stat"]["plateAppearances"]})
    df = pd.DataFrame(rows, columns=["season", "team_id", "mlbam_id", "pa"])
    path.parent.mkdir(parents=True, exist_ok=True)
    df.to_parquet(path)
    return df


def load(source: str = "zips"):
    con = duckdb.connect(str(DUCKDB_PATH), read_only=True)
    games = con.sql("select season, mlbam_id, position, games from marts.player_position_games").df()
    wins = con.sql("select season, team_id, wins from marts.team_seasons").df().set_index(
        ["season", "team_id"])["wins"]
    seasons = [s for s in seasons_on_disk(con, source) if s in set(games["season"]) and
               (wins.index.get_level_values(0) == s).any()]
    projections = con.execute("select * from marts.player_projections where source = ?",
                              [source]).df()
    bat, pit = [], []
    for yr in seasons:
        this = projections[projections["season"] == yr]
        b = this[this["player_type"] == "batter"].rename(columns={
            "plate_appearances": "pa", "bsr_runs": "bsr"})
        b = b.merge(real_pa(yr).rename(columns={"pa": "real_pa"}),
                    on=["season", "team_id", "mlbam_id"], how="left").fillna({"real_pa": 0})
        b["bsr_pct"] = dc.bsr_percentiles(b)
        bat.append(dc.build_batter_pool(b[["season", "team_id", "mlbam_id", "player_name", "pa", "war",
                                           "def_runs", "bsr", "bsr_pct", "real_pa"]],
                                        games[games["season"] == yr]))
        p = this[this["player_type"] == "pitcher"].rename(columns={
            "innings_pitched": "ip", "games_started": "gs"})
        pit.append(p[["season", "team_id", "mlbam_id", "player_name", "ip", "war", "gs"]])
    pool = pd.concat(bat, ignore_index=True)
    pool["key"] = list(zip(pool["season"], pool["team_id"], strict=True))
    pitchers = pd.concat(pit, ignore_index=True)
    pitcher_war = pd.concat(
        [dc.build_pitcher_depth_chart(g) for _, g in pitchers.groupby(["season", "team_id"])]
    ).groupby(["season", "team_id"])["scaled_war"].sum()
    return pool, pitcher_war, wins, seasons, pitchers


def loso_wins_error(team_war: pd.Series, wins: pd.Series, seasons: list[int],
                    center: bool = True) -> tuple[float, float]:
    df = pd.concat([team_war.rename("w"), wins], axis=1).dropna()
    if center:  # ZiPS team-WAR levels drift between seasons (about 20 in 2011-13, 43 now)
        df["w"] = df["w"] - df.groupby(level=0)["w"].transform("mean")
    errors = []
    for yr in seasons:
        train = df[df.index.get_level_values(0) != yr]
        test = df[df.index.get_level_values(0) == yr]
        if train.empty or test.empty:
            continue
        slope, intercept = np.polyfit(train["w"], train["wins"], 1)
        errors += list(test["wins"] - (intercept + slope * test["w"]))
    return float(np.sqrt(np.mean(np.square(errors)))), float(df["w"].corr(df["wins"]))


def score(pool, pitcher_war, wins, seasons, **params) -> dict:
    out = dc.depth_chart_by_team(pool, group="key", **params)
    team = out.groupby(["season", "team_id"])["scaled_war"].sum()
    total = (team + pitcher_war).dropna()
    err, corr = loso_wins_error(total, wins, seasons)
    return {"pa_error": float(np.sqrt(((out["allocated"] - out["real_pa"]) ** 2).mean())),
            "starter_pa": float(out.loc[out["role"] == "starter", "allocated"].mean()),
            "team_war": float(total.mean()), "wins_error": err, "corr": corr}


def compare(pool, pitcher_war, wins, seasons, pitchers) -> pd.DataFrame:
    """Team WAR -> wins, leave-one-season-out, for simpler ways of turning projections into a team."""
    from bucco.models.playing_time import allocate_by_team

    keys = ["season", "team_id"]
    rate = (pool["war"] / pool["pa"]).where(pool["pa"] > 0, 0.0)
    bat = {
        "WAR summed, no allocation": pool.groupby(keys)["war"].sum(),
        "volume-ranked, 6,240 PA budget": allocate_by_team(
            pool, "pa", 6240.0, group="key",
            cap=700, rank_by="volume").groupby(keys)["scaled_war"].sum(),
        "rate-ranked regulars first": allocate_by_team(
            pool, "pa", 6240.0, group="key", cap=700, rank_by="rate",
            min_volume=200).groupby(keys)["scaled_war"].sum(),
        "depth chart (ours)": dc.depth_chart_by_team(pool, group="key").groupby(keys)["scaled_war"].sum(),
        "oracle: projected rates x real PA": (rate * pool["real_pa"]).groupby(
            [pool["season"], pool["team_id"]]).sum(),
    }
    pit_raw = pitchers.groupby(keys)["war"].sum()
    pit_vol = pd.concat([
        allocate_by_team(g, "ip", 1500.0, group=keys, war="war", rank_by="volume")
        for _, g in pitchers.groupby("season")]).groupby(keys)["scaled_war"].sum()
    rows = []
    for name, b in bat.items():
        p = pit_raw if name.startswith("WAR summed") else (
            pit_vol if "volume" in name else pitcher_war)
        total = (b + p).dropna()
        err, corr = loso_wins_error(total, wins, seasons)
        bat_err, _ = loso_wins_error(b.dropna(), wins, seasons)
        rows.append({"method": name, "team_war": total.mean(), "wins_error": err,
                     "corr": corr, "batters_only_error": bat_err})
    return pd.DataFrame(rows)


def parse(values: list[str]) -> dict:
    return {k: float(v) for k, v in (item.split("=") for item in values)}


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    ap.add_argument("params", nargs="*", help="name=value overrides of build_batter_depth_chart")
    ap.add_argument("--source", default="zips", help="projection system, e.g. zips or steamer")
    ap.add_argument("--compare", action="store_true", help="compare with simpler team-WAR rules")
    ap.add_argument("--seasons", help="first-last, e.g. 2022-2026: score only these seasons")
    ap.add_argument("--grid", help="name=v1,v2,... to sweep one parameter")
    args = ap.parse_args(argv)
    pool, pitcher_war, wins, seasons, pitchers = load(args.source)
    if args.seasons:
        first, last = (int(x) for x in args.seasons.split("-"))
        seasons = [y for y in seasons if first <= y <= last]
        pool = pool[pool["season"].between(first, last)]
        pitchers = pitchers[pitchers["season"].between(first, last)]
        pitcher_war = pitcher_war[pitcher_war.index.get_level_values(0).isin(seasons)]
        wins = wins[wins.index.get_level_values(0).isin(seasons)]
    print(f"source: {args.source}; seasons: {seasons}; team-seasons with wins: {len(pitcher_war.index.intersection(wins.index))}")
    if args.compare:
        print(compare(pool, pitcher_war, wins, seasons, pitchers).round(3).to_string(index=False))
        return
    base = parse(args.params)
    rows = []
    if args.grid:
        name, values = args.grid.split("=")
        for v in values.split(","):
            rows.append({name: float(v), **score(pool, pitcher_war, wins, seasons, **base, **{name: float(v)})})
    else:
        rows.append({**base, **score(pool, pitcher_war, wins, seasons, **base)})
    print(pd.DataFrame(rows).round(3).to_string(index=False))


if __name__ == "__main__":
    main(sys.argv[1:])
