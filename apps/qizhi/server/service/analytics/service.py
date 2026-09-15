from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import delete
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from common.config import settings
from common.models.analytics import AnalyticsEventIn, AnalyticsEventName
from common.utils.logger import get_logger
from infra.db.models.analytics_event import AnalyticsEvent
from infra.db.sequence import generate_id


logger = get_logger(__name__)


async def ingest_events(
    db: AsyncSession,
    events: list[AnalyticsEventIn],
    *,
    user_id: str | None,
) -> tuple[int, int]:
    rows = [
        {
            "id": generate_id(),
            "event_id": event.event_id,
            "event_name": event.event_name.value,
            "user_id": user_id,
            "anonymous_id": event.anonymous_id,
            "session_id": event.session_id,
            "page_instance_id": event.page_instance_id,
            "workflow_id": event.workflow_id,
            "page_path": event.page_path,
            "outcome": event.outcome,
            "duration_ms": event.duration_ms,
            "scroll_depth": event.scroll_depth,
            "properties": event.properties or None,
            "schema_version": event.schema_version,
            "source": event.source,
            "client_version": event.client_version,
            "occurred_at": event.occurred_at,
        }
        for event in events
    ]
    statement = insert(AnalyticsEvent).values(rows).on_conflict_do_nothing(index_elements=["event_id"])
    result = await db.execute(statement)
    await db.commit()
    accepted = max(0, int(result.rowcount or 0))
    return accepted, len(events) - accepted


async def record_server_event(
    *,
    event_name: AnalyticsEventName | str,
    user_id: str | None,
    workflow_id: str | None = None,
    duration_ms: int | None = None,
    feature: str | None = None,
    outcome: str | None = None,
    properties: dict[str, Any] | None = None,
) -> None:
    """Write authoritative server lifecycle events in an isolated transaction."""
    from infra.db.database import AsyncSessionLocal

    merged = dict(properties or {})
    if feature:
        merged["feature"] = feature
    event = AnalyticsEvent(
        id=generate_id(),
        event_id=f"server-{generate_id()}",
        event_name=event_name.value if isinstance(event_name, AnalyticsEventName) else event_name,
        user_id=user_id,
        workflow_id=workflow_id,
        duration_ms=duration_ms,
        outcome=outcome,
        properties=merged or None,
        schema_version=1,
        source="server",
        occurred_at=datetime.now(timezone.utc),
    )
    async with AsyncSessionLocal() as db:
        try:
            db.add(event)
            await db.commit()
        except Exception:
            await db.rollback()
            logger.warning("[analytics] server event dropped: %s", event.event_name, exc_info=True)


async def cleanup_expired_events(db: AsyncSession, *, now: datetime | None = None) -> int:
    cutoff = (now or datetime.now(timezone.utc)) - timedelta(days=settings.ANALYTICS_RAW_RETENTION_DAYS)
    result = await db.execute(delete(AnalyticsEvent).where(AnalyticsEvent.received_at < cutoff))
    await db.commit()
    return max(0, int(result.rowcount or 0))
