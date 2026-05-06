from __future__ import annotations

from typing import Dict

from ..config import DEFAULT_RAG_CONFIG


class QueryRouter:
    STRUCTURED_QUERY_TOKENS = (
        "名单", "获奖名单", "获奖情况", "哪些学校", "哪些院校", "哪些高校", "哪些人", "哪些学生",
        "几人", "多少人", "人数", "总数", "统计", "一等奖", "二等奖", "三等奖",
        "A组", "B组", "C组", "晋级", "进入决赛", "决赛", "学校", "院校", "高校", "姓名",
    )

    @staticmethod
    def route(query: str) -> Dict[str, object]:
        normalized = str(query or "").strip()
        if not normalized:
            return {"intent": "empty", "use_realtime": False, "use_internal": False}

        use_realtime = any(keyword in normalized for keyword in DEFAULT_RAG_CONFIG.time_sensitive_keywords)
        asks_for_sources = any(token in normalized for token in ("来源", "出处", "引用", "依据", "证据"))
        prefers_structured = any(token in normalized for token in QueryRouter.STRUCTURED_QUERY_TOKENS)
        use_internal = True

        return {
            "intent": "structured_kb_query" if prefers_structured else ("grounded_answer" if (use_realtime or asks_for_sources) else "kb_augmented_answer"),
            "use_realtime": use_realtime or asks_for_sources,
            "use_internal": use_internal,
            "prefer_structured": prefers_structured,
        }
