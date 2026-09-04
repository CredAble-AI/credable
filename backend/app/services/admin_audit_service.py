import base64
import json
from datetime import datetime

from app.core.errors import InvalidAuditCursorError
from app.schemas.audit import AdminAuditEventListResponse, SessionAuditEvent
from app.services.session_service import CustomerSessionService


class AdminAuditService:
    def __init__(self, session_service: CustomerSessionService) -> None:
        self.session_service = session_service

    def list_events(
        self,
        session_id: str,
        *,
        limit: int,
        cursor: str | None,
    ) -> AdminAuditEventListResponse:
        session_state = self.session_service.get_session(session_id)
        before_timestamp, before_event_id = self._decode_cursor(cursor)
        events = self.session_service.repository.list_audit_events_page(
            session_id,
            before_timestamp=before_timestamp,
            before_event_id=before_event_id,
            limit=limit + 1,
        )
        has_next_page = len(events) > limit
        page = events[:limit]
        next_cursor = self._encode_cursor(page[-1]) if has_next_page else None
        return AdminAuditEventListResponse(
            session_id=session_id,
            demo_only=session_state.session.demo_only,
            events=page,
            next_cursor=next_cursor,
        )

    @staticmethod
    def _encode_cursor(event: SessionAuditEvent) -> str:
        payload = json.dumps(
            {
                "timestamp": event.timestamp.isoformat(),
                "eventId": event.event_id,
            },
            separators=(",", ":"),
        ).encode()
        return base64.urlsafe_b64encode(payload).decode().rstrip("=")

    @staticmethod
    def _decode_cursor(cursor: str | None) -> tuple[datetime | None, str | None]:
        if cursor is None:
            return None, None
        try:
            padding = "=" * (-len(cursor) % 4)
            payload = json.loads(base64.urlsafe_b64decode(cursor + padding))
            if set(payload) != {"timestamp", "eventId"}:
                raise ValueError
            timestamp = datetime.fromisoformat(payload["timestamp"])
            event_id = payload["eventId"]
            if timestamp.tzinfo is None or not isinstance(event_id, str) or not event_id:
                raise ValueError
        except (TypeError, ValueError, UnicodeDecodeError, json.JSONDecodeError):
            raise InvalidAuditCursorError from None
        return timestamp, event_id
