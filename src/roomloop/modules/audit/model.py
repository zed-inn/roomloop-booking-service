from sqlalchemy import Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from roomloop.shared.models.base import Base


class AuditLogModel(Base):
    """persistent immutable audit log entity tracking all domain state modifications"""

    __tablename__ = "audit_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    event_type: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    entity_type: Mapped[str] = mapped_column(String(50), nullable=False)
    entity_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    user_name: Mapped[str | None] = mapped_column(String(100), nullable=True)
    details_json: Mapped[str] = mapped_column(Text, nullable=False)
    created_at_utc: Mapped[str] = mapped_column(
        String(30), nullable=False, index=True
    )
