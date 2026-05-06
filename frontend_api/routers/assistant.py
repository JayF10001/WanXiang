from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed, TimeoutError
import hashlib
import json
import logging
import os
import random
import threading
import time
import uuid
from pathlib import Path
from typing import Iterable
from urllib.parse import urlparse
from fastapi import APIRouter, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, StreamingResponse
from requests import RequestException
from pydantic import BaseModel, ConfigDict, Field

from ..core.config import settings
from ..schemas.assistant import AnalyzeRequest
from ..services.chatbackend_client import client
from ..services.cache_service import cache_service
from ..services.mcp_chat_service import (
    get_backend_session,
    invoke_chat_stream_tool,
    invoke_chat_tool,
    invoke_report_tool,
)
from ..services.panels_fallback import build_panels_payload


router = APIRouter(prefix="/api/assistant", tags=["assistant"])
logger = logging.getLogger(__name__)
SEARCH_DIAGNOSTICS_VERSION = "search-diagnostics-v1"
HOME_SENTIMENT_TIMEOUT = 20
HOME_IMAGE_TIMEOUT = 10
HOME_CACHE_TTL_SECONDS = 180
HOME_STALE_TTL_SECONDS = 900
HOME_CACHE_KEY = "assistant_home_v5"
HOME_PLATFORM_CARD_LIMIT = 4
HOME_TOTAL_CARD_LIMIT = 24
HOME_SENTIMENT_ANALYSIS_LIMIT = HOME_TOTAL_CARD_LIMIT
HOME_IMAGE_ENRICH_LIMIT = HOME_TOTAL_CARD_LIMIT
HOME_MINDSPIDER_NEWS_LIMIT = 18

_assistant_home_cache_lock = threading.Lock()
_assistant_home_cache: dict[str, object] = {
    "refreshing": False,
}

NEGATIVE_HINTS = (
    "塌房", "事故", "起火", "火灾", "爆炸", "身亡", "死亡", "受伤", "遇难", "坠毁", "相撞", "撞车",
    "被曝", "举报", "争议", "冲突", "危机", "投诉", "质疑", "处罚", "调查", "通报", "造假", "违法",
    "暴力", "偷", "偷窥", "扰民", "垃圾", "翻车", "封禁", "跌", "暴跌", "下跌", "出轨", "骚扰", "欺诈",
    "危险", "警告", "紧急", "失联", "失踪", "欠薪", "烂尾", "停运", "停摆", "拖欠", "涉案", "被抓",
    "刑拘", "逮捕", "判刑", "谣言", "辟谣", "打架", "互殴", "威胁", "攻击", "制裁", "战火", "冲击",
    "暴雷", "暴毙", "破产", "清仓", "裁员", "恐慌", "风险", "失火", "中毒", "感染", "确诊", "病亡",
)
POSITIVE_HINTS = (
    "好人好事", "表彰", "获奖", "突破", "成功", "救援", "暖心", "正能量", "上涨", "增长",
    "发布", "落地", "创新", "进展", "改善", "恢复", "回暖", "签约", "合作", "幸福", "加码",
    "投产", "开通", "开园", "启用", "竣工", "交付", "通车", "开业", "首发", "夺冠", "晋级", "刷新",
    "纪录", "提升", "优化", "上线", "官宣", "免费", "支持", "利好", "回升", "上调", "稳步", "圆满",
)

POSITIVE_EMOTIONS = ("喜悦", "期待")
NEGATIVE_EMOTIONS = ("悲伤", "愤怒", "恐惧", "厌恶")
NEUTRAL_EMOTIONS = ("平和", "惊讶")


class UpdateSessionTitleRequest(BaseModel):
    title: str


class GenerateStrategyRequest(BaseModel):
    event_summary: str
    fact_check: str = ""
    initial_actions: str = ""
    short_term_goals: str = ""
    mid_term_goals: str = ""
    long_term_goals: str = ""
    time_constraints: str = ""
    budget_constraints: str = ""
    additional_info: str = ""


class HotspotContextRequest(BaseModel):
    title: str
    platformHint: str = ""
    sourceUrl: str = ""
    publishedAt: str = ""
    maxCandidates: int = 5


class CrawlContextRequest(BaseModel):
    title: str
    sourceUrl: str = ""
    platformHint: str = ""
    sessionId: str = ""
    maxCandidates: int = 5
    forceRefresh: bool = False


class MindSpiderTopicExtractionRequest(BaseModel):
    sources: list[str] = []
    maxKeywords: int = 100


class MindSpiderDeepSentimentRequest(BaseModel):
    extractDate: str = ""
    platforms: list[str] = []
    maxKeywordsPerPlatform: int = 20
    maxCandidatesPerKeyword: int = 3


class VerifySourceCredibilityRequest(BaseModel):
    url: str = ""
    sourceName: str = ""
    platform: str = ""


class VerifyTimeConsistencyRequest(BaseModel):
    title: str = ""
    publishedAt: str = ""
    extractedText: str = ""
    hotspotTime: str = ""


class TimelineDocumentRequest(BaseModel):
    title: str = ""
    content: str = ""
    source: str = ""
    sourceName: str = ""
    publishedAt: str = ""
    url: str = ""


class ExtractTimelineRequest(BaseModel):
    documents: list[TimelineDocumentRequest] = []


def _require_backend_cookies(request: Request):
    backend_cookies = request.session.get("chatbackend_cookies")
    if not backend_cookies:
        raise HTTPException(status_code=401, detail="未登录")
    return backend_cookies


def _resolve_backend_user_id(request: Request) -> str:
    backend_cookies = _require_backend_cookies(request)
    response, payload = client.request_json("GET", "/api/currentUser", session_cookie=backend_cookies)
    if response.status_code >= 400 or not payload.get("success"):
        raise HTTPException(status_code=response.status_code or 401, detail=payload.get("errorMessage") or payload.get("error") or "未登录")
    data = payload.get("data") or {}
    user_id = str(data.get("userid") or "").strip()
    if not user_id:
        raise HTTPException(status_code=401, detail="未登录")
    return user_id


def _run_search_diagnostics(
    *,
    query: str,
    source_url: str,
    platform_hint: str,
    user_id: str,
    max_results: int,
    include_loaded_pages: bool,
) -> dict:
    from ChatBackend.app.services.overview_search_service import OverviewSearchService

    return OverviewSearchService.search(
        query=query,
        source_url=source_url,
        platform_hint=platform_hint,
        session_id="search-diagnostics",
        user_id=user_id,
        max_results=max_results,
        include_loaded_pages=include_loaded_pages,
    )


def _build_search_diagnostics_payload(
    *,
    query: str,
    source_url: str,
    platform_hint: str,
    user_id: str,
    max_results: int,
    include_loaded_pages: bool,
) -> dict:
    result = _run_search_diagnostics(
        query=query,
        source_url=source_url,
        platform_hint=platform_hint,
        user_id=user_id,
        max_results=max_results,
        include_loaded_pages=include_loaded_pages,
    )
    payload = {
        "normalizedQuery": str(result.get("query") or query or "").strip(),
        "items": list(result.get("items") or []),
        "summary": str(result.get("summary") or ""),
        "providerDiagnostics": list(result.get("providerDiagnostics") or []),
        "selectedProviders": list(result.get("selectedProviders") or []),
        "totalDurationMs": int(result.get("totalDurationMs") or 0),
        "partialFailure": bool(result.get("partialFailure")),
        "debugVersion": str(result.get("debugVersion") or SEARCH_DIAGNOSTICS_VERSION),
    }
    if include_loaded_pages:
        payload["loadedPages"] = list(result.get("loadedPages") or [])
    return payload

