from __future__ import annotations

from collections import Counter
from datetime import date, timedelta
from typing import Any

from fastapi import APIRouter, HTTPException, Request

from ..services.chatbackend_client import client


router = APIRouter(prefix="/api/dashboard", tags=["dashboard"])

EMOTION_KEYS = ("喜悦", "期待", "平和", "惊讶", "悲伤", "愤怒", "恐惧", "厌恶")
EMOTION_CALIBRATION_WEIGHTS = {
    "喜悦": 0.85,
    "期待": 0.95,
    "平和": 1.05,
    "惊讶": 0.72,
    "悲伤": 1.0,
    "愤怒": 1.0,
    "恐惧": 1.0,
    "厌恶": 1.0,
}
MINDSPIDER_EVENT_LIMIT = 8
MINDSPIDER_PLATFORM_COORDS = {
    "weibo": (116.4074, 39.9042),
    "zhihu": (121.4737, 31.2304),
    "douyin": (113.2644, 23.1291),
    "bilibili-hot-search": (120.1551, 30.2741),
    "toutiao": (116.4074, 39.9042),
    "tieba": (104.0665, 30.5728),
    "kuaishou": (126.6424, 45.7567),
    "github-trending-today": (-122.4194, 37.7749),
    "thepaper": (121.4737, 31.2304),
    "wallstreetcn": (121.4737, 31.2304),
    "cls-hot": (121.4737, 31.2304),
    "coolapk": (113.2644, 23.1291),
}
NEGATIVE_HINTS = (
    "塌房", "事故", "起火", "火灾", "爆炸", "身亡", "死亡", "受伤", "遇难", "坠毁", "相撞", "撞车",
    "举报", "争议", "冲突", "危机", "投诉", "质疑", "处罚", "调查", "通报", "造假", "违法",
    "危险", "警告", "紧急", "失联", "失踪", "欠薪", "烂尾", "停运", "停摆", "涉案", "被抓",
    "裁员", "风险", "中毒", "病亡", "制裁",
)
POSITIVE_HINTS = (
    "获奖", "突破", "成功", "救援", "暖心", "正能量", "上涨", "增长", "发布", "落地", "创新",
    "改善", "恢复", "回暖", "签约", "合作", "幸福", "加码", "投产", "开通", "启用", "竣工",
    "交付", "通车", "开业", "首发", "夺冠", "晋级", "刷新", "提升", "上线", "支持", "利好", "上调",
)


def _require_backend_cookies(request: Request):
    backend_cookies = request.session.get("chatbackend_cookies")
    if not backend_cookies:
        raise HTTPException(status_code=401, detail="未登录")
    return backend_cookies


def _normalize_emotion_schema(schema: dict[str, Any] | None) -> dict[str, float]:
    values = {
        key: max(float((schema or {}).get(key, 0) or 0), 0.0)
        for key in EMOTION_KEYS
    }
    total = sum(values.values())
    if total <= 0:
        return {
            "喜悦": 0.0,
            "期待": 0.0,
            "平和": 1.0,
            "惊讶": 0.0,
            "悲伤": 0.0,
            "愤怒": 0.0,
            "恐惧": 0.0,
            "厌恶": 0.0,
        }
    return {key: value / total for key, value in values.items()}


def _calibrate_emotion_schema(schema: dict[str, Any] | None) -> dict[str, float]:
    normalized = _normalize_emotion_schema(schema)
    adjusted = {
        key: normalized.get(key, 0.0) * EMOTION_CALIBRATION_WEIGHTS.get(key, 1.0)
        for key in EMOTION_KEYS
    }
    return _normalize_emotion_schema(adjusted)


def _derive_public_sentiment(schema: dict[str, Any] | None) -> tuple[str, dict[str, float], dict[str, float]]:
    calibrated = _calibrate_emotion_schema(schema)
    buckets = {
        "positive": (calibrated["喜悦"] + calibrated["期待"]) / 2,
        "neutral": (calibrated["平和"] + calibrated["惊讶"]) / 2,
        "negative": (calibrated["悲伤"] + calibrated["愤怒"] + calibrated["恐惧"] + calibrated["厌恶"]) / 4,
    }
    sentiment = max(buckets.items(), key=lambda item: item[1])[0]
    return sentiment, calibrated, buckets


