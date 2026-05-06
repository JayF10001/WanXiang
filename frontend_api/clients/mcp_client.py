from __future__ import annotations

from typing import Any, Dict, List

from wanxiang_mcp.server import invoke_stream_tool, invoke_tool, list_tools


class MCPClient:
    def list_tools(self) -> List[Dict[str, str]]:
        return list_tools()

    def invoke(self, name: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        return invoke_tool(name, payload)

    def invoke_stream(self, name: str, payload: Dict[str, Any]):
        return invoke_stream_tool(name, payload)


mcp_client = MCPClient()
