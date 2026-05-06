"""Lightweight multimodal model routing with fallback support."""

from __future__ import annotations

import time
from typing import Any, Callable, Dict, List, Optional

DEFAULT_PROVIDER = "gemini"
TOTAL_BUDGET_SECONDS = 30.0
FALLBACK_SWITCH_MESSAGE = "已自动切换分析通道，继续处理中"

DEFAULT_MODEL_CHAINS: Dict[str, List[str]] = {
    "video": ["gemini-2.5-flash", "gemini-flash-latest"],
    "image": ["gemini-2.5-flash", "gemini-flash-latest"],
    "audio": ["gemini-2.5-flash", "gemini-flash-latest"],
}

DEGRADE_REASON_MESSAGES = {
    "upstream_unavailable": "当前多模态分析服务繁忙，请稍后重试",
    "quota_exhausted": "当前账号额度不足，暂时无法完成多模态分析",
    "network_timeout": "当前多模态分析请求超时，请稍后重试",
    "invalid_response": "多模态分析结果解析异常，请稍后重试",
    "config_error": "多模态分析服务配置不完整，请联系管理员",
    "file_processing_failed": "媒体文件处理失败，请重新上传后重试",
    "unknown_error": "多模态分析失败，请稍后重试",
}


def get_multimodal_model_chain(modality: str = "video") -> List[str]:
    """Return the allowed fallback chain for a given modality."""
    return list(DEFAULT_MODEL_CHAINS.get(modality, DEFAULT_MODEL_CHAINS["video"]))


def build_degrade_message(reason: Optional[str]) -> str:
    return DEGRADE_REASON_MESSAGES.get(str(reason or ""), DEGRADE_REASON_MESSAGES["unknown_error"])


def classify_multimodal_error(error: Exception | str) -> Dict[str, Any]:
    """Classify upstream multimodal failures into stable degrade reasons."""
    raw_error = str(error or "").strip()
    normalized = raw_error.upper()

    if "GOOGLE_API_KEY" in raw_error:
        degrade_reason = "config_error"
        retryable = False
    elif "RESOURCE_EXHAUSTED" in normalized or " 429 " in f" {normalized} " or normalized.startswith("429"):
        degrade_reason = "quota_exhausted"
        retryable = True
    elif "UNAVAILABLE" in normalized or " 503 " in f" {normalized} " or normalized.startswith("503"):
        degrade_reason = "upstream_unavailable"
        retryable = True
    elif any(token in normalized for token in ("TIMEOUT", "TIMED OUT", "READTIMEOUT", "CONNECTTIMEOUT", "CONNECTION RESET", "UNREACHABLE")):
        degrade_reason = "network_timeout"
        retryable = True
    elif any(token in raw_error for token in ("视频文件不存在", "视频处理失败", "state", "ACTIVE")):
        degrade_reason = "file_processing_failed"
        retryable = False
    else:
        degrade_reason = "unknown_error"
        retryable = False

    return {
        "degrade_reason": degrade_reason,
        "retryable": retryable,
        "user_message": build_degrade_message(degrade_reason),
        "raw_error": raw_error,
    }


def _build_processing_meta(
    *,
    phase: str,
    model_attempts: List[Dict[str, Any]],
    fallback_level: int = 0,
    final_model: Optional[str] = None,
    degrade_reason: Optional[str] = None,
    degrade_message: Optional[str] = None,
) -> Dict[str, Any]:
    return {
        "status": "processing",
        "provider": DEFAULT_PROVIDER,
        "phase": phase,
        "fallback_level": int(fallback_level),
        "final_model": final_model,
        "degrade_reason": degrade_reason,
        "degrade_message": degrade_message,
        "model_attempts": [dict(item) for item in model_attempts],
    }


def run_gemini_multimodal_with_fallback(
    *,
    client: Any,
    uploaded_file: Any,
    prompt: str,
    modality: str = "video",
    progress_callback: Optional[Callable[[Dict[str, Any]], None]] = None,
    total_budget_seconds: float = TOTAL_BUDGET_SECONDS,
) -> Dict[str, Any]:
    """
    Call Gemini multimodal models with a two-level fallback chain.

    The uploaded file is reused across attempts; only retryable upstream failures
    trigger a model switch.
    """
    model_attempts: List[Dict[str, Any]] = []
    model_chain = get_multimodal_model_chain(modality)
    started_at = time.monotonic()
    last_failure: Optional[Dict[str, Any]] = None

    if progress_callback:
        progress_callback(_build_processing_meta(phase="llm", model_attempts=model_attempts))

    for index, model in enumerate(model_chain):
        if index > 0 and progress_callback:
            progress_callback(
                _build_processing_meta(
                    phase="fallback",
                    model_attempts=model_attempts,
                    fallback_level=index,
                    final_model=model,
                    degrade_reason=last_failure.get("degrade_reason") if last_failure else None,
                    degrade_message=FALLBACK_SWITCH_MESSAGE,
                )
            )

        attempt_started_at = time.monotonic()
        try:
            response = client.models.generate_content(
                model=model,
                contents=[
                    {"text": prompt},
                    uploaded_file,
                ],
            )
            raw_text = str(getattr(response, "text", "") or "").strip()
            latency_ms = int((time.monotonic() - attempt_started_at) * 1000)

            if not raw_text:
                raise ValueError("模型未返回文本内容")

            model_attempts.append({
                "model": model,
                "status": "success",
                "latency_ms": latency_ms,
            })

            return {
                "status": "success",
                "provider": DEFAULT_PROVIDER,
                "result": None,
                "raw_text": raw_text,
                "final_model": model,
                "fallback_level": index,
                "degrade_reason": last_failure.get("degrade_reason") if index > 0 and last_failure else None,
                "degrade_message": FALLBACK_SWITCH_MESSAGE if index > 0 else None,
                "model_attempts": model_attempts,
                "user_message": None,
            }
        except Exception as exc:  # pragma: no cover - exercised by runtime integration
            latency_ms = int((time.monotonic() - attempt_started_at) * 1000)
            failure = classify_multimodal_error(exc)
            model_attempts.append({
                "model": model,
                "status": "error",
                "latency_ms": latency_ms,
                "reason": failure["degrade_reason"],
            })
            last_failure = failure

            remaining_budget = total_budget_seconds - (time.monotonic() - started_at)
            should_fallback = (
                index + 1 < len(model_chain)
                and bool(failure["retryable"])
                and remaining_budget > 5
            )
            if should_fallback:
                continue

            return {
                "status": "error",
                "provider": DEFAULT_PROVIDER,
                "result": None,
                "raw_text": "",
                "final_model": model,
                "fallback_level": min(index, 1),
                "degrade_reason": failure["degrade_reason"],
                "degrade_message": FALLBACK_SWITCH_MESSAGE if index > 0 else None,
                "model_attempts": model_attempts,
                "user_message": failure["user_message"],
                "error": failure["raw_error"],
            }

    unknown_failure = classify_multimodal_error("未知多模态分析错误")
    return {
        "status": "error",
        "provider": DEFAULT_PROVIDER,
        "result": None,
        "raw_text": "",
        "final_model": None,
        "fallback_level": 0,
        "degrade_reason": unknown_failure["degrade_reason"],
        "degrade_message": None,
        "model_attempts": model_attempts,
        "user_message": unknown_failure["user_message"],
        "error": unknown_failure["raw_error"],
    }
