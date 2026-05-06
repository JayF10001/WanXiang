from __future__ import annotations

from dataclasses import dataclass
import os


@dataclass(frozen=True)
class Settings:
    app_name: str = os.getenv("FEISHU_ADAPTER_APP_NAME", "feishu_adapter")
    app_host: str = os.getenv("FEISHU_ADAPTER_HOST", "127.0.0.1")
    app_port: int = int(os.getenv("FEISHU_ADAPTER_PORT", "8100"))

    frontend_api_base_url: str = os.getenv(
        "FEISHU_FRONTEND_API_BASE_URL",
        os.getenv("FRONTEND_API_BASE_URL", "http://127.0.0.1:8001/api"),
    )
    frontend_api_timeout: float = float(os.getenv("FEISHU_FRONTEND_API_TIMEOUT", "60"))
    frontend_api_bot_email: str = os.getenv("FEISHU_FRONTEND_API_BOT_EMAIL", "").strip()
    frontend_api_bot_password: str = os.getenv("FEISHU_FRONTEND_API_BOT_PASSWORD", "").strip()

    feishu_base_url: str = os.getenv("FEISHU_BASE_URL", "https://open.feishu.cn")
    feishu_app_id: str = os.getenv("FEISHU_APP_ID", "").strip()
    feishu_app_secret: str = os.getenv("FEISHU_APP_SECRET", "").strip()
    feishu_encrypt_key: str = os.getenv("FEISHU_ENCRYPT_KEY", "").strip()
    feishu_verify_signature: bool = os.getenv("FEISHU_VERIFY_SIGNATURE", "false").lower() == "true"

    session_ttl_seconds: int = int(os.getenv("FEISHU_SESSION_TTL_SECONDS", "43200"))
    report_summary_max_chars: int = int(os.getenv("FEISHU_REPORT_SUMMARY_MAX_CHARS", "500"))


settings = Settings()
