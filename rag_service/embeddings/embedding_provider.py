from __future__ import annotations

from math import sqrt
from typing import Iterable, List

from ..config import DEFAULT_RAG_CONFIG
from ..splitters.chinese_splitter import ChineseSplitter


class EmbeddingProvider:
    @staticmethod
    def version() -> str:
        return DEFAULT_RAG_CONFIG.embedding_version

    @staticmethod
    def dimensions() -> int:
        return DEFAULT_RAG_CONFIG.embedding_dimensions

    @classmethod
    def embed_text(cls, text: str) -> List[float]:
        dims = cls.dimensions()
        vector = [0.0] * dims
        tokens = ChineseSplitter.tokenize(text or "")
        if not tokens:
            return vector

        for token in tokens:
            bucket = hash(token) % dims
            vector[bucket] += 1.0

        return cls._normalize(vector)

    @staticmethod
    def _normalize(values: Iterable[float]) -> List[float]:
        vector = [float(item) for item in values]
        norm = sqrt(sum(item * item for item in vector))
        if norm <= 0:
            return vector
        return [round(item / norm, 6) for item in vector]
