"""Season forecasting models. Add new models to REGISTRY so the CLI can run them."""

from bucco.models.base import SeasonForecaster
from bucco.models.blend import BlendModel, make_blend_optimized_model
from bucco.models.depth_chart_model import DepthChartModel, PlayerData
from bucco.models.naive import ConstantModel, PersistenceModel
from bucco.models.player_inputs import (
    make_depth_chart_model,
    make_marcel_ml_pitchers_model,
    make_marcel_park_model,
    make_marcel_park_optimized_model,
    make_marcel_parkfit_model,
    make_marcel_parkfit_optimized_model,
    make_marcel_staff_optimized_model,
    make_steamer_model,
    make_steamer_optimized_model,
    make_zips_optimized_model,
)
from bucco.models.smoothing import HoltModel

REGISTRY = {
    "constant": ConstantModel,
    "last_year": PersistenceModel,
    "holt": HoltModel,
    "depth_chart": make_depth_chart_model,
    "steamer": make_steamer_model,
    "steamer_optimized": make_steamer_optimized_model,
    "zips_optimized": make_zips_optimized_model,
    "blend_optimized": make_blend_optimized_model,
    "marcel_park": make_marcel_park_model,
    "marcel_park_optimized": make_marcel_park_optimized_model,
    "marcel_parkfit": make_marcel_parkfit_model,
    "marcel_parkfit_optimized": make_marcel_parkfit_optimized_model,
    "marcel_staff_optimized": make_marcel_staff_optimized_model,
    "marcel_ml_pitchers": make_marcel_ml_pitchers_model,
}

__all__ = [
    "REGISTRY",
    "BlendModel",
    "ConstantModel",
    "DepthChartModel",
    "HoltModel",
    "PersistenceModel",
    "PlayerData",
    "SeasonForecaster",
    "make_blend_optimized_model",
    "make_depth_chart_model",
    "make_marcel_ml_pitchers_model",
    "make_marcel_park_model",
    "make_marcel_park_optimized_model",
    "make_marcel_parkfit_model",
    "make_marcel_parkfit_optimized_model",
    "make_marcel_staff_optimized_model",
    "make_steamer_model",
    "make_steamer_optimized_model",
    "make_zips_optimized_model",
]