def adapt_session(item: dict) -> dict:
    return {
        "id": str(item.get("id") or item.get("_id") or ""),
        "title": str(item.get("title") or "未命名会话"),
        "updatedAt": str(item.get("updated_at") or item.get("updatedAt") or ""),
        "createdAt": str(item.get("created_at") or item.get("createdAt") or ""),
        "summary": item.get("summary"),
        "hasReport": bool(item.get("report_id")),
        "reportId": str(item.get("report_id")) if item.get("report_id") else None,
        "hasStrategy": bool(item.get("strategy_id")),
        "strategyId": str(item.get("strategy_id")) if item.get("strategy_id") else None,
    }


def _build_fallback_message_id(item: dict, session_id: str, index: int) -> str:
    raw_parts = [
        str(session_id or ""),
        str(item.get("role") or ""),
        str(item.get("created_at") or item.get("createdAt") or item.get("timestamp") or ""),
        str(item.get("content") or ""),
        str(index),
    ]
    digest = hashlib.md5("||".join(raw_parts).encode("utf-8")).hexdigest()[:16]
    return f"{session_id}-msg-{digest}"


def adapt_message(item: dict, session_id: str, index: int = 0) -> dict:
    message_type = str(item.get("message_type") or "plain")
    message_id = str(item.get("id") or item.get("_id") or "").strip()
    render_mode = item.get("render_mode") or item.get("renderMode")
    return {
        "id": message_id or _build_fallback_message_id(item, session_id, index),
        "sessionId": str(item.get("session_id") or session_id),
        "role": str(item.get("role") or "assistant"),
        "content": str(item.get("content") or ""),
        "createdAt": str(item.get("created_at") or item.get("createdAt") or item.get("timestamp") or ""),
        "messageType": message_type,
        "renderMode": str(render_mode or ("report_card" if message_type == "event_report" else "bubble")),
        "status": item.get("status"),
        "tagLabel": item.get("tag_label"),
        "thinking": item.get("thinking"),
        "reportTitle": item.get("report_title"),
        "reportStatus": item.get("report_status"),
        "strategyTitle": item.get("strategy_title"),
        "strategyStatus": item.get("strategy_status"),
        "strategyId": item.get("strategy_id"),
        "groundingStatus": item.get("grounding_status") or item.get("groundingStatus"),
        "confidence": item.get("confidence"),
        "usedRealtimeRetrieval": item.get("used_realtime_retrieval") if item.get("used_realtime_retrieval") is not None else item.get("usedRealtimeRetrieval"),
        "sources": item.get("sources") or [],
        "citations": item.get("citations") or [],
        "facts": item.get("facts") or [],
        "toVerify": item.get("to_verify") or item.get("toVerify") or [],
        "analysis": item.get("analysis") or [],
        "route": item.get("route"),
        "debugMode": item.get("debug_mode") if item.get("debug_mode") is not None else item.get("debugMode"),
        "fallbackReason": item.get("fallback_reason") or item.get("fallbackReason"),
        "upstreamCode": item.get("upstream_code") or item.get("upstreamCode"),
        "upstreamType": item.get("upstream_type") or item.get("upstreamType"),
        "phase": item.get("phase"),
        "searchTimedOut": item.get("search_timed_out") if item.get("search_timed_out") is not None else item.get("searchTimedOut"),
        "searchFailed": item.get("search_failed") if item.get("search_failed") is not None else item.get("searchFailed"),
        "fallbackLevel": item.get("fallback_level") if item.get("fallback_level") is not None else item.get("fallbackLevel"),
        "finalModel": item.get("final_model") or item.get("finalModel"),
        "degradeReason": item.get("degrade_reason") or item.get("degradeReason"),
        "degradeMessage": item.get("degrade_message") or item.get("degradeMessage"),
        "modelAttempts": item.get("model_attempts") or item.get("modelAttempts") or [],
        "audioUrl": item.get("audio_url") or item.get("audioUrl"),
        "ttsStatus": item.get("tts_status") or item.get("ttsStatus"),
        "ttsTaskId": item.get("tts_task_id") or item.get("ttsTaskId"),
        "ttsProvider": item.get("tts_provider") or item.get("ttsProvider"),
        "ttsDurationSeconds": item.get("tts_duration_seconds") if item.get("tts_duration_seconds") is not None else item.get("ttsDurationSeconds"),
        "ttsError": item.get("tts_error") or item.get("ttsError"),
    }


def sse_event(event: str, data: dict) -> str:
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


def _infer_card_sentiment(title: str) -> str:
    normalized = str(title or "").strip()
    if not normalized:
        return "neutral"

    negative_score = sum(1 for keyword in NEGATIVE_HINTS if keyword in normalized)
    positive_score = sum(1 for keyword in POSITIVE_HINTS if keyword in normalized)

    if any(token in normalized for token in ("？", "?")):
        negative_score += 0.3
    if any(token in normalized for token in ("成功", "突破", "获奖", "通车", "救援")):
        positive_score += 0.5
    if any(token in normalized for token in ("身亡", "死亡", "坠毁", "相撞", "处罚", "危险", "事故")):
        negative_score += 0.8

    if negative_score >= positive_score + 0.5 and negative_score >= 1:
        return "negative"
    if positive_score >= negative_score + 0.5 and positive_score >= 1:
        return "positive"
    return "neutral"


def _build_card_image(title: str, platform_name: str, rank: int, sentiment: str) -> str:
    normalized = str(platform_name or "").strip().lower()
    if "微博" in platform_name or "weibo" in normalized:
        return "/fallbacks/微博.jpg"
    if "哔哩" in platform_name or "bilibili" in normalized:
        return "/fallbacks/哔哩哔哩.jpg"
    if "百度" in platform_name or "baidu" in normalized or "tieba" in normalized:
        return "/fallbacks/百度.jpg"
    if "抖音" in platform_name or "douyin" in normalized or "快手" in platform_name or "kuaishou" in normalized:
        return "/fallbacks/抖音.jpg"
    if "知乎" in platform_name or "zhihu" in normalized or "头条" in platform_name or "toutiao" in normalized:
        return "/fallbacks/微博.jpg"
    if "少数派" in platform_name or "sspai" in normalized or "it之家" in platform_name.lower() or "ithome" in normalized or "澎湃" in platform_name or "thepaper" in normalized or "腾讯" in platform_name or "qq-news" in normalized:
        return "/fallbacks/哔哩哔哩.jpg"
    return "/fallbacks/微博.jpg"


def _normalize_title_key(value: str) -> str:
    return "".join(str(value or "").strip().split())


def _derive_sentiment_from_emotion_schema(schema: dict) -> tuple[str, str] | None:
    if not isinstance(schema, dict):
        return None

    positive_score = sum(float(schema.get(key) or 0) for key in POSITIVE_EMOTIONS)
    negative_score = sum(float(schema.get(key) or 0) for key in NEGATIVE_EMOTIONS)
    neutral_score = sum(float(schema.get(key) or 0) for key in NEUTRAL_EMOTIONS)

    buckets = {
        "positive": positive_score,
        "negative": negative_score,
        "neutral": neutral_score,
    }
    top_sentiment, top_score = max(buckets.items(), key=lambda item: item[1])
    if top_score <= 0:
        return None

    label_map = {
        "positive": "正向",
        "negative": "负向",
        "neutral": "中性",
    }
    percent = round(top_score * 100)
    return top_sentiment, f"情感分析：{label_map[top_sentiment]}（后端分析 {percent}%）"


