"""Checks for the PA-allocation optimizer (defense by position, fatigue, the linear program)."""

import numpy as np
import pandas as pd
import pytest

from bucco.models.depth_chart import POSITION_ADJ_RUNS, SLOT_PA
from bucco.models.lineup_optimizer import (
    POSITIONS,
    RELATIVE_FATIGUE_RUNS,
    SELECTION_BASE,
    TIE_BREAK,
    SwitchMatrix,
    defense_at,
    natives_from_adjustment,
    natives_from_games,
    offense_rate,
    offense_segments,
    optimize_team,
    war_scale,
)

REP = 20.0 / 600   # replacement runs per PA
RPW = 10.0


# ---- defense ----------------------------------------------------------------------------
# A small additive matrix: change(p -> q) = h[p] - h[q] (harder positions cost fielding runs).
H = {"1B": 0.0, "2B": 6.0, "3B": 4.0, "SS": 10.0, "LF": 5.0, "CF": 13.0, "RF": 5.0}
SWITCH = SwitchMatrix({(p, q): H[p] - H[q] for p in H for q in H if p != q}, H, adj_floor=False,
                      rarity={})
FLOORED = SwitchMatrix(SWITCH.delta, H, adj_floor=True, rarity={})


def test_the_rarity_penalty_adds_to_selection_only_for_the_named_move():
    rare = SwitchMatrix(SWITCH.delta, H, adj_floor=False, rarity={("LF", "1B"): 6.0})
    assert rare.selection("LF", "1B") == pytest.approx(SWITCH.selection("LF", "1B") + 6.0)
    assert rare.selection("1B", "LF") == pytest.approx(SWITCH.selection("1B", "LF"))
    # Only at positions he has not played: an outfielder who played 1B keeps his 1B value.
    played = defense_at(-7.5, "LF", ("LF", "1B"), rare)["1B"]
    assert played == pytest.approx(defense_at(-7.5, "LF", ("LF", "1B"), SWITCH)["1B"])
    assert defense_at(-7.5, "LF", ("LF",), rare)["1B"] == pytest.approx(
        defense_at(-7.5, "LF", ("LF",), SWITCH)["1B"] - 6.0)


def test_the_adjustment_floor_stops_moves_up_the_spectrum_adding_defense():
    # OAA alone: LF -> 3B costs 1 fielding run but gains 10 of positional adjustment.
    assert SWITCH.change("LF", "3B") == pytest.approx(1.0)
    assert FLOORED.change("LF", "3B") == pytest.approx(-10.0)
    # Where OAA is stricter, or the move is down the spectrum, OAA stands.
    assert FLOORED.change("1B", "CF") == pytest.approx(-15.0)       # adj gap stricter here
    assert FLOORED.change("CF", "LF") == pytest.approx(8.0)          # OAA stricter than +10
    assert FLOORED.change("SS", "1B") == pytest.approx(10.0)
    # Total defense never rises moving up from an average corner outfielder.
    lf = defense_at(POSITION_ADJ_RUNS["LF"], "LF", ("LF",), FLOORED)
    assert max(lf[q] for q in ("2B", "3B", "SS", "CF")) < lf["LF"]


def _defense(def700, anchor, natives):
    return defense_at(def700, anchor, natives, SWITCH)


def _fielding_after_move(native, target):
    """Fielding runs per 700 PA, relative to an average player at `target`, of an average
    player at `native` moved there (a position he has not played)."""
    value = _defense(POSITION_ADJ_RUNS[native], native, (native,))[target]
    return value + TIE_BREAK - POSITION_ADJ_RUNS[target]


def test_fielding_change_follows_the_fit_plus_the_selection_penalty():
    assert _fielding_after_move("SS", "1B") == pytest.approx(10.0 - SELECTION_BASE)
    up = _fielding_after_move("1B", "CF")
    assert up < _fielding_after_move("LF", "CF") < 0
    assert up == pytest.approx(-13.0 - SWITCH.selection("1B", "CF"))
    assert SWITCH.selection("1B", "CF") > SWITCH.selection("CF", "1B") == SELECTION_BASE


def test_a_position_he_played_has_no_selection_penalty():
    played = _defense(-12.5, "1B", ("1B", "RF"))["RF"] + TIE_BREAK
    unplayed = _defense(-12.5, "1B", ("1B",))["RF"] + TIE_BREAK
    assert played == pytest.approx(0.0 - 5.0 + POSITION_ADJ_RUNS["RF"])
    assert unplayed == pytest.approx(played - SWITCH.selection("1B", "RF"))


def test_only_catchers_catch_and_everyone_can_dh():
    infielder = _defense(0.0, "SS", ("SS",))
    assert "C" not in infielder
    assert infielder["DH"] == POSITION_ADJ_RUNS["DH"]
    catcher = _defense(10.0, "C", ("C",))
    assert catcher["C"] == 10.0
    assert catcher["DH"] == POSITION_ADJ_RUNS["DH"]


def test_projection_defense_is_used_as_is_at_the_main_position():
    d = _defense(-8.0, "1B", ("1B",))
    assert d["1B"] == -8.0
    assert d["CF"] - POSITION_ADJ_RUNS["CF"] < d["LF"] - POSITION_ADJ_RUNS["LF"]


def test_catchers_keep_no_catching_value_elsewhere():
    elite = _defense(25.0, "C", ("C",))
    poor = _defense(-5.0, "C", ("C",))
    assert elite["1B"] == poor["1B"] < POSITION_ADJ_RUNS["1B"]


