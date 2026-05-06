"""Adapters from MCP chat tools to ChatBackend chat services."""

from __future__ import annotations

import json
import logging
import os
import sys
import time
from datetime import datetime
import uuid
from typing import Any, Dict, Iterator, Optional

from celery.result import AsyncResult
from openai import OpenAI

CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
WANXIANG_MCP_ROOT = os.path.dirname(CURRENT_DIR)
REPO_ROOT = os.path.dirname(WANXIANG_MCP_ROOT)
CHATBACKEND_ROOT = os.path.join(REPO_ROOT, "ChatBackend")

for path in (REPO_ROOT, CHATBACKEND_ROOT):
    if path not in sys.path:
        sys.path.insert(0, path)

from ChatBackend.app import create_app
from ChatBackend.celery_app import celery
from ChatBackend.app.extensions import db
from ChatBackend.app.services.chat_service import ChatService, safe_json_data
from ChatBackend.app.services.crawler_service import CrawlerService
from ChatBackend.app.services.overview_search_service import OverviewSearchService
from ChatBackend.app.services.mindspider_bridge_service import MindSpiderBridgeService
from ChatBackend.app.services.mindspider_deep_sentiment_service import MindSpiderDeepSentimentService
from ChatBackend.app.services.rag_bridge_service import RagBridgeService
from ChatBackend.app.services.report_service import ReportService
from ChatBackend.app.services.rumor_analysis_service import RumorAnalysisService
from ChatBackend.app.services.langchain_tool_service import LangChainToolService
from ChatBackend.app.services.source_verifier_service import SourceVerifierService
from ChatBackend.app.services.time_verifier_service import TimeVerifierService
from ChatBackend.app.services.timeline_service import TimelineService
from ChatBackend.app.services.tts_service import TTSService
from wanxiang_mcp.tools.function_converter import list_openai_functions

from wanxiang_mcp.schemas.chat import (
    AnalyzeMultimodalData,
    AnalyzeMultimodalInput,
    AnalyzeVideoData,
    AnalyzeVideoInput,
    AuthContext,
    RequestContext,
    ChatMessage,
    ChatSession,
    ChatSettings,
    CreateSessionData,
    CreateSessionInput,
    CrawlNewsContextData,
    CrawlNewsContextInput,
    DeleteSessionData,
    DeleteSessionInput,
    ExportChatData,
    ExportChatInput,
    ExtractTimelineData,
    ExtractTimelineInput,
    TimelineItemData,
    GenerateSessionReportData,
    GenerateStrategySyncData,
    GenerateSessionReportInput,
    GenerateStrategyData,
    GenerateStrategyInput,
    GetHotspotContextData,
    GetHotspotContextInput,
    GetMessagesData,
    GetMessagesInput,
    GetMindSpiderTopicAnalysisData,
    GetMindSpiderTopicAnalysisInput,
    GetMindSpiderDeepSentimentData,
    GetMindSpiderDeepSentimentInput,
    GetSessionData,
    GetTaskStatusData,
    GetTaskStatusInput,
    ListSessionsData,
    ListSessionsInput,
    MCPContext,
    MCPError,
    MCPMeta,
    MCPResponse,
    OverviewSearchData,
    OverviewSearchInput,
    OverviewSearchItemData,
    RenameSessionData,
    RenameSessionInput,
    RumorAnalysisData,
    RumorAnalysisInput,
    RunMindSpiderTopicExtractionData,
    RunMindSpiderTopicExtractionInput,
    RunMindSpiderDeepSentimentData,
    RunMindSpiderDeepSentimentInput,
    SendMessageData,
    SendMessageInput,
    SessionRefInput,
    StreamMessageInput,
    VerifySourceCredibilityData,
    VerifySourceCredibilityInput,
    VerifyTimeConsistencyData,
    VerifyTimeConsistencyInput,
    SearchWebInput,
    SearchWebData,
    LoadUrlsInput,
    LoadUrlsData,
    DbAggregateInput,
    DbAggregateData,
    TextToSpeechInput,
    TextToSpeechAsyncInput,
    TextToSpeechAsyncData,
    TextToSpeechData,
)


_APP = None
logger = logging.getLogger(__name__)


def get_flask_app():
    global _APP
    if _APP is None:
        _APP = create_app()
    return _APP


def _build_meta(context: MCPContext, started_at: float) -> MCPMeta:
    return MCPMeta(
        request_id=context.request.request_id,
        trace_id=context.request.trace_id,
        duration_ms=int((time.time() - started_at) * 1000),
    )


def _ok(context: MCPContext, started_at: float, data: Any) -> MCPResponse[Any]:
    return MCPResponse(success=True, data=data, error=None, meta=_build_meta(context, started_at))


def _err(context: MCPContext, started_at: float, code: str, message: str) -> MCPResponse[Any]:
    return MCPResponse(
        success=False,
        data=None,
        error=MCPError(code=code, message=message),
        meta=_build_meta(context, started_at),
    )


def _to_iso(value: Any) -> Optional[str]:
    if value is None:
        return None
    if isinstance(value, str):
        return value
    if isinstance(value, datetime):
        return value.isoformat()
    return str(value)


def _to_chat_settings(value: Dict[str, Any]) -> ChatSettings:
    return ChatSettings(
        model=value.get("model"),
        temperature=value.get("temperature"),
        enable_search=value.get("enable_search"),
    )


def _to_chat_message(value: Dict[str, Any]) -> Optional[ChatMessage]:
    role = value.get("role")
    if role not in {"user", "assistant"}:
        return None
    return ChatMessage(
        id=str(value.get("id") or value.get("_id") or ""),
        role=role,
        content=str(value.get("content") or ""),
        timestamp=_to_iso(value.get("timestamp")),
        render_mode=str(value.get("render_mode") or value.get("renderMode") or "") or None,
        message_type=str(value.get("message_type") or value.get("messageType") or "") or None,
        report_title=str(value.get("report_title") or value.get("reportTitle") or "") or None,
        report_status=str(value.get("report_status") or value.get("reportStatus") or "") or None,
        strategy_title=str(value.get("strategy_title") or value.get("strategyTitle") or "") or None,
        strategy_status=str(value.get("strategy_status") or value.get("strategyStatus") or "") or None,
        strategy_id=str(value.get("strategy_id") or value.get("strategyId") or "") or None,
        grounding_status=str(value.get("grounding_status") or value.get("groundingStatus") or "") or None,
        confidence=str(value.get("confidence") or "") or None,
        used_realtime_retrieval=bool(value.get("used_realtime_retrieval")) if value.get("used_realtime_retrieval") is not None else (
            bool(value.get("usedRealtimeRetrieval")) if value.get("usedRealtimeRetrieval") is not None else None
        ),
        sources=[safe_json_data(item) for item in (value.get("sources") or [])],
        citations=[safe_json_data(item) for item in (value.get("citations") or [])],
        facts=[str(item) for item in (value.get("facts") or [])],
        to_verify=[str(item) for item in (value.get("to_verify") or value.get("toVerify") or [])],
        analysis=[str(item) for item in (value.get("analysis") or [])],
        route=str(value.get("route") or "") or None,
        debug_mode=bool(value.get("debug_mode")) if value.get("debug_mode") is not None else (
            bool(value.get("debugMode")) if value.get("debugMode") is not None else None
        ),
        fallback_reason=str(value.get("fallback_reason") or value.get("fallbackReason") or "") or None,
        upstream_code=str(value.get("upstream_code") or value.get("upstreamCode") or "") or None,
        upstream_type=str(value.get("upstream_type") or value.get("upstreamType") or "") or None,
        phase=str(value.get("phase") or "") or None,
        search_timed_out=bool(value.get("search_timed_out")) if value.get("search_timed_out") is not None else (
            bool(value.get("searchTimedOut")) if value.get("searchTimedOut") is not None else None
        ),
        search_failed=bool(value.get("search_failed")) if value.get("search_failed") is not None else (
            bool(value.get("searchFailed")) if value.get("searchFailed") is not None else None
        ),
        fallback_level=int(value.get("fallback_level")) if value.get("fallback_level") is not None else (
            int(value.get("fallbackLevel")) if value.get("fallbackLevel") is not None else None
        ),
        final_model=str(value.get("final_model") or value.get("finalModel") or "") or None,
        degrade_reason=str(value.get("degrade_reason") or value.get("degradeReason") or "") or None,
        degrade_message=str(value.get("degrade_message") or value.get("degradeMessage") or "") or None,
        model_attempts=[safe_json_data(item) for item in (value.get("model_attempts") or value.get("modelAttempts") or [])],
        audio_url=str(value.get("audio_url") or value.get("audioUrl") or "") or None,
        tts_status=str(value.get("tts_status") or value.get("ttsStatus") or "") or None,
        tts_task_id=str(value.get("tts_task_id") or value.get("ttsTaskId") or "") or None,
        tts_provider=str(value.get("tts_provider") or value.get("ttsProvider") or "") or None,
        tts_duration_seconds=float(value.get("tts_duration_seconds")) if value.get("tts_duration_seconds") is not None else (
            float(value.get("ttsDurationSeconds")) if value.get("ttsDurationSeconds") is not None else None
        ),
        tts_error=str(value.get("tts_error") or value.get("ttsError") or "") or None,
    )


def _resolve_rag_context(input_data: SendMessageInput | StreamMessageInput) -> Dict[str, str]:
    recommendation_context = input_data.recommendation_context or {}
    return {
        "source_url": str(recommendation_context.get("sourceUrl") or recommendation_context.get("source_url") or "").strip(),
        "platform_hint": str(recommendation_context.get("platformHint") or recommendation_context.get("platform_hint") or "").strip(),
    }


def _build_rag_message_extra_fields(result: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "grounding_status": str(result.get("groundingStatus") or ""),
        "confidence": str(result.get("confidence") or ""),
        "used_realtime_retrieval": bool(result.get("usedRealtimeRetrieval")),
        "sources": safe_json_data(result.get("sources") or []),
        "citations": safe_json_data(result.get("citations") or []),
        "facts": [str(item) for item in (result.get("facts") or [])],
        "to_verify": [str(item) for item in (result.get("toVerify") or [])],
        "analysis": [str(item) for item in (result.get("analysis") or [])],
        "rag_route": safe_json_data(result.get("route") or {}),
    }


STREAM_ROUTE_MAIN = "assistant_sse"
STREAM_ROUTE_DEBUG = "debug_llm_stream"

CONTENT_SAFETY_FALLBACK_MESSAGE = "当前问题触发了上游内容安全限制，未能返回分析结果。请尝试更换表述或补充更多背景信息。"
MODEL_ACCOUNT_FALLBACK_MESSAGE = "当前模型服务不可用或账号状态异常，暂时无法返回分析结果，请稍后重试。"
TOOL_CALL_FALLBACK_MESSAGE = "当前工具调用协议异常，暂时无法返回分析结果，请稍后重试。"
GENERIC_UPSTREAM_FALLBACK_MESSAGE = "上游模型暂时未返回有效分析结果，请稍后重试。"


def _resolve_stream_route(debug_mode: bool) -> str:
    return STREAM_ROUTE_DEBUG if debug_mode else STREAM_ROUTE_MAIN


def _build_stream_event_data(
    *,
    debug_mode: bool,
    route: Optional[str] = None,
    **kwargs: Any,
) -> Dict[str, Any]:
    payload: Dict[str, Any] = {
        "route": route or _resolve_stream_route(debug_mode),
        "debugMode": bool(debug_mode),
    }
    for key, value in kwargs.items():
        if value is not None:
            payload[key] = value
    return safe_json_data(payload)


