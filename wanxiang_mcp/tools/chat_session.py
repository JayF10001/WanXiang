"""MCP tools for 5.3 chat session and strategy module."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Dict, Generic, Iterable, List, Optional, Type, TypeVar

from pydantic import BaseModel

from wanxiang_mcp.adapters import chatbackend_chat
from wanxiang_mcp.runtime.context import parse_context
from wanxiang_mcp.schemas.chat import (
    AnalyzeMultimodalInput,
    AnalyzeVideoInput,
    CreateSessionInput,
    CrawlNewsContextInput,
    DeleteSessionInput,
    ExportChatInput,
    ExtractTimelineInput,
    GenerateSessionReportInput,
    GenerateStrategyInput,
    GetHotspotContextInput,
    GetMessagesInput,
    GetMindSpiderDeepSentimentInput,
    GetMindSpiderTopicAnalysisInput,
    GetTaskStatusInput,
    ListSessionsInput,
    OverviewSearchInput,
    RenameSessionInput,
    RumorAnalysisInput,
    RunMindSpiderDeepSentimentInput,
    RunMindSpiderTopicExtractionInput,
    SendMessageInput,
    SessionRefInput,
    StreamMessageInput,
    VerifySourceCredibilityInput,
    VerifyTimeConsistencyInput,
    SearchWebInput,
    LoadUrlsInput,
    DbAggregateInput,
    TextToSpeechInput,
    TextToSpeechAsyncInput,
)

InputModelT = TypeVar("InputModelT", bound=BaseModel)


@dataclass(frozen=True)
class MCPTool(Generic[InputModelT]):
    name: str
    description: str
    input_model: Type[InputModelT]
    handler: Callable[[Any, InputModelT], Any]

    def invoke(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        context = parse_context(payload.get("context") or {})
        input_data = self.input_model.model_validate(payload.get("input") or {})
        result = self.handler(context, input_data)
        if hasattr(result, "model_dump"):
            return result.model_dump(mode="json")
        return result

    def invoke_stream(self, payload: Dict[str, Any]) -> Iterable[Dict[str, Any]]:
        context = parse_context(payload.get("context") or {})
        input_data = self.input_model.model_validate(payload.get("input") or {})
        return self.handler(context, input_data)


def _tool(
    name: str,
    description: str,
    input_model: Type[InputModelT],
    handler: Callable[[Any, InputModelT], Any],
) -> MCPTool[InputModelT]:
    return MCPTool(
        name=name,
        description=description,
        input_model=input_model,
        handler=handler,
    )


CHAT_SESSION_TOOLS: List[MCPTool[Any]] = [
    _tool(
        "chat.create_session",
        "创建聊天会话，可选是否初始化欢迎消息。",
        CreateSessionInput,
        chatbackend_chat.create_session,
    ),
    _tool(
        "chat.list_sessions",
        "获取当前用户的聊天会话列表。",
        ListSessionsInput,
        chatbackend_chat.list_sessions,
    ),
    _tool(
        "chat.get_session",
        "获取指定会话详情。",
        SessionRefInput,
        chatbackend_chat.get_session,
    ),
    _tool(
        "chat.get_messages",
        "获取指定会话的历史消息。",
        GetMessagesInput,
        chatbackend_chat.get_messages,
    ),
    _tool(
        "chat.send_message",
        "向指定会话发送一条非流式消息。",
        SendMessageInput,
        chatbackend_chat.send_message,
    ),
    _tool(
        "chat.stream_message",
        "向指定会话发送一条流式消息。",
        StreamMessageInput,
        chatbackend_chat.stream_message,
    ),
    _tool(
        "chat.rename_session",
        "更新指定会话标题，并锁定手动标题。",
        RenameSessionInput,
        chatbackend_chat.rename_session,
    ),
    _tool(
        "chat.delete_session",
        "删除指定会话。",
        DeleteSessionInput,
        chatbackend_chat.delete_session,
    ),
    _tool(
        "chat.generate_report_from_session",
        "为指定会话生成正式分析报告。",
        GenerateSessionReportInput,
        chatbackend_chat.generate_report_from_session,
    ),
    _tool(
        "chat.generate_strategy",
        "启动公关策略生成任务。",
        GenerateStrategyInput,
        chatbackend_chat.generate_strategy,
    ),
    _tool(
        "chat.generate_strategy_sync",
        "同步生成公关策略，在异步任务不可用时作为降级方案。",
        GenerateStrategyInput,
        chatbackend_chat.generate_strategy_sync,
    ),
    _tool(
        "chat.search_overview",
        "对指定主题执行总览搜索，返回多条可验证结果、背景摘要和下一步建议。",
        OverviewSearchInput,
        chatbackend_chat.search_overview,
    ),
    _tool(
        "chat.analyze_rumor",
        "对指定主题执行谣言分析，返回已知事实、待核实点、传播风险与澄清建议。",
        RumorAnalysisInput,
        chatbackend_chat.analyze_rumor,
    ),
    _tool(
        "chat.get_task_status",
        "查询策略任务状态。",
        GetTaskStatusInput,
        chatbackend_chat.get_task_status,
    ),
    _tool(
        "chat.verify_source_credibility",
        "校验链接或来源名称的可信度，识别官方源、主流媒体、搜索页、导航页和社交平台。",
        VerifySourceCredibilityInput,
        chatbackend_chat.verify_source_credibility,
    ),
    _tool(
        "chat.verify_time_consistency",
        "校验材料时效性，识别旧闻翻炒、跨月跨年错配和当前热点时间不一致的问题。",
        VerifyTimeConsistencyInput,
        chatbackend_chat.verify_time_consistency,
    ),
    _tool(
        "chat.extract_timeline",
        "从多篇材料中提取结构化时间线。",
        ExtractTimelineInput,
        chatbackend_chat.extract_timeline,
    ),
    _tool(
        "chat.get_hotspot_context",
        "获取指定热点标题的上下文，包括平台、热度、原始链接和可用摘要。",
        GetHotspotContextInput,
        chatbackend_chat.get_hotspot_context,
    ),
    _tool(
        "chat.export_chat",
        "导出指定会话的 JSON 聊天记录。",
        ExportChatInput,
        chatbackend_chat.export_chat,
    ),
    _tool(
        "chat.crawl_news_context",
        "根据新闻标题和可选原始链接抓取相关新闻摘要与正文片段，并将结果存库。",
        CrawlNewsContextInput,
        chatbackend_chat.crawl_news_context,
    ),
    _tool(
        "chat.run_mindspider_topic_extraction",
        "运行最小接入版 MindSpider 热点话题提取，将热点新闻、关键词与总结存入 WanXiang 自己的 Mongo。",
        RunMindSpiderTopicExtractionInput,
        chatbackend_chat.run_mindspider_topic_extraction,
    ),
    _tool(
        "chat.get_mindspider_topic_analysis",
        "获取指定日期的 MindSpider 话题分析结果与对应热点新闻。",
        GetMindSpiderTopicAnalysisInput,
        chatbackend_chat.get_mindspider_topic_analysis,
    ),
    _tool(
        "chat.run_mindspider_deep_sentiment",
        "运行最小接入版 MindSpider DeepSentimentCrawling：基于一期关键词做多平台扩展抓取与情感聚合，异步存入 WanXiang 自己的 Mongo。",
        RunMindSpiderDeepSentimentInput,
        chatbackend_chat.run_mindspider_deep_sentiment,
    ),
    _tool(
        "chat.get_mindspider_deep_sentiment",
        "获取指定日期的 MindSpider 深度情感抓取结果。",
        GetMindSpiderDeepSentimentInput,
        chatbackend_chat.get_mindspider_deep_sentiment,
    ),
    _tool(
        "chat.search_web",
        "使用 DuckDuckGo 搜索互联网，返回标题、链接和摘要片段。",
        SearchWebInput,
        chatbackend_chat.search_web,
    ),
    _tool(
        "chat.load_urls",
        "加载指定 URL 列表的网页内容，返回每页的标题、正文和来源。",
        LoadUrlsInput,
        chatbackend_chat.load_urls,
    ),
    _tool(
        "chat.analyze_multimodal",
        "上传图片、音频或视频文件，执行统一多模态舆情分析，支持单轮最多 10 个文件。",
        AnalyzeMultimodalInput,
        chatbackend_chat.analyze_multimodal,
    ),
    _tool(
        "chat.analyze_video",
        "上传视频文件，通过 Google Gemini 进行多模态舆情分析，返回情感极性、摘要、关键词、风险等级等结构化结果。",
        AnalyzeVideoInput,
        chatbackend_chat.analyze_video,
    ),
    _tool(
        "chat.search_web_tavily",
        "使用 Tavily Search 搜索互联网。Tavily 是专为 AI/RAG 场景优化的搜索引擎，返回结果更干净、更适合模型阅读。",
        SearchWebInput,
        chatbackend_chat.search_web_tavily,
    ),
    _tool(
        "chat.db_aggregate",
        "通过预定义模板执行 MongoDB 聚合查询，支持话题热度、趋势、队列状态等分析。",
        DbAggregateInput,
        chatbackend_chat.db_aggregate,
    ),
    _tool(
        "chat.text_to_speech",
        "将指定文本转换为语音音频，返回可访问的音频 URL。支持多语言多音色，适用于舆情播报、话术演练等场景。",
        TextToSpeechInput,
        chatbackend_chat.text_to_speech,
    ),
    _tool(
        "chat.text_to_speech_async",
        "为指定 assistant 消息异步生成语音，不阻塞主对话流程。适用于对话完成后后台生成音频播放器。",
        TextToSpeechAsyncInput,
        chatbackend_chat.text_to_speech_async,
    ),
]

CHAT_SESSION_TOOL_MAP: Dict[str, MCPTool[Any]] = {
    tool.name: tool for tool in CHAT_SESSION_TOOLS
}


def list_chat_session_tools() -> List[Dict[str, str]]:
    """Return tool metadata for discovery/registration."""
    return [
        {
            "name": tool.name,
            "description": tool.description,
            "input_model": tool.input_model.__name__,
        }
        for tool in CHAT_SESSION_TOOLS
    ]


def get_chat_session_tool(name: str) -> Optional[MCPTool[Any]]:
    """Lookup a tool by name."""
    return CHAT_SESSION_TOOL_MAP.get(name)


def invoke_chat_session_tool(name: str, payload: Dict[str, Any]) -> Dict[str, Any]:
    """Invoke a registered chat-session MCP tool."""
    tool = get_chat_session_tool(name)
    if not tool:
        raise KeyError(f"Unknown MCP tool: {name}")
    return tool.invoke(payload)


def invoke_chat_session_stream_tool(name: str, payload: Dict[str, Any]) -> Iterable[Dict[str, Any]]:
    """Invoke a registered streaming chat-session MCP tool."""
    tool = get_chat_session_tool(name)
    if not tool:
        raise KeyError(f"Unknown MCP tool: {name}")
    return tool.invoke_stream(payload)
