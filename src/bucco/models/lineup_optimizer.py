"""Optimal plate-appearance allocation: each team's batters spread over positions to maximize WAR.

Every team fills the same plate appearances at every position (`SLOT_PA`: 640 at C, 700 elsewhere,
DH included). A linear program decides how many PA each player gets at each position, with a
replacement-level player (0 WAR) always available to fill the rest. See docs/R&D/lineup_optimizer.md.

Value of player i at position q, in runs, for x PA in total and x_q of them at q:

* Batting and baserunning: x * o_i - fatigue. o_i is the projection's `Off` per PA. The rate falls
  as playing time rises, faster and faster: rate(x) = o_i - c * ((x/600)^k - (PA_i/600)^k), where
  PA_i is the projection's own PA. At the projected PA the rate is the projection's; fewer PA give
  a slightly better rate (rest, platoon spots), more PA a worse one. c is `FATIGUE_RUNS`, k is
  `FATIGUE_POWER`.
* Replacement-level credit: `rep_runs` per PA, the same for everyone (WAR is runs above
  replacement).
* Defense, per PA: def_q / 700, where def_q is the player's defensive runs per 700 PA at q. The
  projection's Def (fielding + positional adjustment) is taken to be at his most-played position.
  Elsewhere his fielding changes by the amount fitted from Statcast OAA for players who made that
  move (`SwitchMatrix`, scripts/fit_position_switch.py), minus a selection penalty at positions
  he has not played (see `defense_at`); catchers moving off catcher keep none of their catching
  value;
  - at DH: the DH adjustment (-17.5), with no fielding;
  - at catcher: only players who caught.

WAR = runs / `runs_per_win`. The fatigue curve is cut into SEGMENT_PA steps, so the problem is an
exact linear program (the curve is concave, so the steps fill in order).
"""

from __future__ import annotations

from collections.abc import Mapping

import numpy as np
import pandas as pd
from scipy.optimize import linprog

from bucco.config import DATA_DIR
from bucco.models.depth_chart import POSITION_ADJ_RUNS, SLOT_PA

POSITIONS = ("C", "1B", "2B", "3B", "SS", "LF", "CF", "RF", "DH")
FIELD = POSITIONS[:-1]
MIN_GAMES = 20            # games at a position last season to count as one of his positions
FATIGUE_RUNS = 0.015      # c: runs per PA lost at 600 PA, relative to no playing time
FATIGUE_POWER = 2.0       # k: the loss grows as (PA / 600) ** k
REST_BONUS = 0.5          # share of the better rate kept below the projected PA (0 = none)
RESERVE_PA = 0.0          # PA per team held for players not on the preseason list
SEGMENT_PA = 25.0         # step size of the fatigue curve in the linear program
MAX_PA = 700.0            # most PA any player can get
TIE_BREAK = 0.05          # runs per 700 PA: prefer a player's own position when it's a tie
NAMED_ADJ = {"C": 12.5, "SS": 7.5, "MID": 2.5, "COR": -7.5, "1B": -12.5, "DH": -17.5}
# Selection penalty, on top of the fitted change, at positions a player has NOT played: the
# fitted change comes from players teams chose to move, who were expected to cope. Flat runs per
# 700 PA, plus a share of any rise in difficulty (the fitted difficulty, in fielding runs).
SELECTION_BASE = 2.0
SELECTION_UP = 0.5
# Cap the fielding change of a move at the positional-adjustment gap, so moving up the spectrum
# never adds defensive value. Statcast OAA rates 2B/3B/SS at a third to a half of the difficulty
# the adjustments give them (relative to 1B and the outfield corners), which on its own lets any
# corner outfielder gain about 9 runs per 700 PA by moving to third base.
ADJ_FLOOR = True
# Extra selection penalty for moves the optimizer makes far more often than teams do, relative
# to its usual share of real moves (runs per 700 PA). Fitted by scripts/fit_rarity_penalty.py:
# outfielders went to first base twice as often as on real teams (5x the optimizer's usual share);
# 6 runs brings that in line.
RARITY_PENALTY: dict[tuple[str, str], float] = {("LF", "1B"): 6.0, ("CF", "1B"): 6.0,
                                                 ("RF", "1B"): 6.0}
