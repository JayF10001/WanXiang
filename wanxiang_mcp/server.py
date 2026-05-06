"""wanxiang_mcp server entrypoint placeholder."""

from __future__ import annotations

from typing import Any, Dict, List

from wanxiang_mcp.tools.chat_session import (
    get_chat_session_tool,
    invoke_chat_session_stream_tool,
    invoke_chat_session_tool,
    list_chat_session_tools,
)
from wanxiang_mcp.tools.report import (
    get_report_tool,
    invoke_report_tool,
    list_report_tools,
)


def list_tools() -> List[Dict[str, str]]:
    """List currently registered MCP tools."""
    return list_chat_session_tools() + list_report_tools()


def invoke_tool(name: str, payload: Dict[str, Any]) -> Dict[str, Any]:
    """Invoke a named MCP tool."""
    tool = get_chat_session_tool(name)
    if tool is not None:
        return invoke_chat_session_tool(name, payload)

    report_tool = get_report_tool(name)
    if report_tool is not None:
        return invoke_report_tool(name, payload)

    raise KeyError(f"Unknown MCP tool: {name}")


def invoke_stream_tool(name: str, payload: Dict[str, Any]):
    """Invoke a named streaming MCP tool."""
    tool = get_chat_session_tool(name)
    if tool is None:
        raise KeyError(f"Unknown MCP tool: {name}")
    return invoke_chat_session_stream_tool(name, payload)
