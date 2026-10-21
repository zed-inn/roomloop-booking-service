import json
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from roomloop.config.database import DatabaseConnection
from roomloop.modules.audit.model import AuditLogModel


class AuditLogRepository:
    """database persistence operations for audit logs"""

    def __init__(self, db: DatabaseConnection | None = None) -> None:
        self.db = db

    def record_event(
        self,
        session: Session,
        event_type: str,
        entity_type: str,
        entity_id: int | None,
        user_name: str | None,
        details: dict[str, Any],
        now_utc: str,
    ) -> AuditLogModel:
        """records an immutable audit log entry into the provided active session"""
        record = AuditLogModel(
            event_type=event_type,
            entity_type=entity_type,
            entity_id=entity_id,
            user_name=user_name,
            details_json=json.dumps(details),
            created_at_utc=now_utc,
        )
        session.add(record)
        return record

    def list_events(self, limit: int = 100) -> list[AuditLogModel]:
        """fetches recent audit events from database"""
        if self.db is None:
            raise RuntimeError(
                "[Audit Repository] DatabaseConnection is required to query logs"
            )
        with self.db.get_session() as session:
            stmt = (
                select(AuditLogModel)
                .order_by(AuditLogModel.id.desc())
                .limit(limit)
            )
            return list(session.scalars(stmt).all())
