from __future__ import annotations

from typing import Any, Optional

from pydantic import BaseModel


class QQAuthor(BaseModel):
    id: Optional[str] = None
    user_openid: Optional[str] = None
    username: Optional[str] = None


class QQAttachment(BaseModel):
    content_type: Optional[str] = None
    filename: Optional[str] = None
    size: Optional[int] = None
    url: Optional[str] = None


class QQEventBody(BaseModel):
    id: Optional[str] = None
    content: Optional[str] = None
    timestamp: Optional[str] = None
    author: Optional[QQAuthor] = None
    attachments: list[QQAttachment] = []
    channel_id: Optional[str] = None
    guild_id: Optional[str] = None
    group_openid: Optional[str] = None
    group_id: Optional[str] = None
    user_openid: Optional[str] = None


class QQCallbackData(BaseModel):
    plain_token: Optional[str] = None
    event_ts: Optional[str] = None


class QQWebhookPayload(BaseModel):
    id: Optional[str] = None
    op: Optional[int] = None
    s: Optional[int] = None
    t: Optional[str] = None
    d: Optional[dict[str, Any]] = None
