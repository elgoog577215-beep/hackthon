from common.utils import format_datetime
from infra.db import Session, SessionHistory
from service.session.models import SessionDetail, SessionSummary, SessionHistoryMessage


def session_to_summary(session: Session) -> SessionSummary:
    return SessionSummary(
        id=session.id,
        title=session.title,
        create_time=format_datetime(session.create_time),
        update_time=format_datetime(session.update_time),
    )


def session_to_detail(session: Session, histories: list[SessionHistory] | None = None) -> SessionDetail:
    messages: list[SessionHistoryMessage] = []
    for item in histories or []:
        messages.append(
            SessionHistoryMessage(
                role=item.role or "user",
                type=item.message_type or "text",
                content=item.message_content or "",
                session_id=session.id,
                file_paths=item.file_paths or [],
                cost_time=item.cost_time or 0,
                status=item.status or "success",
                error_message=item.error_message,
            )
        )
    return SessionDetail(
        id=session.id,
        title=session.title,
        create_time=format_datetime(session.create_time),
        update_time=format_datetime(session.update_time),
        messages=messages,
    )
