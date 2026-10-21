import importlib

from roomloop.shared.models.base import Base

MODEL_MODULES: tuple[str, ...] = (
    "roomloop.modules.rooms.model",
    "roomloop.modules.bookings.model",
    "roomloop.modules.audit.model",
)


def register_models() -> type[Base]:
    """loads all domain orm models into base metadata before schema creation"""
    for module_name in MODEL_MODULES:
        importlib.import_module(module_name)
    return Base
