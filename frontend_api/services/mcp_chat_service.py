from __future__ import annotations

from typing import Any, Dict

from fastapi import HTTPException, Request
from requests import RequestException

from ..clients.mcp_client import mcp_client
from ..services.chatbackend_client import client


def get_backend_session(request: Request) -> dict:
    backend_session = request.session.get("chatbackend_cookies")
    if not backend_session:
        raise HTTPException(status_code=401, detail="请先登录")
    return backend_session


def get_current_user_context(request: Request) -> Dict[str, Any]:
    backend_session = get_backend_session(request)
    response, payload = client.request_json("GET", "/api/currentUser", session_cookie=backend_session)
    if response.status_code >= 400 or not payload.get("success"):
        raise HTTPException(status_code=response.status_code or 401, detail=payload.get("errorMessage") or payload.get("error") or "未登录")

    data = payload.get("data", {})
    return {
        "auth": {
            "user_id": str(data.get("userid") or ""),
            "username": str(data.get("name") or ""),
            "roles": ["user"],
        },
        "request": {
            "request_id": request.headers.get("x-request-id") or "frontend-api",
            "trace_id": request.headers.get("x-trace-id"),
            "source": "frontend_api",
        },
    }


def _raise_for_mcp_error(result: Dict[str, Any]) -> None:
    if not result.get("success"):
        error = result.get("error") or {}
        code = error.get("code")
        message = error.get("message") or "请求失败"
        status_code = {
            "invalid_input": 400,
            "unauthorized": 401,
            "forbidden": 403,
            "not_found": 404,
            "conflict": 409,
            "timeout": 504,
            "upstream_error": 502,
            "not_implemented": 501,
        }.get(code, 500)
        raise HTTPException(status_code=status_code, detail=message)


def invoke_mcp_tool(request: Request, tool_name: str, tool_input: Dict[str, Any]) -> Dict[str, Any]:
    try:
        context = get_current_user_context(request)
        payload = {
            "context": context,
            "input": tool_input,
        }
        result = mcp_client.invoke(tool_name, payload)
    except HTTPException:
        raise
    except RequestException as exc:
        raise HTTPException(status_code=502, detail=f"MCP 上游调用失败: {exc}") from exc
    except KeyError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"MCP 调用异常: {exc}") from exc

    _raise_for_mcp_error(result)
    return result


def invoke_chat_tool(request: Request, tool_name: str, tool_input: Dict[str, Any]) -> Dict[str, Any]:
    return invoke_mcp_tool(request, tool_name, tool_input)


def invoke_report_tool(request: Request, tool_name: str, tool_input: Dict[str, Any]) -> Dict[str, Any]:
    return invoke_mcp_tool(request, tool_name, tool_input)


def invoke_chat_stream_tool(request: Request, tool_name: str, tool_input: Dict[str, Any]):
    try:
        context = get_current_user_context(request)
        payload = {
            "context": context,
            "input": tool_input,
        }
        return mcp_client.invoke_stream(tool_name, payload)
    except HTTPException:
        raise
    except RequestException as exc:
        raise HTTPException(status_code=502, detail=f"MCP 上游调用失败: {exc}") from exc
    except KeyError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"MCP 流式调用异常: {exc}") from exc