def _infer_sentiment_from_title(title: str) -> tuple[str, dict[str, float]]:
    text = str(title or "").strip()
    negative_score = sum(1 for keyword in NEGATIVE_HINTS if keyword in text)
    positive_score = sum(1 for keyword in POSITIVE_HINTS if keyword in text)

    if negative_score >= positive_score + 0.5 and negative_score >= 1:
        return "negative", {"positive": 0.12, "neutral": 0.18, "negative": 0.7}
    if positive_score >= negative_score + 0.5 and positive_score >= 1:
        return "positive", {"positive": 0.68, "neutral": 0.2, "negative": 0.12}
    return "neutral", {"positive": 0.2, "neutral": 0.6, "negative": 0.2}


def _normalize_title_key(value: str) -> str:
    return "".join(str(value or "").strip().split())


def _load_mindspider_topic_analysis() -> dict:
    try:
        response, payload = client.request_json("GET", "/api/mindspider/topic-analysis", timeout=8)
        if response.status_code >= 400 or not payload.get("success"):
            return {}
        return payload.get("data") if isinstance(payload.get("data"), dict) else {}
    except Exception:
        return {}


def _build_mindspider_events(existing_events: list[dict[str, Any]], topic_data: dict[str, Any]) -> list[dict[str, Any]]:
    news_items = topic_data.get("news", []) if isinstance(topic_data, dict) else []
    if not isinstance(news_items, list) or not news_items:
        return []

    existing_title_keys = {_normalize_title_key(item.get("title") or "") for item in existing_events}
    topic_keywords = [str(item).strip() for item in topic_data.get("keywords", []) if str(item).strip()]
    topic_summary = str(topic_data.get("summary") or "").strip()
    extract_date = str(topic_data.get("extractDate") or date.today().isoformat())

    built_events: list[dict[str, Any]] = []
    for news in news_items:
        if not isinstance(news, dict):
            continue
        title = str(news.get("title") or "").strip()
        title_key = _normalize_title_key(title)
        if not title or title_key in existing_title_keys:
            continue

        source = str(news.get("source") or "").strip().lower()
        source_name = str(news.get("source_name") or news.get("source") or "MindSpider")
        rank = int(news.get("rank") or len(built_events) + 1)
        x, y = MINDSPIDER_PLATFORM_COORDS.get(source, (116.4074, 39.9042))
        sentiment, buckets = _infer_sentiment_from_title(title)
        introduction = topic_summary or f"{source_name} 热榜第 {rank} 位，建议结合原始链接继续核实细节与传播走向。"
        base_heat = max(30, 120 - rank * 3)
        trend_dates = [(date.today() - timedelta(days=offset)).isoformat() for offset in (2, 1, 0)]
        heat_trend = [
            {"date": trend_dates[0], "value": round(base_heat * 0.72, 1)},
            {"date": trend_dates[1], "value": round(base_heat * 0.86, 1)},
            {"date": trend_dates[2], "value": round(base_heat * 1.0, 1)},
        ]
        built_events.append(
            {
                "id": f"mindspider-{news.get('news_id') or title_key}",
                "title": title,
                "introduction": introduction,
                "type": "热点追踪",
                "x": x,
                "y": y,
                "platform": source_name,
                "rank": rank + 1000,
                "participants": max(1000, 30000 - rank * 600),
                "spreadSpeed": round(max(0.18, 0.9 - rank * 0.02), 3),
                "spreadRange": round(max(0.15, 0.78 - rank * 0.015), 3),
                "emotion": {
                    "schema": {
                        "喜悦": buckets["positive"] * 0.6,
                        "期待": buckets["positive"] * 0.4,
                        "平和": buckets["neutral"] * 0.75,
                        "惊讶": buckets["neutral"] * 0.25,
                        "悲伤": buckets["negative"] * 0.25,
                        "愤怒": buckets["negative"] * 0.35,
                        "恐惧": buckets["negative"] * 0.2,
                        "厌恶": buckets["negative"] * 0.2,
                    },
                    "rationale": "基于标题和来源平台进行快速研判。",
                },
                "stance": {
                    "schema": {"支持": 0.34, "中立": 0.42, "反对": 0.24},
                    "rationale": "MindSpider 一期结果暂未提供真实立场分布，当前为轻量估算值。",
                },
                "heatTrend": heat_trend,
                "timeline": [
                    {"date": extract_date, "event": f"{source_name} 热榜第 {rank} 位"},
                    {"date": extract_date, "event": "已纳入 MindSpider 一期聚合结果"},
                ],
                "wordCloud": [
                    {"word": word, "weight": max(20, 120 - index * 8)}
                    for index, word in enumerate(topic_keywords[:10])
                ],
                "primarySentiment": sentiment,
            }
        )
        existing_title_keys.add(title_key)
        if len(built_events) >= MINDSPIDER_EVENT_LIMIT:
            break

    return built_events


