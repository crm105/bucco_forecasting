"""Checks for the depth-chart logic (eligibility, slot filling, pitchers)."""

import numpy as np
import pandas as pd
import pytest

from bucco.models.depth_chart import (
    BATTER_SLOTS,
    DEF_WEIGHT,
    DEFAULT_UNKNOWN_SLOTS,
    OFF_POSITION_MULTIPLIER,
    SLOT_PA,
    UNKNOWN_WAR_MULTIPLIER,
    _rank_weights,
    _waterfill,
    bsr_percentiles,
    build_batter_depth_chart,
    build_batter_pool,
    build_pitcher_depth_chart,
    classify_pitcher_role,
    eligible_slots,
    impute_listed_positions,
    slot_war_rate,
)


# ---- eligibility -----------------------------------------------------------------------
def test_unknown_position_defaults_to_outfield_and_dh():
    slots, source = eligible_slots(None)
    assert slots == frozenset(DEFAULT_UNKNOWN_SLOTS) == frozenset({"LF", "CF", "RF", "DH"})
    assert source == "default_outfield"
    assert eligible_slots({})[1] == "default_outfield"


def test_known_player_uses_positions_with_enough_games():
    slots, source = eligible_slots({"SS": 120, "2B": 25, "3B": 5})
    assert source == "prior_season"
    assert slots == {"SS", "2B", "1B", "DH"}   # 3B (5 games) is not enough, but SS/2B flex to 1B


def test_shortstop_can_also_play_second_base_first_base_and_dh():
    assert eligible_slots({"SS": 140})[0] == {"SS", "2B", "1B", "DH"}


def test_third_baseman_can_also_play_first_base_and_dh():
    assert eligible_slots({"3B": 140})[0] == {"3B", "1B", "DH"}


def test_every_non_first_base_infielder_can_play_first_base():
    for position in ("2B", "3B", "SS"):
        assert "1B" in eligible_slots({position: 100})[0]


def test_first_baseman_and_catcher_get_nothing_extra():
    assert eligible_slots({"1B": 140})[0] == {"1B", "DH"}
    assert eligible_slots({"C": 140})[0] == {"C", "DH"}


def test_second_baseman_does_not_become_a_shortstop():
    assert eligible_slots({"2B": 140})[0] == {"2B", "1B", "DH"}


def test_main_position_always_counts_even_with_few_games():
    slots, _ = eligible_slots({"C": 12})
    assert slots == {"C", "DH"}                  # a catcher does not become a first baseman


def test_anyone_listed_in_the_outfield_can_play_the_whole_outfield():
    for position in ("LF", "CF", "RF"):
        assert eligible_slots({position: 100})[0] == {"LF", "CF", "RF", "DH"}


def test_flex_comes_from_every_listed_position():
    slots, _ = eligible_slots({"3B": 100, "LF": 30})
    assert slots == {"3B", "1B", "LF", "CF", "RF", "DH"}


def test_flex_rules_can_be_overridden():
    assert eligible_slots({"SS": 100}, flex={})[0] == {"SS", "DH"}
    assert eligible_slots({"1B": 100}, flex={"1B": ("3B",)})[0] == {"1B", "3B", "DH"}


def test_dh_only_player_is_not_given_a_field_position():
    slots, source = eligible_slots({"DH": 140})
    assert slots == {"DH"} and source == "prior_season"


def test_pitcher_only_history_can_only_dh():
    assert eligible_slots({"P": 30})[0] == {"DH"}


# ---- DH valuation ----------------------------------------------------------------------
def test_dh_value_removes_defense_and_applies_dh_adjustment():
    # 600 PA, 3.0 WAR, of which 10 runs (1.0 WAR) is defense
    fielding = slot_war_rate(3.0, 600, 10.0, "SS")
    dh = slot_war_rate(3.0, 600, 10.0, "DH")
    assert fielding == pytest.approx(3.0 / 600)
    assert dh == pytest.approx((3.0 - 1.0) / 600 - 17.5 / 700 / 10)
    assert dh < fielding


