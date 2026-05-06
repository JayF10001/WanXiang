from __future__ import annotations

import json
import requests

from ..config import settings


class FeishuClient:
    def __init__(self) -> None:
        self.base_url = settings.feishu_base_url.rstrip("/")
        self.session = requests.Session()
        self.session.trust_env = False
        self._tenant_access_token: str | None = None

    def _get_tenant_access_token(self) -> str:
        if self._tenant_access_token:
            return self._tenant_access_token
        if not settings.feishu_app_id or not settings.feishu_app_secret:
            raise RuntimeError("缺少飞书配置：FEISHU_APP_ID / FEISHU_APP_SECRET")

        response = self.session.post(
            f"{self.base_url}/open-apis/auth/v3/tenant_access_token/internal",
            json={
                "app_id": settings.feishu_app_id,
                "app_secret": settings.feishu_app_secret,
            },
            timeout=20,
        )
        payload = response.json() if response.content else {}
        if response.status_code >= 400 or payload.get("code") != 0:
            raise RuntimeError(payload.get("msg") or "获取飞书 tenant_access_token 失败")
        self._tenant_access_token = str(payload.get("tenant_access_token") or "")
        return self._tenant_access_token

    def reply_text(self, *, message_id: str, text: str) -> None:
        token = self._get_tenant_access_token()
        response = self.session.post(
            f"{self.base_url}/open-apis/im/v1/messages/{message_id}/reply",
            headers={
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json",
            },
            json={
                "msg_type": "text",
                "content": json.dumps({"text": text}, ensure_ascii=False),
            },
            timeout=20,
        )
        payload = response.json() if response.content else {}
        if response.status_code >= 400 or payload.get("code") != 0:
            raise RuntimeError(payload.get("msg") or "飞书消息回复失败")


feishu_client = FeishuClient()
