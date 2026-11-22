"""Season forecasting models. Add new models to REGISTRY so the CLI can run them."""

from bucco.models.base import SeasonForecaster
from bucco.models.naive import ConstantModel, PersistenceModel
from bucco.models.smoothing import HoltModel

REGISTRY = {
    "constant": ConstantModel,
    "last_year": PersistenceModel,
    "holt": HoltModel,
}

__all__ = ["REGISTRY", "ConstantModel", "HoltModel", "PersistenceModel", "SeasonForecaster"]