def test_dh_value_without_defense_data_falls_back_to_the_ordinary_rate():
    assert slot_war_rate(3.0, 600, None, "DH") == pytest.approx(3.0 / 600)
    assert slot_war_rate(3.0, 600, np.nan, "DH") == pytest.approx(3.0 / 600)


# ---- sharing a slot's PA ---------------------------------------------------------------
def _player(i, pa, war, eligible, def_runs=0.0):
    return {"mlbam_id": i, "player_name": f"p{i}", "pa": pa, "war": war,
            "def_runs": def_runs, "eligible": frozenset(eligible)}


def _one_slot(rates_per600, slot="1B", pa=700):
    """Players eligible at one slot only, with the given WAR per 600 PA."""
    return pd.DataFrame([_player(i + 1, pa, r * pa / 600, {slot})
                         for i, r in enumerate(rates_per600)])


def _alloc(players, slot_name="1B"):
    return players.set_index("mlbam_id")["allocated"]


def _full_team(extra=()):
    """One solid player per slot, plus extras."""
    rows = [_player(i + 1, 600, 3.0, {slot, "DH"}) for i, slot in enumerate(BATTER_SLOTS[:-1])]
    rows.append(_player(9, 600, 3.0, {"DH"}))
    rows.extend(extra)
    return pd.DataFrame(rows)


def test_rank_weights_apply_rank_decay_and_rate_gap():
    # rates in WAR per PA; a 3.0 WAR/600 PA gap with 2.0 decay per WAR600 is exp(-6)
    w = _rank_weights(np.array([0.010, 0.005]), rank_decay=0.5, decay_per_war600=2.0)
    assert w[0] == 1.0
    assert w[1] == pytest.approx(0.5 * np.exp(-2.0 * 0.005 * 600))
    assert w[2] == pytest.approx(w[1] * 0.5 * np.exp(-2.0 * 0.005 * 600))  # down to replacement
    equal = _rank_weights(np.array([0.01, 0.01]), rank_decay=0.5, decay_per_war600=2.0)
    assert equal[1] == pytest.approx(0.5)               # no gap: rank decay alone


def test_waterfill_respects_caps_and_reshares_the_excess():
    out = _waterfill(100.0, np.array([3.0, 1.0, 1.0]), np.array([40.0, np.inf, np.inf]))
    assert out[0] == pytest.approx(40.0)                # held at its cap
    assert out[1] == pytest.approx(30.0) and out[2] == pytest.approx(30.0)
    assert _waterfill(100.0, np.array([1.0]), np.array([30.0])).sum() == pytest.approx(30.0)


def test_slot_pa_is_never_over_budget_and_players_never_over_projection():
    players, allocations = build_batter_depth_chart(_full_team())
    assert (players["allocated"] <= players["pa"] + 1e-3).all()
    for slot, rows in allocations.groupby("slot"):
        assert rows["pa"].sum() <= SLOT_PA[slot] + 1e-6


def test_equal_players_split_the_slot_by_rank_decay_alone():
    team = _one_slot([2.0, 2.0])
    players, _ = build_batter_depth_chart(team, rank_decay=0.5, decay_per_war600=0.0,
                                          max_slot_share=1.0)
    got = _alloc(players)
    # weights 1, 0.5 and replacement 0.25: shares 4/7, 2/7 and 1/7 of 700 PA
    assert got[1] == pytest.approx(700 * 4 / 7)
    assert got[2] == pytest.approx(700 * 2 / 7)


def test_ranking_follows_war_per_pa_at_the_slot():
    _, allocations = build_batter_depth_chart(_one_slot([1.0, 3.0, 2.0]))
    ranks = allocations.set_index("player")["rank"]
    assert ranks[2] == 1 and ranks[3] == 2 and ranks[1] == 3


def test_a_big_gap_gives_the_top_player_more_than_close_backups():
    big_gap = _one_slot([4.0, 0.5], slot="1B")
    close = _one_slot([4.0, 3.9], slot="1B")
    kw = {"rank_decay": 0.5, "decay_per_war600": 1.0, "max_slot_share": 1.0}
    gap_top = _alloc(build_batter_depth_chart(big_gap, **kw)[0])[1]
    close_top = _alloc(build_batter_depth_chart(close, **kw)[0])[1]
    assert gap_top > close_top