def _build_stream_message_extra_fields(
    *,
    debug_mode: bool,
    route: Optional[str] = None,
    grounding_status: Optional[str] = None,
    confidence: Optional[str] = None,
    used_realtime_retrieval: Optional[bool] = None,
    sources: Optional[list[Any]] = None,
    citations: Optional[list[Any]] = None,
    facts: Optional[list[Any]] = None,
    to_verify: Optional[list[Any]] = None,
    analysis: Optional[list[Any]] = None,
    fallback_reason: Optional[str] = None,
    upstream_code: Optional[str] = None,
    upstream_type: Optional[str] = None,
    phase: Optional[str] = None,
    search_timed_out: Optional[bool] = None,
    search_failed: Optional[bool] = None,
) -> Dict[str, Any]:
    extra_fields: Dict[str, Any] = {
        "route": route or _resolve_stream_route(debug_mode),
        "debug_mode": bool(debug_mode),
    }
    if grounding_status is not None:
        extra_fields["grounding_status"] = grounding_status
    if confidence is not None:
        extra_fields["confidence"] = confidence
    if used_realtime_retrieval is not None:
        extra_fields["used_realtime_retrieval"] = bool(used_realtime_retrieval)
    if sources is not None:
        extra_fields["sources"] = safe_json_data(sources)
    if citations is not None:
        extra_fields["citations"] = safe_json_data(citations)
    if facts is not None:
        extra_fields["facts"] = [str(item) for item in facts]
    if to_verify is not None:
        extra_fields["to_verify"] = [str(item) for item in to_verify]
    if analysis is not None:
        extra_fields["analysis"] = [str(item) for item in analysis]
    if fallback_reason is not None:
        extra_fields["fallback_reason"] = fallback_reason
    if upstream_code is not None:
        extra_fields["upstream_code"] = upstream_code
    if upstream_type is not None:
        extra_fields["upstream_type"] = upstream_type
    if phase is not None:
        extra_fields["phase"] = phase
    if search_timed_out is not None:
        extra_fields["search_timed_out"] = bool(search_timed_out)
    if search_failed is not None:
        extra_fields["search_failed"] = bool(search_failed)
    return extra_fields


def _classify_stream_exception(exc: Exception, phase: str = "llm") -> Dict[str, str]:
    raw_message = str(exc or "").strip()
    normalized = raw_message.lower()

    classification = {
        "fallbackReason": "generic_upstream_error",
        "upstreamCode": "upstream_error",
        "upstreamType": "upstream_error",
        "phase": phase,
        "fallbackMessage": GENERIC_UPSTREAM_FALLBACK_MESSAGE,
        "displayMessage": "上游模型暂时未返回有效分析结果，请稍后重试。",
    }

    if (
        "inappropriate-content" in normalized
        or "内容安全" in raw_message
        or "content safety" in normalized
        or "content policy" in normalized
    ):
        classification.update(
            {
                "fallbackReason": "content_safety",
                "upstreamCode": "inappropriate-content",
                "upstreamType": "content_safety",
                "fallbackMessage": CONTENT_SAFETY_FALLBACK_MESSAGE,
                "displayMessage": "当前问题触发了上游内容安全限制，请尝试更换表述或补充更多背景信息。",
            }
        )
        return classification

    if "arrearage" in normalized or "access denied" in normalized or "overdue-payment" in normalized:
        classification.update(
            {
                "fallbackReason": "model_account_unavailable",
                "upstreamCode": "Arrearage" if "arrearage" in normalized else "access_denied",
                "upstreamType": "account_unavailable",
                "fallbackMessage": MODEL_ACCOUNT_FALLBACK_MESSAGE,
                "displayMessage": "模型服务当前不可用或账号异常，请稍后重试。",
            }
        )
        return classification

    if "function.arguments" in normalized or "invalidparameter" in normalized or "must be in json format" in normalized:
        classification.update(
            {
                "fallbackReason": "tool_call_invalid_json",
                "upstreamCode": "InvalidParameter" if "invalidparameter" in normalized else "function.arguments",
                "upstreamType": "tool_call_protocol_error",
                "phase": "tool_call",
                "fallbackMessage": TOOL_CALL_FALLBACK_MESSAGE,
                "displayMessage": "工具调用协议异常，当前无法完成分析，请稍后重试。",
            }
        )
        return classification

    return classification


def _bind_tool_args_to_current_session(
    func_name: str,
    args_dict: Dict[str, Any],
    current_session_id: str,
) -> Dict[str, Any]:
    """Force session-bound tool calls to use the active chat session."""
    safe_args = dict(args_dict or {})
    try:
        from wanxiang_mcp.tools.chat_session import get_chat_session_tool

        tool = get_chat_session_tool(func_name)
        model_fields = getattr(getattr(tool, "input_model", None), "model_fields", {}) if tool else {}
        if "session_id" not in model_fields:
            return safe_args

        incoming_session_id = str(safe_args.get("session_id") or "").strip()
        if incoming_session_id != current_session_id:
            logger.info(
                "Binding tool %s session_id from %r to current session %s",
                func_name,
                incoming_session_id,
                current_session_id,
            )
        safe_args["session_id"] = current_session_id
        return safe_args
    except Exception as exc:
        logger.warning(
            "Failed to bind tool %s to current session %s: %s",
            func_name,
            current_session_id,
            exc,
        )
        return safe_args


def _yield_text_as_stream(text: str) -> Iterator[Dict[str, Any]]:
    buffer_size = 12
    content = str(text or "")
    for offset in range(0, len(content), buffer_size):
        chunk = content[offset: offset + buffer_size]
        if chunk:
            yield {"event": "message", "data": {"chunk": chunk}}


def _build_overview_sources(items: list[dict]) -> list[dict]:
    sources = []
    citations = []
    for index, item in enumerate(items, start=1):
        title = str(item.get("title") or "")
        url = str(item.get("url") or "")
        quote = str(item.get("content_excerpt") or item.get("summary") or "")
        source = {
            "title": title,
            "url": url,
            "sourceType": "realtime_web",
            "summary": str(item.get("summary") or ""),
            "snippet": quote[:220],
            "credibility": str(item.get("credibility") or "medium"),
            "publishedAt": str(item.get("published_at") or ""),
            "score": float(item.get("relevance_score") or 0),
            "keywordScore": float(item.get("relevance_score") or 0),
            "vectorScore": 0.0,
        }
        citation = {
            "id": f"overview-citation-{index}",
            "title": title,
            "url": url,
            "sourceType": "realtime_web",
            "credibility": str(item.get("credibility") or "medium"),
            "publishedAt": str(item.get("published_at") or ""),
            "sourceTitle": title,
            "sourceUrl": url,
            "quote": quote[:800],
            "score": float(item.get("relevance_score") or 0),
            "keywordScore": float(item.get("relevance_score") or 0),
            "vectorScore": 0.0,
        }
        sources.append(source)
        citations.append(citation)
    return [sources, citations]


def _build_overview_assistant_content(query: str, items: list[dict]) -> str:
    if not items:
        return f"当前未检索到与【{query}】直接相关的可验证结果，建议补充更明确的主体、时间或原始链接。"

    lines = [
        f"### 【总览搜索】",
        f"- 主题：{query}",
        f"- 检索结果：共找到 {len(items)} 条较相关结果",
        "",
        "### 【关键信息源】",
    ]
    for item in items[:10]:
        published_at = str(item.get("published_at") or "").strip()
        source_name = str(item.get("source_name") or item.get("platform") or "未知来源").strip()
        lines.append(
            f"- {item.get('title') or '未命名结果'}"
            f"（来源：{source_name}"
            f"{f'，时间：{published_at}' if published_at else ''}）"
        )
    lines.extend(
        [
            "",
            "### 【下一步建议】",
            "- 优先阅读高可信来源的原文或正式报道，避免只依据搜索入口页下结论。",
            "- 若需进一步生成报告或策略，可在此基础上继续追问传播脉络、风险点和动作建议。",
        ]
    )
    return "\n".join(lines)


def _build_rumor_assistant_content(result: dict) -> str:
    query = str(result.get("query") or "")
    verdict = str(result.get("verdict") or "证据不足")
    risk_level = str(result.get("risk_level") or "medium")
    known_facts = [str(item) for item in (result.get("known_facts") or []) if str(item).strip()]
    to_verify = [str(item) for item in (result.get("to_verify") or []) if str(item).strip()]
    suggestions = [str(item) for item in (result.get("suggestions") or []) if str(item).strip()]

    lines = [
        "### 【谣言分析】",
        f"- 主题：{query}",
        f"- 当前判断：{verdict}",
        f"- 风险级别：{risk_level}",
        "",
        "### 【已知事实】",
    ]
    if known_facts:
        lines.extend(f"- {item}" for item in known_facts[:5])
    else:
        lines.append("- 暂无足够高可信材料支持直接定性。")

    lines.extend(["", "### 【待核实信息】"])
    if to_verify:
        lines.extend(f"- {item}" for item in to_verify[:5])
    else:
        lines.append("- 当前未发现明显待核实异常点。")

    lines.extend(["", "### 【建议动作】"])
    lines.extend(f"- {item}" for item in suggestions[:3])
    return "\n".join(lines)


def _to_chat_session(value: Dict[str, Any]) -> ChatSession:
    visible_messages = []
    for item in value.get("messages", []) or []:
        parsed = _to_chat_message(item)
        if parsed is not None:
            visible_messages.append(parsed)

    return ChatSession(
        id=str(value.get("_id") or value.get("id")),
        title=str(value.get("title") or "新对话"),
        title_locked=bool(value.get("title_locked")),
        created_at=_to_iso(value.get("created_at")),
        updated_at=_to_iso(value.get("updated_at")),
        settings=_to_chat_settings(value.get("settings") or {}),
        messages=visible_messages,
    )


def _get_owned_session_or_error(context: MCPContext, session_id: str):
    session = ChatService.get_chat_session(session_id)
    if not session:
        return None, "not_found", "聊天会话不存在"
    if str(session.get("user_id")) != context.auth.user_id:
        return None, "forbidden", "无权访问此聊天会话"
    return session, None, None


def _build_recommendation_context_message(context_data: Optional[Dict[str, Any]]) -> str:
    payload = context_data or {}
    lines = ["【推荐热点上下文】"]
    title = str(payload.get("title") or "").strip()
    platform_hint = str(payload.get("platformHint") or payload.get("platform_hint") or "").strip()
    source_url = str(payload.get("sourceUrl") or payload.get("source_url") or "").strip()
    published_at = str(payload.get("publishedAt") or payload.get("published_at") or "").strip()
    summary = str(payload.get("summary") or "").strip()
    source_label = str(payload.get("sourceLabel") or payload.get("source_label") or "").strip()
    if title:
        lines.append(f"标题：{title}")
    if platform_hint:
        lines.append(f"来源平台：{platform_hint}")
    if source_label and source_label != platform_hint:
        lines.append(f"来源标签：{source_label}")
    if published_at:
        lines.append(f"更新时间：{published_at}")
    if source_url:
        lines.append(f"原始链接：{source_url}")
    if summary:
        lines.append(f"热点摘要：{summary}")
    return "\n".join(lines)


def _persist_recommendation_context_message(session_id: str, context_data: Optional[Dict[str, Any]]) -> None:
    message = _build_recommendation_context_message(context_data)
    if message.strip() == "【推荐热点上下文】":
        return
    ChatService.add_message(session_id, "system", message)


def _normalize_title_key(value: str) -> str:
    return "".join(str(value or "").strip().lower().split())


