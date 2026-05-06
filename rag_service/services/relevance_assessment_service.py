"""检索结果相关性评估服务 - Relevance Assessment Service

评估知识库检索结果的相关性，决定是否需要触发聚合搜索。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List

from ..splitters.chinese_splitter import ChineseSplitter


@dataclass(frozen=True)
class RelevanceAssessmentResult:
    """相关性评估结果"""
    is_relevant: bool  # 检索结果是否相关
    relevance_score: float  # 整体相关性分数 [0, 1]
    top_score: float  # 最高单项分数
    matched_count: int  # 匹配到的结果数量
    low_relevance_items: int  # 低相关性项目数
    recommendation: str  # 建议（use_knowledge_base / trigger_search）
    reasoning: str  # 推理说明


class RelevanceAssessmentService:
    """检索结果相关性判断服务"""

    # 相关性阈值
    HIGH_RELEVANCE_THRESHOLD = 0.35  # 高相关性阈值
    LOW_RELEVANCE_THRESHOLD = 0.15  # 低相关性阈值（触发搜索）
    MIN_MATCHED_ITEMS = 2  # 最少匹配项目数

    # 知识库内容陈旧关键词（出现这些关键词的查询，知识库结果权重降低）
    TIME_SENSITIVE_PATTERNS = (
        "今天", "昨日", "最新", "刚刚", "最近", "目前", "此刻",
        "当前", "现在", "2024", "2025", "2026",
    )

    @classmethod
    def assess_retrieval_relevance(
        cls,
        query: str,
        retrieval_result: Dict[str, Any],
    ) -> RelevanceAssessmentResult:
        """评估知识库检索结果的相关性

        Args:
            query: 用户查询
            retrieval_result: RetrievalService.retrieve() 返回的结果

        Returns:
            RelevanceAssessmentResult: 包含相关性评估结果
        """
        sources = retrieval_result.get("sources") or []

        if not sources:
            return RelevanceAssessmentResult(
                is_relevant=False,
                relevance_score=0.0,
                top_score=0.0,
                matched_count=0,
                low_relevance_items=0,
                recommendation="trigger_search",
                reasoning="知识库检索结果为空，建议触发聚合搜索",
            )

        # 计算各项分数
        scores = []
        for item in sources:
            score = float(item.get("score") or 0)
            keyword_score = float(item.get("keywordScore") or 0)
            vector_score = float(item.get("vectorScore") or 0)

            # 综合分数
            combined = score * 0.5 + keyword_score * 0.25 + vector_score * 0.25
            scores.append(combined)

        top_score = max(scores) if scores else 0.0
        avg_score = sum(scores) / len(scores) if scores else 0.0
        matched_count = sum(1 for s in scores if s >= cls.LOW_RELEVANCE_THRESHOLD)
        low_relevance_count = sum(1 for s in scores if s < cls.LOW_RELEVANCE_THRESHOLD)

        # 判断是否为时间敏感查询
        is_time_sensitive = any(
            kw in str(query)
            for kw in cls.TIME_SENSITIVE_PATTERNS
        )

        # 时间敏感查询的知识库结果权重降低
        effective_avg = avg_score * 0.7 if is_time_sensitive else avg_score

        # 决策逻辑
        if top_score < cls.LOW_RELEVANCE_THRESHOLD:
            recommendation = "trigger_search"
            reasoning = f"最高相关性分数({top_score:.3f})低于阈值({cls.LOW_RELEVANCE_THRESHOLD})，知识库内容不相关"
        elif matched_count < cls.MIN_MATCHED_ITEMS:
            recommendation = "trigger_search"
            reasoning = f"匹配项目数({matched_count})少于最低要求({cls.MIN_MATCHED_ITEMS})"
        elif effective_avg < cls.HIGH_RELEVANCE_THRESHOLD and is_time_sensitive:
            recommendation = "trigger_search"
            reasoning = f"时间敏感查询，但知识库平均相关性({effective_avg:.3f})不足"
        elif low_relevance_count > len(scores) * 0.5:
            recommendation = "trigger_search"
            reasoning = f"超过50%检索结果({low_relevance_count}/{len(scores)})为低相关性"
        else:
            recommendation = "use_knowledge_base"
            reasoning = f"知识库检索结果相关，平均分{avg_score:.3f}，最高分{top_score:.3f}"

        return RelevanceAssessmentResult(
            is_relevant=recommendation == "use_knowledge_base",
            relevance_score=effective_avg,
            top_score=top_score,
            matched_count=matched_count,
            low_relevance_items=low_relevance_count,
            recommendation=recommendation,
            reasoning=reasoning,
        )

    @classmethod
    def assess_semantic_relevance(
        cls,
        query: str,
        text: str,
    ) -> float:
        """评估单个文本与查询的语义相关性

        使用关键词重叠度作为快速判断指标。
        """
        if not query or not text:
            return 0.0

        query_terms = set(ChineseSplitter.tokenize(query))
        text_terms = set(ChineseSplitter.tokenize(text))

        if not query_terms:
            return 0.0

        # Jaccard 相似度
        intersection = query_terms & text_terms
        union = query_terms | text_terms

        return len(intersection) / len(union) if union else 0.0

    @classmethod
    def get_retrieval_stats(
        cls,
        retrieval_result: Dict[str, Any],
    ) -> Dict[str, Any]:
        """获取检索结果的统计信息

        Returns:
            dict: 包含 total, avg_score, top_score, by_source_type 等
        """
        sources = retrieval_result.get("sources") or []
        if not sources:
            return {
                "total": 0,
                "avg_score": 0.0,
                "top_score": 0.0,
                "by_source_type": {},
            }

        scores = [float(s.get("score") or 0) for s in sources]
        by_source_type: Dict[str, int] = {}
        for item in sources:
            st = item.get("sourceType", "unknown")
            by_source_type[st] = by_source_type.get(st, 0) + 1

        return {
            "total": len(sources),
            "avg_score": round(sum(scores) / len(scores), 4),
            "top_score": round(max(scores), 4),
            "by_source_type": by_source_type,
        }
