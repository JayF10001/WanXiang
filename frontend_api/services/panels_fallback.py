from __future__ import annotations

from typing import Any, Dict, List, Optional


DEFAULT_SOURCE_DISTRIBUTION = [
    {"name": "负面", "value": 25.53, "fill": "#ef4444"},
    {"name": "中性", "value": 73.72, "fill": "#eab308"},
    {"name": "正面", "value": 0.75, "fill": "#22c55e"},
]


def _safe_message_content(messages: List[Dict[str, Any]], role: str) -> str:
    for item in messages:
        if item.get("role") == role and item.get("content"):
            return str(item.get("content"))
    return ""


def _build_brief_from_report(raw_report_data: Dict[str, Any], session_title: str, overview: str) -> Dict[str, Any]:
    executive = raw_report_data.get("executiveSummary", {}) if isinstance(raw_report_data.get("executiveSummary"), dict) else {}
    propagation = raw_report_data.get("detailedAnalysis", {}).get("propagationAnalysis", {}) if isinstance(raw_report_data.get("detailedAnalysis"), dict) else {}
    key_findings = executive.get("keyFindings", []) if isinstance(executive.get("keyFindings"), list) else []
    top_trends = executive.get("topTrends", []) if isinstance(executive.get("topTrends"), list) else []
    peak_events = propagation.get("peakEvents", []) if isinstance(propagation.get("peakEvents"), list) else []

    highlights = [
        *[str(item) for item in key_findings[:3]],
        *[f"趋势：{item.get('name', '未命名趋势')}（热度 {item.get('value', '未知')}）" for item in top_trends[:2] if isinstance(item, dict)],
        *[f"峰值事件：{item.get('title') or item.get('description') or '未命名事件'}" for item in peak_events[:2] if isinstance(item, dict)],
    ]

    return {
        "summary": str(key_findings[0] if key_findings else overview or f"{session_title} 报告已生成。"),
        "highlights": highlights[:5] if highlights else [f"当前会话：{session_title}"],
    }


def _build_data_preview_from_report(raw_report_data: Dict[str, Any], session_id: str) -> List[Dict[str, Any]]:
    analysis_details = raw_report_data.get("analysisDetails", {}) if isinstance(raw_report_data.get("analysisDetails"), dict) else {}
    raw_data_summary = raw_report_data.get("rawDataSummary", {}) if isinstance(raw_report_data.get("rawDataSummary"), dict) else {}
    detailed = raw_report_data.get("detailedAnalysis", {}) if isinstance(raw_report_data.get("detailedAnalysis"), dict) else {}

    data_sources = analysis_details.get("dataSources")
    if not isinstance(data_sources, list):
        data_sources = []

    sample_data = raw_data_summary.get("sampleData")
    if not isinstance(sample_data, list):
        sample_data = []

    topic_analysis = detailed.get("topicAnalysis", {}) if isinstance(detailed.get("topicAnalysis"), dict) else {}
    topics = topic_analysis.get("mainTopics")
    if not isinstance(topics, list):
        topics = []

    preview: List[Dict[str, Any]] = []

    for index, item in enumerate(data_sources[:2], start=1):
        if not isinstance(item, dict):
            continue
        preview.append({
            "id": f"{session_id}-report-source-{index}",
            "sourceType": "social" if "社交" in str(item.get("type", "")) else "news",
            "title": str(item.get("name") or f"数据源 {index}"),
            "summary": f"类型：{item.get('type', '未标注')}；可信度：{item.get('reliability', '未知')}；覆盖度：{item.get('coverage', '未知')}",
            "publishedAt": "",
            "sourceLabel": "报告数据源",
        })

    for index, item in enumerate(sample_data[:2], start=1):
        if not isinstance(item, dict):
            continue
        preview.append({
            "id": f"{session_id}-report-sample-{index}",
            "sourceType": "social" if "社交" in str(item.get("source", "")) else "news",
            "title": str(item.get("source") or f"样本 {index}"),
            "summary": str(item.get("content") or ""),
            "publishedAt": str(item.get("timestamp") or ""),
            "sourceLabel": f"情绪：{item.get('sentiment', '未知')}",
        })

    for index, item in enumerate(topics[:1], start=1):
        if not isinstance(item, dict):
            continue
        preview.append({
            "id": f"{session_id}-report-topic-{index}",
            "sourceType": "social",
            "title": f"核心话题：{item.get('topic') or '未命名话题'}",
            "summary": f"关联关键词：{'、'.join(item.get('relatedKeywords', [])[:6]) if isinstance(item.get('relatedKeywords'), list) else '暂无'}；声量：{item.get('sourceCount', '未知')}",
            "publishedAt": "",
            "sourceLabel": f"权重：{item.get('weight', '未知')}",
        })

    return preview


