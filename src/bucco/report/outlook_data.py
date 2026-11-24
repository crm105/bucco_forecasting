"""Gather everything a team outlook shows into one plain dictionary. No HTML in this module.

The outlook explains one team's forecast from a player-projection model (for example
`steamer_optimized`): where its value comes from position by position, how it compares with the
league and its division, and which unsigned players would help most. Every number is computed
here from the database and the projection files, so the page can be rebuilt at any time
(`bucco outlook`). See docs/R&D/lineup_optimizer.md for the lineup optimizer it relies on.

Batting comes from the lineup optimizer (every team fills the same PA at every position);
pitching is the projection as given, which is what the forecast uses.
"""

from __future__ import annotations

from datetime import date
from pathlib import Path

import duckdb
import numpy as np
import pandas as pd

from bucco.config import DUCKDB_PATH
from bucco.evaluate.metrics import Z_80
from bucco.extract.projections import INPUT_DIR
from bucco.models import lineup_optimizer as lo
from bucco.models.base import GAMES

# Current alignment (since 2013). Abbreviations as in the teams seed.
DIVISIONS = {
    "AL East": ["BAL", "BOS", "NYY", "TB", "TOR"],
    "AL Central": ["CLE", "CWS", "DET", "KC", "MIN"],
    "AL West": ["ATH", "HOU", "LAA", "SEA", "TEX"],
    "NL East": ["ATL", "MIA", "NYM", "PHI", "WSH"],
    "NL Central": ["CHC", "CIN", "MIL", "PIT", "STL"],
    "NL West": ["AZ", "COL", "LAD", "SD", "SF"],
}
MODEL_SOURCE = {"steamer_optimized": "steamer", "steamer": "steamer", "depth_chart": "zips"}
SPOTS = ["Rotation", "Bullpen", *lo.POSITIONS]      # rows of the position comparison
STRONG_RANK = 10          # a spot ranked this high or better is a strength
WEAK_RANK = 21            # this low or worse is a weakness
LEADERS = 9               # players per leaders table
FA_CANDIDATES = 40        # unsigned batters re-optimized (best by WAR per 600 PA)
FA_MIN_PA = 150           # projected PA for an unsigned batter to be screened
FA_SHOWN = 10
SP_IP = 175.0             # innings a signed starter is credited with
RP_MIN_IP = 30.0          # relievers this busy count as the team's bullpen
RECENT_SEASONS = 5        # "recent" backtest window


def _query(sql: str, params: list | None = None, path=DUCKDB_PATH) -> pd.DataFrame:
    if not Path(path).exists():
        raise RuntimeError(f"{path} not found. Run `bucco extract all` and `bucco build` first.")
    with duckdb.connect(str(path), read_only=True) as con:
        return con.execute(sql, params or []).df()


def ordinal(n: int) -> str:
    suffix = "th" if 10 <= n % 100 <= 20 else {1: "st", 2: "nd", 3: "rd"}.get(n % 10, "th")
    return f"{n}{suffix}"


def rank_of(values: pd.Series, key, higher_is_better: bool = True) -> int:
    return int(values.rank(ascending=not higher_is_better, method="min")[key])


# ---- forecast and model scores -----------------------------------------------------------
def forecast_table(model: str, season: int, as_of: str | None, abbr: pd.Series,
                   path=DUCKDB_PATH) -> tuple[pd.DataFrame, str]:
    """Every team's forecast wins and 80% range from the saved forecast (latest as-of if None)."""
    rows = _query("select * from forecasts.season_forecasts where model = ? and season = ?",
                  [model, season], path)
    if rows.empty:
        raise RuntimeError(f"no saved {model} forecast for {season}. "
                           f"Run `bucco forecast --model {model}` first.")
    rows["as_of_date"] = rows["as_of_date"].astype(str)
    as_of = as_of or rows["as_of_date"].max()
    rows = rows[rows["as_of_date"] == as_of]
    if rows.empty:
        raise RuntimeError(f"no {model} forecast for {season} as of {as_of}")
    out = pd.DataFrame({"team": rows["team_id"].map(abbr), "wins": rows["pred_win_pct"] * GAMES,
                        "sd": rows["sd_win_pct"] * GAMES}).set_index("team")
    out["low"], out["high"] = out["wins"] - Z_80 * out["sd"], out["wins"] + Z_80 * out["sd"]
    out["rank"] = out["wins"].rank(ascending=False, method="min").astype(int)
    return out, as_of