def _score_hotspot_candidate(candidate: Dict[str, Any], title: str, platform_hint: str = "", source_url: str = "") -> float:
    normalized_title = _normalize_title_key(title)
    candidate_title = _normalize_title_key(candidate.get("title") or "")
    candidate_platform = _normalize_title_key(candidate.get("platform") or candidate.get("type") or "")
    normalized_platform_hint = _normalize_title_key(platform_hint)
    candidate_url = str(candidate.get("url") or candidate.get("mobil_url") or "").strip()

    score = 0.0
    if normalized_title and candidate_title == normalized_title:
        score += 5.0
    elif normalized_title and candidate_title and (normalized_title in candidate_title or candidate_title in normalized_title):
        score += 3.0
    if normalized_platform_hint and normalized_platform_hint in candidate_platform:
        score += 1.5
    if source_url and candidate_url and source_url == candidate_url:
        score += 4.0
    rank = candidate.get("index")
    try:
        rank_value = int(rank)
        score += max(0.0, 1.5 - min(rank_value, 20) * 0.05)
    except Exception:
        pass
    return score


def _find_hotspot_candidate(title: str, platform_hint: str = "", source_url: str = "") -> Dict[str, Any]:
    best_candidate: Dict[str, Any] | None = None
    best_score = 0.0
    try:
        cursor = db.hot_news.find({}, {"_id": 0})
        for item in cursor:
            score = _score_hotspot_candidate(item, title, platform_hint=platform_hint, source_url=source_url)
            if score > best_score:
                best_candidate = item
                best_score = score
    except Exception:
        return {}

    if best_candidate and best_score >= 2.5:
        return {**best_candidate, "_match_score": best_score}
    return {}


def create_session(context: MCPContext, input_data: CreateSessionInput) -> MCPResponse[CreateSessionData]:
    started_at = time.time()
    app = get_flask_app()
    with app.app_context():
        session_id = ChatService.create_chat_session(context.auth.user_id)
        if not session_id:
            return _err(context, started_at, "internal_error", "创建聊天会话失败")

        session = ChatService.get_chat_session(session_id)
        if input_data.initialize_conversation:
            welcome_msg = (
                "👋 您好！我是您的AI公关策略顾问。我将通过对话引导您完成信息输入，"
                "结合实时热点分析，为您自动生成一份专业的公关商业整合策略报告。"
                "整个过程我会处理所有技术细节，您只需要专注于事件本身就好啦。\n\n"
                "为了开始，请告诉我您需要处理的舆情事件主要涉及哪个**垂直领域**？"
                "（例如：汽车、教育、医药、科技、食品等）"
            )
            ChatService.add_message(session_id, "assistant", welcome_msg)
            session = ChatService.get_chat_session(session_id)

        session = ChatService.sanitize_session_for_client(session)
        return _ok(context, started_at, CreateSessionData(session=_to_chat_session(session)))


def list_sessions(context: MCPContext, input_data: ListSessionsInput) -> MCPResponse[ListSessionsData]:
    started_at = time.time()
    app = get_flask_app()
    with app.app_context():
        sessions = ChatService.get_chat_sessions(context.auth.user_id)
        parsed = []
        for item in sessions:
            sanitized = ChatService.sanitize_session_for_client(item)
            parsed.append(_to_chat_session(sanitized))
        return _ok(context, started_at, ListSessionsData(sessions=parsed))


def get_session(context: MCPContext, input_data: SessionRefInput) -> MCPResponse[GetSessionData]:
    started_at = time.time()
    app = get_flask_app()
    with app.app_context():
        session, code, message = _get_owned_session_or_error(context, input_data.session_id)
        if not session:
            return _err(context, started_at, code, message)
        session = ChatService.sanitize_session_for_client(session)
        return _ok(context, started_at, GetSessionData(session=_to_chat_session(session)))


def get_messages(context: MCPContext, input_data: GetMessagesInput) -> MCPResponse[GetMessagesData]:
    started_at = time.time()
    app = get_flask_app()
    with app.app_context():
        session, code, message = _get_owned_session_or_error(context, input_data.session_id)
        if not session:
            return _err(context, started_at, code, message)

        messages = ChatService.get_chat_history(input_data.session_id)
        visible = ChatService.filter_client_visible_messages(messages)
        parsed = [msg for item in visible if (msg := _to_chat_message(item)) is not None]
        return _ok(
            context,
            started_at,
            GetMessagesData(session_id=input_data.session_id, messages=parsed),
        )


def rename_session(context: MCPContext, input_data: RenameSessionInput) -> MCPResponse[RenameSessionData]:
    started_at = time.time()
    app = get_flask_app()
    with app.app_context():
        session, code, message = _get_owned_session_or_error(context, input_data.session_id)
        if not session:
            return _err(context, started_at, code, message)

        if not str(input_data.title).strip():
            return _err(context, started_at, "invalid_input", "标题不能为空")

        result = ChatService.update_session_title(input_data.session_id, input_data.title, manual=True)
        if not result:
            return _err(context, started_at, "internal_error", "更新聊天会话标题失败")

        return _ok(
            context,
            started_at,
            RenameSessionData(
                session_id=input_data.session_id,
                title=input_data.title,
                title_locked=True,
            ),
        )


def delete_session(context: MCPContext, input_data: DeleteSessionInput) -> MCPResponse[DeleteSessionData]:
    started_at = time.time()
    app = get_flask_app()
    with app.app_context():
        session, code, message = _get_owned_session_or_error(context, input_data.session_id)
        if not session:
            return _err(context, started_at, code, message)

        result = ChatService.delete_chat_session(input_data.session_id)
        if not result:
            return _err(context, started_at, "internal_error", "删除聊天会话失败")

        return _ok(
            context,
            started_at,
            DeleteSessionData(session_id=input_data.session_id, deleted=True),
        )


def send_message(context: MCPContext, input_data: SendMessageInput) -> MCPResponse[SendMessageData]:
    started_at = time.time()
    app = get_flask_app()
    with app.app_context():
        session, code, message = _get_owned_session_or_error(context, input_data.session_id)
        if not session:
            return _err(context, started_at, code, message)

        if not str(input_data.message).strip():
            return _err(context, started_at, "invalid_input", "消息内容不能为空")

        if input_data.recommendation_context:
            _persist_recommendation_context_message(input_data.session_id, input_data.recommendation_context)
        ChatService.add_message(input_data.session_id, "user", input_data.message)
        settings = session.get("settings", {})
        rag_context = _resolve_rag_context(input_data)
        rag_result = None
        if RagBridgeService.should_use_rag(
            query=input_data.message,
            kb_id=str(input_data.kb_id or ""),
            user_id=context.auth.user_id,
            source_url=rag_context["source_url"],
            platform_hint=rag_context["platform_hint"],
        ):
            rag_result = RagBridgeService.answer_with_rag(
                query=input_data.message,
                kb_id=str(input_data.kb_id or "") or None,
                user_id=context.auth.user_id,
                source_url=rag_context["source_url"],
                platform_hint=rag_context["platform_hint"],
                session_id=input_data.session_id,
                settings=settings,
            )
            response = str(rag_result.get("answer") or "")
            ChatService.add_message(
                input_data.session_id,
                "assistant",
                response,
                extra_fields=_build_rag_message_extra_fields(rag_result),
            )
        else:
            messages = ChatService.get_chat_history(input_data.session_id)
            response = ChatService.get_model_response(messages, settings)
            ChatService.add_message(input_data.session_id, "assistant", response)

        assistant_message = _to_chat_message({
            "role": "assistant",
            "content": response,
            **(_build_rag_message_extra_fields(rag_result) if rag_result else {}),
        }) or ChatMessage(role="assistant", content=response)
        return _ok(
            context,
            started_at,
            SendMessageData(
                session_id=input_data.session_id,
                assistant_message=assistant_message,
            ),
        )


def generate_strategy(
    context: MCPContext,
    input_data: GenerateStrategyInput,
) -> MCPResponse[GenerateStrategyData]:
    started_at = time.time()
    app = get_flask_app()
    with app.app_context():
        session, code, message = _get_owned_session_or_error(context, input_data.session_id)
        if not session:
            return _err(context, started_at, code, message)

        strategy_title = f"{str(input_data.event_summary or '').strip()[:24] or '当前事件'}传播策略"
        ChatService.add_message(
            input_data.session_id,
            "assistant",
            "好的，我正在整合所有信息，准备生成策略...",
            extra_fields={
                "message_type": "strategy_plan",
                "render_mode": "strategy_card",
                "status": "streaming",
                "strategy_status": "generating",
                "strategy_title": strategy_title,
            },
        )

        task = ChatService.generate_pr_strategy.delay(
            input_data.session_id,
            {
                "event_summary": input_data.event_summary,
                "fact_check": input_data.fact_check,
                "initial_actions": input_data.initial_actions,
                "short_term_goals": input_data.short_term_goals,
                "mid_term_goals": input_data.mid_term_goals,
                "long_term_goals": input_data.long_term_goals,
                "time_constraints": input_data.time_constraints,
                "budget_constraints": input_data.budget_constraints,
                "additional_info": input_data.additional_info,
            },
        )

        return _ok(
            context,
            started_at,
            GenerateStrategyData(task_id=task.id, session_id=input_data.session_id),
        )


def generate_strategy_sync(
    context: MCPContext,
    input_data: GenerateStrategyInput,
) -> MCPResponse[GenerateStrategySyncData]:
    started_at = time.time()
    app = get_flask_app()
    with app.app_context():
        session, code, message = _get_owned_session_or_error(context, input_data.session_id)
        if not session:
            return _err(context, started_at, code, message)

        result = ChatService.generate_pr_strategy.run(
            input_data.session_id,
            {
                "event_summary": input_data.event_summary,
                "fact_check": input_data.fact_check,
                "initial_actions": input_data.initial_actions,
                "short_term_goals": input_data.short_term_goals,
                "mid_term_goals": input_data.mid_term_goals,
                "long_term_goals": input_data.long_term_goals,
                "time_constraints": input_data.time_constraints,
                "budget_constraints": input_data.budget_constraints,
                "additional_info": input_data.additional_info,
            },
        )
        if str(result.get("status") or "") != "success":
            return _err(
                context,
                started_at,
                "upstream_error",
                str(result.get("error") or "策略生成失败"),
            )

        return _ok(
            context,
            started_at,
            GenerateStrategySyncData(
                session_id=input_data.session_id,
                strategy_id=str(result.get("strategy_id") or ""),
                message="策略已同步生成并写入当前会话",
            ),
        )


def analyze_multimodal(
    context: MCPContext,
    input_data: AnalyzeMultimodalInput,
) -> MCPResponse[AnalyzeMultimodalData]:
    started_at = time.time()
    app = get_flask_app()
    with app.app_context():
        session, code, message = _get_owned_session_or_error(context, input_data.session_id)
        if not session:
            return _err(context, started_at, code, message)

        normalized_paths = [str(path) for path in (input_data.file_paths or []) if str(path or "").strip()]
        if not normalized_paths:
            return _err(context, started_at, "invalid_input", "至少需要上传一个媒体文件")

        task = celery.send_task(
            "chat.analyze_multimodal_batch",
            args=[input_data.session_id, normalized_paths, input_data.query],
        )

        return _ok(
            context,
            started_at,
            AnalyzeMultimodalData(
                task_id=str(task.id),
                session_id=input_data.session_id,
                file_count=len(normalized_paths),
            ),
        )


def analyze_video(
    context: MCPContext,
    input_data: AnalyzeVideoInput,
) -> MCPResponse[AnalyzeVideoData]:
    started_at = time.time()
    multimodal_response = analyze_multimodal(
        context,
        AnalyzeMultimodalInput(
            session_id=input_data.session_id,
            file_paths=[input_data.video_path],
            query=input_data.query,
        ),
    )
    if not multimodal_response.success:
        return multimodal_response
    return _ok(
        context,
        started_at,
        AnalyzeVideoData(
            task_id=str(multimodal_response.data.task_id),
            session_id=input_data.session_id,
        ),
    )


