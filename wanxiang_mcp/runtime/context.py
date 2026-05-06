"""Request context helpers for wanxiang_mcp runtime."""

from __future__ import annotations

from typing import Any, Dict

from wanxiang_mcp.schemas.chat import MCPContext


def parse_context(value: Dict[str, Any] | MCPContext) -> MCPContext:
    """Normalize raw dict input into MCPContext."""
    if isinstance(value, MCPContext):
        return value
    return MCPContext.model_validate(value)
