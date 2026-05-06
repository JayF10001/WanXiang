from __future__ import annotations

from flask import Blueprint, current_app, jsonify, request
from flask_login import current_user, login_required

from ..services.rag_bridge_service import RagBridgeService


rag_api = Blueprint("rag_api", __name__)


@rag_api.route("/rag/answer", methods=["POST"])
@login_required
def rag_answer():
    try:
        payload = request.get_json(silent=True) or {}
        query = str(payload.get("query") or "").strip()
        if not query:
            return jsonify({"success": False, "error": "query 不能为空"}), 400

        result = RagBridgeService.answer_with_rag(
            query=query,
            kb_id=str(payload.get("kbId") or "").strip() or None,
            user_id=current_user.get_id(),
            source_url=str(payload.get("sourceUrl") or ""),
            platform_hint=str(payload.get("platformHint") or ""),
            session_id=str(payload.get("sessionId") or ""),
        )
        return jsonify({"success": True, "data": result})
    except Exception as exc:
        current_app.logger.error(f"RAG answer 失败: {exc}")
        return jsonify({"success": False, "error": str(exc)}), 500
