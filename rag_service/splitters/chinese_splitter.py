from __future__ import annotations

import re


class ChineseSplitter:
    @staticmethod
    def tokenize(text: str) -> list[str]:
        normalized = re.sub(r"\s+", " ", str(text or "")).strip().lower()
        if not normalized:
            return []
        return re.findall(r"[\u4e00-\u9fff]{2,}|[a-z0-9]{2,}", normalized)

