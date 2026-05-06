from __future__ import annotations

from typing import Any

from fastapi import APIRouter, File, Form, HTTPException, Request, UploadFile

from ..services.chatbackend_client import client


router = APIRouter(prefix="/api", tags=["knowledge"])


def _require_backend_cookies(request: Request):
    backend_cookies = request.session.get("chatbackend_cookies")
    if not backend_cookies:
        raise HTTPException(status_code=401, detail="未登录")
    return backend_cookies


@router.get("/knowledge-bases")
def list_knowledge_bases(request: Request):
    backend_cookies = _require_backend_cookies(request)
    response, payload = client.request_json("GET", "/api/v1/knowledge-bases", session_cookie=backend_cookies)
    if response.status_code >= 400 or payload.get("success") is False:
        raise HTTPException(status_code=response.status_code or 500, detail=payload.get("error") or payload.get("message") or "获取知识库列表失败")
    return {"success": True, "data": payload.get("data") or [], "message": "获取知识库列表成功"}


@router.post("/knowledge-bases")
def create_knowledge_base(request: Request, body: dict[str, Any]):
    backend_cookies = _require_backend_cookies(request)
    response, payload = client.request_json("POST", "/api/v1/knowledge-bases", json_data=body, session_cookie=backend_cookies)
    if response.status_code >= 400 or payload.get("success") is False:
        raise HTTPException(status_code=response.status_code or 500, detail=payload.get("error") or payload.get("message") or "创建知识库失败")
    return {"success": True, "data": payload.get("data") or {}, "message": "创建知识库成功"}


@router.get("/knowledge-bases/{kb_id}/files")
def list_knowledge_files(request: Request, kb_id: str):
    backend_cookies = _require_backend_cookies(request)
    response, payload = client.request_json("GET", f"/api/v1/knowledge-bases/{kb_id}/files", session_cookie=backend_cookies)
    if response.status_code >= 400 or payload.get("success") is False:
        raise HTTPException(status_code=response.status_code or 500, detail=payload.get("error") or payload.get("message") or "获取知识库文件列表失败")
    return {"success": True, "data": payload.get("data") or [], "message": "获取知识库文件列表成功"}


@router.post("/knowledge-bases/{kb_id}/rebuild-index")
def rebuild_knowledge_base_index(request: Request, kb_id: str):
    backend_cookies = _require_backend_cookies(request)
    response, payload = client.request_json("POST", f"/api/v1/knowledge-bases/{kb_id}/rebuild-index", session_cookie=backend_cookies)
    if response.status_code >= 400 or payload.get("success") is False:
        raise HTTPException(status_code=response.status_code or 500, detail=payload.get("error") or payload.get("message") or "批量重建知识库索引失败")
    return {"success": True, "data": payload.get("data") or {}, "message": payload.get("message") or "知识库批量重建索引任务已提交"}


@router.post("/knowledge-bases/{kb_id}/files")
async def upload_knowledge_file(
    request: Request,
    kb_id: str,
    file: UploadFile = File(...),
    remark: str | None = Form(None),
    tags: str | None = Form(None),
):
    backend_cookies = _require_backend_cookies(request)
    content = await file.read()
    response, payload = client.request_multipart(
        "POST",
        f"/api/v1/knowledge-bases/{kb_id}/files",
        session_cookie=backend_cookies,
        files={"file": (file.filename or "upload.bin", content, file.content_type or "application/octet-stream")},
        data={"remark": remark or "", "tags": tags or ""},
        timeout=60,
    )
    if response.status_code >= 400 or payload.get("success") is False:
        raise HTTPException(status_code=response.status_code or 500, detail=payload.get("error") or payload.get("message") or "上传知识库文件失败")
    return {"success": True, "data": payload.get("data") or {}, "message": "上传知识库文件成功"}


@router.get("/knowledge-files/{file_id}")
def get_knowledge_file(request: Request, file_id: str):
    backend_cookies = _require_backend_cookies(request)
    response, payload = client.request_json("GET", f"/api/v1/knowledge-files/{file_id}", session_cookie=backend_cookies)
    if response.status_code >= 400 or payload.get("success") is False:
        raise HTTPException(status_code=response.status_code or 500, detail=payload.get("error") or payload.get("message") or "获取知识库文件详情失败")
    return {"success": True, "data": payload.get("data") or {}, "message": "获取知识库文件详情成功"}


@router.post("/knowledge-files/{file_id}/retry-parse")
def retry_knowledge_file_parse(request: Request, file_id: str):
    backend_cookies = _require_backend_cookies(request)
    response, payload = client.request_json("POST", f"/api/v1/knowledge-files/{file_id}/retry-parse", session_cookie=backend_cookies, timeout=120)
    if response.status_code >= 400 or payload.get("success") is False:
        raise HTTPException(status_code=response.status_code or 500, detail=payload.get("error") or payload.get("message") or "重新解析知识库文件失败")
    return {"success": True, "data": payload.get("data") or {}, "message": payload.get("message") or "文件重新解析任务已提交"}


@router.post("/knowledge-files/{file_id}/retry-index")
def retry_knowledge_file_index(request: Request, file_id: str):
    backend_cookies = _require_backend_cookies(request)
    response, payload = client.request_json("POST", f"/api/v1/knowledge-files/{file_id}/retry-index", session_cookie=backend_cookies, timeout=120)
    if response.status_code >= 400 or payload.get("success") is False:
        raise HTTPException(status_code=response.status_code or 500, detail=payload.get("error") or payload.get("message") or "重试知识库文件索引失败")
    return {"success": True, "data": payload.get("data") or {}, "message": payload.get("message") or "文件重试索引任务已提交"}


@router.delete("/knowledge-files/{file_id}")
def delete_knowledge_file(request: Request, file_id: str):
    backend_cookies = _require_backend_cookies(request)
    response, payload = client.request_json("DELETE", f"/api/v1/knowledge-files/{file_id}", session_cookie=backend_cookies)
    if response.status_code >= 400 or payload.get("success") is False:
        raise HTTPException(status_code=response.status_code or 500, detail=payload.get("error") or payload.get("message") or "删除知识库文件失败")
    return {"success": True, "data": payload.get("data") or {"id": file_id}, "message": "删除知识库文件成功"}