SWITCH_FILE = DATA_DIR / "derived" / "position_switch.csv"

# Statcast has no catcher OAA, so two players are placed on the spectrum by assumption:
# a catcher playing elsewhere fields like an average first baseman (his catching value does not
# carry over), and a DH-only player like a below-average first baseman. Both then follow the
# fitted changes and selection penalties from first base.
CATCHER_AS_1B_FLD = 0.0
DH_ONLY_AS_1B_FLD = -5.0
# A player who also caught last season but mainly plays elsewhere: a below-average catcher,
# fielding runs per 700 PA. Hand-set.
PART_TIME_CATCHER_FLD = -5.0


class SwitchMatrix:
    """How a fielder's fielding runs per full season (about 700 PA), relative to the average
    player at each position, change when he moves from p to q. Built by
    scripts/fit_position_switch.py from Statcast OAA (C is not covered).

    The change is difficulty[p] - difficulty[q], the additive part of the fit. The per-move
    averages (`delta`) are kept for reference but not used: they are noisy, and because they are
    not additive, some chains of moves add up to free runs (RF -> 1B -> CF -> RF came to +6) that
    an optimizer would exploit.
    """

    def __init__(self, delta: Mapping[tuple[str, str], float], difficulty: Mapping[str, float],
                 adj_floor: bool = ADJ_FLOOR,
                 rarity: Mapping[tuple[str, str], float] | None = None):
        self.delta = dict(delta)
        self.difficulty = dict(difficulty)
        self.adj_floor = adj_floor
        self.rarity = dict(RARITY_PENALTY if rarity is None else rarity)

    def change(self, p: str, q: str) -> float:
        """Fielding change from p to q: the OAA fit, or with `adj_floor` the lower of it and
        the positional-adjustment gap adj(p) - adj(q), whichever is stricter."""
        oaa = self.difficulty[p] - self.difficulty[q]
        if not self.adj_floor:
            return oaa
        return min(oaa, POSITION_ADJ_RUNS[p] - POSITION_ADJ_RUNS[q])

    def selection(self, p: str, q: str, base: float = SELECTION_BASE,
                  up: float = SELECTION_UP) -> float:
        rise = max(0.0, self.difficulty[q] - self.difficulty[p])
        return base + up * rise + self.rarity.get((p, q), 0.0)


def load_switch_matrix(path=SWITCH_FILE, adj_floor: bool = ADJ_FLOOR,
                       rarity: Mapping[tuple[str, str], float] | None = None) -> SwitchMatrix:
    if not path.exists():
        raise RuntimeError(f"{path} not found. Run scripts/fit_position_switch.py first.")
    fit = pd.read_csv(path)
    delta = {(r["from"], r["to"]): r["delta"] for _, r in fit.iterrows()}
    difficulty = {**dict(zip(fit["from"], fit["difficulty_from"], strict=True)),
                  **dict(zip(fit["to"], fit["difficulty_to"], strict=True))}
    return SwitchMatrix(delta, difficulty, adj_floor, rarity)