def generate_report_from_session(
    context: MCPContext,
    input_data: GenerateSessionReportInput,
) -> MCPResponse[GenerateSessionReportData]:
    started_at = time.time()
    app = get_flask_app()
    with app.app_context():
        session, code, message = _get_owned_session_or_error(context, input_data.session_id)
        if not session:
            return _err(context, started_at, code, message)

        result, status_code = ReportService.generate_report(input_data.session_id)
        if status_code >= 400 or not result.get("success"):
            return _err(
                context,
                started_at,
                "upstream_error" if status_code >= 500 else "invalid_input",
                str(result.get("error") or "生成报告失败"),
            )

        return _ok(
            context,
            started_at,
            GenerateSessionReportData(
                session_id=input_data.session_id,
                report_id=str(result.get("report_id") or ""),
                status="completed",
                warning=result.get("warning"),
            ),
        )


def get_hotspot_context(
    context: MCPContext,
    input_data: GetHotspotContextInput,
) -> MCPResponse[GetHotspotContextData]:
    started_at = time.time()
    app = get_flask_app()
    with app.app_context():
        if not str(input_data.title or "").strip():
            return _err(context, started_at, "invalid_input", "热点标题不能为空")

        hotspot_candidate = _find_hotspot_candidate(
            input_data.title,
            platform_hint=input_data.platform_hint,
            source_url=input_data.source_url,
        )
        candidate_url = str(
            input_data.source_url
            or hotspot_candidate.get("url")
            or hotspot_candidate.get("mobil_url")
            or ""
        ).strip()
        candidate_platform = str(
            input_data.platform_hint
            or hotspot_candidate.get("platform")
            or hotspot_candidate.get("type")
            or ""
        ).strip()
        candidate_published_at = str(
            input_data.published_at
            or hotspot_candidate.get("published_at")
            or hotspot_candidate.get("update_time")
            or ""
        ).strip()
        source_trace = []
        if hotspot_candidate:
            source_trace.append("hot_news")

        crawl_result = CrawlerService.crawl_news_context(
            title=input_data.title,
            source_url=candidate_url,
            platform_hint=candidate_platform,
            max_candidates=max(1, min(int(input_data.max_candidates or 5), 10)),
            force_refresh=False,
        )
        if crawl_result.get("success"):
            source_trace.append("crawler")

        summary = str(crawl_result.get("summary") or crawl_result.get("content_excerpt") or "").strip()
        final_url = str(crawl_result.get("final_url") or candidate_url or "").strip()
        published_at = str(crawl_result.get("published_at") or candidate_published_at or "").strip()
        if not source_trace:
            source_trace.append("fallback")

        return _ok(
            context,
            started_at,
            GetHotspotContextData(
                title=str(hotspot_candidate.get("title") or input_data.title or ""),
                platform=candidate_platform,
                source_url=final_url,
                published_at=published_at,
                hot_value=str(hotspot_candidate.get("hot") or ""),
                rank=int(hotspot_candidate.get("index")) if hotspot_candidate.get("index") is not None else None,
                summary=summary,
                source_trace=source_trace,
                relevance_score=float(crawl_result.get("relevance_score") or hotspot_candidate.get("_match_score") or 0.0),
                message=str(crawl_result.get("message") or "获取热点上下文成功"),
            ),
        )


def get_task_status(
    context: MCPContext,
    input_data: GetTaskStatusInput,
) -> MCPResponse[GetTaskStatusData]:
    started_at = time.time()
    app = get_flask_app()
    with app.app_context():
        task_result = AsyncResult(input_data.task_id, app=celery)
        if task_result.ready():
            if task_result.successful():
                result_payload = task_result.result if isinstance(task_result.result, dict) else None
                if isinstance(result_payload, dict) and str(result_payload.get("status") or "").lower() == "error":
                    return _ok(
                        context,
                        started_at,
                        GetTaskStatusData(
                            task_id=input_data.task_id,
                            status="failed",
                            result=result_payload,
                            message=str(
                                result_payload.get("user_message")
                                or result_payload.get("degrade_message")
                                or result_payload.get("error")
                                or "任务执行失败"
                            ),
                        ),
                    )
                return _ok(
                    context,
                    started_at,
                    GetTaskStatusData(
                        task_id=input_data.task_id,
                        status="completed",
                        result=result_payload if result_payload is not None else task_result.result,
                    ),
                )

            return _ok(
                context,
                started_at,
                GetTaskStatusData(
                    task_id=input_data.task_id,
                    status="failed",
                    message=str(task_result.result),
                ),
            )

        processing_result = task_result.info if isinstance(task_result.info, dict) else None
        return _ok(
            context,
            started_at,
            GetTaskStatusData(
                task_id=input_data.task_id,
                status="processing",
                result=processing_result,
                message=str(
                    (processing_result or {}).get("degrade_message")
                    or "任务正在处理中，请稍后再试"
                ),
            ),
        )


def verify_source_credibility(
    context: MCPContext,
    input_data: VerifySourceCredibilityInput,
) -> MCPResponse[VerifySourceCredibilityData]:
    started_at = time.time()
    app = get_flask_app()
    with app.app_context():
        result = SourceVerifierService.verify(
            url=input_data.url,
            source_name=input_data.source_name,
            platform=input_data.platform,
        )
        return _ok(
            context,
            started_at,
            VerifySourceCredibilityData(**result),
        )


def verify_time_consistency(
    context: MCPContext,
    input_data: VerifyTimeConsistencyInput,
) -> MCPResponse[VerifyTimeConsistencyData]:
    started_at = time.time()
    app = get_flask_app()
    with app.app_context():
        result = TimeVerifierService.verify(
            title=input_data.title,
            published_at=input_data.published_at,
            extracted_text=input_data.extracted_text,
            hotspot_time=input_data.hotspot_time,
        )
        return _ok(
            context,
            started_at,
            VerifyTimeConsistencyData(**result),
        )


def extract_timeline(
    context: MCPContext,
    input_data: ExtractTimelineInput,
) -> MCPResponse[ExtractTimelineData]:
    started_at = time.time()
    app = get_flask_app()
    with app.app_context():
        result = TimelineService.extract(
            documents=[item.model_dump() for item in (input_data.documents or [])],
        )
        return _ok(
            context,
            started_at,
            ExtractTimelineData(
                timeline=[TimelineItemData(**item) for item in (result.get("timeline") or [])],
                count=int(result.get("count") or 0),
            ),
        )


def export_chat(context: MCPContext, input_data: ExportChatInput) -> MCPResponse[ExportChatData]:
    started_at = time.time()
    app = get_flask_app()
    with app.app_context():
        session, code, message = _get_owned_session_or_error(context, input_data.session_id)
        if not session:
            return _err(context, started_at, code, message)

        messages = ChatService.get_chat_history(input_data.session_id)
        visible = ChatService.filter_client_visible_messages(messages)
        export_data = {
            "timestamp": datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S"),
            "title": session.get("title", "未命名对话"),
            "messages": visible,
        }
        filename = f"chat_export_{time.strftime('%Y%m%d_%H%M%S')}.json"
        return _ok(
            context,
            started_at,
            ExportChatData(
                filename=filename,
                content=json.dumps(export_data, ensure_ascii=False, indent=2),
            ),
        )


def crawl_news_context(
    context: MCPContext,
    input_data: CrawlNewsContextInput,
) -> MCPResponse[CrawlNewsContextData]:
    started_at = time.time()
    app = get_flask_app()
    with app.app_context():
        if input_data.session_id:
            session, code, message = _get_owned_session_or_error(context, input_data.session_id)
            if not session:
                return _err(context, started_at, code, message)

        result = CrawlerService.crawl_news_context(
            title=input_data.title,
            source_url=input_data.source_url or "",
            platform_hint=input_data.platform_hint or "",
            session_id=input_data.session_id or "",
            user_id=context.auth.user_id,
            max_candidates=max(1, min(int(input_data.max_candidates or 5), 10)),
            force_refresh=bool(input_data.force_refresh),
        )

        if not result.get("success"):
            return _ok(
                context,
                started_at,
                CrawlNewsContextData(
                    query_title=str(result.get("query_title") or input_data.title),
                    status="failed",
                    summary=str(result.get("summary") or ""),
                    content_excerpt=str(result.get("content_excerpt") or ""),
                    source_name=str(result.get("source_name") or ""),
                    final_url=str(result.get("final_url") or ""),
                    published_at=_to_iso(result.get("published_at")),
                    candidate_urls=[str(item) for item in (result.get("candidate_urls") or [])],
                    cached=bool(result.get("cached")),
                    message=str(result.get("message") or "抓取失败"),
                ),
            )

        return _ok(
            context,
            started_at,
            CrawlNewsContextData(
                query_title=str(result.get("query_title") or input_data.title),
                status="ready",
                summary=str(result.get("summary") or ""),
                content_excerpt=str(result.get("content_excerpt") or ""),
                source_name=str(result.get("source_name") or ""),
                final_url=str(result.get("final_url") or ""),
                published_at=_to_iso(result.get("published_at")),
                candidate_urls=[str(item) for item in (result.get("candidate_urls") or [])],
                cached=bool(result.get("cached")),
                message=str(result.get("message") or "抓取成功"),
            ),
        )


def search_overview(
    context: MCPContext,
    input_data: OverviewSearchInput,
) -> MCPResponse[OverviewSearchData]:
    import sys
    print(f"[search_overview MCP] query={input_data.query[:40]} user_id={context.auth.user_id}", file=sys.stderr)
    sys.stderr.flush()
    started_at = time.time()
    app = get_flask_app()
    with app.app_context():
        session, code, message = _get_owned_session_or_error(context, input_data.session_id)
        if not session:
            return _err(context, started_at, code, message)

        result = OverviewSearchService.search(
            query=input_data.query,
            source_url=input_data.source_url or "",
            platform_hint=input_data.platform_hint or "",
            session_id=input_data.session_id,
            user_id=context.auth.user_id,
            max_results=max(3, min(int(input_data.max_results or 10), 12)),
        )
        items = list(result.get("items") or [])
        print(f"[search_overview MCP] got {len(items)} items, first source={items[0].get('source_name') if items else 'NONE'}", file=sys.stderr)
        sys.stderr.flush()
        assistant_content = _build_overview_assistant_content(str(result.get("query") or input_data.query), items)
        sources, citations = _build_overview_sources(items)
        user_content = str(input_data.user_prompt or input_data.query or "").strip()
        if input_data.save_to_history:
            # 仅当需要保存历史时，才写入聊天消息
            if user_content:
                ChatService.add_message(input_data.session_id, "user", user_content)
            extra_fields = {
                "grounding_status": "grounded" if items else "ungrounded",
                "confidence": "high" if any(str(item.get("credibility")) == "high" for item in items) else "medium",
                "used_realtime_retrieval": True,
                "sources": safe_json_data(sources),
                "citations": safe_json_data(citations),
                "facts": [str(item.get("title") or "") for item in items[:5] if str(item.get("title") or "").strip()],
                "to_verify": [],
                "analysis": [str(result.get("summary") or "")],
            }
            ChatService.add_message(input_data.session_id, "assistant", assistant_content, extra_fields=extra_fields)
        messages = ChatService.get_chat_history(input_data.session_id)
        visible = ChatService.filter_client_visible_messages(messages)
        assistant_message = next((msg for msg in reversed(visible) if msg.get("role") == "assistant"), None)
        parsed_items = [
            OverviewSearchItemData(
                title=str(item.get("title") or ""),
                url=str(item.get("url") or ""),
                source_name=str(item.get("source_name") or ""),
                platform=str(item.get("platform") or ""),
                published_at=_to_iso(item.get("published_at")),
                summary=str(item.get("summary") or ""),
                content_excerpt=str(item.get("content_excerpt") or ""),
                credibility=str(item.get("credibility") or "medium"),
                source_type=str(item.get("source_type") or "general_webpage"),
                relevance_score=float(item.get("relevance_score") or 0),
                time_reason=str(item.get("time_reason") or ""),
                credibility_reason=str(item.get("credibility_reason") or ""),
            )
            for item in items
        ]
        return _ok(
            context,
            started_at,
            OverviewSearchData(
                session_id=input_data.session_id,
                query=str(result.get("query") or input_data.query),
                summary=str(result.get("summary") or ""),
                total=len(items),
                items=parsed_items,
                assistant_message=_to_chat_message(assistant_message or {}) if assistant_message else None,
            ),
        )