def _load_backend_sentiment_map(titles: list[str] | None = None) -> dict[str, dict]:
    try:
        unique_titles = []
        seen = set()
        for item in titles or []:
            title = str(item or "").strip()
            if not title or title in seen:
                continue
            seen.add(title)
            unique_titles.append(title)

        if unique_titles:
            response, payload = client.request_json(
                "POST",
                "/api/analyze_news_public/batch",
                json_data={"titles": unique_titles},
                timeout=HOME_SENTIMENT_TIMEOUT,
            )
        else:
            response, payload = client.request_json("GET", "/api/analyze_news_public")
        if response.status_code >= 400:
            return {}

        items = payload.get("data", []) if isinstance(payload.get("data"), list) else []
        sentiment_map: dict[str, dict] = {}
        for item in items:
            if not isinstance(item, dict):
                continue
            title_key = _normalize_title_key(str(item.get("title") or ""))
            if not title_key:
                continue
            sentiment = str(item.get("sentiment") or "").strip()
            sentiment_label = str(item.get("sentiment_label") or "").strip()
            if sentiment not in {"positive", "negative", "neutral"}:
                continue
            sentiment_map[title_key] = {
                "sentiment": sentiment,
                "sentimentLabel": sentiment_label or None,
                "sentimentSourceLabel": "情感来源：后端分析",
            }
        return sentiment_map
    except Exception:
        logger.exception("Failed to load backend sentiment analysis for assistant home")
        return {}


def _normalize_thumbnail_url(value: str) -> str:
    url = str(value or "").strip()
    if not url:
        return ""
    if url.startswith("//"):
        return f"https:{url}"
    return url


def _build_recommendation_summary(
    *,
    title: str,
    platform_name: str,
    rank: int,
    hot_value: str,
    sentiment: str,
    published_at: str,
) -> str:
    sentiment_hint = {
        "positive": "当前呈现出偏正向的传播信号，适合继续关注其扩散范围与受众反馈。",
        "negative": "当前呈现出偏负向的传播信号，建议重点留意争议点、风险点和后续舆论走向。",
        "neutral": "当前更接近信息型或观察型热点，建议结合上下文判断其是否正在转向更明确的舆论情绪。",
    }.get(sentiment, "建议结合上下文和原始链接，进一步判断其传播价值与潜在影响。")

    time_text = f"更新时间约为 {published_at}。" if published_at else ""
    hot_text = f"目前位于 {platform_name} 热榜第 {rank} 位，热度 {hot_value}。" if hot_value else f"目前位于 {platform_name} 热榜第 {rank} 位。"
    return f"{title}。{hot_text}{time_text}{sentiment_hint}"


def _is_listing_like_source_url(url: str) -> bool:
    parsed = urlparse(str(url or "").strip())
    host = (parsed.netloc or "").lower()
    path = parsed.path or ""
    query = parsed.query or ""
    if host == "s.weibo.com":
        return True
    if host.endswith("baidu.com") and (path.startswith("/s") or "wd=" in query):
        return True
    if host.endswith("bing.com") and path.startswith("/search"):
        return True
    if host.endswith("weibo.com") and ("q=" in query or path.startswith("/weibo")):
        return True
    return False


def _is_noisy_recommendation_summary(summary: str) -> bool:
    text = str(summary or "").strip().lower()
    if not text:
        return False
    noisy_patterns = (
        "百度一下",
        "输入法 手写 拼音",
        "关闭 百度首页 设置 登录",
        "hao123",
        "贴吧 学术 登录",
        "更多产品",
        "@description",
        "bds.base64",
        "author lizhouquan",
        "地图 视频 贴吧 学术",
    )
    return any(pattern in text for pattern in noisy_patterns)


def _mindspider_platform_display_name(source: str, source_name: str = "") -> str:
    normalized = str(source or "").strip().lower()
    if normalized == "weibo":
        return "微博"
    if normalized == "zhihu":
        return "知乎"
    if normalized == "douyin":
        return "抖音"
    if normalized == "bilibili-hot-search":
        return "哔哩哔哩"
    if normalized == "toutiao":
        return "今日头条"
    if normalized == "tieba":
        return "百度贴吧"
    if normalized == "kuaishou":
        return "快手"
    if normalized == "github-trending-today":
        return "GitHub Trending"
    if normalized == "coolapk":
        return "酷安"
    if normalized == "thepaper":
        return "澎湃新闻"
    if normalized == "wallstreetcn":
        return "华尔街见闻"
    if normalized == "cls-hot":
        return "财联社"
    return str(source_name or source or "热榜")


def _load_mindspider_topic_analysis() -> dict:
    try:
        response, payload = client.request_json(
            "GET",
            "/api/mindspider/topic-analysis",
            timeout=8,
        )
        if response.status_code >= 400 or not payload.get("success"):
            return {}
        return payload.get("data") if isinstance(payload.get("data"), dict) else {}
    except Exception:
        logger.debug("Failed to load MindSpider topic analysis for assistant home", exc_info=True)
        return {}


def _merge_mindspider_into_hotnews_payload(raw_payload: dict, mindspider_data: dict | None = None) -> dict:
    if not isinstance(raw_payload, dict):
        return {"data": []}

    merged_blocks: list[dict] = []
    block_index_by_name: dict[str, int] = {}
    for block in raw_payload.get("data", []) if isinstance(raw_payload.get("data"), list) else []:
        if not isinstance(block, dict):
            continue
        copied_block = {
            **block,
            "data": [item for item in block.get("data", []) if isinstance(item, dict)],
        }
        name = str(copied_block.get("name") or f"热榜-{len(merged_blocks) + 1}")
        block_index_by_name[name] = len(merged_blocks)
        merged_blocks.append(copied_block)

    news_items = mindspider_data.get("news", []) if isinstance(mindspider_data, dict) else []
    extract_date = str(mindspider_data.get("extractDate") or "").strip() if isinstance(mindspider_data, dict) else ""

    total_added = 0
    for news in news_items:
        if not isinstance(news, dict):
            continue
        title = str(news.get("title") or "").strip()
        if not title:
            continue
        platform_name = _mindspider_platform_display_name(
            str(news.get("source") or ""),
            str(news.get("source_name") or ""),
        )
        if platform_name not in block_index_by_name:
            block_index_by_name[platform_name] = len(merged_blocks)
            merged_blocks.append(
                {
                    "name": platform_name,
                    "source": "mindspider",
                    "fallback_used": False,
                    "update_time": extract_date,
                    "data": [],
                }
            )

        target_block = merged_blocks[block_index_by_name[platform_name]]
        existing_title_keys = {
            _normalize_title_key(str(item.get("title") or ""))
            for item in target_block.get("data", [])
            if isinstance(item, dict)
        }
        title_key = _normalize_title_key(title)
        if title_key in existing_title_keys:
            continue

        target_block.setdefault("data", []).append(
            {
                "title": title,
                "url": news.get("url") or "",
                "published_at": news.get("crawl_date") or extract_date,
                "index": int(news.get("rank") or len(target_block.get("data", [])) + 1),
                "hot": "",
            }
        )
        total_added += 1
        if total_added >= HOME_MINDSPIDER_NEWS_LIMIT:
            break

    return {
        **raw_payload,
        "data": merged_blocks,
    }


def _select_home_platform_blocks(raw_payload: dict, refresh_token: str = "") -> list[dict]:
    platform_blocks = raw_payload.get("data", []) if isinstance(raw_payload.get("data"), list) else []
    refresh_token = str(refresh_token or "").strip()
    if refresh_token and platform_blocks:
        seed = int(hashlib.md5(refresh_token.encode("utf-8")).hexdigest()[:8], 16)
        platform_blocks = list(platform_blocks)
        random.Random(seed).shuffle(platform_blocks)
    return [item for item in platform_blocks if isinstance(item, dict)]


