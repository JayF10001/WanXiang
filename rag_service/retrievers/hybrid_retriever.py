from __future__ import annotations

from typing import Dict, List

from ..config import DEFAULT_RAG_CONFIG
from .internal_retriever import InternalRetriever
from .realtime_retriever import RealtimeRetriever


class HybridRetriever:
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
        include_realtime: bool = True,
        include_internal: bool = True,
        top_k: int | None = None,
    ) -> List[Dict]:
        merged: List[Dict] = []
        seen = set()

        if include_internal:
            for item in InternalRetriever.retrieve(query=query, kb_id=kb_id, user_id=user_id):
                dedupe_key = ("internal", item.get("fileId"), item.get("summary"))
                if dedupe_key in seen:
                    continue
                seen.add(dedupe_key)
                merged.append(item)

        if include_realtime:
            for item in RealtimeRetriever.retrieve(
                query=query,
                source_url=source_url,
                platform_hint=platform_hint,
                session_id=session_id,
                user_id=user_id,
            ):
                dedupe_key = ("realtime", item.get("url"), item.get("summary"))
                if dedupe_key in seen:
                    continue
                seen.add(dedupe_key)
                merged.append(item)

        merged.sort(key=lambda item: float(item.get("score") or 0), reverse=True)
        return merged[: (top_k or DEFAULT_RAG_CONFIG.hybrid_top_k)]