def analyze_rumor(
    context: MCPContext,
    input_data: RumorAnalysisInput,
) -> MCPResponse[RumorAnalysisData]:
    started_at = time.time()
    app = get_flask_app()
    with app.app_context():
        session, code, message = _get_owned_session_or_error(context, input_data.session_id)
        if not session:
            return _err(context, started_at, code, message)

        result = RumorAnalysisService.analyze(
            query=input_data.query,
            source_url=input_data.source_url or "",
            platform_hint=input_data.platform_hint or "",
            session_id=input_data.session_id,
            user_id=context.auth.user_id,
            max_results=max(3, min(int(input_data.max_results or 8), 10)),
        )
        items = list(result.get("items") or [])
        assistant_content = _build_rumor_assistant_content(result)
        sources, citations = _build_overview_sources(items)
        user_content = str(input_data.user_prompt or input_data.query or "").strip()
        if input_data.save_to_history:
            # 仅当需要保存历史时，才写入聊天消息
            if user_content:
                ChatService.add_message(input_data.session_id, "user", user_content)
            extra_fields = {
                "grounding_status": "grounded" if items else "ungrounded",
                "confidence": "high" if any(str(item.get("credibility")) == "high" for item in items) else "medium",
                "used_realtime_retrieval": True,
                "sources": safe_json_data(sources),
                "citations": safe_json_data(citations),
                "facts": [str(item) for item in (result.get("known_facts") or [])],
                "to_verify": [str(item) for item in (result.get("to_verify") or [])],
                "analysis": [str(item) for item in (result.get("suggestions") or [])],
            }
            ChatService.add_message(input_data.session_id, "assistant", assistant_content, extra_fields=extra_fields)
        messages = ChatService.get_chat_history(input_data.session_id)
        visible = ChatService.filter_client_visible_messages(messages)
        assistant_message = next((msg for msg in reversed(visible) if msg.get("role") == "assistant"), None)
        parsed_items = [
            OverviewSearchItemData(
                title=str(item.get("title") or ""),
                url=str(item.get("url") or ""),
                source_name=str(item.get("source_name") or ""),
                platform=str(item.get("platform") or ""),
                published_at=_to_iso(item.get("published_at")),
                summary=str(item.get("summary") or ""),
                content_excerpt=str(item.get("content_excerpt") or ""),
                credibility=str(item.get("credibility") or "medium"),
                source_type=str(item.get("source_type") or "general_webpage"),
                relevance_score=float(item.get("relevance_score") or 0),
                time_reason=str(item.get("time_reason") or ""),
                credibility_reason=str(item.get("credibility_reason") or ""),
            )
            for item in items
        ]
        return _ok(
            context,
            started_at,
            RumorAnalysisData(
                session_id=input_data.session_id,
                query=str(result.get("query") or input_data.query),
                verdict=str(result.get("verdict") or ""),
                risk_level=str(result.get("risk_level") or "medium"),
                summary=str(result.get("summary") or ""),
                known_facts=[str(item) for item in (result.get("known_facts") or [])],
                to_verify=[str(item) for item in (result.get("to_verify") or [])],
                suggestions=[str(item) for item in (result.get("suggestions") or [])],
                items=parsed_items,
                assistant_message=_to_chat_message(assistant_message or {}) if assistant_message else None,
            ),
        )


def text_to_speech(
    context: MCPContext,
    input_data: TextToSpeechInput,
) -> MCPResponse[TextToSpeechData]:
    started_at = time.time()
    app = get_flask_app()
    with app.app_context():
        text = (input_data.text or "").strip()
        if not text:
            return _err(context, started_at, "invalid_input", "文本内容不能为空")

        try:
            result = TTSService.text_to_speech(
                text=text,
                voice_id=input_data.voice_id,
                provider=input_data.provider,
                session_id=input_data.session_id,
            )
            return _ok(
                context,
                started_at,
                TextToSpeechData(
                    audio_url=result["audio_url"],
                    duration_seconds=result["duration_seconds"],
                    provider=result["provider"],
                    text_preview=result["text_preview"],
                ),
            )
        except Exception as exc:
            return _err(context, started_at, "upstream_error", f"TTS 生成失败: {exc}")


def text_to_speech_async(
    context: MCPContext,
    input_data: TextToSpeechAsyncInput,
) -> MCPResponse[TextToSpeechAsyncData]:
    started_at = time.time()
    app = get_flask_app()
    with app.app_context():
        session = ChatService.get_chat_session(input_data.session_id)
        if not session:
            return _err(context, started_at, "not_found", "会话不存在")

        target_message = None
        for item in session.get("messages", []) or []:
            if str(item.get("id") or "") == str(input_data.message_id or ""):
                target_message = item
                break

        if not target_message:
            return _err(context, started_at, "not_found", "目标消息不存在")
        if str(target_message.get("role") or "") != "assistant":
            return _err(context, started_at, "invalid_input", "仅支持为 assistant 消息生成语音")
        if str(target_message.get("render_mode") or target_message.get("renderMode") or "") == "hidden":
            return _err(context, started_at, "invalid_input", "隐藏消息不支持生成语音")

        normalized_text = str(input_data.text or target_message.get("content") or "").strip()
        if not normalized_text:
            return _err(context, started_at, "invalid_input", "文本内容不能为空")

        existing_task_id = str(target_message.get("tts_task_id") or target_message.get("ttsTaskId") or "").strip()
        existing_status = str(target_message.get("tts_status") or target_message.get("ttsStatus") or "").strip().lower()
        if existing_task_id and existing_status == "processing":
            return _ok(
                context,
                started_at,
                TextToSpeechAsyncData(
                    task_id=existing_task_id,
                    status="processing",
                    message_id=input_data.message_id,
                ),
            )

        task = celery.send_task(
            "chat.generate_tts_for_message",
            args=[input_data.session_id, input_data.message_id, normalized_text, input_data.voice_id, input_data.provider],
        )
        ChatService.update_message_fields(
            input_data.session_id,
            input_data.message_id,
            {
                "tts_status": "processing",
                "tts_task_id": str(task.id),
                "tts_error": None,
            },
        )
        return _ok(
            context,
            started_at,
            TextToSpeechAsyncData(
                task_id=str(task.id),
                status="processing",
                message_id=input_data.message_id,
            ),
        )


# ---------------------------------------------------------------------------
# Synchronous wrapper functions for prerequisite tool execution
# These allow calling search_overview / analyze_rumor from non-MCP contexts
# (e.g., prerequisite_service) by constructing a minimal MCPContext in-process.
# ---------------------------------------------------------------------------

def execute_search_overview_sync(session_id, query, user_id, max_results=10):
    """Synchronously execute search_overview (for prerequisite checks)."""
    ctx = MCPContext(
        auth=AuthContext(user_id=user_id),
        request=RequestContext(request_id=f"prereq-{uuid.uuid4()}"),
    )
    input_data = OverviewSearchInput(
        session_id=session_id,
        query=query,
        max_results=max_results,
        save_to_history=False,  # 前置工具调用，不写入聊天历史
    )
    response = search_overview(ctx, input_data)
    return response.data if response else None


def execute_analyze_rumor_sync(session_id, query, user_id, max_results=8):
    """Synchronously execute analyze_rumor (for prerequisite checks)."""
    ctx = MCPContext(
        auth=AuthContext(user_id=user_id),
        request=RequestContext(request_id=f"prereq-{uuid.uuid4()}"),
    )
    input_data = RumorAnalysisInput(
        session_id=session_id,
        query=query,
        max_results=max_results,
        save_to_history=False,  # 前置工具调用，不写入聊天历史
    )
    response = analyze_rumor(ctx, input_data)
    return response.data if response else None


def search_web(
    context: MCPContext,
    input_data: SearchWebInput,
) -> MCPResponse[SearchWebData]:
    started_at = time.time()
    app = get_flask_app()
    with app.app_context():
        results = LangChainToolService.search_web(
            query=input_data.query,
            max_results=max(1, min(int(input_data.max_results or 5), 10)),
        )
        return _ok(
            context,
            started_at,
            SearchWebData(
                query=str(input_data.query or "").strip(),
                results=results,
                count=len(results),
            ),
        )


def search_web_tavily(
    context: MCPContext,
    input_data: SearchWebInput,
) -> MCPResponse[SearchWebData]:
    started_at = time.time()
    app = get_flask_app()
    with app.app_context():
        results = LangChainToolService.search_web_tavily(
            query=input_data.query,
            max_results=max(1, min(int(input_data.max_results or 5), 10)),
        )
        return _ok(
            context,
            started_at,
            SearchWebData(
                query=str(input_data.query or "").strip(),
                results=results,
                count=len(results),
            ),
        )


def load_urls(
    context: MCPContext,
    input_data: LoadUrlsInput,
) -> MCPResponse[LoadUrlsData]:
    started_at = time.time()
    app = get_flask_app()
    with app.app_context():
        pages = LangChainToolService.load_urls(input_data.urls or [])
        return _ok(
            context,
            started_at,
            LoadUrlsData(
                urls=input_data.urls or [],
                pages=pages,
                count=len(pages),
            ),
        )


def db_aggregate(
    context: MCPContext,
    input_data: DbAggregateInput,
) -> MCPResponse[DbAggregateData]:
    started_at = time.time()
    from wanxiang_mcp.utils.db_aggregate_templates import (
        TEMPLATES,
        ALLOWED_COLLECTIONS,
        DEFAULT_LIMIT,
        MAX_LIMIT,
    )

    template = TEMPLATES.get(input_data.template_name)
    if not template:
        return _err(
            context,
            started_at,
            "not_found",
            f"未知模板: {input_data.template_name}",
        )

    collection_name = template["collection"]
    if collection_name not in ALLOWED_COLLECTIONS:
        return _err(
            context,
            started_at,
            "forbidden",
            f"集合 {collection_name} 不在允许列表中",
        )

    limit = max(1, min(int(input_data.limit or DEFAULT_LIMIT), MAX_LIMIT))
    start_date = input_data.start_date or "2026-01-01T00:00:00"

    # 替换模板中的占位符（直接在 dict 上替换，避免 JSON 序列化丢失类型）
    filled_pipeline = []
    for stage in template["pipeline_template"]:
        stage_str = json.dumps(stage)
        if "{{start_date}}" in stage_str:
            stage_str = stage_str.replace('"{{start_date}}"', f'"{start_date}"')
        if "{{limit}}" in stage_str:
            stage_str = stage_str.replace('"{{limit}}"', str(limit))
        if "{{end_date}}" in stage_str:
            if input_data.end_date:
                stage_str = stage_str.replace('"{{end_date}}"', f'"{input_data.end_date}"')
            else:
                stage_str = stage_str.replace('"{{end_date}}"', "null")
        stage = json.loads(stage_str)

        # $limit 必须保证是整数，不能是字符串
        if "$limit" in stage and isinstance(stage["$limit"], str):
            stage["$limit"] = int(stage["$limit"])
        filled_pipeline.append(stage)

    app = get_flask_app()
    with app.app_context():
        collection = getattr(db, collection_name, None)
        if collection is None:
            return _err(
                context,
                started_at,
                "not_found",
                f"集合 {collection_name} 不存在",
            )
        try:
            cursor = collection.aggregate(filled_pipeline)
            rows = list(cursor)
        except Exception as e:
            return _err(
                context,
                started_at,
                "upstream_error",
                f"聚合查询失败: {e}",
            )

    return _ok(
        context,
        started_at,
        DbAggregateData(
            template_name=input_data.template_name,
            rows=rows,
            count=len(rows),
            execution_ms=int((time.time() - started_at) * 1000),
        ),
    )