def _select_home_display_items(platform_block: dict, refresh_token: str = "") -> list[dict]:
    items = platform_block.get("data", []) if isinstance(platform_block.get("data"), list) else []
    display_items = [item for item in items if isinstance(item, dict)]
    platform_name = str(platform_block.get("name") or "热榜")
    refresh_token = str(refresh_token or "").strip()
    if refresh_token and len(display_items) > HOME_PLATFORM_CARD_LIMIT:
        platform_seed_text = f"{refresh_token}:{platform_name}"
        platform_seed = int(hashlib.md5(platform_seed_text.encode("utf-8")).hexdigest()[:8], 16)
        start_index = platform_seed % len(display_items)
        display_items = display_items[start_index:] + display_items[:start_index]
    return display_items[:HOME_PLATFORM_CARD_LIMIT]


def _load_recommendation_thumbnail_map(
    items: list[dict] | None = None,
    *,
    overall_timeout: float | None = None,
    cache_only: bool = False,
) -> dict[str, str]:
    unique_items = []
    seen = set()
    for item in items or []:
        if not isinstance(item, dict):
            continue
        title = str(item.get("title") or "").strip()
        source_url = str(item.get("url") or item.get("mobil_url") or "").strip()
        platform_hint = str(item.get("platform_hint") or item.get("platform") or "").strip()
        key = _normalize_title_key(title)
        if not key or key in seen:
            continue
        seen.add(key)
        unique_items.append({
            "title": title,
            "source_url": source_url,
            "platform_hint": platform_hint,
        })

    if not unique_items:
        return {}

    def fetch_thumbnail(item: dict) -> tuple[str, str]:
        title = str(item.get("title") or "").strip()
        try:
            response, payload = client.request_json(
                "POST",
                "/api/video/thumbnail/resolve",
                json_data={
                    "news_title": title,
                    "source_url": str(item.get("source_url") or ""),
                    "platform_hint": str(item.get("platform_hint") or ""),
                    "max_results": 5,
                    "force_refresh": False,
                    "skip_youtube": True,
                    "cache_only": cache_only,
                },
                timeout=HOME_IMAGE_TIMEOUT + 3,
            )
            if response.status_code >= 400 or not payload.get("success"):
                return title, ""

            thumbnail_url = _normalize_thumbnail_url(payload.get("image_url"))
            return title, thumbnail_url
        except Exception:
            logger.debug("Failed to load video thumbnail for title: %s", title, exc_info=True)
            return title, ""

    thumbnail_map: dict[str, str] = {}
    max_workers = min(8, len(unique_items))
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = [executor.submit(fetch_thumbnail, item) for item in unique_items]
        deadline = time.monotonic() + overall_timeout if overall_timeout else None
        try:
            iterator = as_completed(
                futures,
                timeout=max(0.1, overall_timeout) if overall_timeout else None,
            )
            for future in iterator:
                title, thumbnail_url = future.result()
                if thumbnail_url:
                    thumbnail_map[_normalize_title_key(title)] = thumbnail_url
                if deadline and time.monotonic() >= deadline:
                    break
        except TimeoutError:
            logger.info(
                "Assistant home thumbnail enrichment reached timeout, returning partial results: %s/%s",
                len(thumbnail_map),
                len(unique_items),
            )
        finally:
            for future in futures:
                if not future.done():
                    future.cancel()

    return thumbnail_map


@router.get("/recommendation-summary")
def get_recommendation_summary(request: Request, title: str, source_url: str = ""):
    normalized_title = str(title or "").strip()
    normalized_url = str(source_url or "").strip()
    if not normalized_title:
        raise HTTPException(status_code=400, detail="缺少标题")

    should_try_video_summary = normalized_url and not _is_listing_like_source_url(normalized_url)
    if should_try_video_summary:
        try:
            response, payload = client.request_json(
                "POST",
                "/api/video/summary/resolve",
                json_data={
                    "news_title": normalized_title,
                    "source_url": normalized_url,
                    "force_refresh": False,
                    "cache_only": False,
                },
                timeout=10,
            )
            if response.status_code < 400 and payload.get("success"):
                resolved_summary = str(payload.get("summary") or "").strip()
                if resolved_summary and not _is_noisy_recommendation_summary(resolved_summary):
                    return {
                        "success": True,
                        "data": {
                            "summary": resolved_summary,
                            "summarySource": str(payload.get("summary_source") or "meta_description"),
                        },
                        "message": "获取真实摘要成功",
                    }
        except Exception:
            logger.warning("Failed to resolve recommendation summary for title=%s", normalized_title, exc_info=True)

    try:
        response, payload = client.request_json(
            "POST",
            "/api/crawler/context",
            json_data={
                "title": normalized_title,
                "source_url": normalized_url,
                "max_candidates": 5,
                "force_refresh": False,
            },
            timeout=12,
        )
        if response.status_code >= 400 or not payload.get("success"):
            raise HTTPException(status_code=response.status_code or 500, detail=payload.get("message") or "抓取摘要失败")
        data = payload if isinstance(payload, dict) else {}
        summary = str(data.get("summary") or "").strip()
        excerpt = str(data.get("content_excerpt") or "").strip()
        fallback_summary = summary or excerpt
        if _is_noisy_recommendation_summary(fallback_summary):
            fallback_summary = ""
        if fallback_summary:
            return {
                "success": True,
                "data": {
                    "summary": fallback_summary,
                    "summarySource": "crawler",
                },
                "message": "获取抓取摘要成功",
            }
    except Exception:
        logger.warning("Failed to resolve crawler summary for title=%s", normalized_title, exc_info=True)

    return {
        "success": True,
        "data": {
            "summary": "",
            "summarySource": "fallback",
        },
        "message": "未获取到真实摘要",
    }


@router.post("/crawl-context")
def crawl_context(body: CrawlContextRequest, request: Request):
    result = invoke_chat_tool(
        request,
        "chat.crawl_news_context",
        {
            "title": body.title,
            "source_url": body.sourceUrl,
            "platform_hint": body.platformHint,
            "session_id": body.sessionId or None,
            "max_candidates": body.maxCandidates,
            "force_refresh": body.forceRefresh,
        },
    )
    return {
        "success": True,
        "data": result.get("data") or {},
        "message": "上下文抓取完成",
    }


@router.post("/mindspider/topic-extraction")
def run_mindspider_topic_extraction(body: MindSpiderTopicExtractionRequest, request: Request):
    result = invoke_chat_tool(
        request,
        "chat.run_mindspider_topic_extraction",
        {
            "sources": body.sources,
            "max_keywords": body.maxKeywords,
        },
    )
    return {
        "success": True,
        "data": result.get("data") or {},
        "message": "MindSpider 话题提取任务已启动",
    }


@router.get("/mindspider/topic-analysis")
def get_mindspider_topic_analysis(request: Request, extract_date: str = ""):
    result = invoke_chat_tool(
        request,
        "chat.get_mindspider_topic_analysis",
        {
            "extract_date": extract_date or None,
        },
    )
    return {
        "success": True,
        "data": result.get("data") or {},
        "message": "获取 MindSpider 话题分析成功",
    }


@router.post("/mindspider/deep-sentiment")
def run_mindspider_deep_sentiment(body: MindSpiderDeepSentimentRequest, request: Request):
    result = invoke_chat_tool(
        request,
        "chat.run_mindspider_deep_sentiment",
        {
            "extract_date": body.extractDate or None,
            "platforms": body.platforms,
            "max_keywords_per_platform": body.maxKeywordsPerPlatform,
            "max_candidates_per_keyword": body.maxCandidatesPerKeyword,
        },
    )
    return {
        "success": True,
        "data": result.get("data") or {},
        "message": "MindSpider 深度情感抓取任务已启动",
    }


