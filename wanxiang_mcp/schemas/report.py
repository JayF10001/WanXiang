"""Report MCP schemas."""

from __future__ import annotations

from typing import Any, Dict, Literal, Optional

from pydantic import BaseModel

from wanxiang_mcp.schemas.chat import MCPContext, MCPError, MCPMeta, MCPResponse


class SessionReportInput(BaseModel):
    session_id: str


class ReportRefInput(BaseModel):
    report_id: str


class ReportDocument(BaseModel):
    report_id: str
    session_id: str
    data: Dict[str, Any]
    is_fallback: bool = False
    created_at: Optional[str] = None
    warning: Optional[str] = None


class GenerateReportData(BaseModel):
    report: ReportDocument


class GetReportData(BaseModel):
    report: ReportDocument


class GetLatestSessionReportData(BaseModel):
    report: ReportDocument


class ExportReportPdfInput(BaseModel):
    report_id: Optional[str] = None
    session_id: Optional[str] = None


class ExportReportPdfData(BaseModel):
    report_id: Optional[str] = None
    filename: str
    content_type: Literal["application/pdf", "text/html"]
    content_base64: str
