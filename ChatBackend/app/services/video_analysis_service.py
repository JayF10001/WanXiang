"""Multimodal analysis service using Google Gemini for media analysis."""

from __future__ import annotations

import json
import logging
import os
import time
from pathlib import Path
from typing import Any, Dict, Iterable, List, Tuple

from google import genai as google_genai

try:
    from ChatBackend.celery_app import celery
except ImportError:
    from celery_app import celery

LOGGER = logging.getLogger(__name__)

MEDIA_FILE_READY_TIMEOUT_SECONDS = 20

MODALITY_EXTENSIONS = {
    "image": {".jpg", ".jpeg", ".png", ".webp"},
    "audio": {".mp3", ".wav", ".m4a", ".aac"},
    "video": {".mp4", ".mov", ".avi"},
}

MULTIMODAL_PROMPTS = {
    "image": """你是一个专业的舆情分析师。请分析该图片并输出 JSON：
{
  "sentiment": "极性(正面/负面/中性)",
  "summary": "核心内容摘要(100字以内)",
  "keywords": ["关键词1", "关键词2", "关键词3"],
  "risk_level": "风险等级(高/中/低)",
  "notable_visuals": "图片中的关键视觉元素(品牌、人物、敏感画面等)",
  "scene_description": "场景描述(场所、人物、活动等)",
  "ocr_text": "图片中可识别的重要文字，没有则填无"
}
只输出JSON，不要其他文字。""",
    "audio": """你是一个专业的舆情分析师。请分析该音频并输出 JSON：
{
  "sentiment": "极性(正面/负面/中性)",
  "summary": "核心内容摘要(100字以内)",
  "keywords": ["关键词1", "关键词2", "关键词3"],
  "risk_level": "风险等级(高/中/低)",
  "audio_summary": "音频/语音内容摘要",
  "transcript": "可识别的关键语音或歌词，没有则填无",
  "speaker_tone": "说话者或整体音频语气，如平静/激动/愤怒",
  "notable_audio_events": "重要声音事件，如掌声、爆炸声、警报声，没有则填无"
}
只输出JSON，不要其他文字。""",
    "video": """你是一个专业的舆情分析师。请观看该视频并输出 JSON：
{
  "sentiment": "极性(正面/负面/中性)",
  "summary": "核心内容摘要(100字以内)",
  "keywords": ["关键词1", "关键词2", "关键词3"],
  "risk_level": "风险等级(高/中/低)",
  "notable_visuals": "视频中出现的关键视觉元素(如品牌Logo、敏感画面)",
  "audio_summary": "音频/语音内容摘要",
  "scene_description": "场景描述(场所、人物、活动等)"
}
只输出JSON，不要其他文字。""",
}


def _friendly_failure_message(reason: str | None) -> str:
    from ChatBackend.app.services.multimodal_router_service import build_degrade_message

    return build_degrade_message(reason)


def _build_processing_update(
    *,
    phase: str,
    model_attempts: list[dict[str, Any]] | None = None,
    fallback_level: int = 0,
    final_model: str | None = None,
    degrade_reason: str | None = None,
    degrade_message: str | None = None,
    file_count: int = 0,
    processed_count: int = 0,
    failed_count: int = 0,
    current_file_name: str | None = None,
    current_modality: str | None = None,
) -> dict:
    return {
        "status": "processing",
        "provider": "gemini",
        "phase": phase,
        "fallback_level": fallback_level,
        "final_model": final_model,
        "degrade_reason": degrade_reason,
        "degrade_message": degrade_message,
        "model_attempts": model_attempts or [],
        "file_count": int(file_count or 0),
        "processed_count": int(processed_count or 0),
        "failed_count": int(failed_count or 0),
        "current_file_name": current_file_name,
        "current_modality": current_modality,
    }


