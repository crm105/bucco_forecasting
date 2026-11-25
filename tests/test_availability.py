"""Availability factors from Opening Day 40-man status."""

import numpy as np
import pandas as pd
import pytest

from bucco.models import availability as av


def test_groups_from_status_and_missing_players_are_off_the_40_man():
    rows = pd.DataFrame({"season": [2025] * 4, "mlbam_id": [1, 2, 3, 4]})
    status = pd.DataFrame({"season": [2025] * 3, "mlbam_id": [1, 2, 3],
                           "il_group": ["il_60", "il_short", "none"]})
    assert list(av.status_groups(rows, status)) == ["il_60", "il_short", "active", "off_40"]


DELIVERED = {"il_60": 0.2, "il_short": 0.6, "active": 0.9, "off_40": 0.1}


def _rows():
    rows = []
    for s in (2015, 2016, 2017):
        for g, share in DELIVERED.items():
            rows += [{"season": s, "group": g, "projected": 100.0, "actual": 100.0 * share}] * 40
    return pd.DataFrame(rows)


def test_factors_are_what_each_group_delivered_relative_to_active_players():
    d = _rows()
    f = av.fit_factors(d["group"], d["projected"], d["actual"], d["season"], before=2017)
    assert f["active"] == pytest.approx(1.0)
    assert f["il_60"] == pytest.approx(0.2 / 0.9) and f["off_40"] == pytest.approx(0.1 / 0.9)
    absolute = av.fit_factors(d["group"], d["projected"], d["actual"], d["season"], before=2017,
                              relative=False)
    assert absolute["active"] == pytest.approx(0.9)


def test_each_season_uses_only_earlier_seasons_and_the_first_gets_none():
    d = _rows()
    d.loc[d["season"] == 2017, "actual"] = 0.0           # the target season must not matter
    f = av.availability(d["group"], d["projected"], d["actual"], d["season"], relative=False)
    assert (f[d["season"] == 2015] == 1.0).all()          # nothing earlier to learn from
    il60_2017 = f[(d["season"] == 2017) & (d["group"] == "il_60")]
    assert np.allclose(il60_2017, 0.2)
