"""Injury simulation: team WAR averaged over seasons in which players miss time and teams
reallocate around them.

Our projections already carry the average time a player loses. What they miss is the shape: a
team whose starter misses half the season plays its backup, so depth is worth more than an
average season shows, and a top-heavy team loses more. Here, for each simulated season, every
player's availability A (share of a healthy workload he can give) is drawn, his playing-time
anchor becomes healthy capacity x A, and the lineup and staff optimizers share the team's PA and
innings out again. A team's WAR is the mean over draws.

Availability is fitted from established players, whose playing time mostly reflects health:
hitters projected for 450+ PA, starters for 120+ innings, relievers for 40+. For each one,
A = min(1, delivered / projected over the group's median of that ratio): at or above the
typical delivery counts as fully available. Draws come from the empirical A of earlier target
seasons (2020 left out), by group: hitters 32 and under, hitters 33 and over, starters,
relievers. Healthy capacity = projection / the group's mean A, so expected capacity is the
projection. Players with small projections get the same draws (their own ratios reflect role
decisions, not health). On 2012-2026: about 5% of regular hitters (10% at 33+) and 15-19% of
pitchers delivered under half their projection. See docs/R&D/injury_sim.md.
"""

from __future__ import annotations

import os
from concurrent.futures import ProcessPoolExecutor

import numpy as np
import pandas as pd

from bucco.models import lineup_optimizer as lo
from bucco.models import staff_optimizer as so

GROUPS = ("bat_young", "bat_old", "sp", "rp")
OLD_AGE = 33
ESTABLISHED = {"bat": 450.0, "sp": 120.0, "rp": 40.0}   # projected PA or innings
MIN_SAMPLES = 100           # earlier established player-seasons a group needs
N_SIMS = 100                # simulated seasons per team
MAX_PA = lo.MAX_PA


def batter_group(age) -> np.ndarray:
    return np.where(pd.Series(age).fillna(0).to_numpy() >= OLD_AGE, "bat_old", "bat_young")


def pitcher_group(starter) -> np.ndarray:
    return np.where(np.asarray(starter, dtype=bool), "sp", "rp")


def fit_availability(rows: pd.DataFrame, before: int,
                     shortened: frozenset[int] = frozenset({2020})) -> dict[str, np.ndarray]:
    """Empirical availability draws by group, from target seasons before `before`.

    rows: season, group, projected, actual (established players only)."""
    use = rows[(rows["season"] < before) & ~rows["season"].isin(shortened)
               & (rows["projected"] > 0) & rows["actual"].notna()]
    out = {}
    for g in GROUPS:
        x = use[use["group"] == g]
        if len(x) < MIN_SAMPLES:
            continue
        ratio = (x["actual"] / x["projected"]).to_numpy()
        out[g] = np.minimum(1.0, ratio / np.median(ratio))
    return out


def established_rows(batters: pd.DataFrame, pitchers: pd.DataFrame,
                     actual_b: pd.DataFrame, actual_p: pd.DataFrame) -> pd.DataFrame:
    """season, group, projected, actual for established players (see the module notes).
    batters: season, mlbam_id, age, pa; pitchers: season, mlbam_id, ip, start_share.
    actual_b / actual_p: season, mlbam_id, actual (PA / innings; 0 if he did not play)."""
    b = batters[batters["pa"] >= ESTABLISHED["bat"]].merge(actual_b, on=["season", "mlbam_id"],
                                                          how="left")
    b = pd.DataFrame({"season": b["season"], "group": batter_group(b["age"]),
                      "projected": b["pa"], "actual": b["actual"].fillna(0.0)})
    sp = pitchers["start_share"] >= so.ROTATION_MIN_SHARE
    p = pitchers[(sp & (pitchers["ip"] >= ESTABLISHED["sp"]))
                 | (~sp & (pitchers["ip"] >= ESTABLISHED["rp"]))].copy()
    p = p.merge(actual_p, on=["season", "mlbam_id"], how="left")
    p = pd.DataFrame({"season": p["season"],
                      "group": pitcher_group(p["start_share"] >= so.ROTATION_MIN_SHARE),
                      "projected": p["ip"], "actual": p["actual"].fillna(0.0)})
    return pd.concat([b, p], ignore_index=True)


def _team(args) -> dict:
    """Mean and sd of one team's batting and pitching WAR over the draws."""
    team_id, bat, pit, samples, rep, rpw, options, n_sims, seed = args
    rng = np.random.default_rng(seed)
    first = pit.iloc[0]
    rep_sp, rep_rp, prpw = (float(first[c]) for c in ("sp_rep_per_ip", "rp_rep_per_ip",
                                                      "runs_per_win"))
    pen = float(first["start_penalty"]) if "start_penalty" in pit else 0.0
    bgroup, pgroup = batter_group(bat["age"]), pitcher_group(pit["starter"])

    def draw(groups):
        a, mean = np.ones(len(groups)), np.ones(len(groups))
        for g in set(groups):
            if g in samples:
                m = groups == g
                a[m] = rng.choice(samples[g], size=int(m.sum()))
                mean[m] = samples[g].mean()
        return a, mean

    caps = np.where(pit["starter"].to_numpy(), so.MAX_SP_IP, so.MAX_RP_IP)
    out = []
    for _ in range(n_sims):
        ab, mb = draw(bgroup)
        ap, mp = draw(pgroup)
        b = bat.assign(proj_pa=np.minimum(bat["proj_pa"] / mb, MAX_PA) * ab)
        p = pit.assign(base_ip=np.minimum(pit["base_ip"] / mp, caps) * ap)
        bw = lo.optimize_team(b, rep, rpw, **options)["war"].sum()
        pw = so.optimize_staff(p, rep_sp, rep_rp, prpw, start_penalty=pen)["war"].sum()
        out.append((bw, pw))
    a = np.array(out)
    return {"team_id": team_id, "bat": a[:, 0].mean(), "pit": a[:, 1].mean(),
            "sd": a.sum(axis=1).std()}


def simulate_season(bat_inputs: pd.DataFrame, pitchers: pd.DataFrame,
                    samples: dict[str, np.ndarray], rep: float, rpw: float,
                    options: dict | None = None, n_sims: int = N_SIMS, seed: int = 0,
                    workers: int | None = None) -> pd.DataFrame:
    """team_id, bat, pit, sd: mean team WAR over `n_sims` injury draws, teams re-optimized.

    bat_inputs: lineup_optimizer.player_inputs rows with team_id and age. pitchers: staff
    optimizer rows (rate, base_ip, age, starter, start_share, league constants, team_id)."""
    jobs = [(int(t), bat_inputs[bat_inputs["team_id"] == t].reset_index(drop=True),
             pitchers[pitchers["team_id"] == t].reset_index(drop=True), samples, rep, rpw,
             options or {}, n_sims, seed * 1000 + int(t))
            for t in sorted(set(bat_inputs["team_id"]) & set(pitchers["team_id"]))]
    workers = workers or min(8, os.cpu_count() or 1)
    if workers == 1:
        rows = [_team(j) for j in jobs]
    else:
        with ProcessPoolExecutor(workers) as pool:
            rows = list(pool.map(_team, jobs))
    return pd.DataFrame(rows)
