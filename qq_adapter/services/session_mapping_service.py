from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from threading import Lock

from ..config import settings


@dataclass
class SessionBinding:
    session_id: str
    updated_at: datetime


class SessionMappingService:
    def __init__(self) -> None:
        self._store: dict[str, SessionBinding] = {}
        self._lock = Lock()

    def get_session_id(self, *, qq_user_id: str | None) -> str | None:
        key = str(qq_user_id or "")
        if not key:
            return None
        now = datetime.now(UTC)
        with self._lock:
            binding = self._store.get(key)
            if not binding:
                return None
            if now - binding.updated_at > timedelta(seconds=settings.session_ttl_seconds):
                self._store.pop(key, None)
                return None
            binding.updated_at = now
            return binding.session_id

    def bind_session(self, *, qq_user_id: str | None, session_id: str) -> None:
        key = str(qq_user_id or "")
        if not key:
            return
        with self._lock:
            self._store[key] = SessionBinding(session_id=session_id, updated_at=datetime.now(UTC))


session_mapping_service = SessionMappingService()
