"""Optimal innings: each team's pitchers spread over the rotation and the bullpen to maximize WAR.

Every team fills the same innings: ROTATION_IP by starters and BULLPEN_IP in relief. A linear
program decides how many innings each pitcher throws in each, with a replacement-level pitcher
(0 WAR) always available to fill the rest. Pitchers who started at least ROTATION_MIN_SHARE of
their weighted games (starters, and swingmen such as bulk relievers and spot starters) can pitch
in either; the rest only in relief. With starters only (a cutoff of 0.5), thin rotations went to
replacement level while their swingmen sat in the bullpen; 0.1 scored 9.734 wins RMSE against
9.821 (see docs/R&D/pitcher_innings.md).

Value of pitcher i for x innings in total, x_SP of them in the rotation and x_RP in relief, in
runs:

* Pitching: x * rate_i(x). rate_i is his projected runs above average per inning at his
  baseline innings B_i (bucco.models.innings) and falls as his innings rise past it, faster
  and faster: rate_i(x) = r_i - c_i * ((x / B_i)^k - 1). Below the baseline it improves by
  `rest_bonus` times as much (shorter outings, rest). The baseline is the neutral point.
* Proportional: c_i is scaled by his value over starter replacement (relative to
  REFERENCE_VALUE), so each pitcher loses the same share of his edge per inning past his
  baseline. Without this, an ace's edge is so large that he is pushed to the innings cap.
* Age: c(age) = c0 * exp(g * (age - 27)). Older arms lose more for each inning past their
  baseline. g = 0.05 comes from how far pitchers beat their baseline innings at each age (the
  top tenth of starters 26 and under threw about 1.6 times their baseline, those 31 and over
  about 1.45 times). Innings and wins errors are flat in g (the baseline already has age in
  it), so it is kept for the shape it gives, not for accuracy. c0 = 0.05 is within 0.1 IP of
  the best innings error. See docs/R&D/pitcher_innings.md.
* Replacement-level credit per inning by pool: the starter's replacement level in the rotation,
  the reliever's in relief (lower).
* Role: the same pitcher does worse starting than relieving (fewer strikeouts, more home runs).
  His projected rate reflects his past mix of starts (start share s), so in the rotation he
  loses start_penalty x (1 - s) runs per inning and in relief he gains start_penalty x s. A
  pure reliever pays the whole penalty to start; a pure starter gains it in relief. The same
  penalty for everyone: one that grows with the pitcher's quality scored worse.
  start_penalty is fitted on earlier seasons (bucco.models.innings.fit_start_penalty).

WAR = runs / runs per win. The curve is cut into SEGMENT_IP steps, which makes the problem an
exact linear program (total runs are concave in x, so the steps fill in order).
"""

from __future__ import annotations

import numpy as np
import pandas as pd
from scipy.optimize import linprog

ROTATION_IP = 830.0         # innings a team's starters throw (about 57% of 1,450)
BULLPEN_IP = 620.0
FATIGUE_RUNS = 0.05         # c0 at age 27: runs per inning lost per unit of (x/B)^k - 1
AGE_SLOPE = 0.05            # g: c grows by about 5% per year of age
FATIGUE_POWER = 2.0         # k
REST_BONUS = 0.5            # share of the better rate kept below the baseline
REFERENCE_AGE = 27.0
SEGMENT_IP = 5.0
MAX_SP_IP = 220.0           # most innings for a pitcher who can start
MAX_RP_IP = 100.0           # most innings for one who cannot start
RELIEF_FLOOR_IP = 10.0      # relief innings even a pure starter can throw (long relief)
ROTATION_MIN_SHARE = 0.1    # weighted share of games started to be able to start (swingmen
                            # included; 0.5 left 52 rotation IP a team to replacement level)
MIN_BASE_IP = 5.0           # baselines are floored here, so the curve stays finite
PROPORTIONAL = True         # scale each pitcher's c by his value over replacement (see below)
REFERENCE_VALUE = 0.15      # runs per inning above starter replacement that c0 refers to
MIN_VALUE = 0.02            # floor on that value when scaling
# Leverage: a team's best reliever (closer) and the next SETUP_RELIEVERS (setup men), ranked by
# WAR per inning in relief among those with at least LEVERAGE_MIN_IP relief innings, pitch in
# closer games, so their relief WAR counts LEVERAGE times in team WAR. 2.0 / 1.5 splits the
# difference between the usual chained weights (1.4 / 1.2) and the best backtest
# (docs/R&D/leverage.md).
LEVERAGE = (2.0, 1.5)
SETUP_RELIEVERS = 3
LEVERAGE_MIN_IP = 20.0


def fatigue_c(age, fatigue: float = FATIGUE_RUNS, age_slope: float = AGE_SLOPE):
    """Fatigue coefficient by age (missing age: the reference age)."""
    a = np.nan_to_num(np.asarray(age, dtype=float) - REFERENCE_AGE)
    return fatigue * np.exp(age_slope * a)


