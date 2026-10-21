import json
from typing import Any

from roomloop.modules.audit.repository import AuditLogRepository


class AuditService:
    """business service providing audit trail access"""

    def __init__(self, audit_repo: AuditLogRepository) -> None:
        self.audit_repo = audit_repo

    def get_recent_logs(self, limit: int = 100) -> list[dict[str, Any]]:
        """retrieves structured recent audit logs with parsed json details"""
        records = self.audit_repo.list_events(limit=limit)
        return [
            {
                "id": record.id,
                "event_type": record.event_type,
                "entity_type": record.entity_type,
                "entity_id": record.entity_id,
                "user_name": record.user_name,
                "details": json.loads(record.details_json),
                "created_at_utc": record.created_at_utc,
            }
            for record in records
        ]
