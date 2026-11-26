"""Rung 5b, first version: our own player projections, Marcel style.

Marcel (Tom Tango's "the monkey could do it" system) projects a player from his last three
seasons only:

* Rate: a weighted average of his last three seasons, weighted by playing time and by recency
  (5/4/3 for batters, 3/2/1 for pitchers), with `REG_PA` (or `REG_BF`) of league-average
  performance mixed in. Here the rate is runs above league average per PA (batters: batting and
  stolen-base runs, from player_batting_seasons) or per batter faced (pitchers: FIP-based runs,
  from player_pitching_seasons). League average is 0 by construction, so mixing it in shrinks
  the rate toward 0.
* Playing time: 0.5 x last season + 0.1 x the season before + a constant (200 PA; 60 IP for a
  starter, 25 for a reliever). The 60-game 2020 season is scaled up to 162 games first.
* Aging (optional, `age_curves`): each past season is aged forward to the target season before
  weighting. The curve is fitted with the delta method on pairs of consecutive seasons that
  both finished before the target season (`fit_age_curve`), so it never sees the target season.

Value is put on the same footing as the Steamer and ZiPS files (Off, Def, WAR), using the league
constants of the season before the target season, the last one known before Opening Day:

    batters:  WAR = (off_runs + def_runs + replacement runs per PA x PA) / runs per win
    pitchers: WAR = (pitching runs + replacement runs per IP x IP) / runs per win, with the
              replacement level for his mix of starts and relief (lower for starters)

def_runs is the positional adjustment only (the history has no fielding runs), weighted like the
rate but not regressed; `apply_external_def` can add fielding from outside projections. Players with no MLB history in the three prior seasons (rookies) get no
projection, which leaves their playing time to others or to replacement level.

Everything here is read from the projection frames, whose inputs come only from seasons before
the target season, so a projection never sees the season it forecasts.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

BATTER_WEIGHTS = (5.0, 4.0, 3.0)        # last season, two seasons ago, three seasons ago
PITCHER_WEIGHTS = (3.0, 2.0, 1.0)
REG_PA = 1200.0                         # weighted PA of league average mixed into a batter's rate
REG_BF = 1200.0                         # weighted batters faced, the same for pitchers
PA_BASE = 200.0                         # Marcel playing time: 0.5 y1 + 0.1 y2 + base
SP_IP_BASE = 60.0
RP_IP_BASE = 25.0
PT_WEIGHTS = (0.5, 0.1)
FULL_SEASON_GAMES = 162.0
PRIORS = ("league", "replacement", "fitted")
PRIOR_SCALE = {"batter": 500.0, "pitcher": 200.0}   # volume scale of the fitted prior's log term
MIN_PRIOR_ROWS = 1000                   # earlier player-seasons needed to fit the prior
AGE_RANGE = (20, 40)                  # ages the curve is fitted on; held flat outside
CURVE_AGES = range(15, 51)


def fit_age_curve(history: pd.DataFrame, rate: str, volume: str, before: int,
                  degree: int = 2, center: bool = False) -> pd.Series:
    """Cumulative aging curve by age (runs per unit of `volume`), from seasons before `before`.

    Delta method: for each player with seasons s - 1 and s (both < before), the change in
    `rate` per `volume` at his age in season s, weighted by the harmonic mean of the two
    volumes. A weighted polynomial in age smooths the changes; the curve is their running sum,
    so curve[a] - curve[b] is the expected change in rate from age b to age a. Survivors only:
    players who did not play the next season are not in the pairs, which pulls every change
    down. `center` removes the weighted mean change, keeping only the curve's shape."""
    h = history[history["season"] < before][["mlbam_id", "season", "age", rate, volume]]
    h = h[h[volume] > 0]
    pairs = h.merge(h.assign(season=h["season"] + 1), on=["mlbam_id", "season"],
                    suffixes=("", "_prev"))
    pairs = pairs[pairs["age"].between(*AGE_RANGE)]
    if len(pairs) < 100:
        return pd.Series(0.0, index=list(CURVE_AGES))
    delta = pairs[rate] / pairs[volume] - pairs[f"{rate}_prev"] / pairs[f"{volume}_prev"]
    weight = 2.0 / (1.0 / pairs[volume] + 1.0 / pairs[f"{volume}_prev"])
    if center:
        delta = delta - np.average(delta, weights=weight)
    coef = np.polyfit(pairs["age"].astype(float), delta, degree, w=np.sqrt(weight))
    ages = np.array(list(CURVE_AGES), dtype=float)
    step = np.polyval(coef, np.clip(ages, *AGE_RANGE))
    step = np.where((ages < AGE_RANGE[0]) | (ages > AGE_RANGE[1]), 0.0, step)
    return pd.Series(np.cumsum(step), index=list(CURVE_AGES))