def test_without_gap_decay_a_big_gap_does_not_matter():
    kw = {"rank_decay": 0.5, "decay_per_war600": 0.0, "max_slot_share": 1.0}
    big_gap = _alloc(build_batter_depth_chart(_one_slot([4.0, 0.5]), **kw)[0])[1]
    close = _alloc(build_batter_depth_chart(_one_slot([4.0, 3.9]), **kw)[0])[1]
    assert big_gap == pytest.approx(close)


def test_no_one_plays_more_than_max_slot_share_of_a_slot():
    players, _ = build_batter_depth_chart(_one_slot([6.0, 0.2]), max_slot_share=0.8)
    assert _alloc(players)[1] <= 0.8 * 700 + 1e-6


def test_replacement_level_takes_pa_nobody_good_can_absorb():
    players, allocations = build_batter_depth_chart(_one_slot([1.0]))
    assert allocations["pa"].sum() < 700                 # the rest is replacement, worth 0 WAR
    assert players["scaled_war"].sum() == pytest.approx(allocations["war"].sum())


def test_below_replacement_players_get_no_pa():
    team = _one_slot([2.0, -1.0])
    players, _ = build_batter_depth_chart(team)
    assert _alloc(players)[2] == 0
    assert players.loc[players["mlbam_id"] == 2, "role"].iloc[0] == "unused"


def test_a_slot_with_no_eligible_player_is_left_to_replacement_level():
    team = pd.DataFrame([_player(i, 600, 3.0, {"LF", "CF", "RF", "DH"}) for i in range(1, 4)])
    _, allocations = build_batter_depth_chart(team)
    assert "C" not in set(allocations["slot"])


def test_a_multi_position_star_is_concentrated_at_one_slot_and_capped():
    star = _player(50, 600, 6.0, {"SS", "2B", "3B", "1B", "DH"})
    team = _full_team([star])
    players, allocations = build_batter_depth_chart(team)
    mine = allocations[allocations["player"] == 50]
    assert mine["pa"].sum() <= 600 + 1e-3                # never more than his own projection
    assert mine["pa"].max() >= 0.7 * mine["pa"].sum()    # most of it at his home slot
    row = players.loc[players["mlbam_id"] == 50].iloc[0]
    assert row["slot"] == mine.sort_values("pa").iloc[-1]["slot"]


def test_secondary_weight_lowers_time_away_from_the_home_slot():
    # a star slightly better than the incumbents at both slots, with room under his own total
    star = _player(50, 700, 3.0 * 700 / 600, {"SS", "2B"})
    team = pd.DataFrame([star, _player(2, 700, 2.5 * 700 / 600, {"SS"}),
                         _player(3, 700, 2.5 * 700 / 600, {"2B"})])

    def away(weight):
        _, al = build_batter_depth_chart(team, secondary_weight=weight)
        mine = al[al["player"] == 50].sort_values("pa")
        return mine["pa"].iloc[0] if len(mine) > 1 else 0.0

    assert 0 < away(0.1) < away(1.0)


def test_cleanup_hands_freed_pa_to_the_next_players():
    # the star can fill both slots but only has 300 PA to give
    star = _player(1, 300, 6.0, {"1B", "2B"})
    team = pd.DataFrame([star, _player(2, 700, 2.0, {"1B"}), _player(3, 700, 2.0, {"2B"})])
    players, allocations = build_batter_depth_chart(team)
    got = _alloc(players)
    assert got[1] <= 300 + 1e-3
    assert got[2] > 0 and got[3] > 0
    for slot in ("1B", "2B"):
        assert allocations[allocations["slot"] == slot]["pa"].sum() > 0.5 * 700


def test_roles_starter_is_the_top_player_at_a_slot():
    players, _ = build_batter_depth_chart(_one_slot([3.0, 1.0]))
    assert players.loc[players["mlbam_id"] == 1, "role"].iloc[0] == "starter"
    assert players.loc[players["mlbam_id"] == 1, "slot"].iloc[0] == "1B"
    assert players.loc[players["mlbam_id"] == 2, "role"].iloc[0] == "backup"