@router.get("/mindspider/deep-sentiment")
def get_mindspider_deep_sentiment(request: Request, extract_date: str = ""):
    result = invoke_chat_tool(
        request,
        "chat.get_mindspider_deep_sentiment",
        {
            "extract_date": extract_date or None,
        },
    )
    return {
        "success": True,
        "data": result.get("data") or {},
        "message": "获取 MindSpider 深度情感结果成功",
    }


def _adapt_home_payload(
    raw_payload: dict,
    sentiment_map: dict[str, dict] | None = None,
    thumbnail_map: dict[str, str] | None = None,
    refresh_token: str = "",
) -> dict:
    cards = []
    suggested_prompts = []
    sentiment_map = sentiment_map or {}
    thumbnail_map = thumbnail_map or {}
    platform_blocks = _select_home_platform_blocks(raw_payload, refresh_token)

    for platform_block in platform_blocks:
        platform_name = str(platform_block.get("name") or "热榜")
        upstream_source = str(platform_block.get("source") or "unknown")
        fallback_used = bool(platform_block.get("fallback_used"))
        platform_update_time = str(platform_block.get("update_time") or "").strip()
        display_source_label = f"来源平台：{platform_name}"
        for item in _select_home_display_items(platform_block, refresh_token):
            if not isinstance(item, dict):
                continue
            title = str(item.get("title") or "").strip()
            if not title:
                continue
            rank = int(item.get("index") or len(cards) + 1)
            hot_value = str(item.get("hot") or "未知")
            matched_sentiment = sentiment_map.get(_normalize_title_key(title)) or {}
            sentiment = str(matched_sentiment.get("sentiment") or _infer_card_sentiment(title))
            sentiment_source_label = str(
                matched_sentiment.get("sentimentSourceLabel")
                or "情感来源：快速判断"
            )
            published_at = str(
                item.get("published_at")
                or item.get("publishedAt")
                or item.get("update_time")
                or item.get("updateTime")
                or platform_update_time
                or ""
            ).strip()
            cards.append(
                {
                    "id": f"{platform_name}-{rank}-{len(cards) + 1}",
                    "title": title,
                    "summary": _build_recommendation_summary(
                        title=title,
                        platform_name=platform_name,
                        rank=rank,
                        hot_value=hot_value,
                        sentiment=sentiment,
                        published_at=published_at,
                    ),
                    "author": platform_name,
                    "image": thumbnail_map.get(_normalize_title_key(title)) or _build_card_image(title, platform_name, rank, sentiment),
                    "sentiment": sentiment,
                    "sentimentLabel": matched_sentiment.get("sentimentLabel"),
                    "sentimentSourceLabel": sentiment_source_label,
                    "publishedAt": published_at,
                    "url": item.get("url") or item.get("mobil_url") or "",
                    "hot": hot_value,
                    "sourceLabel": display_source_label,
                    "sourceName": upstream_source,
                    "fallbackUsed": fallback_used,
                }
            )
            if len(suggested_prompts) < 3:
                suggested_prompts.append(f"帮我分析这个热点：{title}")
            if len(cards) >= HOME_TOTAL_CARD_LIMIT:
                break
        if len(cards) >= HOME_TOTAL_CARD_LIMIT:
            break

    if not cards:
        raise HTTPException(status_code=502, detail="未获取到可用的热点推荐数据")

    return {
        "recommendationCards": cards,
        "defaultModel": "万象智体",
        "suggestedPrompts": suggested_prompts or ["分析当前最值得关注的一条热点舆情"],
    }


def _get_cached_home_payload(*, allow_stale: bool = True) -> dict | None:
    cached_entry = cache_service.get(HOME_CACHE_KEY)
    if not cached_entry or not isinstance(cached_entry, dict):
        return None
    cached_data = cached_entry.get("data")
    updated_at = float(cached_entry.get("updated_at") or 0)
    if not cached_data or not isinstance(cached_data, dict):
        return None

    age = time.time() - updated_at
    if age <= HOME_CACHE_TTL_SECONDS:
        return cached_data
    if allow_stale and age <= HOME_STALE_TTL_SECONDS:
        return cached_data
    return None


def _set_cached_home_payload(payload: dict) -> None:
    cache_service.set(
        HOME_CACHE_KEY,
        {
            "data": payload,
            "updated_at": time.time(),
        },
        HOME_STALE_TTL_SECONDS,
    )


def _set_home_refreshing(value: bool) -> None:
    with _assistant_home_cache_lock:
        _assistant_home_cache["refreshing"] = value


def _is_home_refreshing() -> bool:
    with _assistant_home_cache_lock:
        return bool(_assistant_home_cache.get("refreshing"))


def _build_home_payload_sync(*, refresh_token: str = "", full_thumbnail_refresh: bool = False) -> dict:
    response, payload = client.request_json("GET", "/api/proxy/hotnews/all")
    if response.status_code >= 400:
        raise HTTPException(status_code=response.status_code or 502, detail=payload.get("error") or "获取热点推荐失败")

    payload = _merge_mindspider_into_hotnews_payload(payload, _load_mindspider_topic_analysis())

    hot_titles = []
    image_items = []
    platform_blocks = _select_home_platform_blocks(payload, refresh_token)
    for platform_block in platform_blocks:
        for item in _select_home_display_items(platform_block, refresh_token):
            if not isinstance(item, dict):
                continue
            title = str(item.get("title") or "").strip()
            if title:
                hot_titles.append(title)
                if len(image_items) < HOME_IMAGE_ENRICH_LIMIT:
                    image_items.append({
                        "title": title,
                        "url": item.get("url") or item.get("mobileUrl") or item.get("mobil_url") or "",
                        "platform_hint": platform_block.get("name") or "",
                    })
            if len(hot_titles) >= HOME_SENTIMENT_ANALYSIS_LIMIT:
                break
        if len(hot_titles) >= HOME_SENTIMENT_ANALYSIS_LIMIT:
            break

    sentiment_map: dict[str, dict] = {}
    thumbnail_map: dict[str, str] = {}
    with ThreadPoolExecutor(max_workers=2) as executor:
        sentiment_future = executor.submit(_load_backend_sentiment_map, hot_titles)
        thumbnail_future = executor.submit(
            _load_recommendation_thumbnail_map,
            image_items,
            overall_timeout=HOME_IMAGE_TIMEOUT,
            cache_only=not full_thumbnail_refresh,
        )
        try:
            sentiment_map = sentiment_future.result(timeout=HOME_SENTIMENT_TIMEOUT + 2)
        except Exception:
            logger.warning("Assistant home sentiment enrichment skipped due to timeout/error", exc_info=True)
            sentiment_map = {}
        try:
            thumbnail_map = thumbnail_future.result(timeout=HOME_IMAGE_TIMEOUT + 2)
        except Exception:
            logger.warning("Assistant home thumbnail enrichment skipped due to timeout/error", exc_info=True)
            thumbnail_map = {}

    return _adapt_home_payload(
        payload,
        sentiment_map=sentiment_map,
        thumbnail_map=thumbnail_map,
        refresh_token=refresh_token,
    )


def _refresh_home_cache_in_background() -> None:
    if _is_home_refreshing():
        return

    def runner():
        _set_home_refreshing(True)
        try:
            payload = _build_home_payload_sync(full_thumbnail_refresh=True)
            _set_cached_home_payload(payload)
        except Exception:
            logger.warning("Assistant home background refresh failed", exc_info=True)
        finally:
            _set_home_refreshing(False)

    threading.Thread(target=runner, name="assistant-home-refresh", daemon=True).start()


