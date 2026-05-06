from dataclasses import dataclass
import os
from pathlib import Path


_REPO_ROOT = Path(__file__).resolve().parents[2]
_DEFAULT_RUNTIME_STORAGE_ROOT = _REPO_ROOT / "storage" / "runtime"
_LOCAL_ALLOWED_ORIGINS = (
    "http://localhost:3000",
    "http://127.0.0.1:3000",
)


def _get_env(name: str, legacy_name: str | None = None, default: str = "") -> str:
    value = os.getenv(name)
    if value not in {None, ""}:
        return value
    if legacy_name:
        legacy_value = os.getenv(legacy_name)
        if legacy_value not in {None, ""}:
            return legacy_value
    return default


def _parse_csv_env(name: str, fallback: tuple[str, ...], legacy_name: str | None = None) -> tuple[str, ...]:
    raw_value = _get_env(name, legacy_name).strip()
    if not raw_value:
        return fallback
    values = tuple(item.strip() for item in raw_value.split(",") if item.strip())
    return values or fallback


def _resolve_runtime_storage_root() -> str:
    configured = _get_env("WANXIANG_RUNTIME_STORAGE_ROOT", "ZHIMO_RUNTIME_STORAGE_ROOT").strip()
    if configured:
        return configured
    return str(_DEFAULT_RUNTIME_STORAGE_ROOT)


@dataclass(frozen=True)
class Settings:
    app_name: str = os.getenv("FRONTEND_API_APP_NAME", "frontend_api")
    app_host: str = os.getenv("FRONTEND_API_HOST", "127.0.0.1")
    app_port: int = int(os.getenv("FRONTEND_API_PORT", "8001"))
    secret_key: str = os.getenv("FRONTEND_API_SECRET_KEY", "frontend-api-dev-secret")
    chatbackend_base_url: str = os.getenv("CHATBACKEND_BASE_URL", "http://127.0.0.1:5000")
    chatbackend_session_cookie_name: str = os.getenv("CHATBACKEND_SESSION_COOKIE_NAME", "session")
    frontend_origin: str = os.getenv("FRONTEND_ORIGIN", "http://127.0.0.1:3000")
    allowed_origins: tuple[str, ...] = _parse_csv_env("WANXIANG_ALLOWED_ORIGINS", _LOCAL_ALLOWED_ORIGINS, "ZHIMO_ALLOWED_ORIGINS")
    chatbackend_request_timeout: float = float(os.getenv("CHATBACKEND_REQUEST_TIMEOUT", "20"))
    chatbackend_analyze_timeout: float = float(os.getenv("CHATBACKEND_ANALYZE_TIMEOUT", "120"))
    redis_url: str = os.getenv("FRONTEND_API_REDIS_URL", os.getenv("CELERY_BROKER_URL", "redis://localhost:6379/0"))
    runtime_storage_root: str = _resolve_runtime_storage_root()
    multimodal_storage_root: str = _get_env(
        "WANXIANG_MULTIMODAL_STORAGE",
        "ZHIMO_MULTIMODAL_STORAGE",
        os.path.join(_resolve_runtime_storage_root(), "multimodal"),
    )
    tts_storage_root: str = _get_env(
        "WANXIANG_TTS_STORAGE",
        "ZHIMO_TTS_STORAGE",
        os.path.join(_resolve_runtime_storage_root(), "tts"),
    )


settings = Settings()