def defense_at(def700: float, anchor: str | None, natives: tuple[str, ...],
               switch: SwitchMatrix, selection_base: float = SELECTION_BASE,
               selection_up: float = SELECTION_UP) -> dict[str, float]:
    """Defensive runs per 700 PA (fielding + positional adjustment) at each position he can play.

    def700: the projection's defense per 700 PA, taken to be at `anchor`, his most-played
    position, so his fielding there is def700 - adj(anchor). Elsewhere his fielding (relative to
    the average player at that position) is his anchor fielding plus the fitted change; at a
    position he has not played, minus the selection penalty too. Only catchers catch; elsewhere
    a catcher fields like an average first baseman and a DH-only player like a below-average
    one. DH is adj(DH) for everyone. A small TIE_BREAK favors the anchor when two players are
    otherwise interchangeable.
    """
    out = {"DH": POSITION_ADJ_RUNS["DH"]}
    fielding = [p for p in natives if p in FIELD]
    # fld: fielding runs per 700 PA at each position he has played, relative to the average there.
    # move_from: where moves to positions he has not played start, and from what fielding.
    if not fielding:                                  # DH only
        fld = {}
        move_from = {"1B": DH_ONLY_AS_1B_FLD}
    elif (anchor if anchor in fielding else fielding[0]) == "C":
        anchor = "C"
        fld = {"C": def700 - POSITION_ADJ_RUNS["C"]}
        fld.update({p: CATCHER_AS_1B_FLD + switch.change("1B", p) for p in fielding if p != "C"})
        move_from = {"1B": CATCHER_AS_1B_FLD, **{p: f for p, f in fld.items() if p != "C"}}
    else:
        anchor = anchor if anchor in fielding else fielding[0]
        base = def700 - POSITION_ADJ_RUNS[anchor]
        fld = {p: (PART_TIME_CATCHER_FLD if p == "C" else base + switch.change(anchor, p))
               for p in fielding}
        move_from = {p: f for p, f in fld.items() if p != "C"}
    for q in FIELD:
        if q in fld:
            value = fld[q]
        elif q == "C":
            continue                                  # only catchers catch
        else:
            value = max(f + switch.change(p, q) - switch.selection(p, q, selection_base,
                                                                   selection_up)
                        for p, f in move_from.items())
        out[q] = value + POSITION_ADJ_RUNS[q] - (0.0 if q == anchor else TIE_BREAK)
    return out


def natives_from_games(games: Mapping[str, float], min_games: float = MIN_GAMES
                       ) -> tuple[str | None, tuple[str, ...]]:
    """(anchor, positions) from last season's games: the most-played fielding position, and it
    plus any other with min_games. A DH-only player has no anchor and plays ("DH",)."""
    fielding = {p: g for p, g in games.items() if p in FIELD and g > 0}
    if not fielding:
        return None, (("DH",) if games.get("DH", 0) > 0 else ())
    top = max(fielding, key=fielding.get)
    return top, tuple(sorted({top} | {p for p, g in fielding.items() if g >= min_games}))


def natives_from_adjustment(adj700: float) -> tuple[str, ...]:
    """Positions implied by a projection's positional adjustment per 700 PA (for players with no
    MLB games last season): the nearest of the FanGraphs adjustments."""
    groups = {"C": ("C",), "SS": ("SS",), "MID": ("2B", "3B", "CF"), "COR": ("LF", "RF"),
              "1B": ("1B",), "DH": ("DH",)}
    nearest = min(NAMED_ADJ, key=lambda k: abs(NAMED_ADJ[k] - adj700))
    return groups[nearest]


def offense_rate(o_rate: float, proj_pa: float, x, fatigue: float = FATIGUE_RUNS,
                 power: float = FATIGUE_POWER, rest_bonus: float = REST_BONUS):
    """Batting runs per PA at x PA in total: the projection's rate at its own PA, worse above it
    (the change growing as (x / 600) ** power) and better below it, by `rest_bonus` times as
    much. The rate always falls as x rises, so total runs stay concave in x."""
    change = (np.asarray(x) / 600.0) ** power - (proj_pa / 600.0) ** power
    return o_rate - fatigue * np.where(change > 0, change, rest_bonus * change)


def offense_segments(o_rate: float, proj_pa: float, fatigue: float = FATIGUE_RUNS,
                     max_pa: float = MAX_PA, step: float = SEGMENT_PA,
                     power: float = FATIGUE_POWER, rest_bonus: float = REST_BONUS) -> np.ndarray:
    """Average batting runs per PA within each SEGMENT_PA step of playing time (decreasing)."""
    edges = np.arange(0.0, max_pa + step / 2, step)
    total = edges * offense_rate(o_rate, proj_pa, edges, fatigue, power, rest_bonus)
    return np.diff(total) / step


