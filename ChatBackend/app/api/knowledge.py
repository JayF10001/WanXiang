from __future__ import annotations

from flask import Blueprint, current_app, jsonify, request
from flask_login import current_user, login_required

from ..services.knowledge_service import KnowledgeService


knowledge_api = Blueprint("knowledge_api", __name__)


@knowledge_api.route("/knowledge-bases", methods=["GET"])
@login_required
def list_knowledge_bases():
    try:
        items = KnowledgeService.list_knowledge_bases(current_user.get_id())
        return jsonify({"success": True, "data": items})
    except Exception as exc:
        current_app.logger.error(f"获取知识库列表失败: {exc}")
        return jsonify({"success": False, "error": str(exc)}), 500


@knowledge_api.route("/knowledge-bases", methods=["POST"])
@login_required
def create_knowledge_base():
    try:
        payload = request.get_json(silent=True) or {}
        name = str(payload.get("name") or "").strip()
        if not name:
            return jsonify({"success": False, "error": "知识库名称不能为空"}), 400

        kb = KnowledgeService.create_knowledge_base(
            current_user.get_id(),
            name,
            description=str(payload.get("description") or ""),
        )
        return jsonify({"success": True, "data": kb})
    except Exception as exc:
        current_app.logger.error(f"创建知识库失败: {exc}")
        return jsonify({"success": False, "error": str(exc)}), 500


@knowledge_api.route("/knowledge-bases/<kb_id>/files", methods=["GET"])
@login_required
def list_knowledge_files(kb_id: str):
    try:
        items = KnowledgeService.list_files(kb_id, current_user.get_id())
        return jsonify({"success": True, "data": items})
    except ValueError as exc:
        return jsonify({"success": False, "error": str(exc)}), 404
    except Exception as exc:
        current_app.logger.error(f"获取知识库文件列表失败: {exc}")
        return jsonify({"success": False, "error": str(exc)}), 500


@knowledge_api.route("/knowledge-bases/<kb_id>/rebuild-index", methods=["POST"])
@login_required
def rebuild_knowledge_base_index(kb_id: str):
    try:
        result = KnowledgeService.rebuild_index(kb_id, current_user.get_id())
        return jsonify({"success": True, "data": result, "message": "知识库批量重建索引任务已提交"})
    except ValueError as exc:
        return jsonify({"success": False, "error": str(exc)}), 400
    except Exception as exc:
        current_app.logger.error(f"批量重建知识库索引失败: {exc}")
        return jsonify({"success": False, "error": str(exc)}), 500


@knowledge_api.route("/knowledge-bases/<kb_id>/files", methods=["POST"])
@login_required
def upload_knowledge_file(kb_id: str):
    try:
        upload = request.files.get("file")
        if not upload:
            return jsonify({"success": False, "error": "请选择要上传的文件"}), 400

        item = KnowledgeService.upload_file(
            kb_id,
            current_user.get_id(),
            upload,
            remark=str(request.form.get("remark") or ""),
            raw_tags=request.form.get("tags"),
        )
        return jsonify({"success": True, "data": item})
    except ValueError as exc:
        return jsonify({"success": False, "error": str(exc)}), 400
    except Exception as exc:
        current_app.logger.error(f"上传知识库文件失败: {exc}")
        return jsonify({"success": False, "error": str(exc)}), 500


@knowledge_api.route("/knowledge-files/<file_id>", methods=["GET"])
@login_required
def get_knowledge_file(file_id: str):
    try:
        item = KnowledgeService.get_file(file_id, current_user.get_id())
        if not item:
            return jsonify({"success": False, "error": "文件不存在"}), 404
        return jsonify({"success": True, "data": item})
    except Exception as exc:
        current_app.logger.error(f"获取知识库文件详情失败: {exc}")
        return jsonify({"success": False, "error": str(exc)}), 500


@knowledge_api.route("/knowledge-files/<file_id>/retry-parse", methods=["POST"])
@login_required
def retry_knowledge_file_parse(file_id: str):
    try:
        item = KnowledgeService.retry_parse(file_id, current_user.get_id())
        return jsonify({"success": True, "data": item, "message": "文件重新解析任务已提交"})
    except ValueError as exc:
        return jsonify({"success": False, "error": str(exc)}), 400
    except Exception as exc:
        current_app.logger.error(f"重新解析知识库文件失败: {exc}")
        return jsonify({"success": False, "error": str(exc)}), 500


@knowledge_api.route("/knowledge-files/<file_id>/retry-index", methods=["POST"])
@login_required
def retry_knowledge_file_index(file_id: str):
    try:
        item = KnowledgeService.retry_index(file_id, current_user.get_id())
        return jsonify({"success": True, "data": item, "message": "文件重试索引任务已提交"})
    except ValueError as exc:
        return jsonify({"success": False, "error": str(exc)}), 400
    except Exception as exc:
        current_app.logger.error(f"重试知识库文件索引失败: {exc}")
        return jsonify({"success": False, "error": str(exc)}), 500


@knowledge_api.route("/knowledge-files/<file_id>", methods=["DELETE"])
@login_required
def delete_knowledge_file(file_id: str):
    try:
        deleted = KnowledgeService.delete_file(file_id, current_user.get_id())
        if not deleted:
            return jsonify({"success": False, "error": "文件不存在"}), 404
        return jsonify({"success": True, "data": {"id": file_id}})
    except Exception as exc:
        current_app.logger.error(f"删除知识库文件失败: {exc}")
        return jsonify({"success": False, "error": str(exc)}), 500
