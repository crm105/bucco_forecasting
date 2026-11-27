"""How good a player-projection model is, in three layers (`bucco evaluate`).

1. Player projections: for hitters and pitchers, the error of the projected **rate** (WAR per 600
   PA or per 180 innings, and offense runs per 600 PA or FIP-based runs per 9 where the source has
   them), of the **playing time** the model gave each player (PA or innings, after the lineup and
   staff optimizers) and of their product, **production** (WAR).
2. Forecast: team WAR (batting, pitching, total) against what each team produced, and team record
   (the wins backtest), on the same seasons.
3. Rate against playing time: team WAR recomputed with **perfect playing time** (projected rates
   times what each player actually got, for the team he got it with) and with **perfect rates**
   (actual rates times projected playing time). Their errors split the team-WAR error between the
   two; "perfect both" is what is left: players the model never projected.

Actual values are our own park-neutral approximations (marts.player_team_seasons): FIP-based
pitching, offense plus positional adjustment for hitters, no measured fielding. A model projecting
the same quantity (ours) has a home-field edge over Steamer or ZiPS, which project FanGraphs WAR;
comparisons between versions of one model are fair. Rates are compared after removing each
season's league mean (weighted by actual playing time), as are team totals; 2020 is left out.
"""

from __future__ import annotations

import duckdb
import numpy as np
import pandas as pd

from bucco.config import DUCKDB_PATH
from bucco.evaluate import metrics
from bucco.evaluate.backtest import _as_of
from bucco.models.depth_chart_model import pitcher_rate

PARTS = {"batting": ("pa", 600.0, 100.0), "pitching": ("ip", 180.0, 30.0)}
LABEL = {"batting": "Hitters", "pitching": "Pitchers"}
MIN_RATE_PT = {"batting": 50.0, "pitching": 15.0}   # actual time needed to trust an actual rate


def load_actual(path=DUCKDB_PATH) -> pd.DataFrame:
    """season, mlbam_id, team_id, part, playing_time, war, runs (marts.player_team_seasons)."""
    with duckdb.connect(str(path), read_only=True) as con:
        return con.sql("select season, mlbam_id, team_id, part, playing_time, war, runs "
                       "from marts.player_team_seasons").df()


def collect(model, features: pd.DataFrame, seasons) -> dict[str, pd.DataFrame]:
    """Per part, every projected player-season: team_id, mlbam_id, pt (allocated), war
    (allocated), rate (projected WAR per unit of playing time), runs_rate (offense runs per PA
    or runs per inning, where the source has them)."""
    out = {"batting": [], "pitching": []}
    data = model.data
    for season in seasons:
        as_of = _as_of(features[features["season"] == season])
        alloc = data.player_allocations(int(season), as_of)
        if alloc is None:
            raise ValueError(f"{model.name}: no per-player playing time (injury draws)")
        for part, frame in (("batting", data.batters), ("pitching", data.pitchers)):
            vol = PARTS[part][0]
            proj = data._visible(frame, int(season), as_of).dropna(subset=["team_id"])
            proj = proj.groupby("mlbam_id", as_index=False).first()
            own = proj[vol].astype(float)
            rate = (proj["war"] / own.where(own > 0)).rename("own_rate")
            if part == "batting":
                runs = proj["off_runs"] / own.where(own > 0) if "off_runs" in proj else np.nan
            else:
                has = "runs" in proj or "runs_per_ip" in proj
                runs = pitcher_rate(proj) if has else np.nan
            p = proj[["mlbam_id"]].assign(own_rate=rate.to_numpy(), runs_rate=runs)
            a = alloc[part].rename(columns={vol: "pt"})
            per = a.groupby("mlbam_id", as_index=False)[["pt", "war"]].sum()
            p = p.merge(per, on="mlbam_id", how="left").fillna({"pt": 0.0, "war": 0.0})
            p["rate"] = (p["war"] / p["pt"].where(p["pt"] > 0)).fillna(p["own_rate"]).fillna(0.0)
            out[part].append(p.assign(season=int(season)))
            out[f"{part}_team"] = out.get(f"{part}_team", []) + [a.assign(season=int(season))]
    return {k: pd.concat(v, ignore_index=True) for k, v in out.items()}