@router.get("/home")
def get_home(request: Request):
    try:
        refresh_token = str(request.query_params.get("refresh_token") or "").strip()
        cached_payload = _get_cached_home_payload(allow_stale=True)
        if cached_payload and not refresh_token:
            _refresh_home_cache_in_background()
            return {
                "success": True,
                "data": cached_payload,
                "message": "获取首页推荐成功",
                "meta": {
                    "servedFromCache": True,
                    "refreshing": _is_home_refreshing(),
                },
            }

        payload = _build_home_payload_sync(refresh_token=refresh_token, full_thumbnail_refresh=bool(refresh_token))
        if not refresh_token:
            _set_cached_home_payload(payload)
        return {
            "success": True,
            "data": payload,
            "message": "获取首页推荐成功",
            "meta": {
                "servedFromCache": False,
                "refreshing": False,
            },
        }
    except HTTPException:
        raise
    except RequestException as exc:
        logger.exception("Assistant home upstream request failed")
        raise HTTPException(status_code=502, detail=f"上游热点服务调用失败: {exc}") from exc
    except Exception as exc:
        logger.exception("Assistant home route failed")
        raise HTTPException(status_code=500, detail=f"获取首页推荐异常: {exc}") from exc


@router.get("/sessions")
def get_sessions(request: Request):
    result = invoke_chat_tool(request, "chat.list_sessions", {})
    sessions = [adapt_session(item) for item in result.get("data", {}).get("sessions", [])]
    return {
        "success": True,
        "data": {
            "sessions": sessions,
            "activeSessionId": sessions[0]["id"] if sessions else None,
        },
        "message": "获取会话成功",
    }


@router.post("/sessions")
def create_session(request: Request):
    result = invoke_chat_tool(request, "chat.create_session", {"initialize_conversation": False})

    return {
        "success": True,
        "data": adapt_session(result.get("data", {}).get("session", {})),
        "message": "创建会话成功",
    }


@router.delete("/sessions/{session_id}")
def delete_session(session_id: str, request: Request):
    invoke_chat_tool(request, "chat.delete_session", {"session_id": session_id})

    return {
        "success": True,
        "data": {"id": session_id},
        "message": "删除会话成功",
    }


@router.put("/sessions/{session_id}/title")
def update_session_title(session_id: str, body: UpdateSessionTitleRequest, request: Request):
    invoke_chat_tool(request, "chat.rename_session", {"session_id": session_id, "title": body.title})

    return {
        "success": True,
        "data": {"id": session_id, "title": body.title},
        "message": "重命名会话成功",
    }


@router.get("/sessions/{session_id}/messages")
def get_messages(session_id: str, request: Request):
    result = invoke_chat_tool(request, "chat.get_messages", {"session_id": session_id})
    messages = [
        adapt_message(item, session_id, index)
        for index, item in enumerate(result.get("data", {}).get("messages", []))
    ]
    return {"success": True, "data": messages, "message": "获取消息成功"}


class SaveDebugMessageRequest(BaseModel):
    role: str
    content: str


@router.post("/sessions/{session_id}/messages")
def save_debug_message(session_id: str, body: SaveDebugMessageRequest, request: Request):
    """直接保存调试消息到会话，不经过 LLM 或 MCP。用于 debug 工具链验证。"""
    get_backend_session(request)  # 验证用户登录
    try:
        from wanxiang_mcp.adapters.chatbackend_chat import get_flask_app
        from ChatBackend.app.services.chat_service import ChatService
        app = get_flask_app()
        with app.app_context():
            success = ChatService.add_message(session_id, body.role, body.content)
        if success:
            return {"success": True, "message": "消息已保存"}
        return {"success": False, "message": "保存失败，会话不存在"}
    except Exception as exc:
        logger.warning("save_debug_message failed: %s", exc)
        return {"success": False, "message": str(exc)}


@router.post("/sessions/{session_id}/strategy")
def generate_strategy(session_id: str, body: GenerateStrategyRequest, request: Request):
    result = invoke_chat_tool(
        request,
        "chat.generate_strategy",
        {
            "session_id": session_id,
            **body.model_dump(),
        },
    )
    return {
        "success": True,
        "data": result.get("data"),
        "message": "策略生成任务已启动",
    }


@router.post("/sessions/{session_id}/strategy-sync")
def generate_strategy_sync(session_id: str, body: GenerateStrategyRequest, request: Request):
    result = invoke_chat_tool(
        request,
        "chat.generate_strategy_sync",
        {
            "session_id": session_id,
            **body.model_dump(),
        },
    )
    return {
        "success": True,
        "data": result.get("data"),
        "message": "策略已同步生成",
    }


@router.post("/sessions/{session_id}/report")
def generate_session_report(session_id: str, request: Request):
    result = invoke_chat_tool(
        request,
        "chat.generate_report_from_session",
        {
            "session_id": session_id,
        },
    )
    return {
        "success": True,
        "data": result.get("data"),
        "message": "会话报告生成成功",
    }


# Media storage directory
_MULTIMODAL_STORAGE_ROOT = Path(settings.multimodal_storage_root)
_MULTIMODAL_EXTENSION_GROUPS = {
    "image": {"jpg", "jpeg", "png", "webp"},
    "audio": {"mp3", "wav", "m4a", "aac"},
    "video": {"mp4", "mov", "avi"},
}
_MULTIMODAL_SIZE_LIMITS = {
    "image": 20 * 1024 * 1024,
    "audio": 50 * 1024 * 1024,
    "video": 100 * 1024 * 1024,
}


def _detect_multimodal_type(filename: str) -> str:
    ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    for modality, extensions in _MULTIMODAL_EXTENSION_GROUPS.items():
        if ext in extensions:
            return modality
    raise HTTPException(status_code=400, detail="仅支持 jpg/jpeg/png/webp/mp3/wav/m4a/aac/mp4/mov/avi 格式")


async def _store_multimodal_files(session_id: str, files: Iterable[UploadFile]) -> list[str]:
    saved_paths: list[str] = []
    session_dir = _MULTIMODAL_STORAGE_ROOT / session_id
    session_dir.mkdir(parents=True, exist_ok=True)

    for upload in files:
        if not upload.filename:
            raise HTTPException(status_code=400, detail="存在未命名文件，无法识别类型")
        modality = _detect_multimodal_type(upload.filename)
        content = await upload.read()
        size = len(content)
        if size <= 0:
            raise HTTPException(status_code=400, detail=f"文件 {upload.filename} 内容为空")
        if size > _MULTIMODAL_SIZE_LIMITS[modality]:
            limit_mb = _MULTIMODAL_SIZE_LIMITS[modality] // (1024 * 1024)
            raise HTTPException(status_code=400, detail=f"{modality} 文件 {upload.filename} 不能超过 {limit_mb}MB")

        ext = upload.filename.rsplit(".", 1)[-1].lower()
        file_path = session_dir / f"{uuid.uuid4().hex}.{ext}"
        file_path.write_bytes(content)
        saved_paths.append(str(file_path))

    return saved_paths


@router.post("/sessions/{session_id}/multimodal-analysis")
async def analyze_multimodal(
    session_id: str,
    request: Request,
    files: list[UploadFile] = File(...),
    query: str | None = Form(None),
):
    normalized_files = [item for item in (files or []) if item is not None]
    if not normalized_files:
        raise HTTPException(status_code=400, detail="至少需要上传一个媒体文件")
    if len(normalized_files) > 10:
        raise HTTPException(status_code=400, detail="同一轮对话最多上传 10 个文件")

    saved_paths = await _store_multimodal_files(session_id, normalized_files)
    result = invoke_chat_tool(
        request,
        "chat.analyze_multimodal",
        {
            "session_id": session_id,
            "file_paths": saved_paths,
            "query": query,
        },
    )
    return {
        "success": True,
        "data": result.get("data"),
        "message": "多模态分析任务已启动",
    }