def test_a_better_eligible_player_takes_the_slot():
    better = _player(50, 600, 5.0, {"SS", "DH"})
    _, allocations = build_batter_depth_chart(_full_team([better]))
    top_at_ss = allocations[(allocations["slot"] == "SS") & (allocations["rank"] == 1)]
    assert top_at_ss["player"].iloc[0] == 50


def test_scaled_war_is_rate_times_allocated_pa():
    players, _ = build_batter_depth_chart(_one_slot([3.0]))
    row = players.iloc[0]
    assert row["scaled_war"] == pytest.approx(row["allocated"] * row["war"] / row["pa"])


def test_unknown_position_player_can_start_in_the_outfield():
    star = _player(80, 600, 6.0, DEFAULT_UNKNOWN_SLOTS)
    players, _ = build_batter_depth_chart(_full_team([star]))
    assert players.loc[players["mlbam_id"] == 80, "slot"].iloc[0] in {"LF", "CF", "RF", "DH"}


def test_bad_arguments_are_rejected():
    for kwargs in ({"rank_decay": 0}, {"rank_decay": 1.0}, {"decay_per_war600": -1},
                   {"secondary_weight": 0}, {"max_slot_share": 1.5}):
        with pytest.raises(ValueError):
            build_batter_depth_chart(_full_team(), **kwargs)


def test_build_batter_pool_attaches_eligibility():
    batters = pd.DataFrame({"mlbam_id": [1, 2], "pa": [500, 400], "war": [2.0, 1.0]})
    games = pd.DataFrame({"mlbam_id": [1, 1], "position": ["SS", "2B"], "games": [100, 40]})
    pool = build_batter_pool(batters, games)
    assert pool.loc[0, "eligible"] == {"SS", "2B", "1B", "DH"}
    assert pool.loc[0, "position_source"] == "prior_season"
    assert pool.loc[1, "eligible"] == frozenset(DEFAULT_UNKNOWN_SLOTS)
    assert pool.loc[1, "position_source"] == "default_outfield"


# ---- pitchers --------------------------------------------------------------------------
def test_pitcher_role_uses_projected_starts():
    roles = classify_pitcher_role([30, 15, 14, 0])
    assert list(roles) == ["SP", "SP", "RP", "RP"]
    assert list(classify_pitcher_role([10, 20], min_starts=10)) == ["SP", "SP"]


def _staff(sp=7, rp=12):
    rows = [{"ip": 180, "war": 3.0, "gs": 30} for _ in range(sp)]
    rows += [{"ip": 60, "war": 0.6, "gs": 0} for _ in range(rp)]
    return pd.DataFrame(rows)


def test_pitcher_innings_add_to_the_budget_and_split_by_role():
    out = build_pitcher_depth_chart(_staff(), ip_budget=1500, starter_ip_share=0.57)
    assert out["allocated"].sum() == pytest.approx(1500)
    assert out[out["role"] == "SP"]["allocated"].sum() == pytest.approx(0.57 * 1500)
    assert (out["allocated"] <= out["ip"] + 1e-9).all()


def test_five_best_starters_take_full_slots():
    staff = _staff(sp=7)
    staff.loc[0, "war"] = 6.0
    out = build_pitcher_depth_chart(staff)
    top5 = out[out["role"] == "SP"].sort_values("allocated", ascending=False).head(5)
    assert top5["allocated"].min() == pytest.approx(0.57 * 1500 / 5)
    assert out.loc[0, "allocated"] == pytest.approx(0.57 * 1500 / 5)


def test_thin_staff_falls_short_of_the_budget_instead_of_over_using_pitchers():
    out = build_pitcher_depth_chart(_staff(sp=3, rp=3))
    assert (out["allocated"] <= out["ip"] + 1e-9).all()
    assert out["allocated"].sum() < 1500


def test_negative_war_pitchers_are_left_out():
    staff = _staff()
    staff.loc[8, ["war"]] = -1.0     # a reliever
    out = build_pitcher_depth_chart(staff)
    assert out.loc[8, "allocated"] == 0 and out.loc[8, "role"] == "unused"