def build_panels_payload(
    session_id: str,
    session_title: str,
    messages: List[Dict[str, Any]],
    report_payload: Optional[Dict[str, Any]],
    strategy_payload: Optional[Dict[str, Any]],
) -> Dict[str, Any]:
    assistant_summary = _safe_message_content(messages, "assistant")
    user_message = _safe_message_content(messages, "user")
    has_real_report = bool(report_payload and report_payload.get("success") and isinstance(report_payload.get("data"), dict))
    raw_report_data = report_payload.get("data", {}) if has_real_report else {}
    report_meta = raw_report_data.get("meta", {}) if isinstance(raw_report_data.get("meta"), dict) else {}

    overview = (
        raw_report_data.get("overview")
        or raw_report_data.get("summary")
        or assistant_summary
        or f"{session_title} 的报告正在整理中。"
    )

    report = None
    if has_real_report:
        report = {
            "id": str(
                raw_report_data.get("report_id")
                or raw_report_data.get("reportId")
                or raw_report_data.get("id")
                or session_id
            ),
            "title": str(report_meta.get("title") or raw_report_data.get("title") or session_title),
            "createdAt": str(raw_report_data.get("created_at") or raw_report_data.get("createdAt") or ""),
            "isFallback": bool(raw_report_data.get("is_fallback") or report_payload.get("is_fallback") or False),
            "content": raw_report_data,
        }

    strategy = None
    has_real_strategy = bool(strategy_payload and strategy_payload.get("success") and isinstance(strategy_payload.get("data"), dict))
    raw_strategy_data = strategy_payload.get("data", {}) if has_real_strategy else {}
    strategy_meta = raw_strategy_data.get("meta", {}) if isinstance(raw_strategy_data.get("meta"), dict) else {}
    if has_real_strategy:
        strategy = {
            "id": str(
                raw_strategy_data.get("strategy_id")
                or raw_strategy_data.get("strategyId")
                or strategy_payload.get("strategy_id")
                or session_id
            ),
            "title": str(strategy_meta.get("title") or raw_strategy_data.get("title") or f"{session_title}传播策略"),
            "createdAt": str(raw_strategy_data.get("created_at") or raw_strategy_data.get("createdAt") or strategy_payload.get("created_at") or ""),
            "content": raw_strategy_data,
        }

    if has_real_report:
        brief = _build_brief_from_report(raw_report_data, session_title, overview)
        data_preview = _build_data_preview_from_report(raw_report_data, session_id)
    else:
        brief = {
            "summary": overview,
            "highlights": [
                f"当前会话：{session_title}",
                f"用户输入：{user_message or '暂无明确用户输入'}",
                "该简报由 FastAPI 适配层生成，用于补齐当前报告侧栏结构。",
            ],
        }

        data_preview = []
        if user_message:
            data_preview.append(
                {
                    "id": f"{session_id}-preview-1",
                    "sourceType": "news",
                    "title": session_title,
                    "summary": user_message,
                    "publishedAt": "",
                    "sourceLabel": "FastAPI fallback",
                }
            )
        if assistant_summary:
            data_preview.append(
                {
                    "id": f"{session_id}-preview-2",
                    "sourceType": "social",
                    "title": f"{session_title} - AI 摘要",
                    "summary": assistant_summary[:180],
                    "publishedAt": "",
                    "sourceLabel": "FastAPI fallback",
                }
            )

    return {
        "dataPreview": data_preview,
        "brief": brief,
        "report": report,
        "strategy": strategy,
    }