@router.post("/sessions/{session_id}/video-analysis")
async def analyze_video(
    session_id: str,
    request: Request,
    file: UploadFile = File(...),
    query: str | None = Form(None),
):
    if not file.filename:
        raise HTTPException(status_code=400, detail="缺少文件名")
    if _detect_multimodal_type(file.filename) != "video":
        raise HTTPException(status_code=400, detail="仅支持 mp4/mov/avi 格式")
    saved_paths = await _store_multimodal_files(session_id, [file])
    result = invoke_chat_tool(
        request,
        "chat.analyze_multimodal",
        {
            "session_id": session_id,
            "file_paths": saved_paths,
            "query": query,
        },
    )
    return {
        "success": True,
        "data": result.get("data"),
        "message": "视频分析任务已启动",
    }


@router.get("/tasks/{task_id}")
def get_task_status(task_id: str, request: Request):
    result = invoke_chat_tool(request, "chat.get_task_status", {"task_id": task_id})
    return {
        "success": True,
        "data": result.get("data"),
        "message": "获取任务状态成功",
    }


@router.get("/hotspot-context")
def get_hotspot_context(
    request: Request,
    title: str,
    platform_hint: str = "",
    source_url: str = "",
    published_at: str = "",
    max_candidates: int = 5,
):
    result = invoke_chat_tool(
        request,
        "chat.get_hotspot_context",
        {
            "title": title,
            "platform_hint": platform_hint,
            "source_url": source_url,
            "published_at": published_at,
            "max_candidates": max_candidates,
        },
    )
    return {
        "success": True,
        "data": result.get("data"),
        "message": "获取热点上下文成功",
    }


@router.post("/verify/source-credibility")
def verify_source_credibility(body: VerifySourceCredibilityRequest, request: Request):
    result = invoke_chat_tool(
        request,
        "chat.verify_source_credibility",
        {
            "url": body.url,
            "source_name": body.sourceName,
            "platform": body.platform,
        },
    )
    return {
        "success": True,
        "data": result.get("data"),
        "message": "来源可信度校验成功",
    }


@router.post("/verify/time-consistency")
def verify_time_consistency(body: VerifyTimeConsistencyRequest, request: Request):
    result = invoke_chat_tool(
        request,
        "chat.verify_time_consistency",
        {
            "title": body.title,
            "published_at": body.publishedAt,
            "extracted_text": body.extractedText,
            "hotspot_time": body.hotspotTime,
        },
    )
    return {
        "success": True,
        "data": result.get("data"),
        "message": "时效性校验成功",
    }


@router.post("/timeline/extract")
def extract_timeline(body: ExtractTimelineRequest, request: Request):
    result = invoke_chat_tool(
        request,
        "chat.extract_timeline",
        {
            "documents": [
                {
                    "title": item.title,
                    "content": item.content,
                    "source": item.source,
                    "source_name": item.sourceName,
                    "published_at": item.publishedAt,
                    "url": item.url,
                }
                for item in (body.documents or [])
            ],
        },
    )
    return {
        "success": True,
        "data": result.get("data"),
        "message": "时间线提取成功",
    }


class SearchOverviewRequest(BaseModel):
    session_id: str
    query: str
    user_prompt: str = ""
    source_url: str = ""
    platform_hint: str = ""
    max_results: int = 10


class SearchDiagnosticsRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    query: str
    source_url: str = Field("", alias="sourceUrl")
    platform_hint: str = Field("", alias="platformHint")
    max_results: int = Field(10, alias="maxResults")
    include_loaded_pages: bool = Field(False, alias="includeLoadedPages")


class TextToSpeechRequest(BaseModel):
    text: str
    session_id: str = ""
    voice_id: str = ""
    provider: str = ""


class AsyncTextToSpeechRequest(BaseModel):
    session_id: str
    message_id: str
    text: str
    voice_id: str = ""
    provider: str = ""


class AnalyzeRumorRequest(BaseModel):
    session_id: str
    query: str
    user_prompt: str = ""
    source_url: str = ""
    platform_hint: str = ""
    max_results: int = 8


@router.post("/debug/search-diagnostics")
def search_diagnostics(body: SearchDiagnosticsRequest, request: Request):
    backend_cookies = _require_backend_cookies(request)
    user_id = _resolve_backend_user_id(request)
    _ = backend_cookies
    payload = _build_search_diagnostics_payload(
        query=str(body.query or "").strip(),
        source_url=str(body.source_url or "").strip(),
        platform_hint=str(body.platform_hint or "").strip(),
        user_id=user_id,
        max_results=max(1, min(int(body.max_results or 10), 12)),
        include_loaded_pages=bool(body.include_loaded_pages),
    )
    return {
        "success": True,
        "data": payload,
        "message": "搜索诊断成功",
    }


@router.get("/debug/search-overview")
def debug_search_overview_get(request: Request, q: str = "清明上山扫墓却发现母亲的墓不见了"):
    user_id = _resolve_backend_user_id(request)
    payload = _build_search_diagnostics_payload(
        query=q,
        source_url="",
        platform_hint="",
        user_id=user_id,
        max_results=5,
        include_loaded_pages=False,
    )
    return {
        "success": True,
        "data": payload,
        "message": "调试接口-真实搜索返回成功（deprecated，请改用 /api/assistant/debug/search-diagnostics）",
        "deprecated": True,
    }


@router.post("/debug/search-overview")
async def debug_search_overview_post(request: Request):
    body = await request.json()
    query = body.get("query", "清明上山扫墓却发现母亲的墓不见了") if body else "清明上山扫墓却发现母亲的墓不见了"
    source_url = body.get("source_url", "") if body else ""
    platform_hint = body.get("platform_hint", "") if body else ""
    max_results = body.get("max_results", 5) if body else 5
    user_id = _resolve_backend_user_id(request)
    payload = _build_search_diagnostics_payload(
        query=str(query or "").strip(),
        source_url=str(source_url or "").strip(),
        platform_hint=str(platform_hint or "").strip(),
        user_id=user_id,
        max_results=max(1, min(int(max_results or 5), 12)),
        include_loaded_pages=False,
    )
    return {
        "success": True,
        "data": payload,
        "message": "调试接口-真实搜索返回成功（deprecated，请改用 /api/assistant/debug/search-diagnostics）",
        "deprecated": True,
    }


@router.post("/tools/search-overview")
def search_overview(body: SearchOverviewRequest, request: Request):
    import sys
    print(f"[REAL /tools/search-overview] called! query={body.query}", file=sys.stderr)
    sys.stderr.flush()
    result = invoke_chat_tool(
        request,
        "chat.search_overview",
        {
            "session_id": body.session_id,
            "query": body.query,
            "user_prompt": body.user_prompt,
            "source_url": body.source_url,
            "platform_hint": body.platform_hint,
            "max_results": body.max_results,
        },
    )
    return {
        "success": True,
        "data": result.get("data"),
        "message": "总览搜索成功",
    }


@router.post("/tools/analyze-rumor")
def analyze_rumor(body: AnalyzeRumorRequest, request: Request):
    result = invoke_chat_tool(
        request,
        "chat.analyze_rumor",
        {
            "session_id": body.session_id,
            "query": body.query,
            "user_prompt": body.user_prompt,
            "source_url": body.source_url,
            "platform_hint": body.platform_hint,
            "max_results": body.max_results,
        },
    )
    return {
        "success": True,
        "data": result.get("data"),
        "message": "谣言分析成功",
    }


