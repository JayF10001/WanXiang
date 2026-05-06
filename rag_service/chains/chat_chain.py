from __future__ import annotations

from typing import Any, Dict, List


class ChatChain:
    @staticmethod
    def _build_citation_lines(citations: List[Dict[str, Any]]) -> str:
        if not citations:
            return "暂无可用证据片段。"
        lines = []
        for index, item in enumerate(citations[:8], start=1):
            title = str(item.get("title") or f"来源 {index}")
            summary = str(item.get("quote") or item.get("summary") or item.get("content") or "")[:220]
            credibility = str(item.get("credibility") or "unknown")
            published_at = str(item.get("publishedAt") or "")
            url = str(item.get("url") or "")
            source_id = str(item.get("sourceId") or item.get("fileId") or f"source-{index}")
            lines.append(
                f"{index}. 片段ID：{source_id}\n标题：{title}\n可信度：{credibility}\n时间：{published_at or '未知'}\n摘要：{summary}\n链接：{url or '无'}"
            )
        return "\n\n".join(lines)

    @classmethod
    def build_messages(cls, *, query: str, retrieval_result: Dict[str, Any]) -> List[Dict[str, str]]:
        citations = retrieval_result.get("citations") or []
        grounding_status = retrieval_result.get("groundingStatus") or "ungrounded"
        system_prompt = (
            "你是 WanXiang 的 grounded answer 助手。"
            "请严格基于提供的证据片段作答，明确区分【已知事实】【待核实信息】【分析判断】。"
            "如果来源不足，不要把推断写成事实。"
            "如果材料只是局部片段，不要把局部片段概括成全量结论。"
            "除非来源能直接确认数量、范围、完整性，否则不要写死'共有X人'、'全部'、'均为'之类结论。"
        )
        user_prompt = (
            f"用户问题：{query}\n\n"
            f"groundingStatus：{grounding_status}\n\n"
            f"证据片段：\n{cls._build_citation_lines(citations)}\n\n"
            "请输出一段适合聊天展示的回答，要求：\n"
            "1. 优先给出结论和判断。\n"
            "2. 使用清晰结构，但不要过长。\n"
            "3. 不要编造未在来源中出现的确定性事实。\n"
            "4. 若材料不足以支持精确统计，请明确写成'从当前片段可见'或'材料显示部分名单中'。\n"
            "5. 只能根据证据片段作答，不要把不同片段强行拼接成未经证实的整体统计。\n"
            "6. 尽量引用学校、组别、奖项等可直接从材料中确认的信息。"
        )
        return [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ]
