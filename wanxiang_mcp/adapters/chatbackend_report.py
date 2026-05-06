"""Adapters from MCP report tools to ChatBackend report services."""

from __future__ import annotations

import base64
import os
import shutil
import sys
import tempfile
import time
from datetime import datetime
from typing import Any, Optional

CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
WANXIANG_MCP_ROOT = os.path.dirname(CURRENT_DIR)
REPO_ROOT = os.path.dirname(WANXIANG_MCP_ROOT)
CHATBACKEND_ROOT = os.path.join(REPO_ROOT, "ChatBackend")

for path in (REPO_ROOT, CHATBACKEND_ROOT):
    if path not in sys.path:
        sys.path.insert(0, path)

from ChatBackend.app import create_app
from ChatBackend.app.api.report import generate_html_report, generate_pillow_pdf_report
from ChatBackend.app.services.chat_service import ChatService
from ChatBackend.app.services.report_service import ReportService, get_db
from wanxiang_mcp.schemas.chat import MCPContext, MCPError, MCPMeta, MCPResponse
from wanxiang_mcp.schemas.report import (
    ExportReportPdfData,
    ExportReportPdfInput,
    GenerateReportData,
    GetReportData,
    GetLatestSessionReportData,
    ReportDocument,
    ReportRefInput,
    SessionReportInput,
)


_APP = None


def get_flask_app():
    global _APP
    if _APP is None:
        _APP = create_app()
    return _APP


def _build_meta(context: MCPContext, started_at: float) -> MCPMeta:
    return MCPMeta(
        request_id=context.request.request_id,
        trace_id=context.request.trace_id,
        duration_ms=int((time.time() - started_at) * 1000),
    )


def _ok(context: MCPContext, started_at: float, data: Any) -> MCPResponse[Any]:
    return MCPResponse(success=True, data=data, error=None, meta=_build_meta(context, started_at))


def _err(context: MCPContext, started_at: float, code: str, message: str) -> MCPResponse[Any]:
    return MCPResponse(
        success=False,
        data=None,
        error=MCPError(code=code, message=message),
        meta=_build_meta(context, started_at),
    )


def _to_iso(value: Any) -> Optional[str]:
    if value is None:
        return None
    if isinstance(value, str):
        return value
    if isinstance(value, datetime):
        return value.isoformat()
    return str(value)


def _get_owned_session_or_error(context: MCPContext, session_id: str):
    session = ChatService.get_chat_session(session_id)
    if not session:
        return None, "not_found", "聊天会话不存在"
    if str(session.get("user_id")) != context.auth.user_id:
        return None, "forbidden", "无权访问此聊天会话"
    return session, None, None


def _get_owned_report_or_error(context: MCPContext, report_id: str):
    db = get_db()
    report = db.reports.find_one({"report_id": report_id})
    if not report:
        return None, None, "not_found", "报告不存在"

    session_id = str(report.get("session_id") or "")
    session, code, message = _get_owned_session_or_error(context, session_id)
    if not session:
        return None, None, code, message
    return report, session, None, None


def _to_report_document(report: dict, warning: Optional[str] = None) -> ReportDocument:
    return ReportDocument(
        report_id=str(report.get("report_id") or report.get("id") or ""),
        session_id=str(report.get("session_id") or ""),
        data=report.get("data") or {},
        is_fallback=bool(report.get("is_fallback")),
        created_at=_to_iso(report.get("created_at")),
        warning=warning,
    )


def generate_report(
    context: MCPContext,
    input_data: SessionReportInput,
) -> MCPResponse[GenerateReportData]:
    started_at = time.time()
    app = get_flask_app()
    with app.app_context():
        session, code, message = _get_owned_session_or_error(context, input_data.session_id)
        if not session:
            return _err(context, started_at, code, message)

        result, status_code = ReportService.generate_report(input_data.session_id)
        if status_code >= 400 or not result.get("success"):
            return _err(
                context,
                started_at,
                "upstream_error" if status_code >= 500 else "invalid_input",
                result.get("error") or "生成报告失败",
            )

        db = get_db()
        report_id = str(result.get("report_id") or "")
        report = db.reports.find_one({"report_id": report_id}) if report_id else None
        if report is None:
            report = {
                "report_id": report_id,
                "session_id": input_data.session_id,
                "data": result.get("data") or {},
                "is_fallback": bool(result.get("warning")),
                "created_at": time.time(),
            }
        return _ok(
            context,
            started_at,
            GenerateReportData(
                report=_to_report_document(report, warning=result.get("warning")),
            ),
        )


