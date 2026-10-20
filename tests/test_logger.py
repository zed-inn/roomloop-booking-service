import logging

from roomloop.shared.services.logger import (
    app_logger,
    configure_logger,
)


def test_logger_properties():
    """verifies logger name, propagation, and stream handler presence"""
    assert app_logger.name == "RoomLoop"
    assert app_logger.propagate is False
    assert any(isinstance(h, logging.StreamHandler) for h in app_logger.handlers)


def test_logger_stream_formatting():
    """verifies that log output contains timestamp, level, name, and message"""
    handler = next(
        h for h in app_logger.handlers if isinstance(h, logging.StreamHandler)
    )
    record = app_logger.makeRecord(
        name=app_logger.name,
        level=logging.INFO,
        fn="test_logger.py",
        lno=1,
        msg="database connection established",
        args=(),
        exc_info=None,
    )
    formatted = handler.format(record)
    assert "[INFO]" in formatted
    assert "[RoomLoop]" in formatted
    assert "database connection established" in formatted


def test_logger_filters_below_threshold(caplog):
    """verifies messages below active log level are not emitted"""
    with caplog.at_level(logging.INFO, logger="RoomLoop"):
        app_logger.debug("this debug message should not appear")
        assert "this debug message should not appear" not in caplog.text


def test_configure_logger_idempotent():
    """Verifies calling configure_logger multiple times does not add duplicate handlers"""
    logger = configure_logger()
    initial_handler_count = len(logger.handlers)

    # call again
    logger_again = configure_logger()
    assert len(logger_again.handlers) == initial_handler_count
