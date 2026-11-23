"""Checks for the regulars-first playing-time allocation."""

import numpy as np
import pandas as pd
import pytest

from bucco.models.playing_time import (
    PA_BUDGET,
    allocate_by_team,
    allocate_playing_time,
    team_war,
)


def _team(pa, war=None, team_id=1):
    pa = list(pa)
    war = war if war is not None else [pa_i / 200 for pa_i in pa]
    return pd.DataFrame({"team_id": team_id, "pa": pa, "war": war})


def _roster(n=40):
    """A made-up team: projections fall from 650 PA down to a few dozen."""
    pa = np.linspace(650, 40, n)
    return _team(pa)


def test_allocation_adds_up_to_the_budget():
    out = allocate_playing_time(_roster(), "pa", PA_BUDGET)
    assert out["allocated"].sum() == pytest.approx(PA_BUDGET)


def test_nobody_gets_more_than_his_projection_or_the_cap():
    out = allocate_playing_time(_roster(), "pa", PA_BUDGET, cap=500)
    assert (out["allocated"] <= out["pa"] + 1e-9).all()
    assert (out["allocated"] <= 500 + 1e-9).all()


def test_top_twelve_by_projection_are_the_regulars():
    shuffled = _roster().sample(frac=1, random_state=3)
    out = allocate_playing_time(shuffled, "pa", PA_BUDGET)
    regulars = out[out["role"] == "regular"]
    assert len(regulars) == 12
    assert regulars["pa"].min() >= out[out["role"] != "regular"]["pa"].max()
    assert list(out.index) == list(shuffled.index)  # original row order kept


def test_regulars_get_the_non_set_aside_share_pro_rata():
    out = allocate_playing_time(_roster(), "pa", PA_BUDGET, bench_share=0.2)
    regulars = out[out["role"] == "regular"]
    assert regulars["allocated"].sum() == pytest.approx(0.8 * PA_BUDGET)
    # same fraction of projection for every regular
    assert regulars["fraction"].nunique() == 1 or np.ptp(regulars["fraction"]) < 1e-9


def test_bench_share_goes_to_the_bench_and_decays_geometrically():
    # Bench players have huge projections, so no cap binds and the pure decay shows.
    roster = pd.concat([_team([600] * 12), _team([5000] * 6)], ignore_index=True)
    out = allocate_playing_time(roster, "pa", 6000, bench_share=0.1, decay=0.7)
    bench = out[out["role"] == "bench"]["allocated"].to_numpy()
    assert bench.sum() == pytest.approx(600)
    assert bench[1:] / bench[:-1] == pytest.approx(np.full(5, 0.7))


def test_excess_over_a_bench_players_projection_moves_down_the_list():
    roster = pd.concat([_team([600] * 12), _team([40, 400, 400])], ignore_index=True)
    out = allocate_playing_time(roster, "pa", 6000, bench_share=0.1, decay=0.9)
    bench = out[out["role"] != "regular"].sort_values("pa", ascending=False)
    # 400-PA players rank first; nobody exceeds his projection and the pool is fully used
    assert (bench["allocated"] <= bench["pa"] + 1e-9).all()
    assert bench["allocated"].sum() == pytest.approx(600)


def test_unused_regular_share_flows_to_the_bench():
    # 12 regulars projected for 400 each (4,800) can't use their 5,400 share of a 6,000 budget
    roster = pd.concat([_team([400] * 12), _team([300] * 10)], ignore_index=True)
    out = allocate_playing_time(roster, "pa", 6000, bench_share=0.1)
    regulars = out[out["role"] == "regular"]
    assert regulars["allocated"].sum() == pytest.approx(4800)
    assert out["allocated"].sum() == pytest.approx(6000)  # the 1,200 left over goes to the bench


def test_a_thin_roster_cannot_exceed_what_was_projected():
    out = allocate_playing_time(_team([300] * 15), "pa", PA_BUDGET)
    assert out["allocated"].sum() == pytest.approx(4500)  # everyone at his own projection


def test_war_scales_with_the_share_of_playing_time_received():
    out = allocate_playing_time(_roster(), "pa", PA_BUDGET)
    assert out["scaled_war"].to_numpy() == pytest.approx((out["war"] * out["fraction"]).to_numpy())
    negative = _team([600] * 12 + [100], war=[2.0] * 12 + [-1.0])
    scaled = allocate_playing_time(negative, "pa", 6240, bench_share=0.1)
    assert (scaled["scaled_war"][scaled["war"] < 0] <= 0).all()  # a bad bat never gains WAR


def test_zero_projection_players_are_unused():
    roster = pd.concat([_roster(), _team([0, 0])], ignore_index=True)
    out = allocate_playing_time(roster, "pa", PA_BUDGET)
    assert (out.loc[out["pa"] == 0, "allocated"] == 0).all()
    assert (out.loc[out["pa"] == 0, "role"] == "unused").all()


def test_allocate_by_team_budgets_each_team_separately():
    both = pd.concat([_roster().assign(team_id=1), _roster(30).assign(team_id=2)],
                     ignore_index=True)
    out = allocate_by_team(both, "pa", PA_BUDGET)
    sums = out.groupby("team_id")["allocated"].sum()
    assert sums.to_numpy() == pytest.approx([PA_BUDGET, PA_BUDGET])
    assert list(out.index) == list(both.index)
    assert set(team_war(out).index) == {1, 2}


@pytest.mark.parametrize("kwargs", [{"bench_share": -0.1}, {"bench_share": 1.5},
                                    {"decay": 0.0}, {"decay": 1.2}, {"n_regulars": -1}])
def test_bad_arguments_are_rejected(kwargs):
    with pytest.raises(ValueError):
        allocate_playing_time(_roster(), "pa", PA_BUDGET, **kwargs)


def test_rate_ranking_prefers_the_better_player_over_the_bigger_projection():
    # 12 solid players, plus a prospect projected for the most PA but worth nothing, plus a
    # good bench bat with fewer PA
    roster = _team([500] * 12 + [650, 450], war=[2.5] * 12 + [0.0, 3.5])
    by_rate = allocate_playing_time(roster, "pa", 6240, rank_by="rate")
    by_volume = allocate_playing_time(roster, "pa", 6240, rank_by="volume")
    assert by_rate.loc[12, "role"] != "regular"      # the 0-WAR prospect misses the cut
    assert by_volume.loc[12, "role"] == "regular"    # ...but ranks 1st when ranked on volume
    assert by_rate.loc[13, "role"] == "regular"      # the 3.5-WAR bat makes it


def test_rate_ranking_ignores_tiny_samples_below_the_floor():
    # 80 PA at 1.0 WAR is a huge rate, but below the 200 PA floor it can't beat real regulars
    roster = _team([500] * 12 + [80], war=[2.0] * 12 + [1.0])
    out = allocate_playing_time(roster, "pa", 6240, rank_by="rate", min_volume=200)
    assert out.loc[12, "role"] != "regular"
    no_floor = allocate_playing_time(roster, "pa", 6240, rank_by="rate", min_volume=0)
    assert no_floor.loc[12, "role"] == "regular"


def test_unknown_rank_by_is_rejected():
    with pytest.raises(ValueError, match="rank_by"):
        allocate_playing_time(_roster(), "pa", PA_BUDGET, rank_by="vibes")
