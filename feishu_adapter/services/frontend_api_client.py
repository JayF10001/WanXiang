from __future__ import annotations

from typing import Any
import requests

from ..config import settings


class FrontendApiClient:
    def __init__(self) -> None:
        self.base_url = settings.frontend_api_base_url.rstrip("/")
        self.session = requests.Session()
        self.session.trust_env = False
        self._authenticated = False

    def _login(self) -> None:
        if not settings.frontend_api_bot_email or not settings.frontend_api_bot_password:
            raise RuntimeError("缺少飞书机器人服务账号配置：FEISHU_FRONTEND_API_BOT_EMAIL / FEISHU_FRONTEND_API_BOT_PASSWORD")

        response = self.session.post(
            f"{self.base_url}/auth/login",
            json={
                "email": settings.frontend_api_bot_email,
                "password": settings.frontend_api_bot_password,
                "type": "account",
            },
            timeout=settings.frontend_api_timeout,
        )
        payload = response.json() if response.content else {}
        if response.status_code >= 400 or not payload.get("success"):
            raise RuntimeError(payload.get("detail") or payload.get("message") or "飞书服务账号登录 frontend_api 失败")
        self._authenticated = True

    def _request(self, method: str, path: str, **kwargs: Any) -> tuple[requests.Response, dict[str, Any]]:
        if not self._authenticated:
            self._login()

        response = self.session.request(
            method=method,
            url=f"{self.base_url}{path}",
            timeout=kwargs.pop("timeout", settings.frontend_api_timeout),
            **kwargs,
        )
        try:
            payload = response.json()
        except Exception:
            payload = {}

        if response.status_code == 401:
            self._authenticated = False
            self._login()
            response = self.session.request(
                method=method,
                url=f"{self.base_url}{path}",
                timeout=kwargs.pop("timeout", settings.frontend_api_timeout),
                **kwargs,
            )
            try:
                payload = response.json()
            except Exception:
                payload = {}

        return response, payload

    def create_session(self) -> dict[str, Any]:
        response, payload = self._request("POST", "/assistant/sessions")
        if response.status_code >= 400 or not payload.get("success"):
            raise RuntimeError(payload.get("detail") or payload.get("message") or "创建会话失败")
        return payload.get("data") or {}

    def analyze_chat(self, *, session_id: str, message: str) -> dict[str, Any]:
        response, payload = self._request(
            "POST",
            "/assistant/analyze",
            json={
                "mode": "chat",
                "sessionId": session_id,
                "message": message,
            },
            timeout=max(settings.frontend_api_timeout, 120),
        )
        if response.status_code >= 400 or not payload.get("success"):
            raise RuntimeError(payload.get("detail") or payload.get("message") or "聊天分析失败")
        return payload.get("data") or {}

    def generate_report(self, *, session_id: str) -> dict[str, Any]:
        response, payload = self._request(
            "POST",
            "/reports/generate",
            json={"sessionId": session_id},
            timeout=max(settings.frontend_api_timeout, 300),
        )
        if response.status_code >= 400 or not payload.get("success"):
            raise RuntimeError(payload.get("detail") or payload.get("message") or "生成报告失败")
        return payload.get("data") or {}


frontend_api_client = FrontendApiClient()
