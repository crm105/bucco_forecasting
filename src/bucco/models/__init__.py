"""Season forecasting models. Add new models to REGISTRY so the CLI can run them."""

from bucco.models.base import SeasonForecaster
from bucco.models.naive import ConstantModel, PersistenceModel

REGISTRY = {
    "constant": ConstantModel,
    "last_year": PersistenceModel,
}

__all__ = ["REGISTRY", "ConstantModel", "PersistenceModel", "SeasonForecaster"]