def age_curves(history: pd.DataFrame, rate: str, volume: str, seasons,
               center: bool = False) -> dict[int, pd.Series]:
    """One curve per target season, each fitted only on seasons before it."""
    return {int(t): fit_age_curve(history, rate, volume, int(t), center=center)
            for t in sorted(set(seasons))}


def _aging(f: pd.DataFrame, curves: dict[int, pd.Series] | None, k: int) -> pd.Series:
    """Change in rate from the player's age in season y_k to his age in the target season."""
    if curves is None:
        return pd.Series(0.0, index=f.index)
    age = f["age"].astype(float)
    lo, hi = CURVE_AGES[0], CURVE_AGES[-1]
    out = []
    for season, a in zip(f["season"], age, strict=True):
        curve = curves.get(int(season))
        if curve is None or np.isnan(a):
            out.append(0.0)
            continue
        now, then = int(np.clip(a, lo, hi)), int(np.clip(a - k, lo, hi))
        out.append(float(curve[now] - curve[then]))
    return pd.Series(out, index=f.index)


def _full_season(frame: pd.DataFrame, k: int, column: str) -> pd.Series:
    """Season k's count scaled up to a 162-game season (only 2020 changes)."""
    games = frame[f"y{k}_team_games"].fillna(FULL_SEASON_GAMES).clip(lower=1.0)
    return frame[column] * (FULL_SEASON_GAMES / games)


def fitted_prior_means(f: pd.DataFrame, sums: pd.Series, volume: pd.Series, reg: float,
                       target_runs: str, target_volume: str, league: pd.DataFrame,
                       scale: float) -> np.ndarray:
    """The rate each row is shrunk toward, depending on how much history he has.

    Marcel's rate is (sums + reg x mu) / (volume + reg). Here mu = a + b log(1 + volume / scale),
    with a and b fitted, for each target season, on the player-seasons before it (full target
    seasons only) so that the projection matches what players with that much history went on to
    do, weighted by their playing time. Players with little history are thereby shrunk toward
    what such players actually did (well below average), regulars toward about average. Falls
    back to mu = 0 (league average) with fewer than MIN_PRIOR_ROWS earlier rows."""
    shortened = set(league.loc[league["is_shortened_season"], "season"])
    sums, volume = sums.astype(float), volume.astype(float)
    k = reg / (volume + reg)
    log_v = np.log1p(volume / scale)
    tv = f[target_volume].astype(float)
    y = f[target_runs].astype(float) / tv.where(tv > 0) - sums / (volume + reg)
    usable = (tv > 0) & y.notna() & ~f["season"].isin(shortened)
    mu = np.zeros(len(f))
    for season in sorted(f["season"].unique()):
        train = usable & (f["season"] < season)
        rows = (f["season"] == season).to_numpy()
        if train.sum() < MIN_PRIOR_ROWS:
            continue
        x = np.c_[k[train], k[train] * log_v[train]]
        w = np.sqrt(tv[train].to_numpy())
        (a, b), *_ = np.linalg.lstsq(x * w[:, None], y[train].to_numpy() * w, rcond=None)
        mu[rows] = a + b * log_v[rows].to_numpy()
    return mu


def _prior_league(frame: pd.DataFrame, league: pd.DataFrame) -> pd.DataFrame:
    """League constants of the season before each row's target season."""
    cols = ["season", "runs_per_win", "batting_replacement_runs_per_pa",
            "pitching_replacement_runs_per_ip", "sp_replacement_runs_per_ip",
            "rp_replacement_runs_per_ip", "runs_per_pa", "era"]
    prior = league[cols].assign(season=league["season"] + 1)
    return frame[["season"]].merge(prior, on="season", how="left")


