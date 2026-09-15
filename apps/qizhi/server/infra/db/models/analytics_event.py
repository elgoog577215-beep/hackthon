from sqlalchemy import Column, DateTime, ForeignKey, Index, Integer, String, func
from sqlalchemy.dialects.postgresql import JSONB

from infra.db.database import Base
from infra.db.sequence import generate_id


class AnalyticsEvent(Base):
    __tablename__ = "analytics_events"
    __table_args__ = (
        Index("ix_analytics_events_time_name", "occurred_at", "event_name"),
        Index("ix_analytics_events_session_time", "session_id", "occurred_at"),
        Index("ix_analytics_events_workflow", "workflow_id", "event_name"),
        Index("ix_analytics_events_user_received", "user_id", "received_at"),
        Index("ix_analytics_events_anon_received", "anonymous_id", "received_at"),
    )

    id = Column(String, primary_key=True, default=generate_id)
    event_id = Column(String(128), nullable=False, unique=True)
    event_name = Column(String(64), nullable=False, index=True)
    user_id = Column(String, ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)
    anonymous_id = Column(String(128), nullable=True, index=True)
    session_id = Column(String(128), nullable=True, index=True)
    page_instance_id = Column(String(128), nullable=True, index=True)
    workflow_id = Column(String(128), nullable=True, index=True)
    page_path = Column(String(512), nullable=True)
    outcome = Column(String(16), nullable=True)
    duration_ms = Column(Integer, nullable=True)
    scroll_depth = Column(Integer, nullable=True)
    properties = Column(JSONB, nullable=True)
    schema_version = Column(Integer, nullable=False, default=1)
    source = Column(String(16), nullable=False, default="web")
    client_version = Column(String(64), nullable=True)
    occurred_at = Column(DateTime(timezone=True), nullable=False, index=True)
    received_at = Column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.date_trunc("second", func.now()),
        index=True,
    )
