import atexit
import logging
import queue
import sys
from logging.handlers import QueueHandler, QueueListener
from typing import Final

from roomloop.config.env import env

LOG_FORMAT: Final[str] = (
    "%(asctime)s.%(msecs)03d [%(levelname)s] [%(name)s] %(message)s"
)
DATE_FORMAT: Final[str] = "%Y-%m-%d %H:%M:%S"

log_queue: queue.SimpleQueue[logging.LogRecord] = queue.SimpleQueue()
stream_handler: logging.StreamHandler = logging.StreamHandler(sys.stdout)
_listener: QueueListener | None = None


_atexit_registered: bool = False


def configure_logger() -> logging.Logger:
    """configures and returns root logger using non-blocking asynchronous queue listener"""
    global _listener, _atexit_registered

    level: int = getattr(logging, env.LOG_LEVEL.upper(), logging.INFO)

    stream_handler.setLevel(level)
    formatter = logging.Formatter(fmt=LOG_FORMAT, datefmt=DATE_FORMAT)
    stream_handler.setFormatter(formatter)

    root_logger = logging.getLogger("RoomLoop")
    root_logger.setLevel(level)

    if not any(isinstance(h, QueueHandler) for h in root_logger.handlers):
        queue_handler = QueueHandler(log_queue)
        queue_handler.setLevel(level)
        root_logger.addHandler(queue_handler)

    if _listener is None:
        _listener = QueueListener(log_queue, stream_handler, respect_handler_level=True)
        _listener.start()
        if not _atexit_registered:
            atexit.register(stop_logging)
            _atexit_registered = True

    root_logger.propagate = False
    return root_logger


def stop_logging() -> None:
    """flushes and shuts down background log listener safely"""
    global _listener
    if _listener is not None:
        listener = _listener
        _listener = None
        try:
            if getattr(listener, "_thread", None) is not None:
                listener.stop()
        except (AttributeError, RuntimeError):
            pass


app_logger: logging.Logger = configure_logger()