def _coerce_keywords(value: Any) -> list[str]:
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    if isinstance(value, str):
        normalized = value.replace("，", ",").replace("、", ",")
        return [item.strip() for item in normalized.split(",") if item.strip()]
    return []


def _detect_modality(path: str | Path) -> str:
    suffix = Path(path).suffix.lower()
    for modality, suffixes in MODALITY_EXTENSIONS.items():
        if suffix in suffixes:
            return modality
    raise ValueError(f"不支持的媒体文件格式：{suffix or 'unknown'}")


def _default_result_for_modality(modality: str, normalized: str) -> Dict[str, Any]:
    base = {
        "sentiment": "未知",
        "summary": normalized[:200] if normalized else "解析失败",
        "keywords": [],
        "risk_level": "未知",
    }
    if modality == "image":
        base.update({
            "notable_visuals": "无",
            "scene_description": "无",
            "ocr_text": "无",
        })
    elif modality == "audio":
        base.update({
            "audio_summary": "无",
            "transcript": "无",
            "speaker_tone": "未知",
            "notable_audio_events": "无",
        })
    else:
        base.update({
            "notable_visuals": "无",
            "audio_summary": "无",
            "scene_description": "无",
        })
    return base


def _parse_analysis_result(raw_text: str, modality: str) -> Tuple[Dict[str, Any], bool]:
    normalized = str(raw_text or "").strip()
    json_start = normalized.find("{")
    json_end = normalized.rfind("}") + 1
    if json_start != -1 and json_end > json_start:
        try:
            parsed = json.loads(normalized[json_start:json_end])
            result = {
                "sentiment": str(parsed.get("sentiment") or "未知"),
                "summary": str(parsed.get("summary") or normalized[:200] or "解析失败"),
                "keywords": _coerce_keywords(parsed.get("keywords")),
                "risk_level": str(parsed.get("risk_level") or "未知"),
            }
            if modality == "image":
                result.update({
                    "notable_visuals": str(parsed.get("notable_visuals") or "无"),
                    "scene_description": str(parsed.get("scene_description") or "无"),
                    "ocr_text": str(parsed.get("ocr_text") or "无"),
                })
            elif modality == "audio":
                result.update({
                    "audio_summary": str(parsed.get("audio_summary") or "无"),
                    "transcript": str(parsed.get("transcript") or "无"),
                    "speaker_tone": str(parsed.get("speaker_tone") or "未知"),
                    "notable_audio_events": str(parsed.get("notable_audio_events") or "无"),
                })
            else:
                result.update({
                    "notable_visuals": str(parsed.get("notable_visuals") or "无"),
                    "audio_summary": str(parsed.get("audio_summary") or "无"),
                    "scene_description": str(parsed.get("scene_description") or "无"),
                })
            return result, False
        except Exception:
            pass

    return _default_result_for_modality(modality, normalized), True


def _build_file_item_result(
    *,
    file_name: str,
    modality: str,
    result: Dict[str, Any],
    fallback_level: int,
    final_model: str | None,
    degrade_reason: str | None,
    degrade_message: str | None,
    model_attempts: List[Dict[str, Any]],
    status: str = "success",
    error: str | None = None,
) -> Dict[str, Any]:
    payload = {
        "file_name": file_name,
        "modality": modality,
        "status": status,
        "summary": result.get("summary") or "",
        "sentiment": result.get("sentiment") or "未知",
        "risk_level": result.get("risk_level") or "未知",
        "keywords": list(result.get("keywords") or []),
        "fallback_level": int(fallback_level or 0),
        "final_model": final_model,
        "degrade_reason": degrade_reason,
        "degrade_message": degrade_message,
        "model_attempts": model_attempts,
    }
    payload.update(result)
    if error:
        payload["error"] = error
    return payload


