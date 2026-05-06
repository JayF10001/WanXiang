"""工具语义路由服务 - Tool Routing Service

提供基于规则和语义向量的工具匹配能力，帮助 LLM 更准确地判断用户意图并选择合适的工具。
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple
import re

from math import sqrt

from rag_service.embeddings.embedding_provider import EmbeddingProvider
from rag_service.splitters.chinese_splitter import ChineseSplitter


# 工具语义画像
_TOOL_PROFILES: Dict[str, "ToolSemanticProfile"] = {}
_initialized: bool = False


@dataclass(frozen=True)
class ToolSemanticProfile:
    """工具语义画像"""
    name: str
    description: str
    trigger_scenarios: List[str]  # 触发场景关键词
    embedding: List[float]

    # 语义标签
    is_aggregated_search: bool = False
    is_fact_check: bool = False
    is_time_dependent: bool = False
    is_source_verification: bool = False
    requires_urls: bool = False


def _compute_cosine_similarity(a: List[float], b: List[float]) -> float:
    """计算两个向量的余弦相似度"""
    if len(a) != len(b) or not a or not b:
        return 0.0
    dot_product = sum(x * y for x, y in zip(a, b))
    norm_a = sqrt(sum(x * x for x in a))
    norm_b = sqrt(sum(x * x for x in b))
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return dot_product / (norm_a * norm_b)


def _normalize_vector(values: List[float]) -> List[float]:
    """L2 归一化"""
    norm = sqrt(sum(x * x for x in values))
    if norm <= 0:
        return values
    return [round(x / norm, 6) for x in values]


# 触发场景关键词
AGGREGATED_SEARCH_TRIGGERS = (
    "最新", "今天", "昨日", "最近", "刚刚", "进展", "动态", "舆情",
    "热搜", "排行", "排行", "热点", "爆发", "全面", "overview",
    "搜索", "search", "全面了解", "整体情况", "概览",
)

FACT_CHECK_TRIGGERS = (
    "谣言", "假的", "是真的吗", "核实", "验证", "传言",
    "传闻", "未经证实", "rumor", "fake", "verify", "辟谣",
    "假消息", "不实", "消息", "新闻",
)

TIME_DEPENDENT_TRIGGERS = (
    "时间线", "先后", "过程", "演变", "发展", "历时",
    "timeline", "何时", "先后顺序", "发展历程", "演进",
)

SOURCE_VERIFICATION_TRIGGERS = (
    "来源", "出处", "链接", "网站", "可靠吗", "可信吗",
    "官方", "主流媒体", "source", "url", "link", "链接",
)

URL_PATTERNS = re.compile(r"https?://|www\.|\.com|\.cn|\.org|链接|网址", re.IGNORECASE)

# 工具描述
TOOL_DESCRIPTIONS = {
    "chat.search_overview": """聚合搜索工具：用于获取话题的全面可验证信息。

触发场景：
- 用户询问热点事件、最新进展、舆论态势
- 需要多源交叉验证的事实核查
- 知识库检索结果不相关或内容陈旧时自动启用
- 时间敏感型查询（"今天"、"最新"、"刚刚"等）

功能：同时调用 DuckDuckGo + Tavily 双引擎搜索，整合知识库内容，返回结构化可验证结果。

输入：query（搜索主题）、source_url（可选来源）、platform_hint（平台提示）
输出：包含标题、链接、可信度评分、来源类型的搜索结果列表""",

    "chat.analyze_rumor": """谣言分析工具：识别和核实传言真伪。

触发场景：
- 用户询问"是真的吗"、"谣言"、"假消息"
- 涉及传闻、未经官方证实的信息
- 社交媒体流传的未经核实内容

功能：分析传言内容，输出已知事实、待核实点、传播风险、澄清建议

输入：query（疑似谣言内容）
输出：事实核查报告""",

    "chat.verify_source_credibility": """来源可信度校验工具。

触发场景：
- 用户提供URL或来源名称
- 需要核实新闻来源可靠性
- 评估信息可信度

功能：识别官方源、主流媒体、搜索页、导航页和社交平台

输入：source（URL或来源名）、platform（平台类型）
输出：可信度等级（high/medium/low）和原因""",

    "chat.extract_timeline": """时间线提取工具。

触发场景：
- 用户询问事件发展脉络
- 需要梳理事件先后顺序
- "先后"、"过程"、"演变"等时间相关查询

功能：从多篇材料中提取结构化时间线