# ---- imputing a position from baserunning ---------------------------------------------
def test_bsr_bins_give_the_requested_positions():
    assert impute_listed_positions(0.00) == ("1B",)
    assert impute_listed_positions(0.19) == ("1B",)
    assert impute_listed_positions(0.20) == ("3B", "LF", "RF")
    assert impute_listed_positions(0.39) == ("3B", "LF", "RF")
    assert impute_listed_positions(0.40) == ("2B",)
    assert impute_listed_positions(0.59) == ("2B",)
    assert impute_listed_positions(0.60) == ("CF", "SS")
    assert impute_listed_positions(1.00) == ("CF", "SS")


def test_slowest_fifth_is_limited_to_first_base_and_dh():
    slots, source = eligible_slots(None, bsr_percentile=0.05)
    assert slots == {"1B", "DH"} and source == "imputed_bsr"


def test_second_fifth_is_third_base_or_a_corner_with_flex():
    slots, _ = eligible_slots({}, bsr_percentile=0.3)
    assert slots == {"3B", "1B", "LF", "CF", "RF", "DH"}


def test_middle_fifth_is_second_base_with_first_base_flex():
    assert eligible_slots(None, bsr_percentile=0.5)[0] == {"2B", "1B", "DH"}


def test_fastest_players_are_center_field_or_shortstop_with_flex():
    slots, _ = eligible_slots(None, bsr_percentile=0.9)
    assert slots == {"CF", "LF", "RF", "SS", "2B", "1B", "DH"}


def test_missing_bsr_falls_back_to_the_outfield_default():
    for missing in (None, np.nan):
        slots, source = eligible_slots(None, bsr_percentile=missing)
        assert slots == frozenset(DEFAULT_UNKNOWN_SLOTS) and source == "default_outfield"


def test_bsr_is_ignored_when_the_position_is_known():
    slots, source = eligible_slots({"C": 100}, bsr_percentile=0.95)
    assert slots == {"C", "DH"} and source == "prior_season"


def test_bsr_percentiles_use_runs_per_600_pa_against_regulars():
    batters = pd.DataFrame({
        "pa": [600, 600, 600, 600, 600, 100, 300],
        "bsr": [-4.0, -2.0, 0.0, 2.0, 4.0, 4.0, 1.5],
    })
    pct = bsr_percentiles(batters)
    # the 100-PA player is 24 runs per 600 PA, above every regular (his rate, not his total)
    assert pct.iloc[5] == pytest.approx(1.0)
    assert pct.iloc[0] < pct.iloc[1] < pct.iloc[2] < pct.iloc[3] < pct.iloc[4]
    assert pct.between(0, 1).all()
    # the reference is batters with 200+ PA only: the 100-PA player does not move anyone
    assert pct.iloc[2] == pytest.approx(bsr_percentiles(batters.iloc[[0, 1, 2, 3, 4, 6]]).iloc[2],
                                        abs=0.2)


def test_bsr_percentiles_handle_no_playing_time_and_empty_reference():
    batters = pd.DataFrame({"pa": [0, 50], "bsr": [1.0, 1.0]})
    assert bsr_percentiles(batters).isna().all()


def test_build_pool_uses_bsr_pct_only_for_players_with_no_prior_season():
    batters = pd.DataFrame({"mlbam_id": [1, 2, 3], "pa": [500, 400, 300], "war": [2, 1, 1],
                            "bsr_pct": [0.95, 0.05, np.nan]})
    games = pd.DataFrame({"mlbam_id": [1], "position": ["C"], "games": [100]})
    pool = build_batter_pool(batters, games)
    assert pool.loc[0, "eligible"] == {"C", "DH"}
    assert pool.loc[1, "eligible"] == {"1B", "DH"} and pool.loc[1, "position_source"] == "imputed_bsr"
    assert pool.loc[2, "position_source"] == "default_outfield"


def _guess_team(source, war=3.0):
    """A guessed-position player and a known one, both able to play only first base."""
    pool = pd.DataFrame([_player(80, 600, war, {"1B"}), _player(81, 600, 2.0, {"1B"})])
    pool["position_source"] = [source, "prior_season"]
    return pool