def _build_overall_summary(items: List[Dict[str, Any]]) -> Tuple[str, str, List[str], List[str]]:
    successful_items = [item for item in items if str(item.get("status") or "") == "success"]
    if not successful_items:
        return "", "未知", [], []

    summaries: List[str] = []
    all_keywords: List[str] = []
    risk_rank = {"高": 3, "中": 2, "低": 1}
    overall_risk_level = "低"
    seen_keywords: set[str] = set()
    cross_file_signals: List[str] = []

    for item in successful_items:
        file_name = str(item.get("file_name") or "未知文件")
        modality = str(item.get("modality") or "media")
        summary = str(item.get("summary") or "").strip()
        if summary:
            summaries.append(f"{file_name}（{modality}）：{summary}")
        for keyword in item.get("keywords") or []:
            normalized = str(keyword).strip()
            if normalized and normalized not in seen_keywords:
                seen_keywords.add(normalized)
                all_keywords.append(normalized)
        item_risk = str(item.get("risk_level") or "低")
        if risk_rank.get(item_risk, 0) > risk_rank.get(overall_risk_level, 0):
            overall_risk_level = item_risk

    modalities = sorted({str(item.get("modality") or "") for item in successful_items if item.get("modality")})
    if modalities:
        cross_file_signals.append(f"本轮素材涵盖：{'、'.join(modalities)}")
    if len(successful_items) > 1:
        cross_file_signals.append("已对多文件结果做交叉比对，优先参考重复出现的主题、情绪和风险点。")

    overall_summary = "；".join(summaries[:5])
    return overall_summary, overall_risk_level, all_keywords[:10], cross_file_signals


def _build_hidden_multimodal_message_fields(
    *,
    items: List[Dict[str, Any]] | None = None,
    overall_summary: str = "",
    overall_risk_level: str = "",
    common_topics: List[str] | None = None,
    cross_file_signals: List[str] | None = None,
    fallback_level: int = 0,
    final_model: str | None = None,
    degrade_reason: str | None = None,
    degrade_message: str | None = None,
    model_attempts: list[dict[str, Any]] | None = None,
) -> dict:
    normalized_items = [dict(item) for item in (items or [])]
    modalities = sorted({str(item.get("modality") or "") for item in normalized_items if item.get("modality")})
    return {
        "route": "multimodal_analysis",
        "render_mode": "hidden",
        "batch": True,
        "modality": modalities[0] if len(modalities) == 1 else "mixed",
        "modalities": modalities,
        "items": normalized_items,
        "overall_summary": overall_summary,
        "overall_risk_level": overall_risk_level,
        "common_topics": list(common_topics or []),
        "cross_file_signals": list(cross_file_signals or []),
        "grounding_status": "ungrounded",
        "confidence": "medium",
        "used_realtime_retrieval": False,
        "sources": [],
        "citations": [],
        "facts": [],
        "to_verify": [],
        "analysis": [overall_summary] if overall_summary else [],
        "fallback_level": int(fallback_level),
        "final_model": final_model,
        "degrade_reason": degrade_reason,
        "degrade_message": degrade_message,
        "model_attempts": model_attempts or [],
    }


def _build_hidden_content(items: List[Dict[str, Any]], overall_summary: str, overall_risk_level: str) -> str:
    lines = ["【多模态分析结果】"]
    if overall_summary:
        lines.extend(["", f"**综合摘要**: {overall_summary}"])
    if overall_risk_level:
        lines.append(f"**综合风险等级**: {overall_risk_level}")
    for item in items[:10]:
        lines.extend([
            "",
            f"- {item.get('file_name', '未知文件')}（{item.get('modality', 'media')}）",
            f"  摘要: {item.get('summary', '')}",
            f"  风险: {item.get('risk_level', '未知')}",
        ])
    return "\n".join(lines)


def _upload_media_file(client: Any, session_id: str, file_path: Path, modality: str):
    return client.files.upload(
        file=str(file_path),
        config={"display_name": f"wanxiang_{modality}_{session_id}_{file_path.stem}"},
    )