输入：query（主题）、urls（可选材料列表）
输出：按时间排序的事件列表""",

    "chat.get_hotspot_context": """热点上下文工具。

触发场景：
- 用户提及具体热点标题
- 需要获取热点事件的详细背景
- 热度查询、平台分布分析

功能：获取热点标题的上下文，包括平台、热度、原始链接

输入：title（热点标题）
输出：热点详情""",

    "chat.search_web": """DuckDuckGo 网页搜索工具。

触发场景：
- 用户直接要求搜索网页内容
- 需要获取互联网上的公开信息

功能：使用 DuckDuckGo 搜索引擎，返回标题、链接和摘要片段

输入：query（搜索词）、max_results（结果数量，默认5）
输出：搜索结果列表""",

    "chat.load_urls": """网页内容加载工具。

触发场景：
- 用户提供了具体的 URL 列表
- 需要加载指定网页的详细内容

功能：加载 URL 列表的网页内容，返回每页的标题、正文和来源

输入：urls（URL 列表）
输出：网页内容列表""",
}


def _initialize_tool_profiles() -> None:
    """初始化工具语义画像"""
    global _initialized, _TOOL_PROFILES
    if _initialized:
        return

    tool_definitions = [
        {
            "name": "chat.search_overview",
            "description": TOOL_DESCRIPTIONS["chat.search_overview"],
            "is_aggregated_search": True,
            "is_time_dependent": True,
        },
        {
            "name": "chat.analyze_rumor",
            "description": TOOL_DESCRIPTIONS["chat.analyze_rumor"],
            "is_fact_check": True,
        },
        {
            "name": "chat.verify_source_credibility",
            "description": TOOL_DESCRIPTIONS["chat.verify_source_credibility"],
            "is_source_verification": True,
            "requires_urls": True,
        },
        {
            "name": "chat.extract_timeline",
            "description": TOOL_DESCRIPTIONS["chat.extract_timeline"],
            "is_time_dependent": True,
        },
        {
            "name": "chat.get_hotspot_context",
            "description": TOOL_DESCRIPTIONS["chat.get_hotspot_context"],
            "is_aggregated_search": True,
            "is_time_dependent": True,
        },
        {
            "name": "chat.search_web",
            "description": TOOL_DESCRIPTIONS["chat.search_web"],
            "is_aggregated_search": True,
        },
        {
            "name": "chat.load_urls",
            "description": TOOL_DESCRIPTIONS["chat.load_urls"],
            "requires_urls": True,
        },
    ]

    for tool_def in tool_definitions:
        embedding = EmbeddingProvider.embed_text(tool_def["description"])
        _TOOL_PROFILES[tool_def["name"]] = ToolSemanticProfile(
            name=tool_def["name"],
            description=tool_def["description"],
            trigger_scenarios=_extract_trigger_keywords(tool_def["description"]),
            embedding=embedding,
            is_aggregated_search=tool_def.get("is_aggregated_search", False),
            is_fact_check=tool_def.get("is_fact_check", False),
            is_time_dependent=tool_def.get("is_time_dependent", False),
            is_source_verification=tool_def.get("is_source_verification", False),
            requires_urls=tool_def.get("requires_urls", False),
        )

    _initialized = True


def _extract_trigger_keywords(description: str) -> List[str]:
    """从描述中提取触发关键词"""
    tokens = ChineseSplitter.tokenize(description)
    stopwords = {"的", "是", "在", "了", "和", "与", "或", "及", "用于", "包含", "触发", "场景"}
    return [t for t in tokens if t not in stopwords and len(t) >= 2]


class ToolRoutingService:
    """工具语义路由服务"""

    @classmethod
    def route_query_to_tools(
        cls,
        query: str,
        kb_timestamp: Optional[datetime] = None,
        kb_relevant: bool = True,
        top_k: int = 3,
    ) -> List[Tuple[str, float, str]]:
        """路由查询到相关工具

        Args:
            query: 用户查询
            kb_timestamp: 知识库最新更新时间
            kb_relevant: 知识库检索结果是否相关
            top_k: 返回前 k 个最相关工具

        Returns:
            List of (tool_name, score, reason) tuples sorted by relevance
        """
        _initialize_tool_profiles()

        normalized_query = str(query or "").strip().lower()
        if not normalized_query:
            return []

        tool_scores: List[Tuple[str, float, str]] = []

        # 1. 规则匹配分数（高精度）
        rule_scores = cls._compute_rule_based_scores(normalized_query, kb_timestamp, kb_relevant)

        # 2. 语义向量分数
        semantic_scores = {}
        query_embedding = EmbeddingProvider.embed_text(normalized_query)
        for tool_name, profile in _TOOL_PROFILES.items():
            semantic_scores[tool_name] = _compute_cosine_similarity(query_embedding, profile.embedding)

        # 3. 融合分数
        for tool_name, profile in _TOOL_PROFILES.items():
            rule_score = rule_scores.get(tool_name, 0.0)
            semantic_score = semantic_scores.get(tool_name, 0.0)

            # 加权融合：规则 60% + 语义 40%
            final_score = rule_score * 0.6 + semantic_score * 0.4

            if final_score > 0.1:
                reason = cls._generate_match_reason(tool_name, normalized_query, rule_score, semantic_score)
                tool_scores.append((tool_name, final_score, reason))

        # 排序并返回 top_k
        tool_scores.sort(key=lambda x: x[1], reverse=True)
        return tool_scores[:top_k]

    @classmethod
    def _compute_rule_based_scores(
        cls,
        query: str,
        kb_timestamp: Optional[datetime],
        kb_relevant: bool,
    ) -> Dict[str, float]:
        """基于规则的工具匹配分数"""
        scores: Dict[str, float] = {}

        # 时间敏感检测
        is_time_sensitive = any(kw in query for kw in TIME_DEPENDENT_TRIGGERS)

        # 聚合搜索检测
        is_aggregated_search_query = any(kw in query for kw in AGGREGATED_SEARCH_TRIGGERS)

        # 事实核查检测
        is_fact_check_query = any(kw in query for kw in FACT_CHECK_TRIGGERS)

        # 来源验证检测
        is_source_verification_query = any(kw in query for kw in SOURCE_VERIFICATION_TRIGGERS)

        # URL/链接检测
        has_url_mention = bool(URL_PATTERNS.search(query))

        # 知识库过期检测
        kb_stale = False
        if kb_timestamp:
            age_days = (datetime.utcnow() - kb_timestamp).days
            kb_stale = age_days > 30

        # 知识库不相关检测
        kb_irrelevant = not kb_relevant

        for tool_name, profile in _TOOL_PROFILES.items():
            score = 0.0

            if profile.is_aggregated_search:
                if is_aggregated_search_query:
                    score += 0.5
                if is_time_sensitive:
                    score += 0.3
                if kb_stale:
                    score += 0.4
                if kb_irrelevant:
                    score += 0.5

            if profile.is_fact_check and is_fact_check_query:
                score += 0.8

            if profile.is_source_verification and (is_source_verification_query or has_url_mention):
                score += 0.7

            if profile.is_time_dependent:
                # 时间依赖工具：时间敏感查询给高加成
                if is_time_sensitive:
                    score += 0.7
                elif is_aggregated_search_query:
                    score += 0.3

            if profile.requires_urls and has_url_mention:
                score += 0.4

            scores[tool_name] = min(score, 1.0)

        return scores

    @classmethod
    def _generate_match_reason(
        cls,
        tool_name: str,
        query: str,
        rule_score: float,
        semantic_score: float,
    ) -> str:
        """生成匹配原因说明"""
        reasons = []

        if rule_score > 0.3:
            if "search_overview" in tool_name:
                reasons.append("触发聚合搜索场景")
            if "rumor" in tool_name or "analyze_rumor" in tool_name:
                reasons.append("触发谣言核实场景")
            if "source" in tool_name or "credibility" in tool_name:
                reasons.append("触发来源验证场景")
            if "timeline" in tool_name:
                reasons.append("触发时间线提取场景")

        if semantic_score > 0.5:
            reasons.append("语义高度相关")
        elif semantic_score > 0.3:
            reasons.append("语义中度相关")

        return "; ".join(reasons) if reasons else "通用匹配"

    @classmethod
    def get_tool_description(cls, tool_name: str) -> Optional[str]:
        """获取工具的增强描述"""
        return TOOL_DESCRIPTIONS.get(tool_name)

    @classmethod
    def is_time_sensitive_query(cls, query: str) -> bool:
        """判断查询是否为时间敏感型"""
        normalized = str(query or "").strip().lower()
        return any(kw in normalized for kw in TIME_DEPENDENT_TRIGGERS)

    @classmethod
    def is_fact_check_query(cls, query: str) -> bool:
        """判断查询是否为事实核查型"""
        normalized = str(query or "").strip().lower()
        return any(kw in normalized for kw in FACT_CHECK_TRIGGERS)
