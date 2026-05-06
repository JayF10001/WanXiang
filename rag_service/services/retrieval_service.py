from __future__ import annotations

from typing import Any, Dict

from ..retrievers.hybrid_retriever import HybridRetriever
from ..retrievers.structured_retriever import StructuredRetriever
from ..rerankers.citation_reranker import CitationReranker
from .query_router import QueryRouter


class RetrievalService:
    @classmethod
    def retrieve(
        cls,
        *,
        query: str,
        kb_id: str | None = None,
        user_id: str = "",
        source_url: str = "",
        platform_hint: str = "",
        session_id: str = "",
    ) -> Dict[str, Any]:
        route = QueryRouter.route(query)
        normalized_kb_id = None if kb_id == "__all__" else kb_id
        structured_result: Dict[str, Any] = {"sources": [], "filters": {}, "recordCount": 0}

        if bool(route.get("prefer_structured")) and bool(kb_id):
            structured_result = StructuredRetriever.retrieve(
                query=query,
                kb_id=normalized_kb_id,
                user_id=user_id,
            )

        if structured_result.get("sources"):
            sources = structured_result.get("sources") or []
            return {
                "route": route,
                "sources": sources,
                "structuredRecords": structured_result.get("records") or sources,
                "structuredFilters": structured_result.get("filters") or {},
                "structuredRecordCount": int(structured_result.get("recordCount") or 0),
                "structuredAggregations": structured_result.get("aggregations") or {},
                "usedRealtimeRetrieval": False,
                "groundingStatus": "grounded",
            }

        candidates = HybridRetriever.retrieve(
            query=query,
            kb_id=normalized_kb_id,
            user_id=user_id,
            source_url=source_url,
            platform_hint=platform_hint,
            session_id=session_id,
            include_realtime=bool(route.get("use_realtime")),
            include_internal=bool(kb_id),
            top_k=10,
        )
        sources = CitationReranker.rerank(query=query, candidates=candidates)
        return {
            "route": route,
            "sources": sources,
            "structuredRecords": [],
            "structuredFilters": {},
            "structuredRecordCount": 0,
            "structuredAggregations": {},
            "usedRealtimeRetrieval": bool(route.get("use_realtime")),
            "groundingStatus": "grounded" if sources else "ungrounded",
        }
