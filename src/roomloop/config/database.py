import sqlite3
from collections.abc import Generator
from contextlib import contextmanager
from typing import Any

from sqlalchemy import Connection, Engine, create_engine, event, text
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import ConnectionPoolEntry

from roomloop.config.env import env
from roomloop.shared.services.logger import app_logger


class DatabaseConnection:
    """manages database engine and session lifecycle with two-phase initialization and sqlite immediate locking"""

    def __init__(self, db_path: str | None = None, echo: bool = False) -> None:
        if not isinstance(echo, bool):
            raise TypeError(
                f"[Database Connection] echo must be a boolean value, got {type(echo).__name__}"
            )

        if db_path is not None:
            if not isinstance(db_path, str):
                raise TypeError(
                    f"[Database Connection] db_path must be a string or None, got {type(db_path).__name__}"
                )
            cleaned_path = db_path.strip()
            if not cleaned_path:
                raise ValueError(
                    "[Database Connection] db_path cannot be empty or whitespace only"
                )
            self._target_path: str = cleaned_path
        else:
            self._target_path = env.DATABASE_FILE_PATH.strip()

        self._echo: bool = echo
        self._engine: Engine | None = None
        self._session_factory: sessionmaker[Session] | None = None

    @property
    def is_connected(self) -> bool:
        """returns true if the engine has been initialized and is active"""
        return self._engine is not None

    @property
    def engine(self) -> Engine:
        """returns the active sqlalchemy engine or raises runtimeerror if not connected"""
        if self._engine is None:
            raise RuntimeError(
                "[Database Connection] Not connected to database. Call connect() first."
            )
        return self._engine

    def connect(self) -> None:
        """establishes sqlite engine, sets pragmas, and configures session factory"""
        if self._engine is not None:
            app_logger.warning("[Database Connection] Connection already established")
            return

        app_logger.info(
            "[Database Connection] Connecting to sqlite:///%s", self._target_path
        )
        self._engine = create_engine(f"sqlite:///{self._target_path}", echo=self._echo)
        self._setup_sqlite_hooks(self._engine)

        self._session_factory = sessionmaker(
            bind=self._engine,
            autocommit=False,
            autoflush=False,
            expire_on_commit=False,
        )
        app_logger.info("[Database Connection] Established successfully")

    def _setup_sqlite_hooks(self, engine: Engine) -> None:
        """registers sqlite pragmas and immediate transaction locks"""
        if engine.url.drivername.startswith("sqlite"):

            @event.listens_for(engine, "connect")
            def _set_sqlite_pragmas(
                dbapi_connection: sqlite3.Connection,
                connection_record: ConnectionPoolEntry,
            ) -> None:
                # disable pysqlite default transaction control so sqlalchemy manages it
                dbapi_connection.isolation_level = None
                cursor: sqlite3.Cursor = dbapi_connection.cursor()
                try:
                    cursor.execute("PRAGMA foreign_keys = ON")
                    cursor.execute("PRAGMA journal_mode = WAL")
                except sqlite3.Error as err:
                    app_logger.error(
                        "[Database Connection] Failed to set SQLite PRAGMAs: %s", err
                    )
                    raise
                finally:
                    cursor.close()

            @event.listens_for(engine, "begin")
            def _do_begin_immediate(conn: Connection) -> None:
                # eager write lock to serialize concurrent bookings and prevent race conditions
                conn.exec_driver_sql("BEGIN IMMEDIATE")

    def check_connection(self) -> bool:
        """verifies database connectivity with lightweight ping query"""
        if self._engine is None:
            return False
        try:
            with self._engine.connect() as conn:
                raw_result: Any = conn.execute(text("SELECT 1")).scalar()
                if not isinstance(raw_result, int):
                    return False
                return raw_result == 1
        except Exception as err:
            app_logger.error("[Database Connection] Health check ping failed: %s", err)
            return False

    @contextmanager
    def get_session(self) -> Generator[Session, None, None]:
        """context manager and generator yielding an active database session with auto rollback"""
        if self._session_factory is None:
            raise RuntimeError(
                "[Database Connection] Not connected to database. Call connect() first."
            )

        session: Session = self._session_factory()
        try:
            yield session
        except Exception as err:
            app_logger.error(
                "[Database Connection] Rolling back session due to error: %s", err
            )
            session.rollback()
            raise
        finally:
            session.close()

    def disconnect(self) -> None:
        """disposes the underlying engine and connection pool"""
        if self._engine is None:
            app_logger.warning("[Database Connection] Connection already closed")
            return

        app_logger.info("[Database Connection] Disconnecting database...")
        self._engine.dispose()
        self._engine = None
        self._session_factory = None
        app_logger.info("[Database Connection] Disconnected successfully")


db_connection = DatabaseConnection()
