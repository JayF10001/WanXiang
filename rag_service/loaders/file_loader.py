from __future__ import annotations

from typing import Any, Dict, List

from ChatBackend.app.extensions import db


class FileLoader:
    @staticmethod
    def load_knowledge_chunks(*, kb_id: str | None = None, user_id: str | None = None) -> List[Dict[str, Any]]:
        query: Dict[str, Any] = {}
        if kb_id:
            query["kb_id"] = str(kb_id)
        if user_id:
            query["owner_user_id"] = str(user_id)

        try:
            cursor = db.knowledge_chunks.find(query or {})
            items = list(cursor)
        except Exception:
            items = []
        return [dict(item) for item in items]

    @staticmethod
    def load_knowledge_records(*, kb_id: str | None = None, user_id: str | None = None) -> List[Dict[str, Any]]:
        query: Dict[str, Any] = {}
        if kb_id:
            query["kb_id"] = str(kb_id)
        if user_id:
            query["owner_user_id"] = str(user_id)

        try:
            cursor = db.knowledge_records.find(query or {})
            items = list(cursor)
        except Exception:
            items = []
        return [dict(item) for item in items]
