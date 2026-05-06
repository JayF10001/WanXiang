from __future__ import annotations

import base64
from io import BytesIO

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from ..services.mcp_chat_service import invoke_report_tool


router = APIRouter(prefix="/api/reports", tags=["reports"])


class GenerateReportRequest(BaseModel):
    sessionId: str


class ExportReportRequest(BaseModel):
    reportId: str | None = None
    sessionId: str | None = None


def adapt_report(item: dict) -> dict:
    report = item.get("report") or {}
    return {
        "reportId": str(report.get("report_id") or ""),
        "sessionId": str(report.get("session_id") or ""),
        "data": report.get("data") or {},
        "isFallback": bool(report.get("is_fallback")),
        "createdAt": report.get("created_at"),
        "warning": report.get("warning"),
    }


@router.post("/generate")
def generate_report(request: Request, body: GenerateReportRequest):
    result = invoke_report_tool(request, "report.generate_report", {"session_id": body.sessionId})
    return {
        "success": True,
        "data": adapt_report(result.get("data", {})),
        "message": "生成报告成功",
    }


@router.get("/{report_id}")
def get_report(report_id: str, request: Request):
    result = invoke_report_tool(request, "report.get_report", {"report_id": report_id})
    return {
        "success": True,
        "data": adapt_report(result.get("data", {})),
        "message": "获取报告成功",
    }


@router.post("/export-pdf")
def export_report_pdf(request: Request, body: ExportReportRequest):
    if not body.reportId and not body.sessionId:
        raise HTTPException(status_code=400, detail="缺少 reportId 或 sessionId")

    result = invoke_report_tool(
        request,
        "report.export_report_pdf",
        {
            "report_id": body.reportId,
            "session_id": body.sessionId,
        },
    )
    data = result.get("data") or {}
    content_base64 = str(data.get("content_base64") or "")
    if not content_base64:
        raise HTTPException(status_code=500, detail="导出内容为空")

    return StreamingResponse(
        BytesIO(base64.b64decode(content_base64)),
        media_type=str(data.get("content_type") or "application/octet-stream"),
        headers={
            "Content-Disposition": f"attachment; filename={data.get('filename') or 'report_export.bin'}",
        },
    )