def backtest_scores(model: str, path=DUCKDB_PATH) -> dict:
    """RMSE in wins over all scored seasons and the most recent RECENT_SEASONS (2020 left out)."""
    res = _query("select season, pred_win_pct, actual_win_pct from evaluate.backtest_results "
                 "where model = ? and season <> 2020", [model], path)
    if res.empty:
        return {}
    err = (res["pred_win_pct"] - res["actual_win_pct"]) * GAMES
    seasons = sorted(res["season"].unique())
    recent = res["season"] >= seasons[-RECENT_SEASONS]
    return {"rmse": float(np.sqrt((err ** 2).mean())), "first": int(seasons[0]),
            "last": int(seasons[-1]), "rmse_recent": float(np.sqrt((err[recent] ** 2).mean())),
            "recent_first": int(seasons[-RECENT_SEASONS])}


# ---- team WAR, position by position ------------------------------------------------------
def pitcher_roles(pitchers: pd.DataFrame) -> pd.Series:
    """SP if at least half his projected games are starts, else RP."""
    share = pitchers["games_started"] / pitchers["games"].where(pitchers["games"] > 0)
    return pd.Series(np.where(share >= 0.5, "SP", "RP"), index=pitchers.index)


def spot_war(alloc: pd.DataFrame, pitchers: pd.DataFrame, abbr: pd.Series) -> pd.DataFrame:
    """WAR per team (rows, by abbreviation) and spot (columns: positions, SP, RP)."""
    bat = alloc.groupby(["team_id", "position"])["war"].sum().unstack(fill_value=0.0)
    bat = bat.reindex(columns=list(lo.POSITIONS), fill_value=0.0)
    pit = pitchers.assign(role=pitcher_roles(pitchers)).groupby(["team_id", "role"])["war"] \
        .sum().unstack(fill_value=0.0).reindex(columns=["SP", "RP"], fill_value=0.0)
    table = bat.join(pit, how="outer").fillna(0.0)
    table.index = table.index.map(abbr)
    return table


def who_plays(alloc: pd.DataFrame, team_id: int, position: str, n: int = 3) -> list[dict]:
    rows = alloc[(alloc["team_id"] == team_id) & (alloc["position"] == position)]
    rows = rows.sort_values("pa", ascending=False).head(n)
    return [{"name": r.player_name, "pa": float(r.pa), "replacement": r.mlbam_id < 0}
            for r in rows.itertuples()]


def spot_rows(table: pd.DataFrame, team: str, alloc: pd.DataFrame, team_id: int,
              pitchers: pd.DataFrame) -> list[dict]:
    rows = []
    roles = pitcher_roles(pitchers)
    mine = pitchers[pitchers["team_id"] == team_id].assign(role=roles)
    for spot in SPOTS:
        col = {"Rotation": "SP", "Bullpen": "RP"}.get(spot, spot)
        values = table[col]
        if spot in ("Rotation", "Bullpen"):
            top = mine[mine["role"] == col].sort_values("war", ascending=False).head(4)
            who = [{"name": r.player_name, "war": float(r.war)} for r in top.itertuples()]
        else:
            who = who_plays(alloc, team_id, spot)
        rows.append({"spot": spot, "war": float(values[team]), "avg": float(values.mean()),
                     "rank": rank_of(values, team), "best": float(values.max()),
                     "best_team": str(values.idxmax()), "who": who})
    return rows


def run_components(alloc: pd.DataFrame, inputs: pd.DataFrame, batters: pd.DataFrame,
                   abbr: pd.Series) -> pd.DataFrame:
    """Batting, baserunning and defense runs per team in the optimized lineups."""
    keys = ["team_id", "mlbam_id"]
    played = alloc[alloc["mlbam_id"] >= 0].merge(
        inputs[keys + ["o_rate", "proj_pa"] + [f"def_{q}" for q in lo.POSITIONS]], on=keys)
    played = played.join(played.groupby(keys)["pa"].sum().rename("total"), on=keys)
    proj = batters.set_index(keys)
    bsr = (proj["bsr_runs"] / proj["plate_appearances"]).rename("bsr_rate")
    played = played.join(bsr, on=keys)
    offense = played["pa"] * lo.offense_rate(played["o_rate"], played["proj_pa"], played["total"])
    played["baserunning"] = played["pa"] * played["bsr_rate"].fillna(0.0)
    played["batting"] = offense - played["baserunning"]
    played["defense"] = [r.pa * getattr(r, f"def_{r.position}") / 700.0 for r in played.itertuples()]
    out = played.groupby("team_id")[["batting", "baserunning", "defense"]].sum()
    out.index = out.index.map(abbr)
    return out


