from __future__ import annotations

from .frontend_api_client import frontend_api_client
from .session_mapping_service import session_mapping_service
from ..config import settings
from ..utils.text_format import truncate_text


class QQReportService:
    def generate_report(self, *, qq_user_id: str | None) -> str:
        session_id = session_mapping_service.get_session_id(qq_user_id=qq_user_id)
        if not session_id:
            return "当前还没有可用于生成报告的分析会话。请先发送问题或先执行一次深度分析。"

        data = frontend_api_client.generate_report(session_id=session_id)
        report_id = str(data.get("reportId") or "")
        report_content = data.get("data") or {}

        summary = ""
        if isinstance(report_content, dict):
            summary = str(
                report_content.get("summary")
                or report_content.get("overview")
                or report_content.get("brief")
                or ""
            ).strip()

        summary = truncate_text(summary, settings.report_summary_max_chars)
        lines = ["报告已生成。"]
        if report_id:
            lines.append(f"报告ID：{report_id}")
        if summary:
            lines.append(f"摘要：{summary}")
        lines.append("如需更完整内容，可在网页端查看正式报告与导出 PDF。")
        return truncate_text("\n".join(lines), settings.reply_max_chars)


qq_report_service = QQReportService()