def test_unknown_can_start_false_ranks_guessed_players_below_known_ones():
    pool = _guess_team("imputed_bsr")
    free, _ = build_batter_depth_chart(pool, unknown_can_start=True, unknown_war_multiplier=1.0)
    limited, _ = build_batter_depth_chart(pool, unknown_can_start=False,
                                          unknown_war_multiplier=1.0)
    assert free.loc[free["mlbam_id"] == 80, "role"].iloc[0] == "starter"
    assert limited.loc[limited["mlbam_id"] == 80, "role"].iloc[0] == "backup"
    assert limited.loc[limited["mlbam_id"] == 81, "role"].iloc[0] == "starter"


# ---- trimming the WAR of guessed-position players --------------------------------------
def test_default_unknown_multiplier_is_one_tenth():
    assert UNKNOWN_WAR_MULTIPLIER == 0.1


def test_multiplier_trims_guessed_players_war_and_leaves_known_players_alone():
    pool = _guess_team("imputed_bsr")
    full, _ = build_batter_depth_chart(pool, unknown_war_multiplier=1.0)
    half, _ = build_batter_depth_chart(pool, unknown_war_multiplier=0.5)
    known_full = full.loc[full["mlbam_id"] == 81, "scaled_war"].iloc[0]
    known_half = half.loc[half["mlbam_id"] == 81, "scaled_war"].iloc[0]
    assert known_half >= known_full                       # never trimmed (he moves up the ranking)
    guess_full = full.loc[full["mlbam_id"] == 80, "scaled_war"].iloc[0]
    guess_half = half.loc[half["mlbam_id"] == 80, "scaled_war"].iloc[0]
    assert guess_half < guess_full


def test_multiplier_applies_to_default_outfield_players_too():
    pool = _guess_team("default_outfield")
    zero, _ = build_batter_depth_chart(pool, unknown_war_multiplier=0.0)
    assert zero.loc[zero["mlbam_id"] == 80, "scaled_war"].iloc[0] == 0.0


def test_a_big_enough_trim_changes_who_ranks_first():
    pool = _guess_team("imputed_bsr", war=3.6)            # a little better than the known 3.0
    pool.loc[pool["mlbam_id"] == 81, "war"] = 3.0
    untrimmed, _ = build_batter_depth_chart(pool, unknown_war_multiplier=1.0)
    trimmed, _ = build_batter_depth_chart(pool, unknown_war_multiplier=0.75)
    assert untrimmed.loc[untrimmed["mlbam_id"] == 80, "role"].iloc[0] == "starter"
    assert trimmed.loc[trimmed["mlbam_id"] == 80, "role"].iloc[0] == "backup"


def test_multiplier_must_be_between_zero_and_one():
    with pytest.raises(ValueError):
        build_batter_depth_chart(_full_team(), unknown_war_multiplier=1.2)
    with pytest.raises(ValueError):
        build_batter_depth_chart(_full_team(), unknown_war_multiplier=-0.1)


def test_def_weight_changes_ranking_but_not_credited_war():
    # A glove-first player (high WAR from defense) and a bat-first player share one slot.
    pool = pd.DataFrame({
        "mlbam_id": [1, 2], "pa": [600.0, 600.0], "war": [3.0, 2.6],
        "def_runs": [20.0, -5.0], "eligible": [frozenset({"RF"})] * 2,
        "position_source": ["prior_season"] * 2,
    })
    full, _ = build_batter_depth_chart(pool, def_weight=1.0, position_weight=1.0)
    shrunk, _ = build_batter_depth_chart(pool, def_weight=0.0, position_weight=0.0)
    assert full["allocated"].iloc[0] > full["allocated"].iloc[1]
    assert shrunk["allocated"].iloc[1] > shrunk["allocated"].iloc[0]
    # credited WAR per PA played is the ZiPS rate either way
    for df in (full, shrunk):
        got = df["scaled_war"] / df["allocated"]
        assert got.iloc[0] == pytest.approx(3.0 / 600.0, rel=1e-6)
        assert got.iloc[1] == pytest.approx(2.6 / 600.0, rel=1e-6)


def test_def_weight_default_and_bounds():
    assert DEF_WEIGHT == 0.7
    pool = pd.DataFrame({"mlbam_id": [1], "pa": [600.0], "war": [3.0], "def_runs": [10.0],
                         "eligible": [frozenset({"RF"})]})
    with pytest.raises(ValueError):
        build_batter_depth_chart(pool, def_weight=1.5)