def leaders(alloc: pd.DataFrame, batters: pd.DataFrame, pitchers: pd.DataFrame,
            team_id: int, n: int = LEADERS) -> tuple[list[dict], list[dict]]:
    """The team's most valuable batters (optimized lineup) and pitchers (as projected)."""
    mine = alloc[(alloc["team_id"] == team_id) & (alloc["mlbam_id"] >= 0)]
    main = mine.sort_values("pa", ascending=False).drop_duplicates("mlbam_id") \
        .set_index("mlbam_id")["position"]
    agg = mine.groupby("mlbam_id").agg(name=("player_name", "first"), pa=("pa", "sum"),
                                       war=("war", "sum"))
    wrc = batters[batters["team_id"] == team_id].set_index("mlbam_id")["wrc_plus"]
    agg["position"], agg["wrc_plus"] = main, wrc.reindex(agg.index)
    bats = [{"name": r.name, "position": r.position, "pa": float(r.pa),
             "wrc_plus": None if pd.isna(r.wrc_plus) else float(r.wrc_plus), "war": float(r.war)}
            for r in agg.sort_values("war", ascending=False).head(n).itertuples()]
    p = pitchers[pitchers["team_id"] == team_id].assign(role=pitcher_roles(pitchers))
    arms = [{"name": r.player_name, "role": r.role, "ip": float(r.innings_pitched),
             "fip": None if pd.isna(r.fip) else float(r.fip), "war": float(r.war)}
            for r in p.sort_values("war", ascending=False).head(n).itertuples()]
    return bats, arms


# ---- free agents -------------------------------------------------------------------------
def unsigned_players(source: str, season: int, kind: str,
                     directory: Path = INPUT_DIR) -> pd.DataFrame:
    """Players in the projection file with no team (unsigned), in the mart's column names."""
    path = Path(directory) / f"{source}_{kind}_individual_{season}.csv"
    if not path.exists():
        return pd.DataFrame()
    raw = pd.read_csv(path, encoding="utf-8-sig")
    raw = raw[raw["Team"].isna() & raw["MLBAMID"].notna()]
    common = {"Name": "player_name", "MLBAMID": "mlbam_id", "WAR": "war", "G": "games"}
    extra = ({"PA": "plate_appearances", "Off": "off_runs", "Def": "def_runs", "Fld": "fld_runs",
              "BsR": "bsr_runs", "wRC+": "wrc_plus"} if kind == "batters"
             else {"IP": "innings_pitched", "GS": "games_started", "FIP": "fip"})
    cols = {k: v for k, v in {**common, **extra}.items() if k in raw}
    out = raw[list(cols)].rename(columns=cols)
    out["mlbam_id"] = out["mlbam_id"].astype("int64")
    for c in out.columns.drop(["player_name", "mlbam_id"]):
        out[c] = pd.to_numeric(out[c], errors="coerce")
    if "fld_runs" not in out and kind == "batters":
        out["fld_runs"] = np.nan
    return out.reset_index(drop=True)


def last_team(mlbam_ids, season: int, abbr: pd.Series, path=DUCKDB_PATH) -> dict:
    """Each player's team last season (most innings in the field), where known."""
    rows = _query("select mlbam_id, team_id, sum(innings) as inn from staging.stg_mlb__fielding "
                  "where season = ? group by 1, 2", [season - 1], path)
    rows = rows[rows["mlbam_id"].isin(list(mlbam_ids))]
    top = rows.sort_values("inn", ascending=False).drop_duplicates("mlbam_id")
    return dict(zip(top["mlbam_id"], top["team_id"].map(abbr), strict=True))


