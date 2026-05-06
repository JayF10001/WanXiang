"""MCP tools for 5.4 report generation and export module."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Dict, Generic, List, Optional, Type, TypeVar

from pydantic import BaseModel

from wanxiang_mcp.adapters import chatbackend_report
from wanxiang_mcp.runtime.context import parse_context
from wanxiang_mcp.schemas.report import (
    ExportReportPdfInput,
    ReportRefInput,
    SessionReportInput,
)

InputModelT = TypeVar("InputModelT", bound=BaseModel)


@dataclass(frozen=True)
class MCPTool(Generic[InputModelT]):
    name: str
    description: str
    input_model: Type[InputModelT]
    handler: Callable[[Any, InputModelT], Any]

    def invoke(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        context = parse_context(payload.get("context") or {})
        input_data = self.input_model.model_validate(payload.get("input") or {})
        result = self.handler(context, input_data)
        if hasattr(result, "model_dump"):
            return result.model_dump(mode="json")
        return result


def _tool(
    name: str,
    description: str,
    input_model: Type[InputModelT],
    handler: Callable[[Any, InputModelT], Any],
) -> MCPTool[InputModelT]:
    return MCPTool(
        name=name,
        description=description,
        input_model=input_model,
        handler=handler,
    )


REPORT_TOOLS: List[MCPTool[Any]] = [
    _tool(
        "report.generate_report",
        "为指定会话生成正式报告。",
        SessionReportInput,
        chatbackend_report.generate_report,
    ),
    _tool(
        "report.get_latest_report_by_session",
        "按会话获取最近一份正式报告。",
        SessionReportInput,
        chatbackend_report.get_latest_report_by_session,
    ),
    _tool(
        "report.get_report",
        "获取指定报告详情。",
        ReportRefInput,
        chatbackend_report.get_report,
    ),
    _tool(
        "report.export_report_pdf",
        "导出指定报告为 PDF 文件，必要时回退 HTML。",
        ExportReportPdfInput,
        chatbackend_report.export_report_pdf,
    ),
]

REPORT_TOOL_MAP: Dict[str, MCPTool[Any]] = {
    tool.name: tool for tool in REPORT_TOOLS
}


def list_report_tools() -> List[Dict[str, str]]:
    return [
        {
            "name": tool.name,
            "description": tool.description,
            "input_model": tool.input_model.__name__,
        }
        for tool in REPORT_TOOLS
    ]


def get_report_tool(name: str) -> Optional[MCPTool[Any]]:
    return REPORT_TOOL_MAP.get(name)


def invoke_report_tool(name: str, payload: Dict[str, Any]) -> Dict[str, Any]:
    tool = get_report_tool(name)
    if not tool:
        raise KeyError(f"Unknown MCP tool: {name}")
    return tool.invoke(payload)
