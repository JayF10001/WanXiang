from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request

from ..schemas.auth import LoginRequest, RegisterRequest
from ..services.chatbackend_client import client


router = APIRouter(prefix="/api/auth", tags=["auth"])


def adapt_user_from_login_payload(payload):
    user = payload.get("user") or payload.get("data") or {}
    return {
        "id": str(user.get("id") or user.get("userid") or ""),
        "name": str(user.get("name") or user.get("username") or ""),
        "email": str(user.get("email") or ""),
        "role": str(user.get("role") or "user"),
        "avatar": user.get("avatar")
        or "https://gw.alipayobjects.com/zos/antfincdn/XAosXuNZyF/BiazfanxmamNRoxxVxka.png",
    }


@router.post("/login")
def login(request: Request, body: LoginRequest):
    response, payload = client.request_json("POST", "/api/login/account", json_data=body.model_dump())
    if response.status_code >= 400 or payload.get("status") == "error":
        raise HTTPException(status_code=response.status_code or 401, detail=payload.get("message") or payload.get("error") or "登录失败")

    backend_cookies = client.extract_session_cookies(response)
    if backend_cookies:
        request.session["chatbackend_cookies"] = backend_cookies

    return {"success": True, "data": adapt_user_from_login_payload(payload), "message": "登录成功"}


@router.post("/register")
def register(request: Request, body: RegisterRequest):
    response, payload = client.request_json("POST", "/api/register", json_data=body.model_dump())
    if response.status_code >= 400 or payload.get("status") == "error" or payload.get("success") is False:
        raise HTTPException(status_code=response.status_code or 400, detail=payload.get("message") or payload.get("error") or "注册失败")

    backend_cookies = client.extract_session_cookies(response)
    if backend_cookies:
        request.session["chatbackend_cookies"] = backend_cookies

    return {"success": True, "data": adapt_user_from_login_payload(payload), "message": "注册成功"}


@router.get("/current-user")
def current_user(request: Request):
    backend_cookies = request.session.get("chatbackend_cookies")
    if not backend_cookies:
        raise HTTPException(status_code=401, detail="未登录")

    response, payload = client.request_json("GET", "/api/currentUser", session_cookie=backend_cookies)
    if response.status_code >= 400 or not payload.get("success"):
        raise HTTPException(status_code=response.status_code or 401, detail=payload.get("errorMessage") or payload.get("error") or "未登录")

    data = payload.get("data", {})
    return {
        "success": True,
        "data": {
            "id": str(data.get("userid") or ""),
            "name": str(data.get("name") or ""),
            "email": str(data.get("email") or ""),
            "role": "user",
            "avatar": data.get("avatar"),
        },
        "message": "获取当前用户成功",
    }


@router.post("/logout")
def logout(request: Request):
    backend_cookies = request.session.get("chatbackend_cookies")
    if backend_cookies:
        client.request_json("POST", "/api/login/outLogin", session_cookie=backend_cookies)
    request.session.pop("chatbackend_cookies", None)
    return {"success": True, "data": {}, "message": "退出成功"}
