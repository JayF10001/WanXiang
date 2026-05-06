from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request

from ..config import settings
from ..schemas.qq_event import QQCallbackData, QQEventBody, QQWebhookPayload
from ..services.chat_service import qq_chat_service
from ..services.message_parser import extract_text_from_message_content, parse_command
from ..services.qq_client import qq_client
from ..services.report_service import qq_report_service
from ..utils.signature import build_callback_response, verify_qq_signature


router = APIRouter(prefix="/webhook", tags=["qq"])


HELP_TEXT = "\n".join([
    "WanXiang QQ 机器人一期已启用。",
    "支持命令：",
    "1. 直接发送文本：普通对话",
    "2. 深度分析 xxx",
    "3. 分析：xxx",
    "4. 生成报告",
    "5. 报告：先提问后再生成报告",
])


@router.get("/health")
def health():
    return {"success": True, "message": "qq_adapter is healthy"}


def _verify_request_signature(request: Request, body: bytes) -> None:
    if not settings.qq_verify_signature:
        return
    timestamp = request.headers.get("X-Signature-Timestamp", "")
    signature = request.headers.get("X-Signature-Ed25519", "")
    if not verify_qq_signature(timestamp=timestamp, body=body, app_secret=settings.qq_app_secret, provided_signature=signature):
        raise HTTPException(status_code=401, detail="QQ webhook 签名校验失败")


def _reply_error_safe(*, openid: str | None, message_id: str | None, text: str) -> None:
    if not openid or not message_id:
        return
    try:
        qq_client.reply_text(openid=openid, text=text, msg_id=message_id)
    except Exception:
        return


@router.post("/event")
async def handle_event(request: Request):
    body = await request.body()
    payload = QQWebhookPayload.model_validate_json(body)

    if payload.op == 13:
        callback = QQCallbackData.model_validate(payload.d or {})
        response = build_callback_response(
            event_ts=str(callback.event_ts or ""),
            plain_token=str(callback.plain_token or ""),
            app_secret=settings.qq_app_secret,
        )
        return response

    _verify_request_signature(request, body)

    if payload.op != 0:
        return {"success": True, "message": f"忽略 op: {payload.op}"}
    if payload.t != "C2C_MESSAGE_CREATE":
        return {"success": True, "message": f"忽略事件类型: {payload.t or 'unknown'}"}

    event = QQEventBody.model_validate(payload.d or {})
    openid = (
        (event.author.user_openid if event.author else None)
        or (event.author.id if event.author else None)
        or event.user_openid
    )
    message_id = str(event.id or "")

    if not openid:
        return {"success": True, "message": "缺少用户 openid，已忽略"}

    raw_text = extract_text_from_message_content(event.content)
    has_attachments = bool(event.attachments)
    if has_attachments and not raw_text:
        reply = "一期版本目前仅支持文本消息。请直接发送文字、'深度分析 xxx' 或 '生成报告'。"
        qq_client.reply_text(openid=openid, text=reply, msg_id=message_id)
        return {"success": True, "message": "unsupported message type"}

    parsed = parse_command(raw_text)
    try:
        if parsed.command == "empty":
            reply = "未识别到有效文本内容，请重新输入。"
        elif parsed.command == "help":
            reply = HELP_TEXT
        elif parsed.command == "report":
            reply = qq_report_service.generate_report(qq_user_id=openid)
        elif parsed.command == "analysis":
            if not parsed.text:
                reply = "请在“深度分析”后补充要分析的内容，例如：深度分析 某热点事件。"
            else:
                reply = qq_chat_service.analyze(qq_user_id=openid, message=parsed.text)
        else:
            reply = qq_chat_service.chat(qq_user_id=openid, message=parsed.text)
    except Exception as exc:
        reply = f"处理消息时出现异常：{exc}"
        _reply_error_safe(openid=openid, message_id=message_id, text=reply)
        return {"success": False, "message": reply}

    qq_client.reply_text(openid=openid, text=reply, msg_id=message_id)
    return {"success": True}
