from __future__ import annotations

from typing import Any, Dict, List

from ..config import DEFAULT_RAG_CONFIG
from ..embeddings.embedding_provider import EmbeddingProvider
from ..loaders.file_loader import FileLoader
from ..splitters.chinese_splitter import ChineseSplitter
from ..stores.vector_store import VectorStore


class InternalRetriever:
    @staticmethod
    def _score(query: str, text: str) -> float:
        query_terms = ChineseSplitter.tokenize(query)
        text_terms = ChineseSplitter.tokenize(text)
        if not query_terms or not text_terms:
            return 0.0

        text_term_set = set(text_terms)
        matched = sum(1 for term in query_terms if term in text_term_set)
        return matched / max(len(set(query_terms)), 1)

    @classmethod
    def _vector_score(cls, query_embedding: List[float], item: Dict[str, Any]) -> float:
        embedding = item.get("embedding") or []
        if not isinstance(embedding, list) or not embedding:
            return 0.0
        return VectorStore.cosine_similarity(query_embedding, embedding)

    @classmethod
    def retrieve(
        cls,
        *,
        query: str,
        kb_id: str | None = None,
        user_id: str | None = None,
        top_k: int | None = None,
    ) -> List[Dict[str, Any]]:
        candidates = FileLoader.load_knowledge_chunks(kb_id=kb_id, user_id=user_id)
        query_embedding = EmbeddingProvider.embed_text(query)
        scored: List[Dict[str, Any]] = []
        for item in candidates:
            content = str(item.get("content") or "")
            keyword_score = cls._score(query, content)
            vector_score = cls._vector_score(query_embedding, item)
            score = (
                keyword_score * DEFAULT_RAG_CONFIG.keyword_score_weight
                + vector_score * DEFAULT_RAG_CONFIG.vector_score_weight
            )
            if score <= 0:
                continue
            scored.append(
                {
                    "sourceType": "knowledge_chunk",
                    "sourceId": str(item.get("_id") or ""),
                    "fileId": str(item.get("file_id") or ""),
                    "kbId": str(item.get("kb_id") or ""),
                    "title": str((item.get("metadata") or {}).get("originalFilename") or "知识库文档"),
                    "content": content,
                    "summary": content[: DEFAULT_RAG_CONFIG.chunk_preview_length],
                    "url": "",
                    "publishedAt": "",
                    "credibility": "high",
                    "score": round(score, 4),
                    "keywordScore": round(keyword_score, 4),
                    "vectorScore": round(vector_score, 4),
                    "metadata": item.get("metadata") or {},
                }
            )
        scored.sort(key=lambda item: item["score"], reverse=True)
        return scored[: (top_k or DEFAULT_RAG_CONFIG.internal_top_k)]
