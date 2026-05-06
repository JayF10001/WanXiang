from __future__ import annotations

from typing import Any, Dict, List

from ..config import DEFAULT_RAG_CONFIG
from ..splitters.chinese_splitter import ChineseSplitter


class CitationReranker:
    HEADER_HINTS = (
        "获奖名单",
        "学校名称",
        "考生姓名",
        "科目名称",
        "奖项",
        "进入决赛",
        "准考证号",
        "省份",
    )

    LIST_QUERY_HINTS = (
        "名单",
        "获奖",
        "晋级",
        "决赛",
        "学校",
        "姓名",
        "哪些",
        "多少",
    )

    @staticmethod
    def _token_overlap_score(query: str, title: str, summary: str) -> float:
        query_terms = set(ChineseSplitter.tokenize(query))
        if not query_terms:
            return 0.0
        text_terms = set(ChineseSplitter.tokenize(f"{title}\n{summary}"))
        if not text_terms:
            return 0.0
        matched = sum(1 for term in query_terms if term in text_terms)
        return matched / max(len(query_terms), 1)

    @classmethod
    def _header_boost(cls, title: str, summary: str) -> float:
        text = f"{title}\n{summary}"
        hits = sum(1 for hint in cls.HEADER_HINTS if hint in text)
        return min(hits * 0.08, 0.32)

    @classmethod
    def _list_query_boost(cls, query: str, summary: str) -> float:
        if not any(hint in query for hint in cls.LIST_QUERY_HINTS):
            return 0.0
        hits = sum(1 for hint in cls.HEADER_HINTS if hint in summary)
        return min(hits * 0.06, 0.24)

    @staticmethod
    def _title_boost(query: str, title: str) -> float:
        if not title:
            return 0.0
        overlap = CitationReranker._token_overlap_score(query, title, "")
        return min(overlap * 0.45, 0.25)

    @staticmethod
    def _keyword_prior_boost(item: Dict[str, Any]) -> float:
        keyword_score = float(item.get("keywordScore") or 0.0)
        if keyword_score <= 0:
            return 0.0
        return min(keyword_score * 0.18, 0.18)

    @classmethod
    def rerank(cls, *, query: str, candidates: List[Dict[str, Any]], top_k: int | None = None) -> List[Dict[str, Any]]:
        reranked: List[Dict[str, Any]] = []
        for item in candidates:
            title = str(item.get("title") or "")
            summary = str(item.get("summary") or item.get("content") or "")
            base_score = float(item.get("score") or 0.0)
            overlap_score = cls._token_overlap_score(query, title, summary)
            rerank_score = (
                base_score * 0.55
                + overlap_score * 0.2
                + cls._title_boost(query, title)
                + cls._header_boost(title, summary)
                + cls._list_query_boost(query, summary)
                + cls._keyword_prior_boost(item)
            )
            reranked.append({
                **item,
                "baseScore": round(base_score, 4),
                "rerankScore": round(rerank_score, 4),
                "score": round(rerank_score, 4),
            })

        reranked.sort(key=lambda item: float(item.get("rerankScore") or item.get("score") or 0), reverse=True)
        return reranked[: (top_k or DEFAULT_RAG_CONFIG.rerank_output_k)]
