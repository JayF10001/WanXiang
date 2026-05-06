from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request

from ..config import settings
from ..schemas.feishu_event import FeishuChallengeRequest, FeishuEvent
from ..services.card_service import feishu_card_service
from ..services.chat_service import feishu_chat_service
from ..services.feishu_client import feishu_client
from ..services.message_parser import extract_text_from_message_content, parse_command
from ..services.report_service import feishu_report_service
from ..utils.signature import verify_lark_signature


router = APIRouter(prefix="/webhook", tags=["feishu"])


HELP_TEXT = "\n".join([
    "WanXiang 飞书机器人一期已启用。",
    "支持命令：",
    "1. 直接发送文本：普通对话",
    "2. 深度分析 xxx",
    "3. 分析：xxx",
    "4. 生成报告",
    "5. 报告：先提问后再生成报告",
])


@router.get("/health")
def health():
    return {"success": True, "message": "feishu_adapter is healthy"}


def _verify_request_signature(request: Request, body: bytes) -> None:
    if not settings.feishu_verify_signature:
        return
    timestamp = request.headers.get("X-Lark-Request-Timestamp", "")
    nonce = request.headers.get("X-Lark-Request-Nonce", "")
    signature = request.headers.get("X-Lark-Signature", "")
    if not verify_lark_signature(timestamp, nonce, body, settings.feishu_encrypt_key, signature):
        raise HTTPException(status_code=401, detail="飞书签名校验失败")


@router.post("/event")
async def handle_event(request: Request):
    body = await request.body()
    _verify_request_signature(request, body)

    payload = FeishuChallengeRequest.model_validate_json(body)
    if payload.challenge:
        return {"challenge": payload.challenge}

    event = FeishuEvent.model_validate_json(body)
    event_type = str((event.header or {}).get("event_type") or "")
    if event_type != "im.message.receive_v1":
        return {"success": True, "message": f"忽略事件类型: {event_type or 'unknown'}"}

    message = event.event.message if event.event else None
    sender = event.event.sender if event.event else None
    if not message or not sender:
        return {"success": True, "message": "缺少 message 或 sender，已忽略"}

    if message.message_type != "text":
        feishu_client.reply_text(
            message_id=str(message.message_id or ""),
            text="一期版本目前仅支持文本消息。请直接发送文字、'深度分析 xxx' 或 '生成报告'。",
        )
        return {"success": True, "message": "unsupported message type"}

    raw_text = extract_text_from_message_content(message.content)
    parsed = parse_command(raw_text)
    sender_id = sender.sender_id.open_id if sender.sender_id else None
    chat_id = message.chat_id

    if parsed.command == "empty":
        reply = "未识别到有效文本内容，请重新输入。"
    elif parsed.command == "help":
        reply = HELP_TEXT
    elif parsed.command == "report":
        reply = feishu_report_service.generate_report(open_id=sender_id, chat_id=chat_id)
    elif parsed.command == "analysis":
        if not parsed.text:
            reply = "请在“深度分析”后补充要分析的内容，例如：深度分析 某热点事件。"
        else:
            reply = feishu_chat_service.analyze(open_id=sender_id, chat_id=chat_id, message=parsed.text)
    else:
        reply = feishu_chat_service.chat(open_id=sender_id, chat_id=chat_id, message=parsed.text)

    feishu_client.reply_text(message_id=str(message.message_id or ""), text=reply)
    return {"success": True}


@router.post("/card")
async def handle_card(request: Request):
    body = await request.json()
    return feishu_card_service.handle(body)
