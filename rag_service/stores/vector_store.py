from __future__ import annotations

from typing import Iterable, Sequence


class VectorStore:
    @staticmethod
    def cosine_similarity(left: Sequence[float] | Iterable[float], right: Sequence[float] | Iterable[float]) -> float:
        left_list = [float(item) for item in left]
        right_list = [float(item) for item in right]
        if not left_list or not right_list or len(left_list) != len(right_list):
            return 0.0

        score = sum(l * r for l, r in zip(left_list, right_list))
        if score < 0:
            return 0.0
        if score > 1:
            return 1.0
        return round(score, 6)