def run_mindspider_topic_extraction(
    context: MCPContext,
    input_data: RunMindSpiderTopicExtractionInput,
) -> MCPResponse[RunMindSpiderTopicExtractionData]:
    started_at = time.time()
    app = get_flask_app()
    with app.app_context():
        task = MindSpiderBridgeService.run_topic_extraction(
            sources=input_data.sources or None,
            max_keywords=max(1, min(int(input_data.max_keywords or 100), 200)),
        )
        return _ok(
            context,
            started_at,
            RunMindSpiderTopicExtractionData(
                task_id=str(task.id),
                status="processing",
            ),
        )


def get_mindspider_topic_analysis(
    context: MCPContext,
    input_data: GetMindSpiderTopicAnalysisInput,
) -> MCPResponse[GetMindSpiderTopicAnalysisData]:
    started_at = time.time()
    app = get_flask_app()
    with app.app_context():
        result = MindSpiderBridgeService.get_topic_analysis(input_data.extract_date)
        data = result.get("data") or {}
        return _ok(
            context,
            started_at,
            GetMindSpiderTopicAnalysisData(
                extract_date=str(data.get("extractDate") or ""),
                keywords=[str(item) for item in (data.get("keywords") or [])],
                summary=str(data.get("summary") or ""),
                news_count=int(data.get("newsCount") or 0),
                news=list(data.get("news") or []),
            ),
        )


def run_mindspider_deep_sentiment(
    context: MCPContext,
    input_data: RunMindSpiderDeepSentimentInput,
) -> MCPResponse[RunMindSpiderDeepSentimentData]:
    started_at = time.time()
    app = get_flask_app()
    with app.app_context():
        task = MindSpiderDeepSentimentService.run_deep_sentiment(
            extract_date=input_data.extract_date,
            platforms=input_data.platforms or None,
            max_keywords_per_platform=max(1, min(int(input_data.max_keywords_per_platform or 20), 100)),
            max_candidates_per_keyword=max(1, min(int(input_data.max_candidates_per_keyword or 3), 8)),
        )
        return _ok(
            context,
            started_at,
            RunMindSpiderDeepSentimentData(task_id=str(task.id), status="processing"),
        )


def get_mindspider_deep_sentiment(
    context: MCPContext,
    input_data: GetMindSpiderDeepSentimentInput,
) -> MCPResponse[GetMindSpiderDeepSentimentData]:
    started_at = time.time()
    app = get_flask_app()
    with app.app_context():
        result = MindSpiderDeepSentimentService.get_deep_sentiment_analysis(input_data.extract_date)
        data = result.get("data") or {}
        return _ok(
            context,
            started_at,
            GetMindSpiderDeepSentimentData(
                extract_date=str(data.get("extractDate") or ""),
                source_summary=str(data.get("sourceSummary") or ""),
                total_keywords=int(data.get("totalKeywords") or 0),
                total_platforms=int(data.get("totalPlatforms") or 0),
                total_records=int(data.get("totalRecords") or 0),
                platform_stats=[safe_json_data(item) for item in (data.get("platformStats") or [])],
                sentiment_distribution=[safe_json_data(item) for item in (data.get("sentimentDistribution") or [])],
                records=[safe_json_data(item) for item in (data.get("records") or [])],
            ),
        )