def test_positions_from_games_and_from_the_projection():
    assert natives_from_games({"SS": 120, "2B": 25, "3B": 5}) == ("SS", ("2B", "SS"))
    assert natives_from_games({"DH": 100}) == (None, ("DH",))
    assert natives_from_games({}) == (None, ())
    assert natives_from_adjustment(12.0) == ("C",)
    assert natives_from_adjustment(-12.0) == ("1B",)


# ---- fatigue ---------------------------------------------------------------------------
def test_rate_matches_the_projection_at_its_own_pa_and_falls_with_more():
    assert offense_rate(0.02, 550, 550) == pytest.approx(0.02)
    assert offense_rate(0.02, 550, 300) > 0.02 > offense_rate(0.02, 550, 700)


def test_marginal_runs_decrease_so_the_steps_fill_in_order():
    steps = offense_segments(0.02, 550)
    assert np.all(np.diff(steps) < 0)


# ---- the optimizer ---------------------------------------------------------------------
def _player(i, off600, def700, anchor, natives, proj_pa=600):
    d = _defense(def700, anchor, natives)
    return {"mlbam_id": i, "player_name": f"p{i}", "proj_pa": proj_pa, "o_rate": off600 / 600,
            **{f"def_{q}": d.get(q, np.nan) for q in POSITIONS}}


def _team(extra=()):
    base = [_player(1, 0, 10, "C", ("C",)), _player(2, 0, -12.5, "1B", ("1B",)),
            _player(3, 0, 2.5, "2B", ("2B",)), _player(4, 0, 2.5, "3B", ("3B",)),
            _player(5, 0, 7.5, "SS", ("SS",)), _player(6, 0, -7.5, "LF", ("LF",)),
            _player(7, 0, 2.5, "CF", ("CF",)), _player(8, 0, -7.5, "RF", ("RF",))]
    return pd.DataFrame(base + list(extra))


def test_every_position_is_filled_exactly():
    alloc = optimize_team(_team(), REP, RPW)
    filled = alloc.groupby("position")["pa"].sum()
    for q in POSITIONS:
        assert filled[q] == pytest.approx(SLOT_PA[q])


def test_a_better_shortstop_takes_most_of_the_time():
    star = _player(9, 30, 12, "SS", ("SS",))
    alloc = optimize_team(_team([star]), REP, RPW)
    ss = alloc[alloc["position"] == "SS"].set_index("mlbam_id")["pa"]
    assert ss.get(9, 0) > ss.get(5, 0)


def test_a_capped_star_plays_only_up_to_his_cap_and_his_backup_gets_the_rest():
    star = _player(9, 30, 12, "SS", ("SS",))
    free = optimize_team(_team([star]), REP, RPW)
    capped = optimize_team(_team([star | {"pa_cap": 350.0}]), REP, RPW)
    assert free.loc[free["mlbam_id"] == 9, "pa"].sum() > 350
    assert capped.loc[capped["mlbam_id"] == 9, "pa"].sum() == pytest.approx(350.0)
    ss = capped[capped["position"] == "SS"]
    assert ss["pa"].sum() == pytest.approx(SLOT_PA["SS"])     # still filled, by others


def test_replacement_level_fills_what_nobody_can_play_well():
    alloc = optimize_team(_team(), REP, RPW)
    dh = alloc[alloc["position"] == "DH"]
    # eight average hitters already play the field; a ninth spot goes partly to replacement
    assert (dh["mlbam_id"] == -1).any()
    assert alloc.loc[alloc["mlbam_id"] == -1, "war"].sum() == 0


def test_war_scale_recovers_runs_per_win_and_replacement():
    rng = np.random.default_rng(0)
    b = pd.DataFrame({"plate_appearances": rng.uniform(100, 650, 300),
                      "off_runs": rng.normal(0, 10, 300), "def_runs": rng.normal(0, 5, 300)})
    b["war"] = (b["off_runs"] + b["def_runs"] + b["plate_appearances"] * REP) / 9.8
    rpw, rep = war_scale(b)
    assert rpw == pytest.approx(9.8)
    assert rep == pytest.approx(REP)


def test_catchers_and_dh_only_players_move_like_first_basemen():
    catcher = _defense(10.0, "C", ("C",))
    first = _defense(POSITION_ADJ_RUNS["1B"], "1B", ("1B",))
    dh_only = _defense(0.0, None, ("DH",))
    for q in ("CF", "SS", "LF"):
        assert catcher[q] == pytest.approx(first[q])     # an average first baseman
        assert dh_only[q] < catcher[q]                    # a below-average one
    assert catcher["CF"] < _defense(POSITION_ADJ_RUNS["LF"], "LF", ("LF",))["CF"]


# ---- relative fatigue --------------------------------------------------------------------
def test_relative_rate_matches_the_projection_and_scales_with_projected_pa():
    o = 10.0 / 600
    assert offense_rate(o, 50.0, 50.0, relative=True) == pytest.approx(o)
    # a player projected for 50 PA loses as much at 100 as one projected for 600 does at 1,200
    assert offense_rate(o, 50.0, 100.0, relative=True) == \
        pytest.approx(offense_rate(o, 600.0, 1200.0, relative=True))
    steps = offense_segments(o, 50.0, relative=True)
    assert np.all(np.diff(steps) <= 1e-12)


def test_a_small_projection_holds_a_good_hitter_back_only_on_the_relative_curve():
    prospect = _player(20, 20.0, 0.0, "SS", ("SS",), proj_pa=40)       # good, projected 40 PA
    team = _team([prospect])

    def his_pa(alloc):
        return alloc.loc[alloc["mlbam_id"] == 20, "pa"].sum()

    absolute = optimize_team(team, REP, RPW)
    relative = optimize_team(team, REP, RPW, relative=True, fatigue=RELATIVE_FATIGUE_RUNS)
    assert his_pa(absolute) > 300
    assert his_pa(relative) < 150
