"""工具触发决策引擎 - Tool Trigger Decision Engine

综合知识库新鲜度、检索结果相关性，做出工具触发决策。
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

from .knowledge_timestamp_service import KnowledgeTimestampService, TimestampCheckResult
from .relevance_assessment_service import RelevanceAssessmentService, RelevanceAssessmentResult

# 延迟导入避免循环依赖
_tool_routing_service = None


def _get_tool_routing_service():
    global _tool_routing_service
    if _tool_routing_service is None:
        from wanxiang_mcp.tools.tool_routing_service import ToolRoutingService
        _tool_routing_service = ToolRoutingService
    return _tool_routing_service


@dataclass(frozen=True)
class TriggerDecision:
    """触发决策结果"""
    should_force_search: bool  # 是否强制触发聚合搜索
    force_search_reason: str  # 强制搜索原因
    recommended_tools: List[Tuple[str, float, str]]  # 推荐工具列表 (name, score, reason)
    use_knowledge_base: bool  # 是否使用知识库
    kb_timestamp_info: Optional[TimestampCheckResult]  # 知识库时间戳信息


class ToolTriggerDecisionEngine:
    """工具触发决策引擎

    决策流程：
    1. 检查知识库时间戳（是否 > 30天）
    2. 如果知识库时间戳陈旧 → 直接触发聚合搜索
    3. 如果知识库时间戳新鲜 → 执行知识库检索，评估相关性
    4. 如果检索结果不相关 → 触发聚合搜索
    5. 综合推荐工具列表
    """

    # 自动触发搜索的场景
    AUTO_TRIGGER_SCENARIOS = {
        "kb_stale": "知识库内容超过30天未更新",
        "kb_irrelevant": "知识库检索结果不相关",
        "kb_empty": "知识库检索结果为空",
        "time_sensitive": "查询具有强时间敏感性",
    }

    # 时间敏感关键词
    TIME_SENSITIVE_KEYWORDS = (
        "今天", "昨日", "最新", "刚刚", "最近", "此刻", "当前",
        "2024", "2025", "2026", "今日", "本周", "本月",
    )

    @classmethod
    def make_decision(
        cls,
        query: str,
        kb_id: Optional[str] = None,
        user_id: str = "",
        retrieval_result: Optional[Dict[str, Any]] = None,
    ) -> TriggerDecision:
        """做出工具触发决策

        Args:
            query: 用户查询
            kb_id: 知识库ID
            user_id: 用户ID
            retrieval_result: 可选，如果已执行过检索，直接传入结果

        Returns:
            TriggerDecision: 包含决策结果和推荐工具
        """
        decision_reasons: List[str] = []
        should_force_search = False

        # 1. 检查知识库时间戳新鲜度
        timestamp_result = KnowledgeTimestampService.check_knowledge_freshness(
            kb_id=kb_id,
            user_id=user_id,
        )

        if timestamp_result.is_stale:
            should_force_search = True
            decision_reasons.append(
                f"{cls.AUTO_TRIGGER_SCENARIOS['kb_stale']} "
                f"(最新更新: {timestamp_result.age_days}天前)"
            )

        # 2. 如果知识库为空，也应触发搜索
        if not timestamp_result.kb_has_content:
            should_force_search = True
            decision_reasons.append(cls.AUTO_TRIGGER_SCENARIOS["kb_empty"])

        # 3. 评估知识库检索结果相关性
        relevance_result: Optional[RelevanceAssessmentResult] = None
        if retrieval_result and not should_force_search:
            relevance_result = RelevanceAssessmentService.assess_retrieval_relevance(
                query=query,
                retrieval_result=retrieval_result,
            )

            if relevance_result.recommendation == "trigger_search":
                should_force_search = True
                decision_reasons.append(
                    f"{cls.AUTO_TRIGGER_SCENARIOS['kb_irrelevant']} "
                    f"({relevance_result.reasoning})"
                )

        # 4. 时间敏感性检查
        is_time_sensitive = any(
            kw in str(query)
            for kw in cls.TIME_SENSITIVE_KEYWORDS
        )
        if is_time_sensitive and not timestamp_result.is_stale:
            # 时间敏感但不陈旧
            if retrieval_result is None:
                # 未执行RAG，无法判断相关性，时间敏感查询应触发搜索
                should_force_search = True
                decision_reasons.append(cls.AUTO_TRIGGER_SCENARIOS["time_sensitive"])
            elif relevance_result and relevance_result.relevance_score < 0.4:
                # 已执行RAG但相关性低，触发搜索
                should_force_search = True
                decision_reasons.append(cls.AUTO_TRIGGER_SCENARIOS["time_sensitive"])

        # 5. 获取工具推荐
        ToolRoutingService = _get_tool_routing_service()

        kb_relevant = retrieval_result is not None and not should_force_search
        recommended_tools = ToolRoutingService.route_query_to_tools(
            query=query,
            kb_timestamp=timestamp_result.latest_update if timestamp_result else None,
            kb_relevant=kb_relevant,
            top_k=3,
        )

        # 如果强制搜索，确保 search_overview 在推荐列表首位
        if should_force_search and recommended_tools:
            search_overview_tool = "chat.search_overview"
            existing = [t[0] for t in recommended_tools]
            if search_overview_tool not in existing:
                # 将 search_overview 插入首位
                recommended_tools.insert(0, (search_overview_tool, 1.0, "自动触发聚合搜索"))

        return TriggerDecision(
            should_force_search=should_force_search,
            force_search_reason="; ".join(decision_reasons) if decision_reasons else "无",
            recommended_tools=recommended_tools,
            use_knowledge_base=not should_force_search,
            kb_timestamp_info=timestamp_result,
        )

    @classmethod
    def should_use_rag(cls, query: str, kb_id: Optional[str], user_id: str) -> bool:
        """快速判断是否应使用 RAG（知识库检索）

        这是一个轻量级判断，用于在调用完整的 make_decision 之前快速筛选。
        """
        # 检查时间敏感性
        is_time_sensitive = any(kw in str(query) for kw in cls.TIME_SENSITIVE_KEYWORDS)
        if is_time_sensitive:
            # 时间敏感查询，RAG 权重降低
            return False

        # 检查知识库新鲜度
        timestamp_result = KnowledgeTimestampService.check_knowledge_freshness(
            kb_id=kb_id,
            user_id=user_id,
        )

        if timestamp_result.is_stale or not timestamp_result.kb_has_content:
            return False

        return True

    @classmethod
    def get_trigger_stats(cls) -> Dict[str, Any]:
        """获取触发决策统计信息（用于调试）"""
        return {
            "auto_trigger_scenarios": cls.AUTO_TRIGGER_SCENARIOS,
            "time_sensitive_keywords": cls.TIME_SENSITIVE_KEYWORDS,
        }