@router.get("/sessions/{session_id}/panels")
def get_panels(session_id: str, request: Request):
    backend_session = get_backend_session(request)

    session_response, session_payload = client.request_json("GET", f"/api/v1/chat/sessions/{session_id}", session_cookie=backend_session)
    if session_response.status_code >= 400 or not session_payload.get("success"):
        raise HTTPException(status_code=session_response.status_code or 500, detail=session_payload.get("error") or "获取会话详情失败")

    messages_response, messages_payload = client.request_json("GET", f"/api/v1/chat/sessions/{session_id}/messages", session_cookie=backend_session)
    if messages_response.status_code >= 400 or not messages_payload.get("success"):
        raise HTTPException(status_code=messages_response.status_code or 500, detail=messages_payload.get("error") or "获取消息失败")

    session_data = session_payload.get("data", {})
    report_payload = None
    strategy_payload = None
    report_id = session_data.get("report_id")
    if report_id:
        report_response, report_payload = client.request_json("GET", f"/api/v1/reports/{report_id}", session_cookie=backend_session)
        if report_response.status_code >= 400:
            report_payload = None
    else:
        try:
            latest_report_result = invoke_report_tool(request, "report.get_latest_report_by_session", {"session_id": session_id})
            latest_report = latest_report_result.get("data", {}).get("report", {})
            if latest_report:
                report_payload = {
                    "success": True,
                    "data": {
                        "report_id": latest_report.get("report_id"),
                        "created_at": latest_report.get("created_at"),
                        **(latest_report.get("data") or {}),
                    },
                }
        except HTTPException:
            report_payload = None

    strategy_id = session_data.get("strategy_id")
    if strategy_id:
        strategy_response, strategy_payload = client.request_json("GET", f"/api/v1/chat/strategies/{strategy_id}", session_cookie=backend_session)
        if strategy_response.status_code >= 400:
            strategy_payload = None
    else:
        strategy_response, strategy_payload = client.request_json("GET", f"/api/v1/chat/sessions/{session_id}/latest-strategy", session_cookie=backend_session)
        if strategy_response.status_code >= 400:
            strategy_payload = None

    panels = build_panels_payload(
        session_id=session_id,
        session_title=str(session_data.get("title") or "未命名会话"),
        messages=messages_payload.get("data", []),
        report_payload=report_payload,
        strategy_payload=strategy_payload,
    )
    return {"success": True, "data": panels, "message": "获取 panels 成功"}


@router.post("/analyze")
def analyze(request: Request, body: AnalyzeRequest):
    try:
        payload = body.model_dump()
        mode = payload.get("mode")
        if mode == "domain":
            backend_session = get_backend_session(request)
            if not payload.get("domain"):
                raise HTTPException(status_code=400, detail="缺少 domain")
            response, payload = client.request_json(
                "POST",
                "/api/v1/chat/analyze-news",
                json_data={"domain": payload.get("domain")},
                session_cookie=backend_session,
                timeout=settings.chatbackend_analyze_timeout,
            )
        elif mode == "chat":
            if not payload.get("sessionId") or not payload.get("message"):
                raise HTTPException(status_code=400, detail="缺少 sessionId 或 message")
            result = invoke_chat_tool(
                request,
                "chat.send_message",
                {
                    "session_id": payload.get("sessionId"),
                    "message": payload.get("message"),
                    "kb_id": payload.get("kbId") or None,
                    "recommendation_context": payload.get("recommendationContext") or None,
                },
            )
            return {
                "success": True,
                "data": {
                    "response": result.get("data", {}).get("assistant_message", {}).get("content", ""),
                },
                "message": "分析请求成功",
            }
        else:
            raise HTTPException(status_code=400, detail="不支持的分析模式")

        if response.status_code >= 400 or payload.get("success") is False:
            raise HTTPException(status_code=response.status_code or 500, detail=payload.get("error") or payload.get("message") or "分析失败")

        return {"success": True, "data": payload.get("data"), "message": "分析请求成功"}
    except HTTPException:
        raise
    except RequestException as exc:
        logger.exception("Assistant analyze upstream request failed")
        raise HTTPException(status_code=502, detail=f"上游分析服务调用失败: {exc}") from exc
    except Exception as exc:
        logger.exception("Assistant analyze route failed")
        raise HTTPException(status_code=500, detail=f"分析请求异常: {exc}") from exc


@router.post("/stream")
def stream_assistant_message(request: Request, body: AnalyzeRequest):
    payload = body.model_dump()

    if payload.get("mode") != "chat":
        raise HTTPException(status_code=400, detail="流式输出当前仅支持 chat 模式")
    if not payload.get("sessionId") or not payload.get("message"):
        raise HTTPException(status_code=400, detail="缺少 sessionId 或 message")

    try:
        stream = invoke_chat_stream_tool(
            request,
            "chat.stream_message",
            {
                "session_id": payload.get("sessionId"),
                "message": payload.get("message"),
                "kb_id": payload.get("kbId") or None,
                "debug_mode": payload.get("debugMode") or False,
                "recommendation_context": payload.get("recommendationContext") or None,
            },
        )
    except HTTPException:
        raise
    except RequestException as exc:
        logger.exception("Assistant stream upstream request failed")
        raise HTTPException(status_code=502, detail=f"上游流式分析服务调用失败: {exc}") from exc

    def generate():
        try:
            for event in stream:
                event_type = str(event.get("event") or "message")
                data = event.get("data")
                if isinstance(data, dict):
                    payload = data
                elif data is None:
                    payload = {}
                else:
                    payload = {"chunk": str(data)}
                yield sse_event(event_type, payload)
        except Exception as exc:
            logger.exception("Assistant stream SSE iteration failed")
            yield sse_event("error", {"error": str(exc)})

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache, no-transform",
            "X-Accel-Buffering": "no",
            "Connection": "keep-alive",
        },
    )


# TTS 音频存储路径（需与 ChatBackend/app/services/tts_service.py 保持一致）
TTS_STORAGE_ROOT = settings.tts_storage_root


@router.get("/tts/audio/{path:path}")
def serve_tts_audio(path: str):
    """TTS 生成的音频文件访问"""
    file_path = os.path.join(TTS_STORAGE_ROOT, path)
    if not os.path.exists(file_path):
        raise HTTPException(status_code=404, detail="音频文件不存在")
    ext = os.path.splitext(file_path)[1].lower()
    media_type = "audio/mpeg"
    if ext == ".wav":
        media_type = "audio/wav"
    elif ext == ".mp3":
        media_type = "audio/mpeg"
    return FileResponse(
        file_path,
        media_type=media_type,
        headers={
            "Cache-Control": "public, max-age=3600",
            "Content-Disposition": "inline",
        },
    )


@router.post("/tts")
def generate_tts(body: TextToSpeechRequest, request: Request):
    """将文本转换为语音"""
    result = invoke_chat_tool(
        request,
        "chat.text_to_speech",
        {
            "text": body.text,
            "session_id": body.session_id or None,
            "voice_id": body.voice_id or None,
            "provider": body.provider or None,
        },
    )
    return {
        "success": True,
        "data": result.get("data"),
        "message": "TTS 生成成功",
    }


@router.post("/tts/async")
def generate_tts_async(body: AsyncTextToSpeechRequest, request: Request):
    """为指定 assistant 消息异步生成语音"""
    result = invoke_chat_tool(
        request,
        "chat.text_to_speech_async",
        {
            "session_id": body.session_id,
            "message_id": body.message_id,
            "text": body.text,
            "voice_id": body.voice_id or None,
            "provider": body.provider or None,
        },
    )
    return {
        "success": True,
        "data": result.get("data"),
        "message": "TTS 任务已创建",
    }
