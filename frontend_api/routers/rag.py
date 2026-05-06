from __future__ import annotations

from pydantic import BaseModel
from fastapi import APIRouter, HTTPException, Request

from ..services.chatbackend_client import client


router = APIRouter(prefix="/api/rag", tags=["rag"])


class RagAnswerRequest(BaseModel):
    query: str
    kbId: str | None = None
    sourceUrl: str | None = None
    platformHint: str | None = None
    sessionId: str | None = None


def _require_backend_cookies(request: Request):
    backend_cookies = request.session.get("chatbackend_cookies")
    if not backend_cookies:
        raise HTTPException(status_code=401, detail="未登录")
    return backend_cookies


@router.post("/answer")
def rag_answer(request: Request, body: RagAnswerRequest):
    backend_cookies = _require_backend_cookies(request)
    response, payload = client.request_json(
        "POST",
        "/api/v1/rag/answer",
        json_data=body.model_dump(),
        session_cookie=backend_cookies,
        timeout=60,
    )
    if response.status_code >= 400 or payload.get("success") is False:
        raise HTTPException(status_code=response.status_code or 500, detail=payload.get("error") or payload.get("message") or "RAG 回答失败")
    return {"success": True, "data": payload.get("data") or {}, "message": "RAG 回答成功"}