def free_agent_batters(team_inputs: pd.DataFrame, unsigned: pd.DataFrame,
                       positions: pd.DataFrame, rep_runs: float, runs_per_win: float,
                       team_id: int, n_candidates: int = FA_CANDIDATES) -> pd.DataFrame:
    """Gain in team batting WAR from signing each unsigned batter, by re-optimizing the lineup.

    Candidates: unsigned batters with at least FA_MIN_PA projected PA, the best n_candidates by
    WAR per 600 PA. proj_war and proj_pa are the projection's own. `off_position` flags a player the optimizer puts mostly at a position he did
    not play last season (worth a second look).
    """
    cols = ["name", "mlbam_id", "gain", "pa", "where", "natives", "off_position", "wrc_plus",
            "war600", "proj_war", "proj_pa"]
    if unsigned.empty:
        return pd.DataFrame(columns=cols)
    pool = unsigned[unsigned["plate_appearances"] >= FA_MIN_PA].copy()
    pool["war600"] = pool["war"] / pool["plate_appearances"] * 600
    pool = pool.sort_values("war600", ascending=False).head(n_candidates).assign(team_id=team_id)
    base = lo.optimize_team(team_inputs, rep_runs, runs_per_win)["war"].sum()
    rows = []
    for r in pool.itertuples(index=False):
        one = lo.player_inputs(pd.DataFrame([r._asdict()]), positions)
        if one.empty:
            continue
        alloc = lo.optimize_team(pd.concat([team_inputs, one], ignore_index=True),
                                 rep_runs, runs_per_win)
        me = alloc[alloc["mlbam_id"] == r.mlbam_id].groupby("position")["pa"].sum() \
            .sort_values(ascending=False)
        natives = one["natives"].iloc[0]
        main = me.index[0] if len(me) else None
        rows.append({"name": r.player_name, "mlbam_id": r.mlbam_id,
                     "gain": float(alloc["war"].sum() - base), "pa": float(me.sum()),
                     "where": [(q, float(p)) for q, p in me.head(2).items()],
                     "natives": list(natives),
                     "off_position": bool(main and main != "DH" and main not in natives),
                     "wrc_plus": r.wrc_plus, "war600": r.war600,
                     "proj_war": float(r.war), "proj_pa": float(r.plate_appearances)})
    return pd.DataFrame(rows, columns=cols).sort_values("gain", ascending=False)


def best_pair(fa: pd.DataFrame, unsigned: pd.DataFrame, team_inputs: pd.DataFrame,
              positions: pd.DataFrame, rep_runs: float, runs_per_win: float,
              team_id: int) -> dict | None:
    """The two best free agents who would play different positions, signed together."""
    if len(fa) < 2:
        return None
    first = fa.iloc[0]
    second = next((r for _, r in fa.iloc[1:].iterrows()
                   if r["where"] and first["where"] and r["where"][0][0] != first["where"][0][0]),
                  None)
    if second is None:
        return None
    picks = unsigned[unsigned["mlbam_id"].isin([first["mlbam_id"], second["mlbam_id"]])] \
        .assign(team_id=team_id)
    both = lo.player_inputs(picks, positions)
    base = lo.optimize_team(team_inputs, rep_runs, runs_per_win)["war"].sum()
    alloc = lo.optimize_team(pd.concat([team_inputs, both], ignore_index=True),
                             rep_runs, runs_per_win)
    return {"names": [first["name"], second["name"]], "gain": float(alloc["war"].sum() - base),
            "separate": float(first["gain"] + second["gain"])}


def free_agent_pitchers(unsigned: pd.DataFrame, pitchers: pd.DataFrame, team_id: int,
                        n: int = 5) -> tuple[pd.DataFrame, dict]:
    """Starters: gain over the team's weakest starter, per SP_IP innings. Relievers: gain over
    its weakest busy reliever, at the free agent's own innings."""
    mine = pitchers[pitchers["team_id"] == team_id].assign(role=pitcher_roles(pitchers))
    mine = mine[mine["innings_pitched"] > 0].assign(rate=lambda d: d["war"] / d["innings_pitched"])
    sp = mine[mine["role"] == "SP"].sort_values("war", ascending=False).head(5)
    rp = mine[(mine["role"] == "RP") & (mine["innings_pitched"] >= RP_MIN_IP)]
    weakest_sp = sp.sort_values("rate").iloc[0] if len(sp) else None
    weakest_rp = rp.sort_values("rate").iloc[0] if len(rp) else None
    cols = ["name", "role", "ip", "fip", "war", "gain"]
    if unsigned.empty or weakest_sp is None:
        return pd.DataFrame(columns=cols), {}
    fa = unsigned[unsigned["innings_pitched"] > 0].assign(role=pitcher_roles(unsigned))
    fa["rate"] = fa["war"] / fa["innings_pitched"]
    fa["gain"] = np.where(
        fa["role"] == "SP", (fa["rate"] - weakest_sp["rate"]) * SP_IP,
        (fa["rate"] - (weakest_rp["rate"] if weakest_rp is not None else 0.0))
        * fa["innings_pitched"])
    fa = fa[(fa["role"] == "SP") | (fa["innings_pitched"] >= RP_MIN_IP)]
    top = pd.concat([fa[fa["role"] == "SP"].nlargest(n - 1, "gain"),
                     fa[fa["role"] == "RP"].nlargest(1, "gain")])
    top = top.rename(columns={"player_name": "name", "innings_pitched": "ip"})[cols] \
        .sort_values("gain", ascending=False)
    base = {"weakest_sp": weakest_sp["player_name"], "weakest_sp_war": float(weakest_sp["war"]),
            "weakest_sp_ip": float(weakest_sp["innings_pitched"]),
            "weakest_rp": None if weakest_rp is None else weakest_rp["player_name"]}
    return top, base