@router.get("/command-center")
def get_command_center(request: Request):
    backend_cookies = _require_backend_cookies(request)
    response, payload = client.request_json("GET", "/api/currentnews", session_cookie=backend_cookies, timeout=45)
    if response.status_code >= 400:
        raise HTTPException(status_code=response.status_code or 500, detail=payload.get("error") or "获取指挥中枢数据失败")

    raw_items = payload.get("data", []) if isinstance(payload.get("data"), list) else []
    events: list[dict[str, Any]] = []
    platform_counter: Counter[str] = Counter()
    sentiment_counter: Counter[str] = Counter()
    sentiment_totals = {
        "positive": 0.0,
        "neutral": 0.0,
        "negative": 0.0,
    }

    for index, item in enumerate(raw_items):
        if not isinstance(item, dict):
            continue

        platform = str(item.get("platform") or "未知")
        emotion = item.get("emotion") if isinstance(item.get("emotion"), dict) else {}
        stance = item.get("stance") if isinstance(item.get("stance"), dict) else {}
        sentiment, calibrated_emotion_schema, sentiment_buckets = _derive_public_sentiment(
            emotion.get("schema") if isinstance(emotion, dict) else {}
        )
        emotion_for_display = {
            **emotion,
            "schema": calibrated_emotion_schema,
        } if isinstance(emotion, dict) else {"schema": calibrated_emotion_schema}

        event = {
            "id": str(item.get("id") or f"event-{index + 1}"),
            "title": str(item.get("title") or "未命名事件"),
            "introduction": str(item.get("introduction") or ""),
            "type": str(item.get("type") or "未分类"),
            "x": float(item.get("x") or 116.4074),
            "y": float(item.get("y") or 39.9042),
            "platform": platform,
            "rank": int(item.get("rank") or index + 1),
            "participants": float(item.get("participants") or 0),
            "spreadSpeed": float(item.get("spreadSpeed") or 0),
            "spreadRange": float(item.get("spreadRange") or 0),
            "emotion": emotion_for_display,
            "stance": stance,
            "heatTrend": item.get("heatTrend") if isinstance(item.get("heatTrend"), list) else [],
            "timeline": item.get("timeline") if isinstance(item.get("timeline"), list) else [],
            "wordCloud": item.get("wordCloud") if isinstance(item.get("wordCloud"), list) else [],
            "primarySentiment": sentiment,
        }
        events.append(event)
        platform_counter[platform] += 1
        sentiment_counter[sentiment] += 1
        for key, value in sentiment_buckets.items():
            sentiment_totals[key] += float(value or 0)

    for event in _build_mindspider_events(events, _load_mindspider_topic_analysis()):
        events.append(event)
        platform_counter[event["platform"]] += 1
        sentiment_counter[event["primarySentiment"]] += 1
        event_schema = event.get("emotion", {}).get("schema") if isinstance(event.get("emotion"), dict) else {}
        _, _, sentiment_buckets = _derive_public_sentiment(event_schema if isinstance(event_schema, dict) else {})
        for key, value in sentiment_buckets.items():
            sentiment_totals[key] += float(value or 0)

    events.sort(key=lambda item: item.get("rank", 9999))

    total_events = len(events)
    avg_spread_range = round(
        sum(float(item.get("spreadRange") or 0) for item in events) / total_events,
        3,
    ) if total_events else 0
    avg_spread_speed = round(
        sum(float(item.get("spreadSpeed") or 0) for item in events) / total_events,
        3,
    ) if total_events else 0
    sentiment_total_value = sum(sentiment_totals.values()) or 1.0

    summary = {
        "totalEvents": total_events,
        "negativeEvents": sentiment_counter.get("negative", 0),
        "positiveEvents": sentiment_counter.get("positive", 0),
        "neutralEvents": sentiment_counter.get("neutral", 0),
        "avgSpreadRange": avg_spread_range,
        "avgSpreadSpeed": avg_spread_speed,
        "platformDistribution": [{"name": key, "value": value} for key, value in platform_counter.most_common()],
        "sentimentDistribution": [
            {"name": "正向", "value": round(sentiment_totals["positive"] / sentiment_total_value * 100, 1)},
            {"name": "中性", "value": round(sentiment_totals["neutral"] / sentiment_total_value * 100, 1)},
            {"name": "负向", "value": round(sentiment_totals["negative"] / sentiment_total_value * 100, 1)},
        ],
    }

    return {
        "success": True,
        "data": {
            "summary": summary,
            "events": events,
        },
        "message": "获取指挥中枢数据成功",
    }