def player_inputs(batters: pd.DataFrame, positions: pd.DataFrame,
                  switch: SwitchMatrix | None = None, selection_base: float = SELECTION_BASE,
                  selection_up: float = SELECTION_UP) -> pd.DataFrame:
    """Per-player inputs: o_rate (Off per PA), proj_pa, natives, and def700 by position.

    batters: one season's projections with mlbam_id, team_id, player_name, plate_appearances,
    off_runs, def_runs, fld_runs (may be null; used only for players with no MLB games), war.
    positions: last season's games by position (season, mlbam_id, position, games), as in the
    player_position_games mart. switch: the fitted position-switch matrix (default: the saved fit).
    """
    switch = switch or load_switch_matrix()
    games = {pid: dict(zip(g["position"], g["games"], strict=True))
             for pid, g in positions.groupby("mlbam_id")}
    rows = []
    for r in batters.itertuples(index=False):
        pa = float(r.plate_appearances)
        if not pa > 0:
            continue
        anchor, natives = natives_from_games(games.get(r.mlbam_id, {}))
        def700 = r.def_runs / pa * 700.0
        source = "last_season"
        if not natives:                 # no MLB games: use the projection's own adjustment
            adj700 = ((r.def_runs - r.fld_runs) / pa * 700.0 if pd.notna(r.fld_runs) else def700)
            natives = natives_from_adjustment(adj700)
            anchor = natives[0] if natives != ("DH",) else None
            source = "projection"
        rows.append({"mlbam_id": r.mlbam_id, "team_id": r.team_id, "player_name": r.player_name,
                     "proj_pa": pa, "o_rate": r.off_runs / pa, "def700": def700,
                     "anchor": anchor, "natives": natives, "position_source": source,
                     **{f"def_{q}": v for q, v in defense_at(def700, anchor, natives, switch, selection_base,
                                                  selection_up).items()}})
    out = pd.DataFrame(rows)
    for q in POSITIONS:
        if f"def_{q}" not in out:
            out[f"def_{q}"] = np.nan
    return out


def war_scale(batters: pd.DataFrame) -> tuple[float, float]:
    """(runs per win, replacement runs per PA) that best reproduce the projection's WAR:
    WAR = (Off + Def) / runs_per_win + PA * rep_runs / runs_per_win, fit by least squares."""
    b = batters[batters["plate_appearances"] >= 50]
    x = np.c_[b["off_runs"] + b["def_runs"], b["plate_appearances"]]
    (inv_rpw, rep_per_pa_win), *_ = np.linalg.lstsq(x, b["war"], rcond=None)
    return 1.0 / inv_rpw, rep_per_pa_win / inv_rpw


