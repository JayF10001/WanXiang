"""TTS Service - 可插拔 Provider 架构，支持主备切换"""

from __future__ import annotations

import os
import uuid
from abc import ABC, abstractmethod
from typing import Optional, Dict, Any, Tuple

from dotenv import load_dotenv

load_dotenv()

try:
    from ChatBackend.celery_app import celery
except ImportError:
    from celery_app import celery

_REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
_DEFAULT_RUNTIME_STORAGE_ROOT = os.path.join(_REPO_ROOT, "storage", "runtime")


def _get_env(name: str, legacy_name: str | None = None) -> str:
    value = os.getenv(name, "").strip()
    if value:
        return value
    if legacy_name:
        return os.getenv(legacy_name, "").strip()
    return ""


def _resolve_tts_storage_root() -> str:
    configured = _get_env("WANXIANG_TTS_STORAGE", "ZHIMO_TTS_STORAGE")
    if configured:
        return configured
    runtime_root = _get_env("WANXIANG_RUNTIME_STORAGE_ROOT", "ZHIMO_RUNTIME_STORAGE_ROOT") or _DEFAULT_RUNTIME_STORAGE_ROOT
    return os.path.join(runtime_root, "tts")


# TTS 音频存储根目录
TTS_STORAGE_ROOT = _resolve_tts_storage_root()


class TTSProvider(ABC):
    """TTS Provider 抽象接口"""

    @abstractmethod
    def text_to_speech(
        self,
        text: str,
        voice_id: Optional[str] = None,
        **kwargs,
    ) -> bytes:
        """返回音频原始字节数据"""
        raise NotImplementedError

    @property
    @abstractmethod
    def provider_name(self) -> str:
        raise NotImplementedError

    @property
    def file_extension(self) -> str:
        return "mp3"

    @property
    def media_type(self) -> str:
        return "audio/mpeg"


class ElevenLabsProvider(TTSProvider):
    """ElevenLabs TTS Provider"""

    def __init__(self, api_key: Optional[str] = None, voice_id: Optional[str] = None):
        self.api_key = api_key or os.getenv("ELEVENLABS_API_KEY", "")
        self.default_voice_id = voice_id or os.getenv("ELEVENLABS_VOICE_ID", "EXAVITQu4vr4xnSDxMaL")

    @property
    def provider_name(self) -> str:
        return "elevenlabs"

    def text_to_speech(
        self,
        text: str,
        voice_id: Optional[str] = None,
        **kwargs,
    ) -> bytes:
        try:
            from elevenlabs import ElevenLabs
        except ImportError:
            raise RuntimeError(
                "elevenlabs SDK 未安装，请运行: pip install elevenlabs"
            )

        voice = voice_id or self.default_voice_id
        if not voice:
            raise ValueError("未配置 ELEVENLABS_VOICE_ID，且未传入 voice_id")

        client = ElevenLabs(api_key=self.api_key)
        result = client.text_to_speech.convert(voice_id=voice, text=text)
        # convert() 返回 Iterator[bytes]，需要拼接
        return b"".join(result)


class DashScopeProvider(TTSProvider):
    """DashScope CosyVoice TTS Provider"""

    def __init__(self, api_key: Optional[str] = None, voice_id: Optional[str] = None, model: Optional[str] = None):
        self.api_key = api_key or os.getenv("DASHSCOPE_API_KEY") or os.getenv("QWEN_API_KEY", "")
        self.default_voice_id = voice_id or os.getenv("DASHSCOPE_TTS_VOICE", "longxiaochun")
        self.model = model or os.getenv("DASHSCOPE_TTS_MODEL", "cosyvoice-v1")

    @property
    def provider_name(self) -> str:
        return "dashscope"

    @property
    def file_extension(self) -> str:
        return "wav"

    @property
    def media_type(self) -> str:
        return "audio/wav"

    def text_to_speech(
        self,
        text: str,
        voice_id: Optional[str] = None,
        **kwargs,
    ) -> bytes:
        try:
            import dashscope
            from dashscope.audio.tts_v2 import SpeechSynthesizer
        except ImportError:
            raise RuntimeError("dashscope SDK 未安装，请运行: pip install dashscope")

        if not self.api_key:
            raise ValueError("未配置 DASHSCOPE_API_KEY / QWEN_API_KEY")

        voice = voice_id or self.default_voice_id
        if not voice:
            raise ValueError("未配置 DASHSCOPE_TTS_VOICE，且未传入 voice_id")

        dashscope.api_key = self.api_key
        synthesizer = SpeechSynthesizer(model=self.model, voice=voice)
        audio = synthesizer.call(text)
        if not audio:
            raise RuntimeError("DashScope 未返回音频数据")
        return audio


