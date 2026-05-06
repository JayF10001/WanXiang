"""调试路由：无需登录即可测试 MCP 工具。"""

from __future__ import annotations

from typing import Any, Dict, List, Optional
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from ..clients.mcp_client import mcp_client

router = APIRouter(prefix="/debug", tags=["debug"])


class ToolInvokeRequest(BaseModel):
    tool_name: str
    input_data: Dict[str, Any] = {}
    user_id: str = "debug_user"
    username: str = "debug"
    trace_id: Optional[str] = None


@router.get("/tools")
def list_debug_tools() -> Dict[str, Any]:
    """列出所有可用的 MCP 工具（无需登录）。"""
    tools = mcp_client.list_tools()
    return {
        "success": True,
        "data": {
            "tools": tools,
            "count": len(tools),
        },
    }


@router.post("/tools/invoke")
def invoke_debug_tool(req: ToolInvokeRequest) -> Dict[str, Any]:
    """手动调用指定 MCP 工具（无需登录，使用调试上下文）。"""
    payload = {
        "context": {
            "auth": {
                "user_id": req.user_id,
                "username": req.username,
                "roles": ["debug"],
            },
            "request": {
                "request_id": f"debug-{req.tool_name}",
                "trace_id": req.trace_id,
                "source": "debug_api",
            },
        },
        "input": req.input_data,
    }

    try:
        result = mcp_client.invoke(req.tool_name, payload)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=f"未知工具: {exc}")
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"工具执行失败: {exc}")

    return result


@router.get("/templates/{template_name}")
def get_template_info(template_name: str) -> Dict[str, Any]:
    """查看指定聚合模板的详细信息（无需登录）。"""
    from wanxiang_mcp.utils.db_aggregate_templates import TEMPLATES

    template = TEMPLATES.get(template_name)
    if not template:
        available = list(TEMPLATES.keys())
        raise HTTPException(
            status_code=404,
            detail=f"未知模板: {template_name}，可用: {available}",
        )

    return {
        "success": True,
        "data": {
            "name": template_name,
            "description": template["description"],
            "collection": template["collection"],
            "pipeline": template["pipeline_template"],
        },
    }


@router.get("/templates")
def list_templates() -> Dict[str, Any]:
    """列出所有可用的数据库聚合模板。"""
    from wanxiang_mcp.utils.db_aggregate_templates import TEMPLATES

    templates = [
        {
            "name": name,
            "description": tpl["description"],
            "collection": tpl["collection"],
        }
        for name, tpl in TEMPLATES.items()
    ]
    return {
        "success": True,
        "data": {
            "templates": templates,
            "count": len(templates),
        },
    }
