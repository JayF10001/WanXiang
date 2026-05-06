"""
prerequisite_service.py
前置工具检查服务

在调用报告生成、策略生成等目标前，自动检查并执行前置依赖工具。
"""

import re

from .chat_service import ChatService


# 前置依赖配置：key = 目标名称，value = 需要的前置工具列表
TOOL_PREREQUISITES = {
    "report.generate": ["chat.search_overview", "chat.analyze_rumor"],
    "strategy.generate": ["chat.search_overview", "chat.analyze_rumor"],
}


def get_unmet_prerequisites(session_id, target):
    """返回未满足的前置工具列表"""
    session = ChatService.get_chat_session(session_id)
    if not session:
        return []
    tool_results = session.get('tool_results', {})
    required = TOOL_PREREQUISITES.get(target, [])
    return [t for t in required if not tool_results.get(t, {}).get('executed', False)]


def execute_prerequisite(session_id, tool_name, query, user_id):
    """执行单个前置工具，返回结果或抛异常"""
    from wanxiang_mcp.adapters.chatbackend_chat import (
        execute_search_overview_sync,
        execute_analyze_rumor_sync,
    )
    if tool_name == "chat.search_overview":
        return execute_search_overview_sync(session_id, query, user_id)
    elif tool_name == "chat.analyze_rumor":
        return execute_analyze_rumor_sync(session_id, query, user_id)
    else:
        raise ValueError(f"未知的前置工具: {tool_name}")


def _sanitize_prerequisite_query(content: str) -> str:
    """清洗报告/策略类指令，尽量保留检索主题与限定词。"""
    query = str(content or "").strip()
    if not query:
        return ""

    direct_replacements = [
        "请围绕",
        "围绕",
        "请针对",
        "针对",
        "请就",
        "就",
        "请关于",
        "关于",
        "结合",
        "基于",
        "参考",
        "聚焦",
        "从",
    ]
    for token in direct_replacements:
        query = query.replace(token, " ")

    replacements = [
        (r"^[请麻烦帮我你先再继续：:\s]+", ""),
        (r"^(请你|请帮我|帮我|麻烦你|麻烦)\s*", ""),
        (r"(生成|输出|整理|撰写|写一份|写个|做一份|给我做|给我出|给出)\s*(一份|一个|一版)?\s*(完整|正式|结构化|简要|详细|深度)?\s*(舆情|传播|公关|风险|事件)?\s*(分析|研判|总结)?\s*(报告|策略|建议|材料)", " "),
        (r"(请|需要|想要|用于)?\s*(生成|输出|整理|撰写)\s*(报告|策略|建议|材料)", " "),
        (r"(怎么看|帮我分析|请分析|分析一下|研判一下)$", " "),
        (r"\b请\b", " "),
        (r"[，。；、：:（）()【】\\[\\]\"'“”‘’]+", " "),
        (r"\s+", " "),
    ]
    for pattern, repl in replacements:
        query = re.sub(pattern, repl, query, flags=re.IGNORECASE)

    query = query.translate(str.maketrans({
        "，": " ",
        "。": " ",
        "；": " ",
        "、": " ",
        "：": " ",
        ":": " ",
        "（": " ",
        "）": " ",
        "【": " ",
        "】": " ",
        "“": " ",
        "”": " ",
        "‘": " ",
        "’": " ",
    }))
    query = re.sub(r"\s+", " ", query).strip(" ,，。；、：:")
    query = query.strip()
    if len(query) < 6:
        return str(content or "").strip()[:500]
    return query[:500]


def extract_query_from_session(session_id):
    """从会话历史中提取 query（取用户最新一条消息内容）"""
    from .report_service import ReportService
    messages = ReportService.get_session_messages(session_id)
    if not messages:
        return None
    for msg in reversed(messages):
        if msg.get("role") == "user":
            content = msg.get("content", "").strip()
            if content and len(content) > 5:
                return _sanitize_prerequisite_query(content)
    return None
