from __future__ import annotations

from dataclasses import dataclass
import os


@dataclass(frozen=True)
class Settings:
    app_name: str = os.getenv("QQ_ADAPTER_APP_NAME", "qq_adapter")
    app_host: str = os.getenv("QQ_ADAPTER_HOST", "127.0.0.1")
    app_port: int = int(os.getenv("QQ_ADAPTER_PORT", "8102"))

    frontend_api_base_url: str = os.getenv(
        "QQ_FRONTEND_API_BASE_URL",
        os.getenv("FRONTEND_API_BASE_URL", "http://127.0.0.1:8001/api"),
    )
    frontend_api_timeout: float = float(os.getenv("QQ_FRONTEND_API_TIMEOUT", "60"))
    frontend_api_bot_email: str = os.getenv("QQ_FRONTEND_API_BOT_EMAIL", "").strip()
    frontend_api_bot_password: str = os.getenv("QQ_FRONTEND_API_BOT_PASSWORD", "").strip()

    qq_base_url: str = os.getenv("QQ_BASE_URL", "https://api.sgroup.qq.com").strip()
    qq_token_url: str = os.getenv("QQ_TOKEN_URL", "https://bots.qq.com/app/getAppAccessToken").strip()
    qq_app_id: str = os.getenv("QQ_APP_ID", "").strip()
    qq_app_secret: str = os.getenv("QQ_APP_SECRET", "").strip()
    qq_verify_signature: bool = os.getenv("QQ_VERIFY_SIGNATURE", "false").lower() == "true"
    qq_mock_reply: bool = os.getenv("QQ_MOCK_REPLY", "false").lower() == "true"

    session_ttl_seconds: int = int(os.getenv("QQ_SESSION_TTL_SECONDS", "43200"))
    reply_max_chars: int = int(os.getenv("QQ_REPLY_MAX_CHARS", "1200"))
    report_summary_max_chars: int = int(os.getenv("QQ_REPORT_SUMMARY_MAX_CHARS", "500"))


settings = Settings()