def optimize_team(players: pd.DataFrame, rep_runs: float, runs_per_win: float,
                  slot_pa: Mapping[str, float] = SLOT_PA, fatigue: float = FATIGUE_RUNS,
                  max_pa: float = MAX_PA, step: float = SEGMENT_PA,
                  power: float = FATIGUE_POWER, rest_bonus: float = REST_BONUS,
                  reserve_pa: float = RESERVE_PA) -> pd.DataFrame:
    """Best PA by player and position for one team. Returns one row per player-position with PA
    and WAR (replacement-level PA appear with mlbam_id = -1 and 0 WAR).

    reserve_pa: PA held back for players who join during the season, split over positions in
    proportion to their PA and given to replacement level (mlbam_id -2) before optimizing."""
    reserve = {q: reserve_pa * slot_pa[q] / sum(slot_pa.values()) for q in POSITIONS}
    slot_pa = {q: slot_pa[q] - reserve[q] for q in POSITIONS}
    players = players.reset_index(drop=True)
    n = len(players)
    x_index = [(i, q) for i in range(n) for q in POSITIONS
               if pd.notna(players.loc[i, f"def_{q}"])]
    segs = [offense_segments(players.loc[i, "o_rate"], players.loc[i, "proj_pa"], fatigue,
                             max_pa, step, power, rest_bonus) for i in range(n)]
    k = len(segs[0]) if n else 0
    nx, ns, nr = len(x_index), n * k, len(POSITIONS)
    # objective: maximize runs -> minimize the negative
    c = np.zeros(nx + ns + nr)
    for j, (i, q) in enumerate(x_index):
        c[j] = -(players.loc[i, f"def_{q}"] / 700.0 + rep_runs)
    for i in range(n):
        c[nx + i * k: nx + (i + 1) * k] = -segs[i]
    a_eq, b_eq = [], []
    for s, q in enumerate(POSITIONS):          # each position's PA are filled exactly
        row = np.zeros(nx + ns + nr)
        for j, (_, qq) in enumerate(x_index):
            if qq == q:
                row[j] = 1.0
        row[nx + ns + s] = 1.0
        a_eq.append(row)
        b_eq.append(slot_pa[q])
    for i in range(n):                          # a player's PA = his filled fatigue steps
        row = np.zeros(nx + ns + nr)
        for j, (ii, _) in enumerate(x_index):
            if ii == i:
                row[j] = 1.0
        row[nx + i * k: nx + (i + 1) * k] = -1.0
        a_eq.append(row)
        b_eq.append(0.0)
    bounds = [(0, None)] * nx + [(0, step)] * ns + [(0, None)] * nr
    res = linprog(c, A_eq=np.array(a_eq), b_eq=np.array(b_eq), bounds=bounds, method="highs")
    if not res.success:
        raise RuntimeError(f"lineup optimization failed: {res.message}")
    x = res.x
    rows = []
    for j, (i, q) in enumerate(x_index):
        if x[j] > 1e-6:
            rows.append({"mlbam_id": players.loc[i, "mlbam_id"],
                         "player_name": players.loc[i, "player_name"], "position": q, "pa": x[j]})
    for s, q in enumerate(POSITIONS):
        if x[nx + ns + s] > 1e-6:
            rows.append({"mlbam_id": -1, "player_name": "replacement level", "position": q,
                         "pa": x[nx + ns + s]})
        if reserve[q] > 0:
            rows.append({"mlbam_id": -2, "player_name": "in-season additions", "position": q,
                         "pa": reserve[q]})
    alloc = pd.DataFrame(rows, columns=["mlbam_id", "player_name", "position", "pa"])
    # WAR: each player's offense on his total PA (with fatigue), defense and replacement credit
    # by position; replacement-level rows are 0.
    by_id = players.set_index("mlbam_id")
    total = alloc[alloc["mlbam_id"] >= 0].groupby("mlbam_id")["pa"].sum()

    def runs(row):
        if row.mlbam_id < 0:
            return 0.0
        p = by_id.loc[row.mlbam_id]
        x_all = total[row.mlbam_id]
        rate = offense_rate(p["o_rate"], p["proj_pa"], x_all, fatigue, power, rest_bonus)
        return row.pa * (rate + rep_runs + p[f"def_{row.position}"] / 700.0)

    alloc["war"] = alloc.apply(runs, axis=1) / runs_per_win if len(alloc) else []
    return alloc


def optimize_league(batters: pd.DataFrame, positions: pd.DataFrame,
                    fatigue: float = FATIGUE_RUNS, power: float = FATIGUE_POWER,
                    rest_bonus: float = REST_BONUS, reserve_pa: float = RESERVE_PA,
                    switch: SwitchMatrix | None = None, selection_base: float = SELECTION_BASE,
                    selection_up: float = SELECTION_UP, max_pa: float = MAX_PA,
                    anchor_pa: float | None = None) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Optimize every team in one season. Returns (allocations with team_id, player inputs).

    anchor_pa: anchor every player's fatigue curve at this PA instead of his projected PA, so
    the projection's playing time has no say in the allocation."""
    runs_per_win, rep_runs = war_scale(batters)
    inputs = player_inputs(batters, positions, switch, selection_base, selection_up)
    if anchor_pa is not None:
        inputs = inputs.assign(proj_pa=float(anchor_pa))
    out = []
    for team_id, group in inputs.groupby("team_id"):
        alloc = optimize_team(group, rep_runs, runs_per_win, fatigue=fatigue, power=power,
                              rest_bonus=rest_bonus, reserve_pa=reserve_pa, max_pa=max_pa)
        alloc["team_id"] = team_id
        out.append(alloc)
    allocations = pd.concat(out, ignore_index=True)
    allocations.attrs.update(runs_per_win=runs_per_win, rep_runs=rep_runs)
    return allocations, inputs
