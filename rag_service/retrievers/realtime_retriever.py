from __future__ import annotations

from typing import Any, Dict, List

from ChatBackend.app.services.source_verifier_service import SourceVerifierService
from ..config import DEFAULT_RAG_CONFIG
from ..loaders.web_loader import WebLoader


class RealtimeRetriever:
    @classmethod
    def retrieve(
        cls,
        *,
        query: str,
        source_url: str = "",
        platform_hint: str = "",
        session_id: str = "",
        user_id: str = "",
    ) -> List[Dict[str, Any]]:
        result = WebLoader.load_context(
            title=query,
            source_url=source_url,
            platform_hint=platform_hint,
            session_id=session_id,
            user_id=user_id,
            max_candidates=DEFAULT_RAG_CONFIG.realtime_top_k,
        )
        if not result.get("success"):
            return []

        credibility = SourceVerifierService.verify(
            url=str(result.get("final_url") or ""),
            source_name=str(result.get("source_name") or ""),
            platform=platform_hint,
        )
        content = str(result.get("content_excerpt") or result.get("summary") or "")
        return [
            {
                "sourceType": "realtime_web",
                "sourceId": str(result.get("query_key") or ""),
                "fileId": "",
                "kbId": "",
                "title": str(result.get("matched_title") or result.get("query_title") or query),
                "content": content,
                "summary": str(result.get("summary") or content[: DEFAULT_RAG_CONFIG.chunk_preview_length]),
                "url": str(result.get("final_url") or ""),
                "publishedAt": str(result.get("published_at") or ""),
                "credibility": credibility.get("credibility_level", "medium"),
                "score": round(float(result.get("relevance_score") or 0.6), 4),
                "metadata": {
                    "sourceName": str(result.get("source_name") or ""),
                    "platformHint": platform_hint,
                    "candidateUrls": result.get("candidate_urls") or [],
                    "credibilityReason": credibility.get("reason", ""),
                    "sourceKind": credibility.get("source_type", ""),
                },
            }
        ]