def project_batters(frame: pd.DataFrame, league: pd.DataFrame, reg_pa: float = REG_PA,
                    weights: tuple[float, ...] = BATTER_WEIGHTS,
                    curves: dict[int, pd.Series] | None = None,
                    prior: str = "league", park: bool = False,
                    milb_weight: float = 0.0) -> pd.DataFrame:
    """Marcel batter projections from batter_projection_frame rows (pitchers' batting dropped).
    `milb_weight`: with y1-y3_milb_pa and y1-y3_milb_runs in the frame (major-league equivalents,
    bucco.models.milb), each minor-league season joins the weighted history like an MLB season,
    its PA counted at this weight (0: none).
    `park`: project from park-neutral Off (`off_runs_neutral`) instead of Off as played.
    `curves`: aging curves of off_runs per PA by target season (`age_curves`), or None.
    `prior`: what the rate is shrunk toward: "league" (average), "replacement" (Off + Def at
    replacement level) or "fitted" (`fitted_prior_means`, by how much history he has).

    Returns season, mlbam_id, player_name, age, last_team_id, pa, off_runs, def_runs, fld_runs,
    bsr, has_position (any MLB positional history), war and wrc_plus (approximate: 100 x (1 + batting runs per PA / league runs per PA), no
    park adjustment)."""
    f = frame[~frame["is_pitcher"].fillna(False).astype(bool)].reset_index(drop=True)
    w_pa = sum(w * f[f"y{k}_pa"] for k, w in enumerate(weights, start=1))
    off_col = "off_runs_neutral" if park else "off_runs"
    off = sum(w * (f[f"y{k}_{off_col}"].fillna(0.0) + f[f"y{k}_pa"] * _aging(f, curves, k))
              for k, w in enumerate(weights, start=1))
    if milb_weight and "y1_milb_pa" in f:
        for k, w in enumerate(weights, start=1):
            m_pa = f[f"y{k}_milb_pa"].fillna(0.0)
            w_pa = w_pa + w * milb_weight * m_pa
            off = off + w * milb_weight * (f[f"y{k}_milb_runs"].fillna(0.0)
                                           + m_pa * _aging(f, curves, k))
    bsr = sum(w * f[f"y{k}_baserunning_runs"].fillna(0.0) for k, w in enumerate(weights, 1))
    pos = sum(w * f[f"y{k}_positional_runs"].fillna(0.0) for k, w in enumerate(weights, 1))
    pos_pa = sum(w * f[f"y{k}_pa"].where(f[f"y{k}_positional_runs"].notna(), 0.0)
                 for k, w in enumerate(weights, start=1))
    bsr_rate = bsr / (w_pa + reg_pa)
    def_rate = (pos / pos_pa.where(pos_pa > 0)).fillna(0.0)
    pa = (PT_WEIGHTS[0] * _full_season(f, 1, "y1_pa") + PT_WEIGHTS[1] * _full_season(f, 2, "y2_pa")
          + PA_BASE)
    lg = _prior_league(f, league)
    rep = lg["batting_replacement_runs_per_pa"].to_numpy()
    if prior not in PRIORS:
        raise ValueError(f"prior must be one of {PRIORS}, not {prior!r}")
    if prior == "league":
        mu = 0.0
    elif prior == "replacement":
        mu = -rep - def_rate.to_numpy()
    else:
        mu = fitted_prior_means(f, off, w_pa, reg_pa, f"target_{off_col}", "target_pa", league,
                                PRIOR_SCALE["batter"])
    off_rate = (off + reg_pa * mu) / (w_pa + reg_pa)
    rpw = lg["runs_per_win"].to_numpy()
    out = pd.DataFrame({
        "season": f["season"], "mlbam_id": f["mlbam_id"], "player_name": f["player_name"],
        "age": f["age"], "last_team_id": f["last_team_id"], "pa": pa,
        "off_runs": off_rate * pa, "def_runs": def_rate * pa, "fld_runs": 0.0,
        "bsr": bsr_rate * pa, "has_position": (pos_pa > 0).to_numpy(),
    })
    out["war"] = (out["off_runs"] + out["def_runs"] + rep * pa) / rpw
    out["wrc_plus"] = 100.0 * (1.0 + (off_rate - bsr_rate) / lg["runs_per_pa"].to_numpy())
    return out


