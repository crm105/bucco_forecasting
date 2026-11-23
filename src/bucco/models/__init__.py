"""Season forecasting models. Add new models to REGISTRY so the CLI can run them."""

from bucco.models.base import SeasonForecaster
from bucco.models.depth_chart_model import DepthChartModel, PlayerData
from bucco.models.naive import ConstantModel, PersistenceModel
from bucco.models.player_inputs import make_depth_chart_model
from bucco.models.smoothing import HoltModel

REGISTRY = {
    "constant": ConstantModel,
    "last_year": PersistenceModel,
    "holt": HoltModel,
    "depth_chart": make_depth_chart_model,
}

__all__ = ["REGISTRY", "ConstantModel", "DepthChartModel", "HoltModel", "PersistenceModel",
           "PlayerData", "SeasonForecaster", "make_depth_chart_model"]