# ---- the whole outlook -------------------------------------------------------------------
def build_outlook_data(team: str = "PIT", season: int | None = None,
                       model: str = "steamer_optimized", as_of: str | None = None,
                       path=DUCKDB_PATH, projections_dir: Path = INPUT_DIR) -> dict:
    source = MODEL_SOURCE.get(model)
    if source is None:
        raise ValueError(f"outlook needs a player-projection model: {sorted(MODEL_SOURCE)}")
    teams = _query("select team_id, team_name, team_abbr from seeds.teams", path=path)
    abbr = teams.set_index("team_id")["team_abbr"]
    if team not in set(abbr):
        raise ValueError(f"unknown team {team!r}")
    team_id = int(teams.loc[teams["team_abbr"] == team, "team_id"].iloc[0])
    if season is None:
        seasons = _query("select max(season) as s from forecasts.season_forecasts where model = ?",
                         [model], path)
        season = int(seasons["s"].iloc[0])
    forecast, as_of = forecast_table(model, season, as_of, abbr, path)

    proj = _query("select * from marts.player_projections where source = ? and season = ? "
                  "and team_id is not null and mlbam_id is not null", [source, season], path)
    positions = _query("select mlbam_id, position, games from marts.player_position_games "
                       "where season = ?", [season], path)
    batters = proj[proj["player_type"] == "batter"]
    pitchers = proj[proj["player_type"] == "pitcher"]
    alloc, inputs = lo.optimize_league(batters, positions)
    rpw, rep = alloc.attrs["runs_per_win"], alloc.attrs["rep_runs"]

    table = spot_war(alloc, pitchers, abbr)
    bat = table[list(lo.POSITIONS)].sum(axis=1)
    pit = table[["SP", "RP"]].sum(axis=1)
    total = bat + pit
    spots = spot_rows(table, team, alloc, team_id, pitchers)
    runs = run_components(alloc, inputs, batters, abbr)
    bats, arms = leaders(alloc, batters, pitchers, team_id)

    division = next(d for d, members in DIVISIONS.items() if team in members)
    div_rows = sorted(({"team": t, "name": teams.set_index("team_abbr").loc[t, "team_name"],
                        "wins": float(forecast.loc[t, "wins"]), "batting": float(bat[t]),
                        "pitching": float(pit[t])} for t in DIVISIONS[division]),
                      key=lambda r: -r["wins"])

    fa_bat_pool = unsigned_players(source, season, "batters", projections_dir)
    team_inputs = inputs[inputs["team_id"] == team_id]
    fa_bat = free_agent_batters(team_inputs, fa_bat_pool, positions, rep, rpw, team_id)
    if len(fa_bat):
        teams_before = last_team(fa_bat["mlbam_id"], season, abbr, path)
        fa_bat["last_team"] = fa_bat["mlbam_id"].map(teams_before)
    pair = best_pair(fa_bat, fa_bat_pool, team_inputs, positions, rep, rpw, team_id)
    fa_pit, pit_base = free_agent_pitchers(
        unsigned_players(source, season, "pitchers", projections_dir), pitchers, team_id)

    def summary(values: pd.Series) -> dict:
        return {"value": float(values[team]), "avg": float(values.mean()),
                "rank": rank_of(values, team)}

    return {
        "team": team, "team_id": team_id,
        "team_name": teams.set_index("team_abbr").loc[team, "team_name"],
        "season": season, "model": model, "source": source, "as_of": as_of,
        "today": date.today().isoformat(),
        "forecast": {"wins": float(forecast.loc[team, "wins"]),
                     "low": float(forecast.loc[team, "low"]),
                     "high": float(forecast.loc[team, "high"]),
                     "rank": int(forecast.loc[team, "rank"])},
        "total": summary(total), "batting": summary(bat), "pitching": summary(pit),
        "spots": spots,
        "scatter": [{"team": t, "batting": float(bat[t]), "pitching": float(pit[t])}
                    for t in table.index],
        "runs": {c: summary(runs[c]) for c in runs.columns},
        "leaders": {"batters": bats, "pitchers": arms},
        "division": {"name": division, "rows": div_rows},
        "free_agents": {"batters": fa_bat.head(FA_SHOWN).to_dict("records"), "pair": pair,
                        "pitchers": fa_pit.to_dict("records"), "pitching_base": pit_base},
        "scores": backtest_scores(model, path),
        "runs_per_win": float(rpw),
    }