def stream_message(context: MCPContext, input_data: StreamMessageInput) -> Iterator[Dict[str, Any]]:
    app = get_flask_app()

    def generate() -> Iterator[Dict[str, Any]]:
        debug_mode = bool(getattr(input_data, "debug_mode", False))
        route = _resolve_stream_route(debug_mode)
        logger = app.logger

        with app.app_context():
            session, code, message = _get_owned_session_or_error(context, input_data.session_id)
            if not session:
                yield {"event": "error", "data": {"error": message, "code": code}}
                return

            if not str(input_data.message).strip():
                yield {"event": "error", "data": {"error": "消息内容不能为空", "code": "invalid_input"}}
                return

            if input_data.recommendation_context:
                _persist_recommendation_context_message(input_data.session_id, input_data.recommendation_context)
            save_result = ChatService.add_message(input_data.session_id, "user", input_data.message)
            if not save_result:
                yield {"event": "error", "data": {"error": "保存用户消息失败", "code": "internal_error"}}
                return

            messages = ChatService.get_chat_history(input_data.session_id)
            # DEBUG: log message history to verify video analysis context
            print(f"[DEBUG stream_message] session_id={input_data.session_id}, messages_count={len(messages)}", file=sys.stderr)
            for i, msg in enumerate(messages[-5:]):
                msg_role = msg.get('role', 'unknown')
                msg_content = str(msg.get('content', ''))[:80]
                print(f"[DEBUG stream_message] msg[{len(messages)-5+i}] role={msg_role}, content={msg_content}", file=sys.stderr)
            settings = session.get("settings", {})
            logger.info(
                "Starting stream route=%s session_id=%s debug_mode=%s",
                route,
                input_data.session_id,
                debug_mode,
            )
            greeting_response = ChatService.build_greeting_response(messages)
            if greeting_response:
                assistant_saved = ChatService.add_message(
                    input_data.session_id,
                    "assistant",
                    greeting_response,
                    extra_fields=_build_stream_message_extra_fields(debug_mode=debug_mode, route=route),
                )
                yield {
                    "event": "start",
                    "data": _build_stream_event_data(
                        debug_mode=debug_mode,
                        route=route,
                        status="started",
                        session_id=input_data.session_id,
                    ),
                }
                yield {"event": "ready", "data": _build_stream_event_data(debug_mode=debug_mode, route=route, status="ready")}
                yield {"event": "message", "data": {"chunk": greeting_response}}
                if not assistant_saved:
                    yield {
                        "event": "warning",
                        "data": _build_stream_event_data(
                            debug_mode=debug_mode,
                            route=route,
                            warning="响应已生成，但保存 AI 消息失败",
                        ),
                    }
                yield {
                    "event": "done",
                    "data": _build_stream_event_data(
                        debug_mode=debug_mode,
                        route=route,
                        status="complete",
                        full_text=greeting_response,
                    ),
                }
                return

            if debug_mode:
                prepared_messages = ChatService.prepare_messages_for_generation(messages, settings, debug_mode=True)
                prepared_messages = list(prepared_messages) + [
                    {
                        "role": "system",
                        "content": (
                            "当前是 debug_llm_stream 纯 LLM 对照模式。"
                            "不要调用任何工具，不要输出工具调用 JSON，不要建议搜索。"
                            "请直接基于已有上下文给出简洁、完整的自然语言回答。"
                        ),
                    }
                ]

                # Read API config directly from environment/env, not via Flask context
                api_key = os.getenv('QWEN_API_KEY') or os.getenv('OPENAI_API_KEY')
                base_url = os.getenv('QWEN_BASE_URL') or os.getenv('OPENAI_BASE_URL') or 'https://dashscope.aliyuncs.com/compatible-mode/v1'
                model = os.getenv('QWEN_MODEL') or os.getenv('QWEN_FALLBACK_MODEL') or 'qwen-plus'

                timeout = float(os.getenv('LLM_REQUEST_TIMEOUT') or '90.0')
            else:
                prepared_messages = ChatService.prepare_messages_for_generation(messages, settings)
                provider_config = ChatService.resolve_chat_provider(settings)
                qwen_fallback_model = ChatService.get_qwen_fallback_model()

                timeout = app.config.get("LLM_REQUEST_TIMEOUT") or os.getenv("LLM_REQUEST_TIMEOUT") or 90.0
                try:
                    timeout = float(timeout)
                except (ValueError, TypeError):
                    timeout = 90.0

                max_tokens = app.config.get("MAX_TOKENS") or os.getenv("MAX_TOKENS") or 2048
                try:
                    max_tokens = int(max_tokens)
                except (ValueError, TypeError):
                    max_tokens = 2048

                provider_specific_params = dict(app.config.get("PROVIDER_SPECIFIC_PARAMS", {}) or {})
                env_specific_params = os.getenv("PROVIDER_SPECIFIC_PARAMS")
                if env_specific_params:
                    try:
                        env_params = json.loads(env_specific_params)
                        if isinstance(env_params, dict):
                            provider_specific_params.update(env_params)
                    except Exception:
                        logger.warning("Failed to parse PROVIDER_SPECIFIC_PARAMS from env")

                web_search_config = app.config.get("WEB_SEARCH_CONFIG", {"enable": True})
                env_web_search = os.getenv("WEB_SEARCH_CONFIG")
                if env_web_search:
                    try:
                        web_search_config = json.loads(env_web_search)
                    except Exception:
                        logger.warning("Failed to parse WEB_SEARCH_CONFIG from env")

        # DEBUG MODE: Skip greeting, search, RAG, and grounding - just stream LLM response
        if debug_mode:
            if not api_key or not base_url:
                yield {
                    "event": "start",
                    "data": _build_stream_event_data(
                        debug_mode=debug_mode,
                        route=route,
                        status="started",
                        session_id=input_data.session_id,
                    ),
                }
                yield {"event": "ready", "data": _build_stream_event_data(debug_mode=debug_mode, route=route, status="ready")}
                yield {
                    "event": "error",
                    "data": _build_stream_event_data(
                        debug_mode=debug_mode,
                        route=route,
                        error="API 服务未配置",
                        code="upstream_error",
                        fallbackReason="generic_upstream_error",
                        upstreamCode="upstream_error",
                        upstreamType="upstream_error",
                        phase="llm",
                    ),
                }
                return

            client = OpenAI(api_key=api_key, base_url=base_url, timeout=timeout)
            request_params = {
                "model": model,
                "messages": prepared_messages,
                "temperature": float(settings.get('temperature', 0.2)),
                "stream": True,
            }

            yield {
                "event": "start",
                "data": _build_stream_event_data(
                    debug_mode=debug_mode,
                    route=route,
                    status="started",
                    session_id=input_data.session_id,
                ),
            }
            yield {"event": "ready", "data": _build_stream_event_data(debug_mode=debug_mode, route=route, status="ready")}

            full_response = ""
            stream_issue: Optional[Dict[str, str]] = None
            try:
                response = client.chat.completions.create(**request_params)
                for chunk in response:
                    if not chunk.choices:
                        continue
                    delta = chunk.choices[0].delta
                    if hasattr(delta, "content") and delta.content:
                        full_response += delta.content
                        yield {"event": "message", "data": {"chunk": delta.content}}
            except Exception as e:
                stream_issue = _classify_stream_exception(e)
                logger.error(
                    "MCP stream failed route=%s model=%s: %s",
                    route,
                    model,
                    e,
                    exc_info=True,
                )
                if full_response.strip():
                    with app.app_context():
                        saved_partial = ChatService.add_message(
                            input_data.session_id,
                            "assistant",
                            full_response,
                            extra_fields=_build_stream_message_extra_fields(
                                debug_mode=debug_mode,
                                route=route,
                                fallback_reason=stream_issue["fallbackReason"],
                                upstream_code=stream_issue["upstreamCode"],
                                upstream_type=stream_issue["upstreamType"],
                                phase=stream_issue["phase"],
                            ),
                        )
                    if not saved_partial:
                        yield {
                            "event": "warning",
                            "data": _build_stream_event_data(
                                debug_mode=debug_mode,
                                route=route,
                                warning="响应已部分生成，但保存 AI 消息失败",
                            ),
                        }
                    yield {
                        "event": "warning",
                        "data": _build_stream_event_data(
                            debug_mode=debug_mode,
                            route=route,
                            warning=f"响应在生成尾部中断，已保留已生成内容。{stream_issue['displayMessage']}",
                            code="partial_response",
                            fallbackReason=stream_issue["fallbackReason"],
                            upstreamCode=stream_issue["upstreamCode"],
                            upstreamType=stream_issue["upstreamType"],
                            phase=stream_issue["phase"],
                        ),
                    }
                    yield {
                        "event": "done",
                        "data": _build_stream_event_data(
                            debug_mode=debug_mode,
                            route=route,
                            status="partial_complete",
                            full_text=full_response,
                            warning=stream_issue["displayMessage"],
                            fallbackReason=stream_issue["fallbackReason"],
                            upstreamCode=stream_issue["upstreamCode"],
                            upstreamType=stream_issue["upstreamType"],
                            phase=stream_issue["phase"],
                        ),
                    }
                else:
                    with app.app_context():
                        ChatService.add_message(
                            input_data.session_id,
                            "assistant",
                            stream_issue["fallbackMessage"],
                            extra_fields=_build_stream_message_extra_fields(
                                debug_mode=debug_mode,
                                route=route,
                                fallback_reason=stream_issue["fallbackReason"],
                                upstream_code=stream_issue["upstreamCode"],
                                upstream_type=stream_issue["upstreamType"],
                                phase=stream_issue["phase"],
                            ),
                        )
                    yield {
                        "event": "error",
                        "data": _build_stream_event_data(
                            debug_mode=debug_mode,
                            route=route,
                            error=stream_issue["displayMessage"],
                            code="upstream_error",
                            fallbackReason=stream_issue["fallbackReason"],
                            upstreamCode=stream_issue["upstreamCode"],
                            upstreamType=stream_issue["upstreamType"],
                            phase=stream_issue["phase"],
                        ),
                    }
                return

            if full_response:
                with app.app_context():
                    ChatService.add_message(
                        input_data.session_id,
                        "assistant",
                        full_response,
                        extra_fields=_build_stream_message_extra_fields(debug_mode=debug_mode, route=route),
                    )

            yield {
                "event": "done",
                "data": _build_stream_event_data(
                    debug_mode=debug_mode,
                    route=route,
                    status="complete",
                    full_text=full_response,
                ),
            }
            return

        rag_context = _resolve_rag_context(input_data)

        # Always use real-time search_overview instead of RAG grounding
        # Wrap with a timeout so search hangs don't kill the SSE stream
        search_timeout_seconds = 12

        # Yield start/ready BEFORE starting the search so frontend_api
        # receives events immediately and doesn't timeout during search
        yield {
            "event": "start",
            "data": _build_stream_event_data(
                debug_mode=debug_mode,
                route=route,
                status="started",
                session_id=input_data.session_id,
            ),
        }
        yield {"event": "ready", "data": _build_stream_event_data(debug_mode=debug_mode, route=route, status="ready")}

        def _run_search():
            with app.app_context():
                return OverviewSearchService.search(
                    query=str(input_data.message),
                    source_url=rag_context["source_url"],
                    platform_hint=rag_context["platform_hint"],
                    session_id=input_data.session_id,
                    user_id=context.auth.user_id,
                    max_results=10,
                )

        search_result = None
        search_timed_out = False
        search_failed = False
        try:
            import threading
            result_holder = [None]
            exc_holder = [None]

            def _search_target():
                try:
                    result_holder[0] = _run_search()
                except Exception as e:
                    exc_holder[0] = e

            t = threading.Thread(target=_search_target, daemon=True)
            t.start()
            t.join(timeout=search_timeout_seconds)
            if t.is_alive():
                logger.warning("OverviewSearchService.search timed out after %ds, using empty result", search_timeout_seconds)
                search_timed_out = True
            elif exc_holder[0]:
                raise exc_holder[0]
            else:
                search_result = result_holder[0]
        except Exception as exc:
            logger.warning("OverviewSearchService.search failed: %s", exc)
            search_failed = True

        if search_result is None:
            search_result = {"items": [], "summary": ""}

        items = list(search_result.get("items") or [])

        # Build grounding payload (matching the format expected by frontend SSE handler)
        sources, citations = _build_overview_sources(items)
        grounding_payload = {
            "groundingStatus": "grounded" if items else "ungrounded",
            "confidence": "high" if any(str(item.get("credibility")) == "high" for item in items) else "medium",
            "usedRealtimeRetrieval": True,
            "sources": safe_json_data(sources),
            "citations": safe_json_data(citations),
            "facts": [str(item.get("title") or "") for item in items[:5] if str(item.get("title") or "").strip()],
            "toVerify": [],
            "analysis": [str(search_result.get("summary") or "")],
            "route": route,
            "debugMode": debug_mode,
            "searchTimedOut": search_timed_out,
            "searchFailed": search_failed,
        }

        # Yield grounding event so frontend can display search results while LLM prepares
        yield {"event": "grounding", "data": grounding_payload}

        # Only inject search context as assistant message if search returned actual results
        # or returned empty legitimately (not timeout). If all search services timed out,
        # skip injection to let LLM respond naturally without misleading "no results" message.
        if not (search_timed_out and not items):
            search_context_text = _build_overview_assistant_content(
                str(input_data.message), items
            )

            # Insert search context as assistant message after system prompt(s)
            insert_idx = 1  # after system prompt
            if len(prepared_messages) > 1 and prepared_messages[1].get("role") == "system":
                insert_idx = 2  # after system + next system context
            prepared_messages = (
                prepared_messages[:insert_idx]
                + [{"role": "assistant", "content": search_context_text}]
                + prepared_messages[insert_idx:]
            )

        api_key = provider_config.get("api_key")
        base_url = provider_config.get("base_url")
        model = provider_config.get("model")
        provider = provider_config.get("provider")

        if not api_key or not base_url:
            yield {
                "event": "error",
                "data": _build_stream_event_data(
                    debug_mode=debug_mode,
                    route=route,
                    error="API 服务未配置",
                    code="upstream_error",
                    fallbackReason="generic_upstream_error",
                    upstreamCode="upstream_error",
                    upstreamType="upstream_error",
                    phase="llm",
                ),
            }
            return

        client = OpenAI(api_key=api_key, base_url=base_url, timeout=timeout)

        # DEBUG
        print(f"[DEBUG stream_message] LLM call starting, model={model}, msg_count={len(prepared_messages)}, first_msg_len={len(prepared_messages[0].get('content','') if prepared_messages else 'N/A')}", file=sys.stderr)
        sys.stderr.flush()

        # Get tools in OpenAI function format
        available_functions = list_openai_functions()

        request_params: Dict[str, Any] = {
            "model": model,
            "messages": prepared_messages,
            "temperature": settings.get("temperature", 0.2),
            "stream": True,
        }
        if max_tokens > 0:
            request_params["max_tokens"] = max_tokens
        for key, value in provider_specific_params.items():
            request_params[key] = value
        if settings.get("enable_search", False):
            request_params["extra_body"] = {"web_search": web_search_config}
        if available_functions:
            request_params["tools"] = available_functions
            request_params["tool_choice"] = "auto"
        request_params = safe_json_data(request_params)

        full_response = ""
        tool_generated_response = ""
        tool_generated_response_saved = False
        error_occurred = False
        stream_issue: Optional[Dict[str, str]] = None

        try:
            # Helper to execute tools and continue conversation
            def execute_tools_and_continue(
                tool_calls: list,
                current_messages: list,
            ) -> Iterator[Dict[str, Any]]:
                """Execute tool calls and yield the subsequent response."""
                nonlocal tool_generated_response, tool_generated_response_saved
                # Execute each tool call
                tool_results = []
                for tc in tool_calls:
                    tc_id = str(tc.get("id") or "")
                    tc_function = tc.get("function") or {}
                    func_name = str(tc_function.get("name") or "")
                    func_args = tc_function.get("arguments") or "{}"

                    # Parse arguments
                    try:
                        args_dict = json.loads(func_args)
                    except (json.JSONDecodeError, TypeError):
                        args_dict = {}
                    args_dict = _bind_tool_args_to_current_session(
                        func_name,
                        args_dict if isinstance(args_dict, dict) else {},
                        input_data.session_id,
                    )

                    # Execute the tool
                    try:
                        # Lazy import to avoid circular dependency
                        from wanxiang_mcp.tools.chat_session import invoke_chat_session_tool
                        tool_result = invoke_chat_session_tool(
                            func_name,
                            {"context": {"auth": context.auth, "request": {"request_id": "tool-execution", "source": "llm"}}, "input": args_dict},
                        )
                        if isinstance(tool_result, dict):
                            tool_data = tool_result.get("data") or {}
                            assistant_message = tool_data.get("assistant_message") or {}
                            assistant_content = str(assistant_message.get("content") or "").strip()
                            if assistant_content:
                                tool_generated_response = assistant_content
                                tool_generated_response_saved = True
                        tool_result_content = json.dumps(tool_result, ensure_ascii=False) if tool_result else ""
                    except Exception as tool_err:
                        logger.warning("Tool %s failed: %s", func_name, tool_err)
                        tool_result_content = f"{{\"error\": \"{str(tool_err)}\"}}"

                    tool_results.append(
                        {
                            "tool_call_id": tc_id,
                            "role": "tool",
                            "content": tool_result_content,
                        }
                    )

                # Add tool results to messages
                for tr in tool_results:
                    current_messages.append({"role": "tool", "tool_call_id": tr["tool_call_id"], "content": tr["content"]})
                current_messages.append(
                    {
                        "role": "system",
                        "content": "请基于以上工具结果直接输出最终中文回答，不要继续调用工具，也不要输出工具调用 JSON。",
                    }
                )

                # Make follow-up LLM call
                follow_up_params = dict(request_params)
                follow_up_params["messages"] = current_messages
                follow_up_params.pop("tools", None)
                follow_up_params.pop("tool_choice", None)

                follow_up_response = client.chat.completions.create(**follow_up_params)

                # Stream the follow-up response
                follow_up_buffer = ""
                for f_chunk in follow_up_response:
                    if not f_chunk.choices:
                        continue
                    f_delta = f_chunk.choices[0].delta
                    if hasattr(f_delta, "content") and f_delta.content:
                        follow_up_buffer += f_delta.content
                        yield {"event": "message", "data": {"chunk": f_delta.content}}
                return follow_up_buffer

            try:
                response = client.chat.completions.create(**request_params)
            except Exception as first_error:
                with app.app_context():
                    should_retry = (
                        provider == "qwen"
                        and model != qwen_fallback_model
                        and ChatService.should_retry_with_qwen_fallback(first_error)
                    )
                if not should_retry:
                    raise
                logger.warning(
                    "Primary qwen stream model unavailable, retrying with fallback model=%s: %s",
                    qwen_fallback_model,
                    first_error,
                )
                request_params["model"] = qwen_fallback_model
                response = client.chat.completions.create(**request_params)

            buffer = ""
            chunk_count = 0
            last_send_time = time.time()
            buffer_max_size = 5
            max_interval = 0.1

            # Collect tool call data across chunks
            tool_calls_data: list[Dict[str, Any]] = []

            for chunk in response:
                chunk_count += 1
                if not chunk.choices:
                    continue
                print(f"[DEBUG stream_message] LLM chunk #{chunk_count}: {str(chunk)[:80]}", file=sys.stderr)
                sys.stderr.flush()

                delta = chunk.choices[0].delta

                # Check for tool calls in this delta
                if hasattr(delta, "tool_calls") and delta.tool_calls:
                    for tc_delta in delta.tool_calls:
                        tc_index = tc_delta.index if hasattr(tc_delta, "index") else 0

                        while len(tool_calls_data) <= tc_index:
                            tool_calls_data.append(
                                {
                                    "id": "",
                                    "type": "function",
                                    "function": {
                                        "name": "",
                                        "arguments": "",
                                    },
                                }
                            )
                        current_tool_call = tool_calls_data[tc_index]

                        tc_id = str(getattr(tc_delta, "id") or "")
                        if tc_id:
                            current_tool_call["id"] = tc_id

                        tc_function = getattr(tc_delta, "function", None)
                        if tc_function is not None:
                            name_part = str(getattr(tc_function, "name", "") or "")
                            if name_part:
                                current_tool_call["function"]["name"] += name_part
                            arguments_part = str(getattr(tc_function, "arguments", "") or "")
                            if arguments_part:
                                current_tool_call["function"]["arguments"] += arguments_part

                        # If content is also present, yield it
                        if hasattr(delta, "content") and delta.content:
                            buffer += delta.content
                            current_time = time.time()
                            should_flush = (
                                len(buffer) >= buffer_max_size
                                or chunk_count <= 2
                                or (current_time - last_send_time) >= max_interval
                            )
                            if should_flush:
                                full_response += buffer
                                yield {"event": "message", "data": {"chunk": buffer}}
                                buffer = ""
                                last_send_time = current_time
                    continue

                # Regular content
                if not hasattr(delta, "content") or delta.content is None:
                    continue
                if delta.content == "":
                    continue

                buffer += delta.content
                current_time = time.time()
                should_flush = (
                    len(buffer) >= buffer_max_size
                    or chunk_count <= 2
                    or (current_time - last_send_time) >= max_interval
                )
                if should_flush:
                    full_response += buffer
                    yield {"event": "message", "data": {"chunk": buffer}}
                    buffer = ""
                    last_send_time = current_time

            if buffer:
                full_response += buffer
                yield {"event": "message", "data": {"chunk": buffer}}

            # Check if we collected tool calls - execute them and continue
            if tool_calls_data:
                logger.info("Model requested %d tool calls: %s", len(tool_calls_data), [tc.get("function", {}).get("name") for tc in tool_calls_data])
                # Build updated messages with assistant's tool call message
                assistant_tool_msg = {
                    "role": "assistant",
                    "tool_calls": tool_calls_data,
                }
                updated_messages = prepared_messages + [assistant_tool_msg]
                # Execute tools and stream follow-up
                follow_up_text = ""
                for event in execute_tools_and_continue(tool_calls_data, updated_messages):
                    if event.get("event") == "message":
                        follow_up_text += event.get("data", {}).get("chunk", "")
                if not follow_up_text.strip() and tool_generated_response.strip() and not full_response.strip():
                    logger.info(
                        "Using tool-generated assistant content as final response for session %s because follow-up LLM output was empty",
                        input_data.session_id,
                    )
                    full_response = tool_generated_response
                else:
                    full_response += follow_up_text

        except Exception as exc:
            error_occurred = True
            stream_issue = _classify_stream_exception(exc)
            logger.error("MCP stream failed provider=%s model=%s: %s", provider, model, exc, exc_info=True)
            if full_response.strip():
                with app.app_context():
                    save_result = ChatService.add_message(
                        input_data.session_id,
                        "assistant",
                        full_response,
                        extra_fields=_build_stream_message_extra_fields(
                            debug_mode=debug_mode,
                            route=route,
                            grounding_status=str(grounding_payload.get("groundingStatus") or ""),
                            confidence=str(grounding_payload.get("confidence") or ""),
                            used_realtime_retrieval=bool(grounding_payload.get("usedRealtimeRetrieval")),
                            sources=grounding_payload.get("sources") or [],
                            citations=grounding_payload.get("citations") or [],
                            facts=grounding_payload.get("facts") or [],
                            to_verify=grounding_payload.get("toVerify") or [],
                            analysis=grounding_payload.get("analysis") or [],
                            fallback_reason=stream_issue["fallbackReason"],
                            upstream_code=stream_issue["upstreamCode"],
                            upstream_type=stream_issue["upstreamType"],
                            phase=stream_issue["phase"],
                            search_timed_out=search_timed_out,
                            search_failed=search_failed,
                        ),
                    )
                if not save_result:
                    yield {
                        "event": "warning",
                        "data": _build_stream_event_data(
                            debug_mode=debug_mode,
                            route=route,
                            warning="响应已部分生成，但保存 AI 消息失败",
                        ),
                    }
                yield {
                    "event": "warning",
                        "data": _build_stream_event_data(
                            debug_mode=debug_mode,
                            route=route,
                            warning=f"响应在生成尾部中断，已保留已生成内容。{stream_issue['displayMessage']}",
                            code="partial_response",
                            fallbackReason=stream_issue["fallbackReason"],
                            upstreamCode=stream_issue["upstreamCode"],
                            upstreamType=stream_issue["upstreamType"],
                            phase=stream_issue["phase"],
                    ),
                }
                yield {
                    "event": "done",
                    "data": _build_stream_event_data(
                        debug_mode=debug_mode,
                        route=route,
                        status="partial_complete",
                        full_text=full_response,
                        warning=stream_issue["displayMessage"],
                        fallbackReason=stream_issue["fallbackReason"],
                        upstreamCode=stream_issue["upstreamCode"],
                        upstreamType=stream_issue["upstreamType"],
                        phase=stream_issue["phase"],
                    ),
                }
            else:
                with app.app_context():
                    ChatService.add_message(
                        input_data.session_id,
                        "assistant",
                        stream_issue["fallbackMessage"],
                        extra_fields=_build_stream_message_extra_fields(
                            debug_mode=debug_mode,
                            route=route,
                            grounding_status=str(grounding_payload.get("groundingStatus") or ""),
                            confidence=str(grounding_payload.get("confidence") or ""),
                            used_realtime_retrieval=bool(grounding_payload.get("usedRealtimeRetrieval")),
                            sources=grounding_payload.get("sources") or [],
                            citations=grounding_payload.get("citations") or [],
                            facts=grounding_payload.get("facts") or [],
                            to_verify=grounding_payload.get("toVerify") or [],
                            analysis=grounding_payload.get("analysis") or [],
                            fallback_reason=stream_issue["fallbackReason"],
                            upstream_code=stream_issue["upstreamCode"],
                            upstream_type=stream_issue["upstreamType"],
                            phase=stream_issue["phase"],
                            search_timed_out=search_timed_out,
                            search_failed=search_failed,
                        ),
                    )
                yield {
                    "event": "error",
                    "data": _build_stream_event_data(
                        debug_mode=debug_mode,
                        route=route,
                        error=stream_issue["displayMessage"],
                        code="upstream_error",
                        fallbackReason=stream_issue["fallbackReason"],
                        upstreamCode=stream_issue["upstreamCode"],
                        upstreamType=stream_issue["upstreamType"],
                        phase=stream_issue["phase"],
                    ),
                }

        effective_response = full_response.strip() if full_response else ""

        if effective_response:
            if not error_occurred:
                if tool_generated_response_saved and effective_response == tool_generated_response:
                    save_result = True
                else:
                    with app.app_context():
                        save_result = ChatService.add_message(
                            input_data.session_id,
                            "assistant",
                            effective_response,
                            extra_fields=_build_stream_message_extra_fields(
                                debug_mode=debug_mode,
                                route=route,
                                grounding_status=str(grounding_payload.get("groundingStatus") or ""),
                                confidence=str(grounding_payload.get("confidence") or ""),
                                used_realtime_retrieval=bool(grounding_payload.get("usedRealtimeRetrieval")),
                                sources=grounding_payload.get("sources") or [],
                                citations=grounding_payload.get("citations") or [],
                                facts=grounding_payload.get("facts") or [],
                                to_verify=grounding_payload.get("toVerify") or [],
                                analysis=grounding_payload.get("analysis") or [],
                                search_timed_out=search_timed_out,
                                search_failed=search_failed,
                            ),
                        )
                if not save_result:
                    yield {
                        "event": "warning",
                        "data": _build_stream_event_data(
                            debug_mode=debug_mode,
                            route=route,
                            warning="响应已生成，但保存 AI 消息失败",
                        ),
                    }
        else:
            if stream_issue is None:
                stream_issue = {
                    "fallbackReason": "empty_response",
                    "upstreamCode": "empty_response",
                    "upstreamType": "upstream_error",
                    "phase": "llm",
                    "fallbackMessage": GENERIC_UPSTREAM_FALLBACK_MESSAGE,
                    "displayMessage": "上游模型未返回有效分析结果，已替换为提示信息。",
                }
            if not error_occurred:
                with app.app_context():
                    save_result = ChatService.add_message(
                        input_data.session_id,
                        "assistant",
                        stream_issue["fallbackMessage"],
                        extra_fields=_build_stream_message_extra_fields(
                            debug_mode=debug_mode,
                            route=route,
                            grounding_status=str(grounding_payload.get("groundingStatus") or ""),
                            confidence=str(grounding_payload.get("confidence") or ""),
                            used_realtime_retrieval=bool(grounding_payload.get("usedRealtimeRetrieval")),
                            sources=grounding_payload.get("sources") or [],
                            citations=grounding_payload.get("citations") or [],
                            facts=grounding_payload.get("facts") or [],
                            to_verify=grounding_payload.get("toVerify") or [],
                            analysis=grounding_payload.get("analysis") or [],
                            fallback_reason=stream_issue["fallbackReason"],
                            upstream_code=stream_issue["upstreamCode"],
                            upstream_type=stream_issue["upstreamType"],
                            phase=stream_issue["phase"],
                            search_timed_out=search_timed_out,
                            search_failed=search_failed,
                        ),
                    )
                yield {
                    "event": "warning",
                    "data": _build_stream_event_data(
                        debug_mode=debug_mode,
                        route=route,
                        warning=stream_issue["displayMessage"],
                        fallbackReason=stream_issue["fallbackReason"],
                        upstreamCode=stream_issue["upstreamCode"],
                        upstreamType=stream_issue["upstreamType"],
                        phase=stream_issue["phase"],
                    ),
                }

        if not error_occurred:
            yield {
                "event": "done",
                "data": _build_stream_event_data(
                    debug_mode=debug_mode,
                    route=route,
                    status="complete",
                    full_text=effective_response or stream_issue["fallbackMessage"],
                    warning=stream_issue["displayMessage"] if stream_issue else None,
                    fallbackReason=stream_issue["fallbackReason"] if stream_issue else None,
                    upstreamCode=stream_issue["upstreamCode"] if stream_issue else None,
                    upstreamType=stream_issue["upstreamType"] if stream_issue else None,
                    phase=stream_issue["phase"] if stream_issue else None,
                ),
            }

    return generate()