class TTSService:
    """TTS 统一入口，支持 Provider 切换"""

    PROVIDER_MAP: Dict[str, type[TTSProvider]] = {
        "dashscope": DashScopeProvider,
        "elevenlabs": ElevenLabsProvider,
    }

    _provider_cache: Dict[str, TTSProvider] = {}

    @classmethod
    def _get_provider_instance(cls, provider_name: str) -> TTSProvider:
        normalized = str(provider_name or "").strip().lower()
        if not normalized:
            raise ValueError("TTS provider 不能为空")
        if normalized in cls._provider_cache:
            return cls._provider_cache[normalized]
        provider_cls = cls.PROVIDER_MAP.get(normalized)
        if not provider_cls:
            raise ValueError(f"未知的 TTS Provider: {provider_name}")
        instance = provider_cls()
        cls._provider_cache[normalized] = instance
        return instance

    @classmethod
    def _get_default_provider_chain(cls) -> list[str]:
        primary = str(
            os.getenv("TTS_PROVIDER_PRIMARY")
            or os.getenv("TTS_PROVIDER")
            or "dashscope"
        ).strip().lower()
        fallback = str(
            os.getenv("TTS_PROVIDER_FALLBACK")
            or ("elevenlabs" if primary != "elevenlabs" else "dashscope")
        ).strip().lower()
        chain = []
        for item in [primary, fallback]:
            if item and item not in chain:
                chain.append(item)
        return chain

    @classmethod
    def configure(cls, provider_name: str, **kwargs) -> None:
        """运行时切换 Provider（用于测试）"""
        provider_cls = cls.PROVIDER_MAP.get(provider_name.lower())
        if not provider_cls:
            raise ValueError(f"未知的 TTS Provider: {provider_name}")
        cls._provider_cache[provider_name.lower()] = provider_cls(**kwargs)

    @classmethod
    def _synthesize_with_provider_chain(
        cls,
        provider_chain: list[str],
        *,
        text: str,
        voice_id: Optional[str] = None,
        **kwargs,
    ) -> Tuple[TTSProvider, bytes]:
        errors: list[str] = []
        for provider_name in provider_chain:
            provider = cls._get_provider_instance(provider_name)
            try:
                audio_bytes = provider.text_to_speech(text, voice_id=voice_id, **kwargs)
                return provider, audio_bytes
            except Exception as exc:
                errors.append(f"{provider_name}: {exc}")
        raise RuntimeError("；".join(errors) if errors else "没有可用的 TTS Provider")

    @classmethod
    def text_to_speech(
        cls,
        text: str,
        voice_id: Optional[str] = None,
        provider: Optional[str] = None,
        session_id: Optional[str] = None,
        **kwargs,
    ) -> Dict[str, Any]:
        """
        将文本转为语音，保存为 MP3 文件。

        返回:
            {
                "audio_url": str,       # 访问 URL
                "file_path": str,       # 磁盘路径
                "duration_seconds": float,
                "provider": str,
                "text_preview": str,    # 前50字预览
            }
        """
        # 文本校验
        text = (text or "").strip()
        if not text:
            raise ValueError("文本内容不能为空")
        if len(text) > 5000:
            raise ValueError("文本内容不能超过 5000 字")

        if provider:
            provider_chain = [str(provider).strip().lower()]
        else:
            provider_chain = cls._get_default_provider_chain()

        active_provider, audio_bytes = cls._synthesize_with_provider_chain(
            provider_chain,
            text=text,
            voice_id=voice_id,
            **kwargs,
        )

        session_dir = os.path.join(TTS_STORAGE_ROOT, str(session_id or "global"))
        os.makedirs(session_dir, exist_ok=True)
        filename = f"{uuid.uuid4().hex}.{active_provider.file_extension}"
        file_path = os.path.join(session_dir, filename)
        with open(file_path, "wb") as f:
            f.write(audio_bytes)

        duration = len(text) / 150 * 60

        return {
            "audio_url": f"/api/assistant/tts/audio/{session_id or 'global'}/{filename}",
            "file_path": file_path,
            "duration_seconds": round(duration, 1),
            "provider": active_provider.provider_name,
            "media_type": active_provider.media_type,
            "text_preview": text[:50] + ("..." if len(text) > 50 else ""),
        }


@celery.task(name="chat.generate_tts_for_message", bind=True, max_retries=1, default_retry_delay=15)
def generate_tts_for_message(
    self,
    session_id: str,
    message_id: str,
    text: str,
    voice_id: Optional[str] = None,
    provider: Optional[str] = None,
) -> Dict[str, Any]:
    from ChatBackend.app.services.chat_service import ChatService

    normalized_text = str(text or "").strip()
    if not normalized_text:
        error_message = "文本内容不能为空"
        ChatService.update_message_fields(
            session_id,
            message_id,
            {
                "tts_status": "failed",
                "tts_error": error_message,
            },
        )
        return {
            "status": "error",
            "message_id": message_id,
            "error": error_message,
            "tts_status": "failed",
            "tts_error": error_message,
        }

    processing_meta = {
        "message_id": message_id,
        "tts_status": "processing",
        "phase": "tts",
        "provider": provider or None,
        "user_message": "正在生成语音",
    }
    self.update_state(state="PROGRESS", meta=processing_meta)
    ChatService.update_message_fields(
        session_id,
        message_id,
        {
            "tts_status": "processing",
            "tts_error": None,
        },
    )

    try:
        result = TTSService.text_to_speech(
            text=normalized_text,
            voice_id=voice_id,
            provider=provider,
            session_id=session_id,
        )
        update_fields = {
            "audio_url": result["audio_url"],
            "tts_status": "ready",
            "tts_provider": result["provider"],
            "tts_duration_seconds": result["duration_seconds"],
            "tts_error": None,
        }
        ChatService.update_message_fields(session_id, message_id, update_fields)
        return {
            "status": "completed",
            "message_id": message_id,
            "audio_url": result["audio_url"],
            "provider": result["provider"],
            "duration_seconds": result["duration_seconds"],
            "tts_status": "ready",
            "text_preview": result["text_preview"],
        }
    except Exception as exc:
        error_message = str(exc)
        ChatService.update_message_fields(
            session_id,
            message_id,
            {
                "tts_status": "failed",
                "tts_error": error_message,
            },
        )
        return {
            "status": "error",
            "message_id": message_id,
            "error": error_message,
            "tts_status": "failed",
            "tts_error": error_message,
            "user_message": "语音生成失败",
        }
