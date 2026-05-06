from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
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

    def _make_key(self, *, open_id: str | None, chat_id: str | None) -> str:
        return f"{chat_id or 'private'}::{open_id or 'unknown'}"

    def get_session_id(self, *, open_id: str | None, chat_id: str | None) -> str | None:
        key = self._make_key(open_id=open_id, chat_id=chat_id)
        with self._lock:
            binding = self._store.get(key)
            if not binding:
                return None
            if datetime.utcnow() - binding.updated_at > timedelta(seconds=settings.session_ttl_seconds):
                self._store.pop(key, None)
                return None
            binding.updated_at = datetime.utcnow()
            return binding.session_id

    def bind_session(self, *, open_id: str | None, chat_id: str | None, session_id: str) -> None:
        key = self._make_key(open_id=open_id, chat_id=chat_id)
        with self._lock:
            self._store[key] = SessionBinding(session_id=session_id, updated_at=datetime.utcnow())


session_mapping_service = SessionMappingService()