def project_pitchers(frame: pd.DataFrame, league: pd.DataFrame, reg_bf: float = REG_BF,
                     weights: tuple[float, ...] = PITCHER_WEIGHTS,
                     curves: dict[int, pd.Series] | None = None,
                     prior: str = "league", park: bool = False,
                     milb_weight: float = 0.0) -> pd.DataFrame:
    """Marcel pitcher projections from pitcher_projection_frame rows.
    `milb_weight`: with y1-y3_milb_bf, _runs, _outs, _gs and _games in the frame (major-league
    equivalents, bucco.models.milb), each minor-league season joins the weighted history like an
    MLB season (runs, batters faced, innings, starts and games), counted at this weight.
    `park`: project from park-neutral runs (`pitching_runs_neutral`) instead of runs as pitched.
    `curves`: aging curves of pitching_runs per BF by target season (`age_curves`), or None.
    `prior`: as for batters ("replacement" is replacement-level runs per batter faced).

    Returns season, mlbam_id, player_name, age, last_team_id, role (SP if he started at least
    half his weighted games), ip, gs, bf, runs (FIP-based runs above average), war, fip (on
    the ERA scale of the season before), runs_per_ip (the rate, which stays known when
    projected innings are 0), start_share and the season-before constants sp_rep_per_ip,
    rp_rep_per_ip and runs_per_win."""
    f = frame.reset_index(drop=True)
    w_bf = sum(w * f[f"y{k}_bf"] for k, w in enumerate(weights, start=1))
    runs_col = "pitching_runs_neutral" if park else "pitching_runs"
    runs = sum(w * (f[f"y{k}_{runs_col}"].fillna(0.0) + f[f"y{k}_bf"] * _aging(f, curves, k))
               for k, w in enumerate(weights, start=1))
    w_ip = sum(w * f[f"y{k}_outs"] / 3.0 for k, w in enumerate(weights, start=1))
    w_gs = sum(w * f[f"y{k}_gs"] for k, w in enumerate(weights, start=1))
    w_g = sum(w * f[f"y{k}_games"] for k, w in enumerate(weights, start=1))
    if milb_weight and "y1_milb_bf" in f:
        for k, w in enumerate(weights, start=1):
            m_bf = f[f"y{k}_milb_bf"].fillna(0.0)
            d = w * milb_weight
            w_bf = w_bf + d * m_bf
            runs = runs + d * (f[f"y{k}_milb_runs"].fillna(0.0) + m_bf * _aging(f, curves, k))
            w_ip = w_ip + d * f[f"y{k}_milb_outs"].fillna(0.0) / 3.0
            w_gs = w_gs + d * f[f"y{k}_milb_gs"].fillna(0.0)
            w_g = w_g + d * f[f"y{k}_milb_games"].fillna(0.0)
    bf_per_ip = (w_bf / w_ip.where(w_ip > 0)).fillna(4.3)
    lg = _prior_league(f, league)
    if prior not in PRIORS:
        raise ValueError(f"prior must be one of {PRIORS}, not {prior!r}")
    if prior == "league":
        mu = 0.0
    elif prior == "replacement":
        mu = -(lg["pitching_replacement_runs_per_ip"] / bf_per_ip).to_numpy()
    else:
        mu = fitted_prior_means(f, runs, w_bf, reg_bf, f"target_{runs_col}", "target_bf",
                                league, PRIOR_SCALE["pitcher"])
    runs_per_bf = (runs + reg_bf * mu) / (w_bf + reg_bf)
    starter = (w_gs >= 0.5 * w_g) & (w_gs > 0)
    ip = (PT_WEIGHTS[0] * _full_season(f, 1, "y1_outs") / 3.0
          + PT_WEIGHTS[1] * _full_season(f, 2, "y2_outs") / 3.0
          + np.where(starter, SP_IP_BASE, RP_IP_BASE))
    gs_per_ip = (w_gs / w_ip.where(w_ip > 0)).fillna(0.0)
    out = pd.DataFrame({
        "season": f["season"], "mlbam_id": f["mlbam_id"], "player_name": f["player_name"],
        "age": f["age"], "last_team_id": f["last_team_id"],
        "role": np.where(starter, "SP", "RP"), "ip": ip, "gs": gs_per_ip * ip,
        "bf": bf_per_ip * ip,
    })
    out["runs"] = runs_per_bf * out["bf"]
    out["runs_per_ip"] = runs_per_bf * bf_per_ip      # the rate, kept even at 0 innings
    # replacement level by role: lower for starters, mixed by his weighted share of starts
    start_share = (w_gs / w_g.where(w_g > 0)).fillna(0.0).clip(0.0, 1.0).to_numpy()
    rep = (lg["rp_replacement_runs_per_ip"]
           + (lg["sp_replacement_runs_per_ip"] - lg["rp_replacement_runs_per_ip"]) * start_share)
    out["war"] = (out["runs"] + rep.to_numpy() * ip) / lg["runs_per_win"].to_numpy()
    out["fip"] = lg["era"].to_numpy() - 9.0 * out["runs"] / ip
    out["start_share"] = start_share
    out["sp_rep_per_ip"] = lg["sp_replacement_runs_per_ip"].to_numpy()
    out["rp_rep_per_ip"] = lg["rp_replacement_runs_per_ip"].to_numpy()
    out["runs_per_win"] = lg["runs_per_win"].to_numpy()
    return out


