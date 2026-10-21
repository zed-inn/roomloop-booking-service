import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from roomloop.config.database import DatabaseConnection
from roomloop.config.fastapi import FastApiApp
from roomloop.server import ListenerOpts, Server


def test_listener_opts_validation():
    """verifies listener options validate host and port boundaries"""
    valid_opts = ListenerOpts(host="127.0.0.1", port=9000)
    assert valid_opts.host == "127.0.0.1"
    assert valid_opts.port == 9000

    with pytest.raises(ValidationError):
        ListenerOpts(host="", port=8000)

    with pytest.raises(ValidationError):
        ListenerOpts(host="localhost", port=70000)


def test_fastapi_app_initialization():
    """verifies fastapiapp initializes pure fastapi instance with documentation and middlewares"""
    custom_app = FastApiApp()
    assert custom_app.app.title == "RoomLoop Booking Service API"


def test_server_listener_opts_injection():
    """verifies server correctly accepts and validates custom listener options"""
    test_server = Server(listener_opts={"host": "0.0.0.0", "port": 9090})
    assert test_server.listener_opts.host == "0.0.0.0"
    assert test_server.listener_opts.port == 9090


def test_health_check_endpoint_reflects_injected_database(tmp_path):
    """verifies /health endpoint dynamically reflects database connection state"""
    test_db_path = str(tmp_path / "health_test.db")
    test_db = DatabaseConnection(db_path=test_db_path)
    test_server = Server(database=test_db)

    with TestClient(test_server.fastapi.app) as client:
        # before connect: degraded / 503
        res_disconnected = client.get("/health")
        assert res_disconnected.status_code == 503
        data_disc = res_disconnected.json()
        assert data_disc["status"] == "degraded"
        assert data_disc["database"] == "disconnected"

        # after connect: ok / 200
        test_db.connect()
        res_connected = client.get("/health")
        assert res_connected.status_code == 200
        data_conn = res_connected.json()
        assert data_conn["status"] == "ok"
        assert data_conn["database"] == "connected"
        assert "environment" in data_conn

    test_db.disconnect()


@pytest.mark.anyio
async def test_server_prerequisites_and_shutdown(tmp_path, caplog):
    """verifies server lifecycle start_prerequisites and shutdown without running seeder automatically"""
    import logging

    from roomloop.modules.rooms.model import RoomModel

    test_db_path = str(tmp_path / "prereq_test.db")
    test_db = DatabaseConnection(db_path=test_db_path)
    test_server = Server(database=test_db)

    with caplog.at_level(logging.INFO, logger="RoomLoop"):
        await test_server.start_prerequisites()
        assert test_server.database.is_connected is True
        assert "run seeder before dev/start" in caplog.text

    # verify seeder was not run automatically
    with test_db.get_session() as session:
        assert session.query(RoomModel).count() == 0

    await test_server.shutdown()
    assert test_server.database.is_connected is False


def test_request_logging_middleware_logs_traffic(caplog):
    """verifies that request logging middleware emits method, path, status, and latency via app_logger"""
    import logging

    test_server = Server()
    with (
        caplog.at_level(logging.INFO, logger="RoomLoop"),
        TestClient(test_server.fastapi.app) as client,
    ):
        res = client.get("/health")
        assert res.status_code in (200, 503)

    assert "[HTTP] GET /health" in caplog.text
    assert "ms" in caplog.text
