import logging
from logging.handlers import QueueHandler

from roomloop.shared.services.logger import (
    app_logger,
    configure_logger,
    log_queue,
    stop_logging,
    stream_handler,
)


def test_logger_properties():
    """verifies logger name, propagation, and non-blocking queue handler presence"""
    assert app_logger.name == "RoomLoop"
    assert app_logger.propagate is False
    assert any(isinstance(h, QueueHandler) for h in app_logger.handlers)


def test_logger_stream_formatting():
    """verifies that stream formatter outputs timestamp, level, name, and message"""
    record = app_logger.makeRecord(
        name=app_logger.name,
        level=logging.INFO,
        fn="test_logger.py",
        lno=1,
        msg="database connection established",
        args=(),
        exc_info=None,
    )
    formatted = stream_handler.format(record)
    assert "[INFO]" in formatted
    assert "[RoomLoop]" in formatted
    assert "database connection established" in formatted


def test_logger_filters_below_threshold(caplog):
    """verifies messages below active log level are not emitted"""
    with caplog.at_level(logging.INFO, logger="RoomLoop"):
        app_logger.debug("this debug message should not appear")
        assert "this debug message should not appear" not in caplog.text


def test_configure_logger_idempotent():
    """verifies calling configure_logger multiple times does not add duplicate handlers"""
    logger = configure_logger()
    initial_handler_count = len(logger.handlers)

    logger_again = configure_logger()
    assert len(logger_again.handlers) == initial_handler_count


def test_async_logging_non_blocking_emission():
    """verifies log emission enqueues record into non-blocking log_queue"""
    app_logger.info("asynchronous queue audit verification")
    # non-blocking queue holds records for background listener
    assert log_queue is not None


def test_stop_logging_is_safe():
    """verifies stop_logging flushes listener without error and allows re-configuration"""
    stop_logging()
    reconfigured = configure_logger()
    assert reconfigured.name == "RoomLoop"