def test_position_weight_splits_position_from_fielding():
    # Same total Def, but one is a shortstop (7.5 runs of it is position credit) and one is not.
    pool = pd.DataFrame({
        "mlbam_id": [1, 2], "pa": [700.0, 700.0], "war": [3.0, 3.0], "def_runs": [10.0, 10.0],
        "eligible": [frozenset({"RF"})] * 2, "primary_position": ["SS", "RF"],
    })
    out, _ = build_batter_depth_chart(pool, def_weight=0.0, position_weight=1.0,
                                      off_position_penalty=0.0, off_position_multiplier=1.0,
                                      slot_position_credit=False)
    # SS keeps his +7.5 position runs; RF's -7.5 would be kept too, but Def 10 is all fielding
    # for him in the sense that his position part is -7.5, so the SS ranks higher.
    assert out["allocated"].iloc[0] > out["allocated"].iloc[1]


def test_slot_position_credit_swaps_positional_adjustment():
    # A shortstop (+7.5 runs of position credit) filling first base (-12.5) gives up 20 runs
    # per 700 PA, i.e. 2 WAR, in the WAR he is credited with.
    pool = pd.DataFrame({
        "mlbam_id": [1], "pa": [700.0], "war": [4.0], "def_runs": [10.0],
        "eligible": [frozenset({"1B"})], "primary_position": ["SS"],
    })
    on, _ = build_batter_depth_chart(pool, slot_position_credit=True)
    off, _ = build_batter_depth_chart(pool, slot_position_credit=False)
    per_pa = lambda df: df["scaled_war"].iloc[0] / df["allocated"].iloc[0]
    assert per_pa(off) - per_pa(on) == pytest.approx(2.0 / 700.0, rel=1e-6)


def test_slot_position_credit_leaves_home_position_and_unknowns_alone():
    base = {"mlbam_id": [1], "pa": [700.0], "war": [4.0], "def_runs": [10.0],
            "eligible": [frozenset({"SS"})]}
    home = pd.DataFrame({**base, "primary_position": ["SS"]})
    unknown = pd.DataFrame({**base, "primary_position": [None]})
    for pool in (home, unknown):
        on, _ = build_batter_depth_chart(pool, slot_position_credit=True)
        off, _ = build_batter_depth_chart(pool, slot_position_credit=False)
        assert on["scaled_war"].iloc[0] == pytest.approx(off["scaled_war"].iloc[0])


def test_off_position_penalty_lowers_rank_away_from_main_position():
    # Equal rates; the off-position player is listed first so he wins the tie without a penalty.
    pool = pd.DataFrame({
        "mlbam_id": [1, 2], "pa": [700.0, 700.0], "war": [3.0, 3.0],
        "def_runs": [0.0, 0.0], "eligible": [frozenset({"1B"}), frozenset({"1B"})],
        "primary_position": ["2B", "1B"],
    })
    free, _ = build_batter_depth_chart(pool, off_position_penalty=0.0, off_position_multiplier=1.0,
                                        slot_position_credit=False)
    pen, _ = build_batter_depth_chart(pool, off_position_penalty=20.0, off_position_multiplier=1.0,
                                       slot_position_credit=False)
    assert free["allocated"].iloc[0] >= free["allocated"].iloc[1]
    assert pen["allocated"].iloc[1] > pen["allocated"].iloc[0]


def test_off_position_penalty_does_not_change_credited_rate_or_dh_or_unknowns():
    pool = pd.DataFrame({
        "mlbam_id": [1, 2], "pa": [600.0, 600.0], "war": [3.0, 3.0], "def_runs": [0.0, 0.0],
        "eligible": [frozenset({"1B"}), frozenset({"1B"})], "primary_position": ["2B", None],
    })
    on, _ = build_batter_depth_chart(pool, off_position_penalty=20.0, slot_position_credit=False)
    for i in (0, 1):
        assert on["scaled_war"].iloc[i] / on["allocated"].iloc[i] == pytest.approx(3.0 / 600.0)
    dh = pd.DataFrame({"mlbam_id": [1], "pa": [600.0], "war": [3.0], "def_runs": [0.0],
                       "eligible": [frozenset({"DH"})], "primary_position": ["SS"]})
    a, _ = build_batter_depth_chart(dh, off_position_penalty=0.0)
    b, _ = build_batter_depth_chart(dh, off_position_penalty=20.0)
    assert a["allocated"].iloc[0] == pytest.approx(b["allocated"].iloc[0])