def pitching_rate(rate: float, base_ip: float, x, c: float, power: float = FATIGUE_POWER,
                  rest_bonus: float = REST_BONUS):
    """Runs above average per inning at x innings in total."""
    change = (np.asarray(x, dtype=float) / max(base_ip, MIN_BASE_IP)) ** power - 1.0
    return rate - c * np.where(change > 0, change, rest_bonus * change)


def pitching_segments(rate: float, base_ip: float, c: float, max_ip: float,
                      step: float = SEGMENT_IP, power: float = FATIGUE_POWER,
                      rest_bonus: float = REST_BONUS) -> np.ndarray:
    """Average runs above average per inning within each `step` of innings (decreasing)."""
    edges = np.arange(0.0, max_ip + step / 2, step)
    total = edges * pitching_rate(rate, base_ip, edges, c, power, rest_bonus)
    return np.diff(total) / step


def optimize_staff(pitchers: pd.DataFrame, rep_sp: float, rep_rp: float, runs_per_win: float,
                   rotation_ip: float = ROTATION_IP, bullpen_ip: float = BULLPEN_IP,
                   fatigue: float = FATIGUE_RUNS, age_slope: float = AGE_SLOPE,
                   power: float = FATIGUE_POWER, rest_bonus: float = REST_BONUS,
                   step: float = SEGMENT_IP, proportional: bool = PROPORTIONAL,
                   start_penalty: float = 0.0) -> pd.DataFrame:
    """Best innings by pitcher and pool (SP, RP) for one team.

    pitchers: mlbam_id, player_name, rate (runs above average per inning), base_ip, age,
    starter (bool), optionally start_share (default: 1 for starters, 0 otherwise). rep_sp,
    rep_rp: replacement-level runs per inning credited in the rotation and in relief.
    start_penalty: runs per inning a pure reliever loses by starting (see the module notes). Returns one row per pitcher-pool with ip and war; replacement-level innings
    appear with mlbam_id -1 and 0 WAR.

    proportional: c is also scaled by the pitcher's value over starter replacement (rate +
    rep_sp, floored at MIN_VALUE) relative to REFERENCE_VALUE, so every pitcher loses the same
    share of his edge per inning past his baseline and an ace is pushed no further, in ratio to
    his baseline, than a back-end starter of his age."""
    p = pitchers.reset_index(drop=True)
    n = len(p)
    starter = p["starter"].astype(bool).to_numpy()
    share = (p["start_share"].astype(float).to_numpy() if "start_share" in p
             else starter.astype(float))
    role = {"SP": -start_penalty * (1.0 - share), "RP": start_penalty * share}
    cs = fatigue_c(p["age"], fatigue, age_slope)
    if proportional:
        value = np.maximum(p["rate"].astype(float).to_numpy() + rep_sp, MIN_VALUE)
        cs = cs * value / REFERENCE_VALUE
    caps = np.where(starter, MAX_SP_IP, MAX_RP_IP)
    k = round(MAX_SP_IP / step)
    segs = np.full((n, k), -1e3)           # steps past a pitcher's cap are never worth filling
    for i in range(n):
        m = round(float(caps[i]) / step)
        segs[i, :m] = pitching_segments(float(p.loc[i, "rate"]), float(p.loc[i, "base_ip"]),
                                        float(cs[i]), caps[i], step, power, rest_bonus)
    x_index = [(i, "SP") for i in range(n) if starter[i]] + [(i, "RP") for i in range(n)]
    nx, ns = len(x_index), n * k
    c = np.zeros(nx + ns + 2)               # minimize -runs
    for j, (i, pool) in enumerate(x_index):
        c[j] = -((rep_sp if pool == "SP" else rep_rp) + role[pool][i])
    c[nx:nx + ns] = -segs.ravel()
    a_eq, b_eq = [], []
    for s, (pool, total) in enumerate((("SP", rotation_ip), ("RP", bullpen_ip))):
        row = np.zeros(nx + ns + 2)
        row[[j for j, (_, q) in enumerate(x_index) if q == pool]] = 1.0
        row[nx + ns + s] = 1.0
        a_eq.append(row)
        b_eq.append(total)
    for i in range(n):                      # a pitcher's innings = his filled steps
        row = np.zeros(nx + ns + 2)
        row[[j for j, (ii, _) in enumerate(x_index) if ii == i]] = 1.0
        row[nx + i * k: nx + (i + 1) * k] = -1.0
        a_eq.append(row)
        b_eq.append(0.0)
    # Relief innings follow his role: at most MAX_RP_IP x (1 - start share) + RELIEF_FLOOR_IP.
    # Swapping two pitchers between the rotation and the bullpen barely changes team WAR (the
    # replacement levels and the starting penalty cancel), so without this the solver splits
    # pitchers between pools arbitrarily (Skenes 180 innings mostly in relief). What keeps
    # starters in rotations is stamina, which the rates do not see.
    relief_cap = MAX_RP_IP * (1.0 - share) + RELIEF_FLOOR_IP
    bounds = ([(0, relief_cap[i] if pool == "RP" else None) for i, pool in x_index]
              + [(0, step)] * ns + [(0, None)] * 2)
    res = linprog(c, A_eq=np.array(a_eq), b_eq=np.array(b_eq), bounds=bounds, method="highs")
    if not res.success:
        raise RuntimeError(f"staff optimization failed: {res.message}")
    x = res.x
    total = np.zeros(n)
    for j, (i, _) in enumerate(x_index):
        total[i] += x[j]
    rows = []
    for j, (i, pool) in enumerate(x_index):
        if x[j] > 1e-6:
            rate = float(pitching_rate(float(p.loc[i, "rate"]), float(p.loc[i, "base_ip"]),
                                       total[i], float(cs[i]), power, rest_bonus))
            rep = (rep_sp if pool == "SP" else rep_rp) + role[pool][i]
            rows.append({"mlbam_id": p.loc[i, "mlbam_id"], "player_name": p.loc[i, "player_name"],
                         "pool": pool, "ip": x[j], "war": x[j] * (rate + rep) / runs_per_win})
    for s, pool in enumerate(("SP", "RP")):
        if x[nx + ns + s] > 1e-6:
            rows.append({"mlbam_id": -1, "player_name": "replacement level", "pool": pool,
                         "ip": x[nx + ns + s], "war": 0.0})
    return pd.DataFrame(rows, columns=["mlbam_id", "player_name", "pool", "ip", "war"])


