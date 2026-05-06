from __future__ import annotations

import logging
import time

import requests

from ..config import settings
from ..utils.text_format import truncate_text


logger = logging.getLogger(__name__)


class QQClient:
    def __init__(self) -> None:
        self.base_url = settings.qq_base_url.rstrip("/")
        self.token_url = settings.qq_token_url.rstrip("/")
        self.session = requests.Session()
        self.session.trust_env = False
        self._access_token: str | None = None
        self._expires_at: float = 0

    def _get_access_token(self) -> str:
        if settings.qq_mock_reply:
            return "mock-access-token"
        now = time.time()
        if self._access_token and now < self._expires_at:
            return self._access_token
        if not settings.qq_app_id or not settings.qq_app_secret:
            raise RuntimeError("缺少 QQ 配置：QQ_APP_ID / QQ_APP_SECRET")

        response = self.session.post(
            self.token_url,
            json={
                "appId": settings.qq_app_id,
                "clientSecret": settings.qq_app_secret,
            },
            timeout=20,
        )
        payload = response.json() if response.content else {}
        access_token = str(payload.get("access_token") or payload.get("accessToken") or "")
        expires_in = int(payload.get("expires_in") or payload.get("expiresIn") or 7200)
        if response.status_code >= 400 or not access_token:
            raise RuntimeError(payload.get("message") or payload.get("msg") or "获取 QQ access_token 失败")

        self._access_token = access_token
        self._expires_at = now + max(expires_in - 60, 60)
        return access_token

    def reply_text(self, *, openid: str, text: str, msg_id: str | None = None, event_id: str | None = None) -> None:
        content = truncate_text(text, settings.reply_max_chars)
        if settings.qq_mock_reply:
            logger.info("QQ mock reply openid=%s msg_id=%s event_id=%s text=%s", openid, msg_id, event_id, content)
            return

        token = self._get_access_token()
        payload = {
            "content": content,
            "msg_type": 0,
        }
        if msg_id:
            payload["msg_id"] = msg_id
        if event_id:
            payload["event_id"] = event_id

        response = self.session.post(
            f"{self.base_url}/v2/users/{openid}/messages",
            headers={
                "Authorization": f"QQBot {token}",
                "X-Union-Appid": settings.qq_app_id,
                "Content-Type": "application/json",
            },
            json=payload,
            timeout=20,
        )
        body = response.json() if response.content else {}
        if response.status_code == 401:
            self._access_token = None
            token = self._get_access_token()
            response = self.session.post(
                f"{self.base_url}/v2/users/{openid}/messages",
                headers={
                    "Authorization": f"QQBot {token}",
                    "X-Union-Appid": settings.qq_app_id,
                    "Content-Type": "application/json",
                },
                json=payload,
                timeout=20,
            )
            body = response.json() if response.content else {}

        if response.status_code >= 400:
            raise RuntimeError(body.get("message") or body.get("msg") or "QQ 消息回复失败")


qq_client = QQClient()