def rescale_innings(pitchers: pd.DataFrame, new_ip: pd.Series) -> pd.DataFrame:
    """Pitcher projections at other innings (e.g. baseline innings): ip, gs, bf, runs and war
    scaled with the innings, so the rates stay the same. Rows where new_ip is missing keep
    theirs."""
    out = pitchers.copy()
    ip = out["ip"].astype(float)
    target = pd.Series(np.asarray(new_ip, dtype=float), index=out.index).fillna(ip)
    scale = (target / ip.where(ip > 0)).fillna(1.0)
    for col in ("gs", "bf", "runs", "war"):
        out[col] = out[col] * scale
    out["ip"] = target
    return out


def apply_external_def(batters: pd.DataFrame, def_rates: pd.DataFrame,
                       league: pd.DataFrame) -> pd.DataFrame:
    """Replace each batter's Def rate (positional adjustment only: the history has no fielding
    runs) with an outside projection's Def per PA (fielding + positional), where one exists.

    def_rates: season, mlbam_id, def_rate (Def runs per PA, e.g. the mean of Steamer's and
    ZiPS's for that season). The difference from the positional rate is credited as fielding
    (fld_runs) and added to Def and WAR at the runs per win of the season before. Batters with
    no outside rate keep their positional Def and get no fielding runs. A batter with no MLB
    positional history (`has_position` false) has no positional rate to split it from, so his
    fld_runs are left unknown and the lineup optimizer reads his position from the whole Def, as
    it does for an outside projection's players with no MLB games."""
    out = batters.copy()
    rate = out[["season", "mlbam_id"]].merge(
        def_rates[["season", "mlbam_id", "def_rate"]], on=["season", "mlbam_id"],
        how="left")["def_rate"].to_numpy()
    pa = out["pa"].astype(float)
    pos_rate = (out["def_runs"] / pa.where(pa > 0)).fillna(0.0)
    fld = (pd.Series(rate, index=out.index) - pos_rate).fillna(0.0) * pa
    rpw = _prior_league(out, league)["runs_per_win"].to_numpy()
    out["fld_runs"] = fld
    if "has_position" in out:
        out["fld_runs"] = fld.where(out["has_position"].astype(bool))
    out["def_runs"] = out["def_runs"] + fld
    out["war"] = out["war"] + fld / rpw
    return out


# ---- park fit: how a batter's profile suits his team's park ------------------------------
# Events whose rates a park changes, with the league_seasons column of their wOBA weight (runs
# above an out, times the wOBA scale) and of their league rate per PA.
PARK_EVENTS = {"singles": ("w_single", "singles_rate"), "doubles": ("w_double", "doubles_rate"),
               "triples": ("w_triple", "triples_rate"), "hr": ("w_hr", "hr_rate"),
               "ubb": ("w_ubb", "ubb_rate"), "hbp": ("w_hbp", "hbp_rate")}