def optimize_staffs(pitchers: pd.DataFrame, min_start_share: float = ROTATION_MIN_SHARE,
                    **options) -> pd.DataFrame:
    """Optimize every team in one season. pitchers: as for `optimize_staff` plus team_id,
    sp_rep_per_ip, rp_rep_per_ip and runs_per_win (the season's league constants), and
    optionally start_penalty (the season's, used unless given in `options`). With a
    start_share column, `starter` (able to start) is start_share >= min_start_share."""
    if "start_share" in pitchers:
        pitchers = pitchers.assign(starter=pitchers["start_share"] >= min_start_share)
    out = []
    for team_id, group in pitchers.groupby("team_id"):
        first = group.iloc[0]
        opts = dict(options)
        if "start_penalty" in group and "start_penalty" not in opts:
            opts["start_penalty"] = float(first["start_penalty"])
        alloc = optimize_staff(group, float(first["sp_rep_per_ip"]), float(first["rp_rep_per_ip"]),
                               float(first["runs_per_win"]), **opts)
        alloc["team_id"] = team_id
        out.append(alloc)
    return pd.concat(out, ignore_index=True)



def leverage_tiers(alloc: pd.DataFrame, setup: int = SETUP_RELIEVERS,
                   min_ip: float = LEVERAGE_MIN_IP) -> pd.DataFrame:
    """Each team's closer and setup men (see LEVERAGE): team_id, mlbam_id, ip and war in relief,
    and tier ("closer" or "setup"). alloc: optimize_staffs output (team_id, mlbam_id, pool, ip,
    war). The closer is the reliever with the most relief WAR per inning among those with
    min_ip relief innings; the next `setup` are the setup men."""
    rp = alloc[(alloc["pool"] == "RP") & (alloc["mlbam_id"] >= 0)]
    rp = rp.groupby(["team_id", "mlbam_id"], as_index=False)[["ip", "war"]].sum()
    rp = rp[rp["ip"] >= min_ip].assign(rate=lambda d: d["war"] / d["ip"])
    rp = rp.sort_values(["team_id", "rate", "mlbam_id"], ascending=[True, False, True])
    rank = rp.groupby("team_id").cumcount()
    rp = rp[rank <= setup].assign(tier=np.where(rank[rank <= setup] == 0, "closer", "setup"))
    return rp.drop(columns="rate").reset_index(drop=True)


def leverage_war(alloc: pd.DataFrame, weights: tuple[float, float] = LEVERAGE,
                 setup: int = SETUP_RELIEVERS, min_ip: float = LEVERAGE_MIN_IP) -> pd.Series:
    """Extra team WAR from leverage, by team_id: (weight - 1) x relief WAR of each team's closer
    (weights[0]) and setup men (weights[1]) (`leverage_tiers`). Players' own WAR is left
    leverage-free, as actual WAR is."""
    t = leverage_tiers(alloc, setup, min_ip)
    extra = t["war"] * np.where(t["tier"] == "closer", weights[0] - 1.0, weights[1] - 1.0)
    return extra.groupby(t["team_id"]).sum().reindex(alloc["team_id"].unique(), fill_value=0.0)
