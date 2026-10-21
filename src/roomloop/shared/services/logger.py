import logging
import sys
from typing import Final

from roomloop.config.env import env

LOG_FORMAT: Final[str] = (
    """%(asctime)s.%(msecs)03d [%(levelname)s] [%(name)s] %(message)s"""
)
DATE_FORMAT: Final[str] = "%Y-%m-%d %H:%M:%S"


def configure_logger() -> logging.Logger:
    """Configures and returns root logger"""
    level: int = getattr(logging, env.LOG_LEVEL.upper(), logging.INFO)

    handler = logging.StreamHandler(sys.stdout)
    handler.setLevel(level)

    formatter = logging.Formatter(fmt=LOG_FORMAT, datefmt=DATE_FORMAT)
    handler.setFormatter(formatter)

    root_logger = logging.getLogger("RoomLoop")
    root_logger.setLevel(level)

    if not root_logger.handlers:
        root_logger.addHandler(handler)

    root_logger.propagate = False
    return root_logger


app_logger: logging.Logger = configure_logger()
