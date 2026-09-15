import asyncio
import time
from collections import defaultdict, deque
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import func, select

from common.models import ApiResponse
from common.models.analytics import AnalyticsBatchIn, AnalyticsIngestResult
from infra.db import User, get_db
from infra.db.models.analytics_event import AnalyticsEvent
from service.analytics import ingest_events
from service.auth import get_optional_current_user
from common.utils.logger import get_logger


router = APIRouter()
logger = get_logger(__name__)
_RATE_LIMIT = 240
_RATE_WINDOW_SECONDS = 60.0
_rate_lock = asyncio.Lock()
_rate_windows: dict[str, deque[float]] = defaultdict(deque)


async def _enforce_rate_limit(key: str, event_count: int, *, limit: int = _RATE_LIMIT) -> None:
    now = time.monotonic()
    async with _rate_lock:
        window = _rate_windows[key]
        while window and now - window[0] >= _RATE_WINDOW_SECONDS:
            window.popleft()
        if len(window) + event_count > limit:
            raise HTTPException(status_code=status.HTTP_429_TOO_MANY_REQUESTS, detail="analytics rate limit exceeded")
        window.extend([now] * event_count)
        if len(_rate_windows) > 10_000:
            for candidate in list(_rate_windows):
                if not _rate_windows[candidate] or now - _rate_windows[candidate][-1] >= _RATE_WINDOW_SECONDS:
                    _rate_windows.pop(candidate, None)


async def _enforce_persisted_rate_limit(
    db: AsyncSession,
    *,
    user_id: str | None,
    anonymous_id: str,
    event_count: int,
) -> None:
    statement = select(func.count(AnalyticsEvent.id)).where(
        AnalyticsEvent.received_at >= datetime.now(timezone.utc) - timedelta(seconds=_RATE_WINDOW_SECONDS)
    )
    statement = statement.where(
        AnalyticsEvent.user_id == user_id
        if user_id
        else AnalyticsEvent.anonymous_id == anonymous_id
    )
    recent = int((await db.execute(statement)).scalar() or 0)
    if recent + event_count > _RATE_LIMIT:
        raise HTTPException(status_code=status.HTTP_429_TOO_MANY_REQUESTS, detail="analytics rate limit exceeded")


@router.post("/events", response_model=ApiResponse[AnalyticsIngestResult])
async def collect_events(
    batch: AnalyticsBatchIn,
    request: Request,
    current_user: User | None = Depends(get_optional_current_user),
    db: AsyncSession = Depends(get_db),
) -> ApiResponse[AnalyticsIngestResult]:
    visitor_key = current_user.id if current_user else batch.events[0].anonymous_id
    await _enforce_rate_limit(f"visitor:{visitor_key}", len(batch.events))
    peer = request.client.host if request.client else "unknown"
    await _enforce_rate_limit(f"peer:{peer}", len(batch.events), limit=600)
    await _enforce_persisted_rate_limit(
        db,
        user_id=current_user.id if current_user else None,
        anonymous_id=batch.events[0].anonymous_id,
        event_count=len(batch.events),
    )
    accepted, duplicates = await ingest_events(
        db,
        batch.events,
        user_id=current_user.id if current_user else None,
    )
    if duplicates:
        logger.info("[analytics] ignored %d duplicate events for visitor=%s", duplicates, visitor_key)
    return ApiResponse.success_response(AnalyticsIngestResult(accepted=accepted, duplicates=duplicates))