def _wait_until_file_active(
    *,
    client: Any,
    uploaded_file: Any,
    timeout_seconds: int = MEDIA_FILE_READY_TIMEOUT_SECONDS,
):
    started_at = time.monotonic()
    current = uploaded_file
    while current.state.name == "PROCESSING":
        if time.monotonic() - started_at > timeout_seconds:
            raise RuntimeError("媒体文件处理失败，状态：PROCESSING_TIMEOUT")
        time.sleep(2)
        current = client.files.get(name=current.name)
    return current


def _analyze_single_media_file(
    *,
    client: Any,
    session_id: str,
    file_path: str,
    query: str | None,
    progress_callback,
) -> Dict[str, Any]:
    from ChatBackend.app.services.multimodal_router_service import run_gemini_multimodal_with_fallback

    file_obj = Path(file_path)
    if not file_obj.exists():
        raise RuntimeError(f"媒体文件不存在：{file_path}")

    modality = _detect_modality(file_obj)
    uploaded_file = _upload_media_file(client, session_id, file_obj, modality)
    progress_callback(phase="preparing_file", modality=modality, file_name=file_obj.name)
    uploaded_file = _wait_until_file_active(client=client, uploaded_file=uploaded_file)

    if uploaded_file.state.name != "ACTIVE":
        raise RuntimeError(f"媒体文件处理失败，状态：{uploaded_file.state.name}")

    user_prompt = f"用户要求：{query}\n\n" if query else ""
    analysis_prompt = f"{user_prompt}{MULTIMODAL_PROMPTS[modality]}"

    routing_result = run_gemini_multimodal_with_fallback(
        client=client,
        uploaded_file=uploaded_file,
        prompt=analysis_prompt,
        modality=modality,
        progress_callback=lambda meta: progress_callback(
            phase=str(meta.get("phase") or "llm"),
            modality=modality,
            file_name=file_obj.name,
            fallback_level=int(meta.get("fallback_level") or 0),
            final_model=meta.get("final_model"),
            degrade_reason=meta.get("degrade_reason"),
            degrade_message=meta.get("degrade_message"),
            model_attempts=meta.get("model_attempts") or [],
        ),
    )

    if routing_result.get("status") != "success":
        return _build_file_item_result(
            file_name=file_obj.name,
            modality=modality,
            result=_default_result_for_modality(modality, ""),
            fallback_level=int(routing_result.get("fallback_level") or 0),
            final_model=routing_result.get("final_model"),
            degrade_reason=routing_result.get("degrade_reason"),
            degrade_message=routing_result.get("degrade_message") or routing_result.get("user_message"),
            model_attempts=routing_result.get("model_attempts") or [],
            status="failed",
            error=str(routing_result.get("error") or routing_result.get("user_message") or ""),
        )

    raw_text = str(routing_result.get("raw_text") or "")
    result, parsed_with_text_fallback = _parse_analysis_result(raw_text, modality)
    degrade_reason = routing_result.get("degrade_reason")
    if parsed_with_text_fallback and not degrade_reason:
        degrade_reason = "invalid_response"

    return _build_file_item_result(
        file_name=file_obj.name,
        modality=modality,
        result=result,
        fallback_level=int(routing_result.get("fallback_level") or 0),
        final_model=routing_result.get("final_model"),
        degrade_reason=degrade_reason,
        degrade_message=routing_result.get("degrade_message"),
        model_attempts=routing_result.get("model_attempts") or [],
    )


def _update_batch_progress(
    task,
    *,
    phase: str,
    file_count: int,
    processed_count: int,
    failed_count: int,
    current_file_name: str | None = None,
    current_modality: str | None = None,
    fallback_level: int = 0,
    final_model: str | None = None,
    degrade_reason: str | None = None,
    degrade_message: str | None = None,
    model_attempts: list[dict[str, Any]] | None = None,
):
    task.update_state(
        state="PROGRESS",
        meta=_build_processing_update(
            phase=phase,
            model_attempts=model_attempts,
            fallback_level=fallback_level,
            final_model=final_model,
            degrade_reason=degrade_reason,
            degrade_message=degrade_message,
            file_count=file_count,
            processed_count=processed_count,
            failed_count=failed_count,
            current_file_name=current_file_name,
            current_modality=current_modality,
        ),
    )


