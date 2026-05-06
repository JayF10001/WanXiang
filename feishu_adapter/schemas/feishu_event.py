from __future__ import annotations

from typing import Any, Optional
from pydantic import BaseModel


class FeishuSenderId(BaseModel):
    open_id: Optional[str] = None
    union_id: Optional[str] = None
    user_id: Optional[str] = None


class FeishuSender(BaseModel):
    sender_id: Optional[FeishuSenderId] = None
    sender_type: Optional[str] = None
    tenant_key: Optional[str] = None


class FeishuMessage(BaseModel):
    message_id: Optional[str] = None
    root_id: Optional[str] = None
    parent_id: Optional[str] = None
    create_time: Optional[str] = None
    chat_id: Optional[str] = None
    chat_type: Optional[str] = None
    message_type: Optional[str] = None
    content: Optional[str] = None


class FeishuEventBody(BaseModel):
    sender: Optional[FeishuSender] = None
    message: Optional[FeishuMessage] = None


class FeishuEvent(BaseModel):
    schema: Optional[str] = None
    header: Optional[dict[str, Any]] = None
    event: Optional[FeishuEventBody] = None


class FeishuChallengeRequest(BaseModel):
    challenge: Optional[str] = None
    token: Optional[str] = None
    type: Optional[str] = None
    event: Optional[FeishuEventBody] = None
    header: Optional[dict[str, Any]] = None
