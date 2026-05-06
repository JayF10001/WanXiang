from __future__ import annotations

import re
from typing import Any, Dict, List


class TimelineService:
    DATE_PATTERNS = (
        r"(\d{4}[/-]\d{1,2}[/-]\d{1,2})",
        r"(\d{4}年\d{1,2}月\d{1,2}日)",
    )

    @staticmethod
    def _clean_text(value: str, limit: int = 400) -> str:
        text = re.sub(r"\s+", " ", str(value or "")).strip()
        return text[:limit]

    @classmethod
    def _extract_time(cls, text: str, fallback: str = "") -> str:
        cleaned = cls._clean_text(text, limit=600)
        for pattern in cls.DATE_PATTERNS:
            matched = re.search(pattern, cleaned)
            if matched and matched.group(1):
                return matched.group(1)
        return str(fallback or "").strip()

    @classmethod
    def _extract_event(cls, title: str, content: str) -> str:
        normalized_title = cls._clean_text(title, limit=120)
        if normalized_title:
            return normalized_title
        sentences = re.split(r"[。！？!?；;\n]", str(content or ""))
        for sentence in sentences:
            cleaned = cls._clean_text(sentence, limit=180)
            if len(cleaned) >= 12:
                return cleaned
        return cls._clean_text(content, limit=180)

    @classmethod
    def _extract_actor(cls, title: str, content: str) -> str:
        candidates = re.findall(r"[\u4e00-\u9fff]{2,8}", f"{title} {content}")
        for candidate in candidates:
            if candidate not in {"热点", "事件", "分析", "报道", "消息", "记者", "来源"}:
                return candidate
        return ""

    @classmethod
    def extract(cls, *, documents: List[Dict[str, Any]]) -> Dict[str, Any]:
        timeline: List[Dict[str, str]] = []
        for index, document in enumerate(documents or []):
            if not isinstance(document, dict):
                continue
            title = str(document.get("title") or "").strip()
            content = str(document.get("content") or document.get("summary") or document.get("content_excerpt") or "").strip()
            source = str(document.get("source") or document.get("source_name") or document.get("url") or f"文档{index + 1}").strip()
            published_at = str(document.get("published_at") or document.get("publishedAt") or "").strip()
            if not any([title, content, source]):
                continue

            event = cls._extract_event(title, content)
            if not event:
                continue
            timeline.append(
                {
                    "time": cls._extract_time(content or title, fallback=published_at),
                    "event": event,
                    "actor": cls._extract_actor(title, content),
                    "source": source,
                }
            )

        timeline.sort(key=lambda item: item.get("time") or "9999-99-99")
        return {
            "timeline": timeline,
            "count": len(timeline),
        }