def get_report(context: MCPContext, input_data: ReportRefInput) -> MCPResponse[GetReportData]:
    started_at = time.time()
    app = get_flask_app()
    with app.app_context():
        report, _session, code, message = _get_owned_report_or_error(context, input_data.report_id)
        if not report:
            return _err(context, started_at, code, message)
        return _ok(context, started_at, GetReportData(report=_to_report_document(report)))


def get_latest_report_by_session(
    context: MCPContext,
    input_data: SessionReportInput,
) -> MCPResponse[GetLatestSessionReportData]:
    started_at = time.time()
    app = get_flask_app()
    with app.app_context():
        session, code, message = _get_owned_session_or_error(context, input_data.session_id)
        if not session:
            return _err(context, started_at, code, message)

        result, status_code = ReportService.get_latest_report_by_session(input_data.session_id)
        if status_code >= 400 or not result.get("success"):
            return _err(
                context,
                started_at,
                "not_found" if status_code == 404 else "upstream_error",
                result.get("error") or "获取会话最新报告失败",
            )

        report = {
            "report_id": str(result.get("report_id") or ""),
            "session_id": input_data.session_id,
            "data": result.get("data") or {},
            "is_fallback": bool(result.get("is_fallback")),
            "created_at": result.get("created_at"),
        }
        return _ok(
            context,
            started_at,
            GetLatestSessionReportData(report=_to_report_document(report)),
        )


def export_report_pdf(
    context: MCPContext,
    input_data: ExportReportPdfInput,
) -> MCPResponse[ExportReportPdfData]:
    started_at = time.time()
    app = get_flask_app()
    with app.app_context():
        report = None
        report_id = input_data.report_id

        if report_id:
            report, _session, code, message = _get_owned_report_or_error(context, report_id)
            if not report:
                return _err(context, started_at, code, message)
        elif input_data.session_id:
            session, code, message = _get_owned_session_or_error(context, input_data.session_id)
            if not session:
                return _err(context, started_at, code, message)
            db = get_db()
            report = db.reports.find_one({"session_id": input_data.session_id}, sort=[("created_at", -1)])
            if not report:
                return _err(context, started_at, "not_found", "会话暂无可导出的报告")
            report_id = str(report.get("report_id") or "")
        else:
            return _err(context, started_at, "invalid_input", "缺少 report_id 或 session_id")

        report_data = report.get("data") or {}
        html_path = None
        pdf_path = None
        try:
            with tempfile.NamedTemporaryFile(suffix=".html", delete=False) as html_file:
                html_path = html_file.name
                html_content = generate_html_report(report_data)
                html_file.write(html_content.encode("utf-8"))

            pdf_path = html_path.replace(".html", ".pdf")
            content_type = "application/pdf"
            filename = f"report_{report_id or 'export'}.pdf"

            try:
                wkhtmltopdf_path = shutil.which("wkhtmltopdf")
                if not wkhtmltopdf_path:
                    raise RuntimeError("wkhtmltopdf unavailable")
                import pdfkit

                pdfkit.from_file(
                    html_path,
                    pdf_path,
                    configuration=pdfkit.configuration(wkhtmltopdf=wkhtmltopdf_path),
                )
            except Exception:
                generate_pillow_pdf_report(report_data, pdf_path)

            if os.path.exists(pdf_path):
                with open(pdf_path, "rb") as file:
                    content_base64 = base64.b64encode(file.read()).decode("ascii")
                return _ok(
                    context,
                    started_at,
                    ExportReportPdfData(
                        report_id=report_id,
                        filename=filename,
                        content_type="application/pdf",
                        content_base64=content_base64,
                    ),
                )

            content_type = "text/html"
            filename = f"report_{report_id or 'export'}.html"
            content_base64 = base64.b64encode(html_content.encode("utf-8")).decode("ascii")
            return _ok(
                context,
                started_at,
                ExportReportPdfData(
                    report_id=report_id,
                    filename=filename,
                    content_type=content_type,
                    content_base64=content_base64,
                ),
            )
        except Exception as exc:
            return _err(context, started_at, "internal_error", f"导出报告失败: {exc}")
        finally:
            for path in (html_path, pdf_path):
                try:
                    if path and os.path.exists(path):
                        os.remove(path)
                except Exception:
                    pass