@celery.task(name="chat.analyze_multimodal_batch", bind=True, max_retries=2, default_retry_delay=60)
def analyze_multimodal_batch(self, session_id: str, file_paths: Iterable[str], query: str | None) -> dict:
    from ChatBackend.app import create_app
    from ChatBackend.app.services.chat_service import ChatService
    from ChatBackend.app.services.multimodal_router_service import classify_multimodal_error

    app = create_app()
    with app.app_context():
        normalized_paths = [str(path) for path in (file_paths or []) if str(path or "").strip()]
        if not normalized_paths:
            error_msg = "未提供可分析的媒体文件"
            user_message = _friendly_failure_message("file_processing_failed")
            ChatService.add_message(
                session_id,
                "assistant",
                user_message,
                extra_fields=_build_hidden_multimodal_message_fields(
                    degrade_reason="file_processing_failed",
                    degrade_message=user_message,
                ),
            )
            return {
                "status": "error",
                "provider": "gemini",
                "error": error_msg,
                "user_message": user_message,
                "file_count": 0,
                "processed_count": 0,
                "failed_count": 0,
                "items": [],
            }

        api_key = os.environ.get("GOOGLE_API_KEY")
        if not api_key:
            error_msg = "未配置 GOOGLE_API_KEY 环境变量"
            user_message = _friendly_failure_message("config_error")
            ChatService.add_message(
                session_id,
                "assistant",
                user_message,
                extra_fields=_build_hidden_multimodal_message_fields(
                    degrade_reason="config_error",
                    degrade_message=user_message,
                ),
            )
            return {
                "status": "error",
                "provider": "gemini",
                "error": error_msg,
                "user_message": user_message,
                "file_count": len(normalized_paths),
                "processed_count": 0,
                "failed_count": 0,
                "items": [],
            }

        client = google_genai.Client(api_key=api_key)
        file_count = len(normalized_paths)
        processed_count = 0
        failed_count = 0
        items: List[Dict[str, Any]] = []

        _update_batch_progress(
            self,
            phase="uploading",
            file_count=file_count,
            processed_count=processed_count,
            failed_count=failed_count,
        )

        for file_path in normalized_paths:
            file_name = Path(file_path).name
            try:
                item_result = _analyze_single_media_file(
                    client=client,
                    session_id=session_id,
                    file_path=file_path,
                    query=query,
                    progress_callback=lambda **progress: _update_batch_progress(
                        self,
                        phase=progress.get("phase", "llm"),
                        file_count=file_count,
                        processed_count=processed_count,
                        failed_count=failed_count,
                        current_file_name=progress.get("file_name"),
                        current_modality=progress.get("modality"),
                        fallback_level=int(progress.get("fallback_level") or 0),
                        final_model=progress.get("final_model"),
                        degrade_reason=progress.get("degrade_reason"),
                        degrade_message=progress.get("degrade_message"),
                        model_attempts=progress.get("model_attempts") or [],
                    ),
                )
            except Exception as exc:
                classified = classify_multimodal_error(exc)
                modality = "unknown"
                try:
                    modality = _detect_modality(file_path)
                except Exception:
                    pass
                item_result = _build_file_item_result(
                    file_name=file_name,
                    modality=modality,
                    result=_default_result_for_modality(modality if modality in MULTIMODAL_PROMPTS else "video", ""),
                    fallback_level=0,
                    final_model=None,
                    degrade_reason=classified["degrade_reason"],
                    degrade_message=classified["user_message"],
                    model_attempts=[],
                    status="failed",
                    error=classified["raw_error"],
                )

            items.append(item_result)
            processed_count += 1
            if str(item_result.get("status") or "") != "success":
                failed_count += 1

            _update_batch_progress(
                self,
                phase="processing",
                file_count=file_count,
                processed_count=processed_count,
                failed_count=failed_count,
                current_file_name=file_name,
                current_modality=str(item_result.get("modality") or ""),
                fallback_level=int(item_result.get("fallback_level") or 0),
                final_model=item_result.get("final_model"),
                degrade_reason=item_result.get("degrade_reason"),
                degrade_message=item_result.get("degrade_message"),
                model_attempts=item_result.get("model_attempts") or [],
            )

        overall_summary, overall_risk_level, common_topics, cross_file_signals = _build_overall_summary(items)
        successful_items = [item for item in items if str(item.get("status") or "") == "success"]
        failed_items = [item for item in items if str(item.get("status") or "") != "success"]
        dominant_item = successful_items[-1] if successful_items else (items[-1] if items else {})
        final_model = dominant_item.get("final_model")
        fallback_level = max(int(item.get("fallback_level") or 0) for item in items) if items else 0
        degrade_reason = failed_items[0].get("degrade_reason") if failed_items and not successful_items else None
        degrade_message = None
        if failed_items and successful_items:
            degrade_message = "部分文件分析失败，其余结果已完成汇总"
        elif failed_items and not successful_items:
            degrade_message = str(failed_items[0].get("degrade_message") or _friendly_failure_message(failed_items[0].get("degrade_reason")))

        hidden_fields = _build_hidden_multimodal_message_fields(
            items=items,
            overall_summary=overall_summary,
            overall_risk_level=overall_risk_level,
            common_topics=common_topics,
            cross_file_signals=cross_file_signals,
            fallback_level=fallback_level,
            final_model=final_model,
            degrade_reason=degrade_reason,
            degrade_message=degrade_message,
            model_attempts=dominant_item.get("model_attempts") or [],
        )
        hidden_content = _build_hidden_content(items, overall_summary, overall_risk_level)

        ChatService.add_message(session_id, "assistant", hidden_content, extra_fields=hidden_fields)

        if successful_items:
            return {
                "status": "success",
                "provider": "gemini",
                "session_id": session_id,
                "file_count": file_count,
                "processed_count": processed_count,
                "failed_count": failed_count,
                "items": items,
                "overall_summary": overall_summary,
                "overall_risk_level": overall_risk_level,
                "common_topics": common_topics,
                "cross_file_signals": cross_file_signals,
                "fallback_level": fallback_level,
                "final_model": final_model,
                "degrade_reason": degrade_reason,
                "degrade_message": degrade_message,
                "model_attempts": dominant_item.get("model_attempts") or [],
                "user_message": None,
            }

        user_message = degrade_message or _friendly_failure_message("unknown_error")
        return {
            "status": "error",
            "provider": "gemini",
            "session_id": session_id,
            "file_count": file_count,
            "processed_count": processed_count,
            "failed_count": failed_count,
            "items": items,
            "overall_summary": overall_summary,
            "overall_risk_level": overall_risk_level,
            "common_topics": common_topics,
            "cross_file_signals": cross_file_signals,
            "fallback_level": fallback_level,
            "final_model": final_model,
            "degrade_reason": degrade_reason,
            "degrade_message": user_message,
            "model_attempts": dominant_item.get("model_attempts") or [],
            "user_message": user_message,
            "error": failed_items[0].get("error") if failed_items else "多模态分析失败",
        }


@celery.task(name="chat.analyze_video", bind=True, max_retries=2, default_retry_delay=60)
def analyze_video(self, session_id: str, video_path: str, query: str | None) -> dict:
    """Compatibility wrapper for legacy single-video entry."""
    return analyze_multimodal_batch.run(session_id, [video_path], query)