def _centered(x: pd.Series, season: pd.Series, w: pd.Series) -> pd.Series:
    mean = (x * w).groupby(season).transform("sum") / w.groupby(season).transform("sum")
    return x - mean


def _wrmse(e: pd.Series, w: pd.Series) -> float:
    return float(np.sqrt(np.average(e ** 2, weights=w))) if len(e) else np.nan


def population(actual: pd.DataFrame, rosters: pd.DataFrame | None) -> dict[str, pd.DataFrame]:
    """The players every model is scored on for playing time and production, per part: everyone
    on an Opening Day 40-man roster (rosters: season, player_type, mlbam_id) plus everyone who
    played (`bucco evaluate` passes marcel_rosters "mlb_org", so organizations' minor leaguers
    count too: a model that gives them innings they never throw pays for it). The same for every
    model, whatever its source lists."""
    out = {}
    for part in PARTS:
        played = actual.loc[(actual["part"] == part) & (actual["playing_time"] > 0),
                            ["season", "mlbam_id"]]
        keys = [played]
        if rosters is not None:
            kind = "batter" if part == "batting" else "pitcher"
            keys.append(rosters.loc[rosters["player_type"] == kind, ["season", "mlbam_id"]])
        out[part] = pd.concat(keys).drop_duplicates()
    return out


def player_table(proj: dict, actual: pd.DataFrame,
                 pop: dict[str, pd.DataFrame] | None = None) -> pd.DataFrame:
    """Layer 1: one row per part (hitters, pitchers). Playing time and production are scored on
    `pop` (see `population`; 0 for a player the model did not project) in the model's seasons;
    without it, on the players the model projected. Rates are scored on players the model
    projected who played enough to have one."""
    rows = {}
    for part, (vol, per, min_pt) in PARTS.items():
        act = (actual[actual["part"] == part].groupby(["season", "mlbam_id"], as_index=False)
               [["playing_time", "war", "runs"]].sum()
               .rename(columns={"war": "war_a", "runs": "runs_a"}))
        mine = proj[part]
        if pop is not None:
            keys = pop[part][pop[part]["season"].isin(set(mine["season"]))]
            x = keys.merge(mine, on=["season", "mlbam_id"], how="left") \
                .fillna({"pt": 0.0, "war": 0.0})
        else:
            x = mine.copy()
        x = x.merge(act, on=["season", "mlbam_id"], how="left")
        x = x[~x["season"].isin(metrics.SHORTENED_SEASONS)]
        x[["playing_time", "war_a", "runs_a"]] = x[["playing_time", "war_a", "runs_a"]].fillna(0.0)
        r = x[(x["playing_time"] >= min_pt) & x["rate"].notna()]
        w = r["playing_time"]
        e_rate = _centered(r["rate"] * per, r["season"], w) - _centered(
            r["war_a"] / w * per, r["season"], w)
        row = {"players": len(x), f"rate (WAR per {per:.0f})": _wrmse(e_rate, w)}
        if r["runs_rate"].notna().any():
            rr = r[r["runs_rate"].notna()]
            ww = rr["playing_time"]
            scale = 600.0 if part == "batting" else 9.0
            e_runs = _centered(rr["runs_rate"] * scale, rr["season"], ww) - _centered(
                rr["runs_a"] / ww * scale, rr["season"], ww)
            label = "off runs per 600" if part == "batting" else "runs per 9"
            row[f"rate ({label})"] = _wrmse(e_runs, ww)
        e_pt = x["pt"] - x["playing_time"]
        row[f"playing time ({vol.upper()})"] = float(np.sqrt((e_pt ** 2).mean()))
        row[f"playing time bias ({vol.upper()})"] = float(e_pt.mean())
        e_war = x["war"] - x["war_a"]
        e_war = e_war - e_war.groupby(x["season"]).transform("mean")
        row["production (WAR)"] = float(np.sqrt((e_war ** 2).mean()))
        rows[LABEL[part]] = row
    return pd.DataFrame(rows).T


