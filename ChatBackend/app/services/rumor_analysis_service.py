from __future__ import annotations

from typing import Any, Dict, List

from .overview_search_service import OverviewSearchService


class RumorAnalysisService:
    RUMOR_HINTS = ("谣言", "辟谣", "传言", "不实", "假的", "网传", "谣", "澄清")

    @classmethod
    def analyze(
        cls,
        *,
        query: str,
        source_url: str = "",
        platform_hint: str = "",
        session_id: str = "",
        user_id: str = "",
        max_results: int = 8,
    ) -> Dict[str, Any]:
        overview = OverviewSearchService.search(
            query=query,
            source_url=source_url,
            platform_hint=platform_hint,
            session_id=session_id,
            user_id=user_id,
            max_results=max_results,
        )
        items = list(overview.get("items") or [])
        normalized_query = str(query or "").strip()
        if not items:
            return {
                "success": False,
                "query": normalized_query,
                "verdict": "证据不足",
                "risk_level": "medium",
                "summary": f"未检索到与【{normalized_query}】直接相关的可验证材料，当前无法完成可靠谣言分析。",
                "known_facts": [],
                "to_verify": ["缺少可核验来源，需补充原始链接、发布时间或更明确的事件主体。"],
                "suggestions": ["优先补充原始爆料链接、首发平台和具体时间。"],
                "items": [],
            }

        high_cred = [item for item in items if str(item.get("credibility") or "") == "high"]
        medium_or_low = [item for item in items if str(item.get("credibility") or "") != "high"]
        rumor_hint = any(token in normalized_query for token in cls.RUMOR_HINTS)

        known_facts = [
            f"{item.get('title')}（{item.get('source_name') or item.get('platform') or '未知来源'}）"
            for item in high_cred[:4]
        ]
        to_verify = [
            f"{item.get('title')}：{item.get('credibility_reason') or item.get('time_reason') or '需进一步核验'}"
            for item in medium_or_low[:4]
        ]

        if rumor_hint and high_cred:
            verdict = "存在可核验材料，需区分事实与传播性说法"
            risk_level = "medium"
        elif rumor_hint and not high_cred:
            verdict = "高风险传言，当前缺少高可信佐证"
            risk_level = "high"
        elif high_cred:
            verdict = "当前更像普通事件讨论，未发现明确谣言定性依据"
            risk_level = "low"
        else:
            verdict = "证据混杂，存在误传或旧闻翻炒风险"
            risk_level = "medium"

        suggestions = [
            "优先引用官方通报、主流媒体或原始声明，避免直接转述二手总结。",
            "对发布时间、首发平台和关键截图进行交叉核验，警惕旧闻翻炒。",
            "若需要对外回应，建议将“已知事实 / 待核实信息 / 判断建议”分层表达。",
        ]
        summary = (
            f"针对【{normalized_query}】共检索到 {len(items)} 条相关结果，"
            f"其中高可信来源 {len(high_cred)} 条。当前判断：{verdict}。"
        )
        return {
            "success": True,
            "query": normalized_query,
            "verdict": verdict,
            "risk_level": risk_level,
            "summary": summary,
            "known_facts": known_facts,
            "to_verify": to_verify,
            "suggestions": suggestions,
            "items": items,
        }
