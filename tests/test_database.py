import pytest
from sqlalchemy import text

from roomloop.config.database import DatabaseConnection


def test_database_connection_initial_state(tmp_path):
    """verifies that a fresh database connection is not connected until connect() is called"""
    db_file = str(tmp_path / "test_init.db")
    db = DatabaseConnection(db_path=db_file)
    assert db.is_connected is False

    with pytest.raises(RuntimeError, match="Not connected to database"):
        _ = db.engine

    with (
        pytest.raises(RuntimeError, match="Not connected to database"),
        db.get_session(),
    ):
        pass


def test_database_connection_validation_boundaries():
    """verifies invalid arguments to DatabaseConnection raise appropriate errors"""
    with pytest.raises(TypeError, match="echo must be a boolean"):
        DatabaseConnection(echo="invalid")  # type: ignore

    with pytest.raises(TypeError, match="db_path must be a string"):
        DatabaseConnection(db_path=123)  # type: ignore

    with pytest.raises(ValueError, match="db_path cannot be empty"):
        DatabaseConnection(db_path="   ")


def test_database_connect_and_disconnect(tmp_path):
    """verifies connect and disconnect cycle properly manages engine and pool"""
    db_file = str(tmp_path / "test_lifecycle.db")
    db = DatabaseConnection(db_path=db_file)

    db.connect()
    assert db.is_connected is True
    assert db.check_connection() is True

    # calling connect again should be idempotent
    db.connect()
    assert db.is_connected is True

    db.disconnect()
    assert db.is_connected is False
    assert db.check_connection() is False

    # calling disconnect again should be a no-op
    db.disconnect()
    assert db.is_connected is False


def test_sqlite_pragmas_configured(tmp_path):
    """verifies that foreign_keys and journal_mode pragmas are set on connection"""
    db_file = str(tmp_path / "test_pragmas.db")
    db = DatabaseConnection(db_path=db_file)
    db.connect()

    try:
        with db.engine.connect() as conn:
            fk_result = conn.execute(text("PRAGMA foreign_keys")).scalar()
            assert fk_result == 1

            wal_result = conn.execute(text("PRAGMA journal_mode")).scalar()
            assert str(wal_result).lower() == "wal"
    finally:
        db.disconnect()


def test_session_lifecycle_and_rollback(tmp_path):
    """verifies session commits and rolls back properly on exception"""
    db_file = str(tmp_path / "test_session.db")
    db = DatabaseConnection(db_path=db_file)
    db.connect()

    try:
        # create a test table
        with db.engine.begin() as conn:
            conn.execute(text("CREATE TABLE items (id INTEGER PRIMARY KEY, name TEXT)"))

        # test successful session insert
        with db.get_session() as session:
            session.execute(text("INSERT INTO items (id, name) VALUES (1, 'widget')"))
            session.commit()

        # verify row was inserted
        with db.get_session() as session:
            row = session.execute(text("SELECT name FROM items WHERE id = 1")).scalar()
            assert row == "widget"

        # test rollback on exception
        with (
            pytest.raises(ValueError, match="simulated failure"),
            db.get_session() as session,
        ):
            session.execute(text("INSERT INTO items (id, name) VALUES (2, 'gadget')"))
            raise ValueError("simulated failure")

        # verify row 2 was rolled back
        with db.get_session() as session:
            row_2 = session.execute(
                text("SELECT name FROM items WHERE id = 2")
            ).scalar()
            assert row_2 is None
    finally:
        db.disconnect()
