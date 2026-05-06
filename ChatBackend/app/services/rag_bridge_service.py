from __future__ import annotations

from typing import Any, Dict

from ChatBackend.app.extensions import db
from rag_service.services.answer_service import AnswerService
from rag_service.services.retrieval_service import RetrievalService
from rag_service.services.query_router import QueryRouter


class RagBridgeService:
    @staticmethod
    def _user_has_indexed_knowledge(user_id: str = "") -> bool:
        if not user_id:
            return False
        try:
            return bool(db.knowledge_chunks.find_one({"owner_user_id": str(user_id)}))
        except Exception:
            return False

    @classmethod
    def should_use_rag(
        cls,
        *,
        query: str,
        kb_id: str = "",
        user_id: str = "",
        source_url: str = "",
        platform_hint: str = "",
    ) -> bool:
        route = QueryRouter.route(query)
        if kb_id:
            return True
        if route.get("use_realtime") or route.get("intent") == "grounded_answer":
            return True
        if source_url or platform_hint:
            return True
        return False

    @staticmethod
    def answer_with_rag(
        *,
        query: str,
        kb_id: str | None = None,
        user_id: str = "",
        source_url: str = "",
        platform_hint: str = "",
        session_id: str = "",
        settings: Dict[str, Any] | None = None,
    ) -> Dict[str, Any]:
        retrieval_result = RetrievalService.retrieve(
            query=query,
            kb_id=kb_id,
            user_id=user_id,
            source_url=source_url,
            platform_hint=platform_hint,
            session_id=session_id,
        )
        answer_result = AnswerService.answer(
            query=query,
            retrieval_result=retrieval_result,
            settings=settings,
        )
        return {
            **answer_result,
            "route": retrieval_result.get("route") or {},
        }