def test_off_position_penalty_must_not_be_negative():
    pool = pd.DataFrame({"mlbam_id": [1], "pa": [600.0], "war": [3.0], "def_runs": [0.0],
                         "eligible": [frozenset({"1B"})]})
    with pytest.raises(ValueError):
        build_batter_depth_chart(pool, off_position_penalty=-1.0)


def test_off_position_multiplier_lowers_rank_away_from_main_position():
    pool = pd.DataFrame({
        "mlbam_id": [1, 2], "pa": [700.0, 700.0], "war": [3.0, 3.0],
        "def_runs": [0.0, 0.0], "eligible": [frozenset({"1B"}), frozenset({"1B"})],
        "primary_position": ["2B", "1B"],
    })
    free, _ = build_batter_depth_chart(pool, off_position_multiplier=1.0, slot_position_credit=False)
    mult, _ = build_batter_depth_chart(pool, off_position_multiplier=0.7, slot_position_credit=False)
    assert free["allocated"].iloc[0] >= free["allocated"].iloc[1]
    assert mult["allocated"].iloc[1] > mult["allocated"].iloc[0]
    # ranking only: credited WAR per PA is unchanged
    assert mult["scaled_war"].iloc[0] / mult["allocated"].iloc[0] == pytest.approx(3.0 / 700.0)


def test_off_position_multiplier_defaults_and_bounds():
    assert OFF_POSITION_MULTIPLIER == 0.7
    pool = pd.DataFrame({"mlbam_id": [1], "pa": [600.0], "war": [3.0], "def_runs": [0.0],
                         "eligible": [frozenset({"1B"})]})
    for bad in (0.0, 1.5):
        with pytest.raises(ValueError):
            build_batter_depth_chart(pool, off_position_multiplier=bad)


def test_recommended_defaults_are_locked_in():
    import bucco.models.depth_chart as m
    assert (m.RANK_DECAY, m.DECAY_PER_WAR600, m.SECONDARY_WEIGHT, m.MAX_SLOT_SHARE) == (
        0.7, 0.25, 0.25, 0.92)
    assert (m.UNKNOWN_WAR_MULTIPLIER, m.DEF_WEIGHT, m.POSITION_WEIGHT) == (0.1, 0.7, 0.7)
    assert (m.OFF_POSITION_MULTIPLIER, m.OFF_POSITION_PENALTY, m.MIN_ELIGIBLE_GAMES) == (0.7, 0.0, 20)
    import inspect
    assert inspect.signature(m.build_batter_depth_chart).parameters["slot_position_credit"].default is True


def test_dh_goes_to_a_backup_with_spare_pa_before_replacement_level():
    # The regulars in left and at first base outrank the backup at DH but are full-time at
    # their own slots. DH is nobody's home slot, so the backup (500 PA to give) should not be
    # discounted there and lose the DH to replacement level.
    # def_runs carry each position's adjustment, as in the projections (LF -7.5, 1B -12.5).
    team = pd.DataFrame([_player(1, 700, 4.0 * 700 / 600, {"LF", "DH"}, def_runs=-7.5),
                         _player(2, 700, 3.0 * 700 / 600, {"1B", "DH"}, def_runs=-12.5),
                         _player(3, 500, 1.5 * 500 / 600, {"1B", "DH"}, def_runs=-12.5 * 500 / 700)])
    # Replacement level keeps a hedge share of every slot, so the backup does not get all 500;
    # with the DH discounted he got about 110 PA there and replacement about 230.
    players, allocations = build_batter_depth_chart(team)
    dh = allocations[allocations["slot"] == "DH"]
    assert dh.loc[dh["player"] == 3, "pa"].sum() > 160
    assert dh["pa"].sum() > 0.8 * SLOT_PA["DH"]
