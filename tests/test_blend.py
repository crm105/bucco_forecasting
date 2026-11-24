"""The blended model: weight tuned on earlier seasons only, fallback to one component."""

from datetime import date
from typing import ClassVar

import numpy as np
import pandas as pd
import pytest

from bucco.models.base import forecast_frame
from bucco.models.blend import PRIOR_WEIGHT, BlendModel

SEASONS = range(2012, 2022)
TEAMS = [1, 2, 3, 4]
rng = np.random.default_rng(0)
TRUTH = {(s, t): 0.5 + rng.normal(0, 0.05) for s in SEASONS for t in TEAMS}


class Fake:
    """Forecasts the truth plus its own noise; remembers what history it was fitted on."""

    seen: ClassVar[list] = []

    def __init__(self, noise, seasons=SEASONS, seed=1):
        self.name, self.noise, self.seasons = "fake", noise, set(seasons)
        self.r = np.random.default_rng(seed)
        self.err = {k: self.r.normal(0, noise) for k in TRUTH}

    def fit(self, history):
        Fake.seen.append(int(history["season"].max()) if len(history) else None)

    def predict(self, season, as_of, features):
        mean = [TRUTH[(season, t)] + self.err[(season, t)] for t in features["team_id"]]
        return forecast_frame(features, pd.Series(mean), 0.06)


def _history(last):
    return pd.DataFrame([{"season": s, "team_id": t, "win_pct": TRUTH[(s, t)],
                          "games_played": 162} for s in SEASONS if s <= last for t in TEAMS])


def _feats(season):
    return pd.DataFrame({"season": season, "team_id": TEAMS})


def test_the_better_component_gets_more_weight():
    blend = BlendModel(lambda: Fake(0.04, seed=1), lambda: Fake(0.005, seed=2))
    blend.fit(_history(2020))
    assert blend.weight > 0.8


def test_too_little_history_uses_the_prior_weight():
    blend = BlendModel(lambda: Fake(0.04, seed=1), lambda: Fake(0.005, seed=2))
    blend.fit(_history(2013))
    assert blend.weight == PRIOR_WEIGHT


def test_weight_never_sees_the_target_season():
    Fake.seen = []
    blend = BlendModel(lambda: Fake(0.02, seed=1), lambda: Fake(0.02, seed=2))
    blend.fit(_history(2017))
    assert max(s for s in Fake.seen if s is not None) <= 2017
    blend.predict(2018, date(2018, 3, 29), _feats(2018))


def test_the_blend_is_the_weighted_average_and_keeps_the_league_total():
    a, b = Fake(0.02, seed=1), Fake(0.02, seed=2)
    blend = BlendModel(lambda: a, lambda: b)
    blend.fit(_history(2019))
    out = blend.predict(2020, date(2020, 7, 23), _feats(2020))["mean_win_pct"]
    pa = a.predict(2020, None, _feats(2020))["mean_win_pct"]
    pb = b.predict(2020, None, _feats(2020))["mean_win_pct"]
    w = blend.weight
    assert list(out) == pytest.approx(list((1 - w) * pa + w * pb))
    assert out.sum() == pytest.approx((1 - w) * pa.sum() + w * pb.sum())


def test_a_season_only_one_component_covers_uses_that_component():
    blend = BlendModel(lambda: Fake(0.02, seed=1), lambda: Fake(0.02, seasons=range(2012, 2019)))
    blend.fit(_history(2019))
    out = blend.predict(2020, date(2020, 7, 23), _feats(2020))
    alone = Fake(0.02, seed=1).predict(2020, None, _feats(2020))
    assert list(out["mean_win_pct"]) == pytest.approx(list(alone["mean_win_pct"]))
    with pytest.raises(ValueError):
        BlendModel(lambda: Fake(0.02, seasons=[2012]), lambda: Fake(0.02, seasons=[2012])) \
            .predict(2015, None, _feats(2015))
