"""Depth-chart logic: decide who plays, where and how much, then give each player his WAR.

The ZiPS player files give each player's WAR for his own projected playing time, estimated
without regard to the rest of the roster (see docs/R&D/proportional_fill.md). A depth chart
fixes that by filling the real slots on a team.

Batters (9 slots: C, 1B, 2B, 3B, SS, LF, CF, RF, DH)
    1. Eligibility. A player can fill a slot if he played it (or a position that flexes to it,
       such as SS to 2B) enough last season (see `eligible_slots` and `FLEX_SLOTS`). A player
       with no MLB season last year has no known position, so one is guessed from his
       baserunning (`BSR_BINS`), or the outfield and DH if that is missing too.
    2. Ranking. At each slot the eligible players are ranked by projected WAR per plate
       appearance at that slot. The DH slot is valued on batting alone, since a DH has no
       defense (his ZiPS WAR is rebuilt with the DH positional adjustment).
    3. Sharing. The slot's season of plate appearances (640 at catcher, 700 elsewhere) is shared
       down the ranking. Each step down multiplies the weight by `RANK_DECAY` (days off and
       injuries, so even a clear starter does not play every inning) and by
       exp(-`DECAY_PER_WAR600` x the rate the next player gives up, in WAR per 600 PA). A slot
       with a big gap between its best player and the next gets a near full-time starter, while
       a slot with equal options splits its time. Replacement level is the last player in every
       ranking, so PA nobody good can absorb go to zero WAR instead of to a bad player.
    4. Cleanup. A player eligible at several slots can't play all of them. His home slot is the
       one where he would get the most PA. He keeps full weight there, and weight
       `SECONDARY_WEIGHT` at every other slot. His total is limited to his own projected PA and no
       slot gives one player more than `MAX_SLOT_SHARE`. When he is over his limit, his shares at
       the other slots are scaled back first (never the home slot), and the freed PA go to the
       next players at those slots, repeating until nobody is over.

Pitchers
    A pitcher is a starter if ZiPS projects him for at least `min_starts` starts
    (`classify_pitcher_role`). The five best starters share `starter_ip_share` of the team's
    innings, the rest of that share goes to the next starters with a decay, and relievers share
    what remains with a decay.

Nothing here reads files or the database. The inputs are DataFrames, so the backtest decides
what a team is allowed to know.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping

import numpy as np
import pandas as pd

from bucco.models.playing_time import _spread_bench

# --- batters ----------------------------------------------------------------------------
BATTER_SLOTS = ("C", "1B", "2B", "3B", "SS", "LF", "CF", "RF", "DH")
FIELD_POSITIONS = ("C", "1B", "2B", "3B", "SS", "LF", "CF", "RF")
SLOT_PA = {"C": 640.0, **{s: 700.0 for s in BATTER_SLOTS if s != "C"}}  # FanGraphs
# How a slot's plate appearances are shared among its eligible players (see build_batter_depth_chart)
RANK_DECAY = 0.7              # each rank down gets this fraction of the one above: rest days, injuries
DECAY_PER_WAR600 = 0.25       # extra decay per 1.0 WAR-per-600-PA of rate the next player gives up
SECONDARY_WEIGHT = 0.25       # weight at any slot other than the player's home slot
MAX_SLOT_SHARE = 0.92         # most of a slot's PA one player can get (about 150 of 162 games)
MAX_PLAYER_PA = 700.0         # most PA one player can get over all slots
_MAX_ITER = 200
_TOL = 1e-6
MIN_ELIGIBLE_GAMES = 20       # games at a position last season to count as able to play it
# Extra slots a player can fill because of a position he is listed at (his main position, or one
# he played at least MIN_ELIGIBLE_GAMES games at). Everyone can also DH, so DH is not listed.
FLEX_SLOTS: dict[str, tuple[str, ...]] = {
    "2B": ("1B",),
    "SS": ("2B", "1B"),
    "3B": ("1B",),
    "LF": ("LF", "CF", "RF"),
    "CF": ("LF", "CF", "RF"),
    "RF": ("LF", "CF", "RF"),
}
DEFAULT_UNKNOWN_SLOTS = ("LF", "CF", "RF", "DH")  # no prior season and no BsR: outfield or DH
# No prior MLB season: guess a position from baserunning (BsR per 600 PA, as a percentile among
# batters projected for 200+ PA that season). Faster players tend to play up the middle. Each
# bin is a set of listed positions, and FLEX_SLOTS then adds what those positions can also play.
BSR_BINS: tuple[tuple[float, tuple[str, ...]], ...] = (
    (0.2, ("1B",)),                  # slowest fifth: first base (or DH)
    (0.4, ("3B", "LF", "RF")),       # 20-40%: third base or a corner outfield spot
    (0.6, ("2B",)),                  # 40-60%: second base
    (1.0, ("CF", "SS")),             # 60% and up: center field or shortstop
)
BSR_REFERENCE_MIN_PA = 200.0
# Defense shrink, applied when ranking only (credited WAR stays ZiPS). See docs/R&D/depth_chart.md.
POSITION_WEIGHT = 0.7         # share of the positional adjustment kept; splitting it from fielding did not help
OFF_POSITION_MULTIPLIER = 0.7  # factor on the ranking rate away from his main position
OFF_POSITION_PENALTY = 0.0    # runs per 700 PA off the ranking rate away from his main position (off)
DEF_WEIGHT = 0.7              # share of ZiPS defense runs kept when ranking; see docs/R&D/depth_chart.md
# Players whose position is a guess have their projected WAR trimmed by this factor: they are
# the least certain to hold a job (see docs/R&D/depth_chart.md).
UNKNOWN_WAR_MULTIPLIER = 0.1
UNKNOWN_POSITION_SOURCES = ("default_outfield", "imputed_bsr")
RUNS_PER_WIN = 10.0
# FanGraphs positional adjustments, runs per 162 games (about 700 PA for a regular).
POSITION_ADJ_RUNS = {"C": 12.5, "1B": -12.5, "2B": 2.5, "3B": 2.5, "SS": 7.5,
                     "LF": -7.5, "CF": 2.5, "RF": -7.5, "DH": -17.5}
DH_ADJ_RUNS = -17.5           # FanGraphs positional adjustment for DH, per 162 games
DH_ADJ_RUNS_PER_PA = DH_ADJ_RUNS / 700.0

# --- pitchers ---------------------------------------------------------------------------
MIN_STARTS = 15               # ZiPS-projected starts to be called a starter
ROTATION_SIZE = 5
IP_BUDGET = 1500.0
STARTER_IP_SHARE = 0.57       # real starters throw about 57% of team innings
SP_DECAY = 0.5
RP_DECAY = 0.85
MIN_RP_IP = 20.0              # relievers projected for less than this are not ranked

_BIG = 1e6


# ---------------------------------------------------------------------------------------
# Eligibility
# ---------------------------------------------------------------------------------------
def impute_listed_positions(bsr_percentile: float) -> tuple[str, ...]:
    """Positions to list a player at, from his baserunning percentile (0 slowest, 1 fastest)."""
    for upper, positions in BSR_BINS:
        if bsr_percentile < upper:
            return positions
    return BSR_BINS[-1][1]


def bsr_percentiles(batters: pd.DataFrame, bsr: str = "bsr", pa: str = "pa",
                    min_pa: float = BSR_REFERENCE_MIN_PA) -> pd.Series:
    """Each batter's baserunning percentile for one season, from 0 (slowest) to 1.

    BsR is baserunning runs. It grows with playing time, so it is converted to runs per 600 PA
    first, then ranked against batters projected for at least `min_pa` PA in the same frame
    (pass the whole league's batters for one season, not one team).
    """
    per600 = batters[bsr].astype(float) / batters[pa].astype(float).where(batters[pa] > 0) * 600
    reference = np.sort(per600[batters[pa] >= min_pa].dropna().to_numpy())
    if len(reference) == 0:
        return pd.Series(np.nan, index=batters.index)
    pct = np.searchsorted(reference, per600.to_numpy(), side="right") / len(reference)
    return pd.Series(np.clip(pct, 0.0, 1.0), index=batters.index).where(per600.notna())


def listed_positions(
    games_by_position: Mapping[str, float] | None,
    min_games: float = MIN_ELIGIBLE_GAMES,
    bsr_percentile: float | None = None,
) -> tuple[frozenset[str], str]:
    """The positions a batter is listed at, and where that came from.

    Known player: his main field position plus every field position with at least `min_games`
    games last season (source "prior_season"). A player who only DHed or only pitched has none.
    No prior MLB season: a guess from his baserunning percentile ("imputed_bsr"), or the
    outfield if that is missing too ("default_outfield").
    """
    if not games_by_position:
        if bsr_percentile is None or pd.isna(bsr_percentile):
            return frozenset(DEFAULT_UNKNOWN_SLOTS) - {"DH"}, "default_outfield"
        return frozenset(impute_listed_positions(float(bsr_percentile))), "imputed_bsr"
    field = {p: float(g) for p, g in games_by_position.items() if p in FIELD_POSITIONS}
    listed = {p for p, g in field.items() if g >= min_games}
    if field:
        listed.add(max(field, key=lambda p: (field[p], p)))
    return frozenset(listed), "prior_season"


def primary_position(games_by_position: Mapping[str, float] | None) -> str | None:
    """The field position with the most games last season, or None if he has no field games."""
    field = {p: float(g) for p, g in (games_by_position or {}).items() if p in FIELD_POSITIONS}
    return max(field, key=lambda p: (field[p], p)) if field else None


def eligible_slots(
    games_by_position: Mapping[str, float] | None,
    min_games: float = MIN_ELIGIBLE_GAMES,
    flex: Mapping[str, tuple[str, ...]] = FLEX_SLOTS,
    bsr_percentile: float | None = None,
) -> tuple[frozenset[str], str]:
    """Slots a batter can fill, and where that came from.

    `games_by_position` is last season's games at each position (as in player_position_games).

    A player with no prior MLB season has no known position. If his baserunning percentile is
    given, a position is guessed from it (`BSR_BINS`) and the source is "imputed_bsr". Without
    it he is assumed to fit the outfield or DH ("default_outfield").

    For a known player, his listed positions (see `listed_positions`) are his main field
    position plus every field position with at least `min_games` games. He can fill each of
    those, plus whatever `flex` adds for them. By default (`FLEX_SLOTS`):
      * a shortstop can also play second base and first base;
      * a second or third baseman can also play first base (so any infielder can);
      * anyone listed in the outfield can play any outfield position;
      * everyone can DH.
    A catcher or first baseman gets nothing extra beyond positions he really played. A player who
    only DHed (or only pitched) can only DH. Imputed positions get the same flex.
    """
    listed, source = listed_positions(games_by_position, min_games, bsr_percentile)
    slots = set(listed)
    for position in listed:
        slots.update(flex.get(position, ()))
    slots.add("DH")
    return frozenset(slots), source


def build_batter_pool(batters: pd.DataFrame, position_games: pd.DataFrame,
                      min_games: float = MIN_ELIGIBLE_GAMES) -> pd.DataFrame:
    """Attach eligible slots to projected batters.

    `batters` needs mlbam_id, pa, war and (optionally) def_runs and `bsr_pct`, the baserunning
    percentile from `bsr_percentiles` (computed over the whole league's batters for the
    season, before splitting by team). `bsr_pct` is only used for players with no prior MLB
    season. `position_games` is the player_position_games mart for ONE target season: mlbam_id,
    position, games.
    """
    games = {pid: dict(zip(g["position"], g["games"], strict=True))
             for pid, g in position_games.groupby("mlbam_id")}
    out = batters.copy()
    pct = out["bsr_pct"] if "bsr_pct" in out else pd.Series(np.nan, index=out.index)
    result = [eligible_slots(games.get(pid), min_games, bsr_percentile=p)
              for pid, p in zip(out["mlbam_id"], pct, strict=True)]
    out["eligible"] = [r[0] for r in result]
    out["primary_position"] = [primary_position(games.get(pid)) for pid in out["mlbam_id"]]
    out["position_source"] = [r[1] for r in result]
    return out


# ---------------------------------------------------------------------------------------
# Batters
# ---------------------------------------------------------------------------------------
def slot_war_rate(war: float, pa: float, def_runs: float | None, slot: str,
                  position_runs: float = 0.0) -> float:
    """WAR per plate appearance if the player fills `slot`.

    Outside DH this is the ZiPS rate, taken as is (his ZiPS position is assumed to be near the
    slot). At DH his fielding and position credit disappear and the DH adjustment is applied, so
    the DH slot is valued on batting.

    `position_runs` is added to WAR (as runs) before the rate is taken; the depth chart uses
    it to swap the positional adjustment of his own position for the one at `slot`.
    """
    if pa <= 0:
        return 0.0
    rate = (war + position_runs / RUNS_PER_WIN) / pa
    if slot != "DH" or def_runs is None or pd.isna(def_runs):
        return rate
    return rate - def_runs / (RUNS_PER_WIN * pa) + DH_ADJ_RUNS_PER_PA / RUNS_PER_WIN


def _waterfill(total: float, weights: np.ndarray, caps: np.ndarray) -> np.ndarray:
    """Share `total` in proportion to `weights`, with no entry above its cap.

    An entry that would pass its cap is held at the cap and the excess is shared again among
    the rest in proportion to their weights. If every cap is reached the total is not used up.
    """
    alloc = np.zeros(len(weights))
    remaining = float(total)
    live = (weights > 0) & (caps > 0)
    for _ in range(len(weights) + 1):
        if remaining <= 1e-9 or not live.any():
            break
        w = np.where(live, weights, 0.0)
        give = np.minimum(remaining * w / w.sum(), caps - alloc)
        alloc += give
        remaining -= give.sum()
        live &= alloc < caps - 1e-9
    return alloc


def _rank_weights(rates: np.ndarray, rank_decay: float, decay_per_war600: float) -> np.ndarray:
    """Weights for players ranked best to worst, ending with replacement level (rate 0).

    The weight of each player is the one above times `rank_decay` times
    exp(-`decay_per_war600` x the rate he gives up, in WAR per 600 PA).
    """
    full = np.append(rates, 0.0)
    gaps = np.maximum(0.0, full[:-1] - full[1:]) * 600.0
    steps = rank_decay * np.exp(-decay_per_war600 * gaps)
    return np.concatenate([[1.0], np.cumprod(steps)])


def build_batter_depth_chart(
    pool: pd.DataFrame,
    rank_decay: float = RANK_DECAY,
    decay_per_war600: float = DECAY_PER_WAR600,
    secondary_weight: float = SECONDARY_WEIGHT,
    max_slot_share: float = MAX_SLOT_SHARE,
    slot_pa: Mapping[str, float] = SLOT_PA,
    unknown_can_start: bool = True,
    unknown_war_multiplier: float = UNKNOWN_WAR_MULTIPLIER,
    def_weight: float = DEF_WEIGHT,
    position_weight: float = POSITION_WEIGHT,
    slot_position_credit: bool = True,
    off_position_penalty: float = OFF_POSITION_PENALTY,
    off_position_multiplier: float = OFF_POSITION_MULTIPLIER,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Share one team's plate appearances among its batters, slot by slot.

    `pool` is one team's batters from `build_batter_pool` (mlbam_id, pa, war, eligible, and
    optionally def_runs and position_source). Returns (players, allocations):

    * players: the pool plus `slot` (the slot where he gets the most PA, or None), `role`
      ("starter" if he gets the most PA at some slot, "backup" if he gets PA but never the most,
      else "unused"), `allocated` (total PA), `fraction` (allocated / projected) and `scaled_war`.
    * allocations: one row per player per slot with `rank`, `pa` and `war`. The PA a slot gives
      to replacement level are not listed; they are the slot's PA minus these rows.

    rank_decay: weight of each rank as a fraction of the rank above, before gaps. 0.25 gives a
        slot with equal players a 75% / 19% / 5% split.
    decay_per_war600: how much faster the weights fall for each 1.0 WAR per 600 PA the next
        player gives up. 0 ignores the gap and uses `rank_decay` alone.
    secondary_weight: weight multiplier at every slot except the player's home slot (the one
        where he would get the most PA). 1.0 treats every eligible slot the same.
    max_slot_share: the most of a slot's PA any one player can receive.
    unknown_can_start: if False, players whose position is a guess (`position_source` is
        "default_outfield" or "imputed_bsr") are ranked below every known player at each slot.
    unknown_war_multiplier: multiplies the projected WAR (and defense runs) of those same
        players before ranking, so it changes both their rank and the WAR they are credited with.
    def_weight: share of each player's projected defense runs (the ZiPS `Def` column, which
        includes the positional adjustment) kept before ranking. The rest is taken out of his
        WAR as (1 - def_weight) * Def / RUNS_PER_WIN. 1.0 uses ZiPS WAR as is; 0 ranks on
        batting and baserunning alone. This only changes who gets the playing time: the WAR a
        player is credited with for it still uses his unshrunk ZiPS WAR (and `Def`, at DH).
    position_weight: share of the positional adjustment (`POSITION_ADJ_RUNS` for his
        `primary_position`, scaled by PA / 700) kept. With the pool's `primary_position`, `Def`
        is split into the positional part, kept at this weight, and the fielding part
        (the rest), kept at `def_weight`. Without it all of `Def` is treated as fielding.
    slot_position_credit: if True, a player with a known `primary_position` who fills another
        slot has his positional adjustment swapped for that slot's (a shortstop at first base
        loses 20 runs per 700 PA of position credit), both in ranking and in the WAR credited.
        His fielding runs are assumed to carry over. DH is valued separately (see
        `slot_war_rate`). Players with no known primary position are left as is.
    off_position_penalty: runs per 700 PA subtracted from a player's ranking rate at any
        non-DH slot other than his `primary_position`. Ranking only: the credited WAR is not
        reduced. Players with no known primary position are never penalized. 0 turns it off.
    off_position_multiplier: factor (0 to 1) applied to a positive ranking rate in the same
        off-position cases, after the penalty above. 0.8 takes 20% off. Ranking only. 1 turns it off.
    """
    if not 0.0 < rank_decay < 1.0:
        raise ValueError("rank_decay must be in (0, 1)")
    if decay_per_war600 < 0:
        raise ValueError("decay_per_war600 must not be negative")
    if not 0.0 < secondary_weight <= 1.0:
        raise ValueError("secondary_weight must be in (0, 1]")
    if not 0.0 < max_slot_share <= 1.0:
        raise ValueError("max_slot_share must be in (0, 1]")
    if not 0.0 <= unknown_war_multiplier <= 1.0:
        raise ValueError("unknown_war_multiplier must be between 0 and 1")
    if not 0.0 <= def_weight <= 1.0:
        raise ValueError("def_weight must be between 0 and 1")
    if not 0.0 <= position_weight <= 1.0:
        raise ValueError("position_weight must be between 0 and 1")
    if off_position_penalty < 0:
        raise ValueError("off_position_penalty must not be negative")
    if not 0.0 < off_position_multiplier <= 1.0:
        raise ValueError("off_position_multiplier must be in (0, 1]")

    pool = pool.reset_index(drop=True)
    n = len(pool)
    pa = pool["pa"].astype(float).to_numpy()
    war = pool["war"].astype(float).to_numpy()
    def_runs = (pool["def_runs"].astype(float).to_numpy()
                if "def_runs" in pool else np.full(n, np.nan))
    eligible = list(pool["eligible"])
    guessed = (np.zeros(n, dtype=bool) if "position_source" not in pool
               else pool["position_source"].isin(UNKNOWN_POSITION_SOURCES).to_numpy())
    credit_war, credit_def = war, def_runs      # what the team is credited with: ZiPS as is
    if def_weight < 1.0 or position_weight < 1.0:
        have_def = ~np.isnan(def_runs)
        primary = (pool["primary_position"] if "primary_position" in pool
                   else pd.Series([None] * n))
        pos_adj = np.array([POSITION_ADJ_RUNS.get(q, 0.0) if q else 0.0 for q in primary]) * pa / 700.0
        raw = np.nan_to_num(def_runs)
        kept = def_weight * (raw - pos_adj) + position_weight * pos_adj
        war = np.where(have_def, war - (raw - kept) / RUNS_PER_WIN, war)
        def_runs = np.where(have_def, kept, def_runs)
    war = np.where(guessed, war * unknown_war_multiplier, war)
    def_runs = np.where(guessed, def_runs * unknown_war_multiplier, def_runs)
    credit_war = np.where(guessed, credit_war * unknown_war_multiplier, credit_war)
    credit_def = np.where(guessed, credit_def * unknown_war_multiplier, credit_def)
    primary_adj = np.full(n, np.nan)
    if slot_position_credit and "primary_position" in pool:
        primary_adj = np.array([POSITION_ADJ_RUNS.get(q, np.nan) if q else np.nan
                                for q in pool["primary_position"]])

    def swap_runs(i: int, slot: str, weight: float) -> float:
        """Runs to add to player i's WAR when he fills `slot` instead of his own position."""
        if slot == "DH" or np.isnan(primary_adj[i]):
            return 0.0
        return weight * (POSITION_ADJ_RUNS[slot] - primary_adj[i]) * pa[i] / 700.0

    main_pos = list(pool["primary_position"]) if "primary_position" in pool else [None] * n

    def off_position(i: int, slot: str) -> bool:
        return not (slot == "DH" or main_pos[i] is None or pd.isna(main_pos[i])
                    or main_pos[i] == slot)

    def penalty_runs(i: int, slot: str) -> float:
        return off_position_penalty * pa[i] / 700.0 if off_position(i, slot) else 0.0

    def rank_rate(i: int, slot: str) -> float:
        rate = slot_war_rate(war[i], pa[i], def_runs[i], slot,
                             swap_runs(i, slot, position_weight) - penalty_runs(i, slot))
        return rate * off_position_multiplier if off_position(i, slot) and rate > 0 else rate

    blocked = guessed & (not unknown_can_start)
    player_cap = np.minimum(pa, MAX_PLAYER_PA)

    # Rank each slot's eligible players and turn the ranking into weights.
    plan = []                                   # per slot: (slot, players, weights, caps, rates)
    for slot in BATTER_SLOTS:
        rates = {i: rank_rate(i, slot)
                 for i in range(n) if slot in eligible[i] and pa[i] > 0}
        players = sorted((i for i, r in rates.items() if r > 0),
                         key=lambda i: (blocked[i], -rates[i], -pa[i], i))
        r = np.array([rates[i] for i in players])
        weights = _rank_weights(r, rank_decay, decay_per_war600)
        caps = np.append(np.full(len(players), max_slot_share * slot_pa[slot]), np.inf)
        plan.append((slot, players, weights, caps, r))

    # Home slot: where each player would get the most PA if nobody had a total limit.
    first_pass = np.zeros((len(BATTER_SLOTS), n))
    for s, (slot, players, weights, caps, _) in enumerate(plan):
        first_pass[s, players] = _waterfill(slot_pa[slot], weights, caps)[:-1]
    home = first_pass.argmax(axis=0)
    weight_at = []                                  # per slot: weights with the home preference
    for s, (_, players, weights, _, _) in enumerate(plan):
        mine = np.array([home[i] == s for i in players] + [True])
        weight_at.append(weights * np.where(mine, 1.0, secondary_weight))

    # Share every slot's PA, then pull back players who are over their own total limit. Only
    # the non-home shares are scaled back, so a multi-position player stays at his home slot.
    scale = np.ones(n)
    shares = np.zeros((len(BATTER_SLOTS), n))
    for _ in range(_MAX_ITER):
        shares[:] = 0.0
        for s, (slot, players, _, caps, _) in enumerate(plan):
            w = weight_at[s].copy()
            away = np.array([home[i] != s for i in players] + [False])
            w = np.where(away, w * np.append(scale[players], 1.0), w)
            got = _waterfill(slot_pa[slot], w, np.minimum(caps, np.append(player_cap[players], np.inf)))
            shares[s, players] = got[:-1]
        total = shares.sum(axis=0)
        ratio = np.divide(player_cap, total, out=np.ones(n), where=total > 0)
        active = (total > player_cap * (1 + _TOL)) | ((scale < 1) & (total < player_cap * (1 - _TOL)))
        if not active.any():
            break
        updated = np.where(active, np.minimum(1.0, scale * ratio), scale)
        if np.allclose(updated, scale, rtol=1e-9, atol=0):
            break
        scale = updated
    total = shares.sum(axis=0)
    over = total > player_cap * (1 + _TOL)
    if over.any():                              # not converged: hard-scale what is left
        shares[:, over] *= (player_cap[over] / total[over])

    rows = []
    for s, (slot, players, _, _, r) in enumerate(plan):
        order = {i: k for k, i in enumerate(players)}
        for i in players:
            if shares[s, i] > 1e-9:
                rows.append({"player": i, "slot": slot, "rank": order[i] + 1, "pa": shares[s, i],
                             "war": slot_war_rate(credit_war[i], pa[i], credit_def[i], slot,
                                                      swap_runs(i, slot, 1.0)) * shares[s, i]})
    allocations = pd.DataFrame(rows, columns=["player", "slot", "rank", "pa", "war"])

    players_out = pool.copy()
    players_out["slot"] = None
    players_out["role"] = "unused"
    players_out["allocated"] = 0.0
    players_out["scaled_war"] = 0.0
    if len(allocations):
        grouped = allocations.groupby("player").agg(allocated=("pa", "sum"),
                                                    scaled_war=("war", "sum"))
        players_out.loc[grouped.index, "allocated"] = grouped["allocated"]
        players_out.loc[grouped.index, "scaled_war"] = grouped["scaled_war"]
        biggest = allocations.sort_values("pa", ascending=False).drop_duplicates("player")
        players_out.loc[biggest["player"], "slot"] = biggest["slot"].to_numpy()
        players_out.loc[biggest["player"], "role"] = "backup"
        top = allocations.sort_values("pa", ascending=False).drop_duplicates("slot")
        players_out.loc[top["player"], "role"] = "starter"
        for _, row in top.sort_values("pa").iterrows():     # a starter's slot is the one he tops
            players_out.loc[row["player"], "slot"] = row["slot"]
    players_out["fraction"] = np.divide(players_out["allocated"], pa, out=np.zeros(n), where=pa > 0)
    allocations["player"] = allocations["player"].map(
        (lambda i: pool.loc[i, "mlbam_id"]) if "mlbam_id" in pool else (lambda i: i))
    return players_out, allocations


def depth_chart_by_team(
    pool: pd.DataFrame,
    group: str | list[str] = "team_id",
    **kwargs,
) -> pd.DataFrame:
    """Build a batting depth chart for every team (and season) in `group`.

    Returns the players frame for all teams, stacked, with the group columns kept.
    """
    parts = [build_batter_depth_chart(rows, **kwargs)[0] for _, rows in pool.groupby(group)]
    return pd.concat(parts, ignore_index=True) if parts else pool.iloc[0:0]


# ---------------------------------------------------------------------------------------
# Pitchers
# ---------------------------------------------------------------------------------------
def classify_pitcher_role(projected_starts: Iterable[float] | pd.Series,
                          min_starts: float = MIN_STARTS) -> np.ndarray:
    """"SP" if ZiPS projects at least `min_starts` starts, otherwise "RP".

    On 2023 to 2026 ZiPS files, a cutoff of 15 starts labelled 88% of pitchers who threw 30 or
    more innings correctly, found 92% of real starters and captured 93% of their innings. A
    top-five-by-starts rule captured only 55%, because teams really use about seven starters.
    """
    starts = np.asarray(list(projected_starts), dtype=float)
    return np.where(starts >= min_starts, "SP", "RP")


def build_pitcher_depth_chart(
    pitchers: pd.DataFrame,
    ip_budget: float = IP_BUDGET,
    starter_ip_share: float = STARTER_IP_SHARE,
    rotation_size: int = ROTATION_SIZE,
    sp_decay: float = SP_DECAY,
    rp_decay: float = RP_DECAY,
    min_starts: float = MIN_STARTS,
    min_rp_ip: float = MIN_RP_IP,
) -> pd.DataFrame:
    """Share one team's innings among its pitchers.

    `pitchers` needs ip, war and gs (projected starts). Returns the frame with `role` (SP, RP
    or unused), `allocated` (IP), `fraction` and `scaled_war`.
    """
    out = pitchers.reset_index(drop=True).copy()
    n = len(out)
    ip = out["ip"].astype(float).to_numpy()
    war = out["war"].astype(float).to_numpy()
    rate = np.divide(war, ip, out=np.zeros(n), where=ip > 0)
    is_sp = classify_pitcher_role(out["gs"], min_starts) == "SP"
    allocated = np.zeros(n)

    # Starters: the best `rotation_size` by WAR at a full-slot workload get that workload.
    sp_budget = ip_budget * starter_ip_share
    slot_ip = sp_budget / rotation_size
    sp_idx = [i for i in range(n) if is_sp[i] and ip[i] > 0 and rate[i] > 0]
    sp_idx.sort(key=lambda i: -(rate[i] * min(ip[i], slot_ip)))
    for i in sp_idx[:rotation_size]:
        allocated[i] = min(ip[i], slot_ip)
    # Whatever the rotation could not absorb (a starter projected for fewer innings than a full
    # slot) goes to the next starters, with a decay, within each pitcher's projected innings.
    rest = sorted(sp_idx[rotation_size:], key=lambda i: (-rate[i], -ip[i]))
    ordered = sp_idx[:rotation_size] + rest
    shortfall = sp_budget - allocated.sum()
    if shortfall > 0 and ordered:
        room = np.array([ip[i] - allocated[i] for i in ordered])
        for i, amount in zip(ordered, _spread_bench(shortfall, room, sp_decay), strict=True):
            allocated[i] += amount

    # Relievers: every pitcher not labelled a starter.
    rp_idx = [i for i in range(n) if not is_sp[i] and ip[i] >= min_rp_ip and rate[i] > 0]
    rp_idx.sort(key=lambda i: (-rate[i], -ip[i]))
    rp_budget = ip_budget - sp_budget
    shares = _spread_bench(rp_budget, np.array([ip[i] for i in rp_idx]), rp_decay)
    for i, amount in zip(rp_idx, shares, strict=True):
        allocated[i] += amount

    out["role"] = np.where(allocated > 0, np.where(is_sp, "SP", "RP"), "unused")
    out["allocated"] = allocated
    out["fraction"] = np.divide(allocated, ip, out=np.zeros(n), where=ip > 0)
    out["scaled_war"] = rate * allocated
    return out


def team_war(players: pd.DataFrame, group: str | list[str] = "team_id") -> pd.Series:
    """Sum of scaled WAR per team from a depth chart frame."""
    return players.groupby(group)["scaled_war"].sum()