def batter_profiles(frame: pd.DataFrame, league: pd.DataFrame, reg_pa: float = REG_PA,
                    weights: tuple[float, ...] = BATTER_WEIGHTS) -> pd.DataFrame:
    """Each batter's event rates per PA (singles, doubles, triples, home runs, unintentional
    walks, hit by pitch) and left-side share, Marcel style: his last three seasons weighted
    5/4/3 by PA, with reg_pa of league-average rates (of the season before the target) mixed in.
    Rates are as played (the event mix matters here, not the level)."""
    f = frame[~frame["is_pitcher"].fillna(False).astype(bool)].reset_index(drop=True)
    lg = f[["season"]].merge(league.assign(season=league["season"] + 1), on="season", how="left")
    w_pa = sum(w * f[f"y{k}_pa"] for k, w in enumerate(weights, start=1)).astype(float)
    out = pd.DataFrame({"season": f["season"], "mlbam_id": f["mlbam_id"]})
    for event, (_, rate) in PARK_EVENTS.items():
        def count(k: int, event: str = event) -> pd.Series:
            if event == "ubb":
                return f[f"y{k}_bb"] - f[f"y{k}_ibb"]
            return f[f"y{k}_{event}"]
        n = sum(w * count(k) for k, w in enumerate(weights, start=1)).astype(float)
        out[f"rate_{event}"] = (n + reg_pa * lg[rate].to_numpy()) / (w_pa + reg_pa)
    side_w = sum(w * f[f"y{k}_pa"].where(f[f"y{k}_left_share"].notna(), 0)
                 for k, w in enumerate(weights, start=1)).astype(float)
    side = sum(w * f[f"y{k}_pa"] * f[f"y{k}_left_share"].fillna(0)
               for k, w in enumerate(weights, start=1)).astype(float)
    bats_side = f["bats"].map({"L": 1.0, "R": 0.0}).fillna(0.5) if "bats" in f else 0.5
    out["left_share"] = (side / side_w.where(side_w > 0)).fillna(bats_side)
    return out


def park_runs_per_pa(rows: pd.DataFrame, profiles: pd.DataFrame, team_parks: pd.DataFrame,
                     league: pd.DataFrame) -> pd.Series:
    """Runs per PA a batter's profile gains (+) or loses (-) from his team's park, at half the
    park factor (half his games at home), using his side mix. rows: season, mlbam_id, team_id.
    team_parks: season, team_id, side, pf_<event> (the factors to use for that season); a team
    missing there is neutral. Run values are the wOBA weights over the wOBA scale (runs above
    an out) of the season before."""
    keys = ["season", "mlbam_id"]
    r = rows[keys + ["team_id"]].merge(profiles, on=keys, how="left")
    lg = r[["season"]].merge(league.assign(season=league["season"] + 1), on="season", how="left")
    left = r.merge(team_parks[team_parks["side"] == "L"], on=["season", "team_id"], how="left")
    right = r.merge(team_parks[team_parks["side"] == "R"], on=["season", "team_id"], how="left")
    share = r["left_share"].fillna(0.5)
    runs = pd.Series(0.0, index=r.index)
    for event, (weight, _) in PARK_EVENTS.items():
        pf = (share * left[f"pf_{event}"] + (1 - share) * right[f"pf_{event}"]).fillna(1.0)
        value = lg[weight] / lg["woba_scale"]
        runs += r[f"rate_{event}"].fillna(0.0) * (pf - 1.0) / 2.0 * value.fillna(0.0)
    return pd.Series(runs.to_numpy(), index=rows.index)


def apply_park_fit(rows: pd.DataFrame, runs_per_pa: pd.Series, league: pd.DataFrame,
                   team_means: pd.Series | None = None, pa: str = "pa") -> pd.DataFrame:
    """Add each batter's park fit to his Off and WAR: his park runs per PA minus his team's
    PA-weighted average (team_means, by season and team_id; default: from these rows), so a
    team's total is unchanged and only differences between its batters remain."""
    out = rows.copy()
    if team_means is None:
        team_means = (runs_per_pa * out[pa]).groupby([out["season"], out["team_id"]]).sum() \
            / out[pa].groupby([out["season"], out["team_id"]]).sum()
    mean = pd.Series(list(zip(out["season"], out["team_id"], strict=True)),
                     index=out.index).map(team_means).fillna(0.0)
    fit = runs_per_pa - mean
    rpw = out[["season"]].merge(league.assign(season=league["season"] + 1)[["season", "runs_per_win"]],
                                on="season", how="left")["runs_per_win"].to_numpy()
    out["park_fit"] = fit * 600.0               # runs per 600 PA, for display
    out["off_runs"] = out["off_runs"] + fit * out[pa]
    out["war"] = out["war"] + fit * out[pa] / rpw
    return out
