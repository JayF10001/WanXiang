from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class RAGConfig:
    internal_top_k: int = 5
    structured_top_k: int = 12
    realtime_top_k: int = 3
    hybrid_top_k: int = 6
    rerank_candidate_k: int = 10
    rerank_output_k: int = 6
    chunk_preview_length: int = 220
    embedding_dimensions: int = 128
    embedding_version: str = "hash-embedding-v1"
    keyword_score_weight: float = 0.35
    vector_score_weight: float = 0.65
    time_sensitive_keywords: tuple[str, ...] = (
        "今天", "今日", "昨天", "最近", "刚刚", "最新", "目前", "本周", "本月", "今年",
        "2024", "2025", "2026", "今日舆情", "最新进展",
    )


DEFAULT_RAG_CONFIG = RAGConfig()