def decomposition(proj: dict, actual: pd.DataFrame, seasons) -> pd.DataFrame:
    """Layer 3: team WAR RMSE (batting, pitching, total) under each counterfactual."""
    keep = [s for s in seasons if s not in metrics.SHORTENED_SEASONS]
    teams = {}
    for part in PARTS:
        act = actual[(actual["part"] == part) & actual["season"].isin(keep)]
        p = proj[part][proj[part]["season"].isin(keep)]
        alloc = proj[f"{part}_team"]
        alloc = alloc[alloc["season"].isin(keep)]
        rates = p.set_index(["season", "mlbam_id"])["rate"]
        tot = act.groupby(["season", "mlbam_id"])[["playing_time", "war"]].sum()
        a_rate = (tot["war"] / tot["playing_time"]).where(tot["playing_time"] >= MIN_RATE_PT[part])
        key_a = pd.MultiIndex.from_frame(act[["season", "mlbam_id"]])
        key_p = pd.MultiIndex.from_frame(alloc[["season", "mlbam_id"]])
        proj_rate_a = rates.reindex(key_a).to_numpy()
        actual_rate_p = a_rate.reindex(key_p).to_numpy()
        own_rate_p = rates.reindex(key_p).to_numpy()
        projected_anywhere = ~np.isnan(proj_rate_a)
        frames = {
            "projection": alloc.assign(v=alloc["war"]),
            "perfect playing time": act.assign(v=act["playing_time"] * np.nan_to_num(proj_rate_a)),
            "perfect rates": alloc.assign(v=alloc["pt"] * np.where(
                np.isnan(actual_rate_p), own_rate_p, actual_rate_p)),
            "perfect both": act.assign(v=np.where(projected_anywhere, act["war"], 0.0)),
            "actual": act.assign(v=act["war"]),
        }
        teams[part] = {k: f.groupby(["season", "team_id"])["v"].sum() for k, f in frames.items()}
    rows = {}
    for scen in ("projection", "perfect playing time", "perfect rates", "perfect both"):
        row = {}
        tot_p = tot_a = 0
        for part in PARTS:
            pr, ac = teams[part][scen], teams[part]["actual"]
            idx = pr.index.union(ac.index)
            pr, ac = pr.reindex(idx, fill_value=0.0), ac.reindex(idx, fill_value=0.0)
            tot_p, tot_a = tot_p + pr, tot_a + ac
            row[part] = _team_rmse(pr, ac)
        row["total"] = _team_rmse(tot_p, tot_a)
        rows[scen] = row
    out = pd.DataFrame(rows).T
    out.index = ["Full projection", "Perfect playing time (rate error left)",
                 "Perfect rates (playing-time error left)", "Perfect both (unprojected players)"]
    return out


def _team_rmse(pred: pd.Series, act: pd.Series) -> float:
    season = pred.index.get_level_values("season")
    e = (pred - pred.groupby(season).transform("mean")) - (act - act.groupby(season).transform("mean"))
    return float(np.sqrt((e ** 2).mean()))


def forecast_table(proj: dict, actual: pd.DataFrame, results: pd.DataFrame, model: str,
                   seasons) -> pd.Series:
    """Layer 2: team WAR RMSE (batting, pitching, total) and the wins backtest, same seasons."""
    dec = decomposition(proj, actual, seasons).iloc[0]
    out = {"team WAR: batting": dec["batting"], "team WAR: pitching": dec["pitching"],
           "team WAR: total": dec["total"]}
    r = results[(results["model"] == model) & results["season"].isin(seasons)]
    if len(r):
        s = metrics.by_model(r).iloc[0]
        out |= {"record: RMSE (wins)": s["rmse"], "record: typical miss (wins)": s["mae"],
                "record: inside 80% range": s["cover_80"]}
    return pd.Series(out)
