from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from hashlib import sha256
from pathlib import Path
from typing import Any
import csv
import io
import json
import threading
import time

from bson import ObjectId
from flask import current_app
from werkzeug.datastructures import FileStorage
from werkzeug.utils import secure_filename

from ..extensions import db
from .knowledge_index_service import KnowledgeIndexService


@dataclass(frozen=True)
class KnowledgeFileValidation:
    allowed_extensions: tuple[str, ...] = ("pdf", "docx", "txt", "md", "html", "json", "csv")
    max_size_bytes: int = 20 * 1024 * 1024


class KnowledgeService:
    validation = KnowledgeFileValidation()

    @staticmethod
    def _now() -> datetime:
        return datetime.utcnow()

    @staticmethod
    def _to_object_id(value: str) -> ObjectId | str:
        if db.is_in_memory:
            return value
        return ObjectId(value)

    @staticmethod
    def _project_root() -> Path:
        return Path(current_app.root_path).resolve().parents[1]

    @classmethod
    def _storage_root(cls) -> Path:
        root = cls._project_root() / "storage" / "knowledge"
        root.mkdir(parents=True, exist_ok=True)
        return root

    @classmethod
    def _absolute_storage_path(cls, storage_path: str) -> Path:
        return cls._storage_root() / storage_path

    @staticmethod
    def _format_dt(value: Any) -> str:
        if isinstance(value, datetime):
            return value.isoformat()
        return str(value or "")

    @staticmethod
    def _parse_tags(raw_tags: str | None) -> list[str]:
        if not raw_tags:
            return []
        try:
            parsed = json.loads(raw_tags)
            if isinstance(parsed, list):
                return [str(item).strip() for item in parsed if str(item).strip()]
        except Exception:
            pass
        return [item.strip() for item in str(raw_tags).split(",") if item.strip()]

    @staticmethod
    def _safe_decode(payload: bytes) -> str:
        for encoding in ("utf-8", "utf-8-sig", "gbk", "gb2312"):
            try:
                return payload.decode(encoding)
            except Exception:
                continue
        return payload.decode("utf-8", errors="ignore")

    @classmethod
    def _build_parse_summary(cls, filename: str, content_type: str, payload: bytes) -> dict[str, Any]:
        extension = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
        summary: dict[str, Any] = {
            "fileType": extension or "unknown",
            "contentType": content_type or "application/octet-stream",
            "extractMode": "metadata_only",
            "charCount": 0,
            "lineCount": 0,
            "preview": "",
        }

        if extension in {"txt", "md", "html", "json", "csv"}:
            text = cls._safe_decode(payload)
            summary["extractMode"] = "light_text"
            summary["charCount"] = len(text)
            summary["lineCount"] = len([line for line in text.splitlines() if line.strip()]) or (1 if text else 0)
            if extension == "csv":
                try:
                    rows = list(csv.reader(io.StringIO(text)))
                    summary["rowCount"] = max(len(rows) - 1, 0)
                    summary["columnCount"] = len(rows[0]) if rows else 0
                except Exception:
                    summary["rowCount"] = 0
                    summary["columnCount"] = 0
            summary["preview"] = text.strip().replace("\n", " ")[:180]
        elif extension in {"pdf", "docx"}:
            summary["extractMode"] = "binary_deferred"
            summary["preview"] = "当前仅完成原始文件保存，正文抽取将在后续解析链路中接入。"

        return summary

    @classmethod
    def _update_parse_state(
        cls,
        file_id: str,
        *,
        parse_status: str,
        parse_error: str | None = None,
        parse_summary: dict[str, Any] | None = None,
    ) -> None:
        document = db.knowledge_files.find_one({"_id": cls._to_object_id(file_id)})
        if not document:
            return

        metadata = dict(document.get("metadata") or {})
        if parse_summary is not None:
            metadata["parseSummary"] = parse_summary

        db.knowledge_files.update_one(
            {"_id": document.get("_id")},
            {
                "$set": {
                    "parse_status": parse_status,
                    "parse_error": parse_error,
                    "updated_at": cls._now(),
                    "metadata": metadata,
                }
            },
        )

    @classmethod
    def _backfill_parse_summary_if_missing(cls, document: dict[str, Any]) -> dict[str, Any]:
        metadata = dict(document.get("metadata") or {})
        if metadata.get("parseSummary"):
            return document
        if str(document.get("parse_status") or "") != "ready":
            return document

        storage_path = str(document.get("storage_path") or "")
        if not storage_path:
            return document

        absolute_path = cls._absolute_storage_path(storage_path)
        if not absolute_path.exists():
            return document

        try:
            payload = absolute_path.read_bytes()
            summary = cls._build_parse_summary(
                str(document.get("original_filename") or ""),
                str(document.get("content_type") or ""),
                payload,
            )
            metadata["parseSummary"] = summary
            updated_at = cls._now()
            db.knowledge_files.update_one(
                {"_id": document.get("_id")},
                {"$set": {"metadata": metadata, "updated_at": updated_at}},
            )
            document["metadata"] = metadata
            document["updated_at"] = updated_at
        except Exception as exc:
            current_app.logger.warning(f"知识库文件摘要回填失败 {document.get('_id')}: {exc}")
        return document

    @classmethod
    def _process_file_parse(cls, app: Any, file_id: str) -> None:
        with app.app_context():
            try:
                cls._update_parse_state(file_id, parse_status="processing", parse_error=None)
                time.sleep(0.6)

                document = db.knowledge_files.find_one({"_id": cls._to_object_id(file_id)})
                if not document:
                    return

                storage_path = str(document.get("storage_path") or "")
                absolute_path = cls._absolute_storage_path(storage_path)
                if not absolute_path.exists():
                    raise FileNotFoundError("原始文件不存在，无法继续解析")

                payload = absolute_path.read_bytes()
                summary = cls._build_parse_summary(
                    str(document.get("original_filename") or ""),
                    str(document.get("content_type") or ""),
                    payload,
                )
                cls._update_parse_state(file_id, parse_status="ready", parse_error=None, parse_summary=summary)
                try:
                    KnowledgeIndexService.index_file(file_id)
                except Exception as index_exc:
                    current_app.logger.error(f"知识库文件索引失败 {file_id}: {index_exc}")
                    db.knowledge_files.update_one(
                        {"_id": cls._to_object_id(file_id)},
                        {
                            "$set": {
                                "index_status": "failed",
                                "index_error": str(index_exc),
                                "chunk_count": 0,
                                "structured_record_count": 0,
                                "updated_at": cls._now(),
                            }
                        },
                    )
            except Exception as exc:
                current_app.logger.error(f"知识库文件解析失败 {file_id}: {exc}")
                cls._update_parse_state(file_id, parse_status="failed", parse_error=str(exc))
                db.knowledge_files.update_one(
                    {"_id": cls._to_object_id(file_id)},
                    {
                        "$set": {
                            "index_status": "failed",
                            "index_error": "文件解析失败，未进入索引阶段",
                            "chunk_count": 0,
                            "structured_record_count": 0,
                            "updated_at": cls._now(),
                        }
                    },
                )

    @classmethod
    def _process_file_index(cls, app: Any, file_id: str) -> None:
        with app.app_context():
            try:
                KnowledgeIndexService.index_file(file_id)
            except Exception as exc:
                current_app.logger.error(f"知识库文件索引失败 {file_id}: {exc}")
                db.knowledge_files.update_one(
                    {"_id": cls._to_object_id(file_id)},
                    {
                        "$set": {
                            "index_status": "failed",
                            "index_error": str(exc),
                            "chunk_count": 0,
                            "structured_record_count": 0,
                            "updated_at": cls._now(),
                        }
                    },
                )

    @classmethod
    def enqueue_parse(cls, file_id: str) -> None:
        app = current_app._get_current_object()
        worker = threading.Thread(
            target=cls._process_file_parse,
            args=(app, file_id),
            daemon=True,
            name=f"knowledge-parse-{file_id}",
        )
        worker.start()

    @classmethod
    def enqueue_index(cls, file_id: str) -> None:
        app = current_app._get_current_object()
        worker = threading.Thread(
            target=cls._process_file_index,
            args=(app, file_id),
            daemon=True,
            name=f"knowledge-index-{file_id}",
        )
        worker.start()

    @classmethod
    def _ensure_index_state_if_missing(cls, document: dict[str, Any]) -> dict[str, Any]:
        if not document:
            return document
        if str(document.get("parse_status") or "") != "ready":
            return document
        if str(document.get("index_status") or "") in {"ready", "processing", "failed"}:
            return document

        file_id = str(document.get("_id") or "")
        if not file_id:
            return document

        db.knowledge_files.update_one(
            {"_id": document.get("_id")},
            {
                "$set": {
                    "index_status": "processing",
                    "index_error": None,
                    "updated_at": cls._now(),
                }
            },
        )
        document["index_status"] = "processing"
        document["index_error"] = None
        cls.enqueue_index(file_id)
        return document

    @classmethod
    def _serialize_kb(cls, doc: dict[str, Any]) -> dict[str, Any]:
        return {
            "id": str(doc.get("_id")),
            "name": str(doc.get("name") or ""),
            "description": str(doc.get("description") or ""),
            "scope": str(doc.get("scope") or "private"),
            "ownerUserId": str(doc.get("owner_user_id") or ""),
            "createdAt": cls._format_dt(doc.get("created_at")),
            "updatedAt": cls._format_dt(doc.get("updated_at")),
        }

    @classmethod
    def _serialize_file(cls, doc: dict[str, Any]) -> dict[str, Any]:
        metadata = doc.get("metadata") or {}
        parse_summary = metadata.get("parseSummary") or {}
        return {
            "id": str(doc.get("_id")),
            "kbId": str(doc.get("kb_id") or ""),
            "ownerUserId": str(doc.get("owner_user_id") or ""),
            "originalFilename": str(doc.get("original_filename") or ""),
            "filename": str(doc.get("filename") or ""),
            "contentType": str(doc.get("content_type") or ""),
            "size": int(doc.get("size") or 0),
            "storagePath": str(doc.get("storage_path") or ""),
            "sha256": str(doc.get("sha256") or ""),
            "status": str(doc.get("status") or "uploaded"),
            "parseStatus": str(doc.get("parse_status") or "pending"),
            "parseError": doc.get("parse_error"),
            "indexStatus": str(doc.get("index_status") or "pending"),
            "indexError": doc.get("index_error"),
            "chunkCount": int(doc.get("chunk_count") or 0),
            "structuredRecordCount": int(doc.get("structured_record_count") or 0),
            "indexedAt": cls._format_dt(doc.get("indexed_at")),
            "parserVersion": str(doc.get("parser_version") or ""),
            "splitterVersion": str(doc.get("splitter_version") or ""),
            "embeddingVersion": str(doc.get("embedding_version") or ""),
            "structuredParserVersion": str(doc.get("structured_parser_version") or ""),
            "parseSummary": parse_summary,
            "uploadSource": str(doc.get("upload_source") or "frontend_new"),
            "remark": str(metadata.get("remark") or ""),
            "tags": metadata.get("tags") or [],
            "createdAt": cls._format_dt(doc.get("created_at")),
            "updatedAt": cls._format_dt(doc.get("updated_at")),
        }

    @classmethod
    def create_knowledge_base(cls, user_id: str, name: str, description: str = "", scope: str = "private") -> dict[str, Any]:
        now = cls._now()
        document = {
            "name": name.strip(),
            "description": description.strip(),
            "scope": scope or "private",
            "owner_user_id": str(user_id),
            "created_at": now,
            "updated_at": now,
        }
        result = db.knowledge_bases.insert_one(document)
        document["_id"] = result.inserted_id
        return cls._serialize_kb(document)

    @classmethod
    def list_knowledge_bases(cls, user_id: str) -> list[dict[str, Any]]:
        items = list(db.knowledge_bases.find({"owner_user_id": str(user_id)}))
        items.sort(key=lambda item: item.get("updated_at") or datetime.min, reverse=True)
        return [cls._serialize_kb(item) for item in items]

    @classmethod
    def upload_file(
        cls,
        kb_id: str,
        user_id: str,
        upload: FileStorage,
        *,
        remark: str = "",
        raw_tags: str | None = None,
        upload_source: str = "frontend_new",
    ) -> dict[str, Any]:
        kb = db.knowledge_bases.find_one({
            "_id": cls._to_object_id(kb_id),
            "owner_user_id": str(user_id),
        })
        if not kb:
            raise ValueError("知识库不存在或无权访问")

        original_filename = str(upload.filename or "").strip()
        if not original_filename:
            raise ValueError("请选择要上传的文件")

        extension = original_filename.rsplit(".", 1)[-1].lower() if "." in original_filename else ""
        if extension not in cls.validation.allowed_extensions:
            raise ValueError(f"暂不支持该文件类型：.{extension or 'unknown'}")

        payload = upload.read()
        if not payload:
            raise ValueError("文件内容为空")
        if len(payload) > cls.validation.max_size_bytes:
            raise ValueError("文件大小不能超过 20MB")

        file_id = ObjectId() if not db.is_in_memory else f"kf_{int(datetime.utcnow().timestamp() * 1000)}"
        safe_name = secure_filename(original_filename) or f"source.{extension}"
        stored_filename = f"source.{extension}" if extension else "source"
        relative_dir = Path(str(kb_id)) / str(file_id)
        relative_path = relative_dir / stored_filename
        absolute_dir = cls._storage_root() / relative_dir
        absolute_dir.mkdir(parents=True, exist_ok=True)
        absolute_path = absolute_dir / stored_filename
        absolute_path.write_bytes(payload)

        now = cls._now()
        document = {
            "_id": file_id,
            "kb_id": str(kb_id),
            "owner_user_id": str(user_id),
            "original_filename": original_filename,
            "filename": safe_name,
            "content_type": str(upload.content_type or "application/octet-stream"),
            "size": len(payload),
            "storage_path": str(relative_path),
            "sha256": sha256(payload).hexdigest(),
            "status": "uploaded",
            "parse_status": "pending",
            "parse_error": None,
            "index_status": "pending",
            "index_error": None,
            "chunk_count": 0,
            "structured_record_count": 0,
            "indexed_at": None,
            "parser_version": "",
            "splitter_version": "",
            "embedding_version": "",
            "structured_parser_version": "",
            "upload_source": upload_source,
            "metadata": {
                "remark": remark.strip(),
                "tags": cls._parse_tags(raw_tags),
            },
            "created_at": now,
            "updated_at": now,
        }
        db.knowledge_files.insert_one(document)
        db.knowledge_bases.update_one({"_id": kb.get("_id")}, {"$set": {"updated_at": now}})
        cls.enqueue_parse(str(file_id))
        return cls._serialize_file(document)

    @classmethod
    def list_files(cls, kb_id: str, user_id: str) -> list[dict[str, Any]]:
        kb = db.knowledge_bases.find_one({
            "_id": cls._to_object_id(kb_id),
            "owner_user_id": str(user_id),
        })
        if not kb:
            raise ValueError("知识库不存在或无权访问")

        items = list(db.knowledge_files.find({
            "kb_id": str(kb_id),
            "owner_user_id": str(user_id),
        }))
        items.sort(key=lambda item: item.get("created_at") or datetime.min, reverse=True)
        items = [cls._backfill_parse_summary_if_missing(item) for item in items]
        items = [cls._ensure_index_state_if_missing(item) for item in items]
        return [cls._serialize_file(item) for item in items]

    @classmethod
    def get_file(cls, file_id: str, user_id: str) -> dict[str, Any] | None:
        document = db.knowledge_files.find_one({
            "_id": cls._to_object_id(file_id),
            "owner_user_id": str(user_id),
        })
        if not document:
            return None
        document = cls._backfill_parse_summary_if_missing(document)
        document = cls._ensure_index_state_if_missing(document)
        return cls._serialize_file(document)

    @classmethod
    def retry_parse(cls, file_id: str, user_id: str) -> dict[str, Any]:
        document = db.knowledge_files.find_one({
            "_id": cls._to_object_id(file_id),
            "owner_user_id": str(user_id),
        })
        if not document:
            raise ValueError("文件不存在或无权访问")

        now = cls._now()
        db.knowledge_chunks.delete_many({"file_id": str(document.get("_id") or "")})
        db.knowledge_records.delete_many({"file_id": str(document.get("_id") or "")})
        db.knowledge_files.update_one(
            {"_id": document.get("_id")},
            {
                "$set": {
                    "parse_status": "pending",
                    "parse_error": None,
                    "index_status": "pending",
                    "index_error": None,
                    "chunk_count": 0,
                    "structured_record_count": 0,
                    "indexed_at": None,
                    "parser_version": "",
                    "splitter_version": "",
                    "embedding_version": "",
                    "structured_parser_version": "",
                    "updated_at": now,
                }
            },
        )
        app = current_app._get_current_object()
        cls._process_file_parse(app, str(document.get("_id") or ""))
        refreshed = db.knowledge_files.find_one({"_id": document.get("_id")}) or document
        return cls._serialize_file(refreshed)

    @classmethod
    def retry_index(cls, file_id: str, user_id: str) -> dict[str, Any]:
        document = db.knowledge_files.find_one({
            "_id": cls._to_object_id(file_id),
            "owner_user_id": str(user_id),
        })
        if not document:
            raise ValueError("文件不存在或无权访问")
        if str(document.get("parse_status") or "") != "ready":
            raise ValueError("文件尚未完成解析，请先重新解析后再重试索引")

        now = cls._now()
        db.knowledge_chunks.delete_many({"file_id": str(document.get("_id") or "")})
        db.knowledge_records.delete_many({"file_id": str(document.get("_id") or "")})
        db.knowledge_files.update_one(
            {"_id": document.get("_id")},
            {
                "$set": {
                    "index_status": "pending",
                    "index_error": None,
                    "chunk_count": 0,
                    "structured_record_count": 0,
                    "indexed_at": None,
                    "parser_version": "",
                    "splitter_version": "",
                    "embedding_version": "",
                    "structured_parser_version": "",
                    "updated_at": now,
                }
            },
        )
        KnowledgeIndexService.index_file(str(document.get("_id") or ""))
        refreshed = db.knowledge_files.find_one({"_id": document.get("_id")}) or document
        return cls._serialize_file(refreshed)

    @classmethod
    def rebuild_index(cls, kb_id: str, user_id: str) -> dict[str, Any]:
        kb = db.knowledge_bases.find_one({
            "_id": cls._to_object_id(kb_id),
            "owner_user_id": str(user_id),
        })
        if not kb:
            raise ValueError("知识库不存在或无权访问")

        items = list(db.knowledge_files.find({
            "kb_id": str(kb_id),
            "owner_user_id": str(user_id),
        }))
        parse_queued = 0
        index_queued = 0
        now = cls._now()

        for document in items:
            file_id = str(document.get("_id") or "")
            if not file_id:
                continue

            db.knowledge_chunks.delete_many({"file_id": file_id})
            db.knowledge_records.delete_many({"file_id": file_id})

            if str(document.get("parse_status") or "") == "ready":
                db.knowledge_files.update_one(
                    {"_id": document.get("_id")},
                    {
                        "$set": {
                            "index_status": "pending",
                            "index_error": None,
                            "chunk_count": 0,
                            "structured_record_count": 0,
                            "indexed_at": None,
                            "parser_version": "",
                            "splitter_version": "",
                            "embedding_version": "",
                            "structured_parser_version": "",
                            "updated_at": now,
                        }
                    },
                )
                cls.enqueue_index(file_id)
                index_queued += 1
            else:
                db.knowledge_files.update_one(
                    {"_id": document.get("_id")},
                    {
                        "$set": {
                            "parse_status": "pending",
                            "parse_error": None,
                            "index_status": "pending",
                            "index_error": None,
                            "chunk_count": 0,
                            "structured_record_count": 0,
                            "indexed_at": None,
                            "parser_version": "",
                            "splitter_version": "",
                            "embedding_version": "",
                            "structured_parser_version": "",
                            "updated_at": now,
                        }
                    },
                )
                cls.enqueue_parse(file_id)
                parse_queued += 1

        db.knowledge_bases.update_one({"_id": kb.get("_id")}, {"$set": {"updated_at": now}})
        return {
            "kbId": str(kb_id),
            "totalFiles": len(items),
            "parseQueued": parse_queued,
            "indexQueued": index_queued,
            "queuedCount": parse_queued + index_queued,
        }

    @classmethod
    def delete_file(cls, file_id: str, user_id: str) -> bool:
        document = db.knowledge_files.find_one({
            "_id": cls._to_object_id(file_id),
            "owner_user_id": str(user_id),
        })
        if not document:
            return False

        storage_path = str(document.get("storage_path") or "")
        if storage_path:
            absolute_path = cls._storage_root() / storage_path
            if absolute_path.exists():
                absolute_path.unlink()
            parent_dir = absolute_path.parent
            if parent_dir.exists():
                try:
                    parent_dir.rmdir()
                except OSError:
                    pass

        db.knowledge_files.delete_one({"_id": document.get("_id")})
        db.knowledge_chunks.delete_many({"file_id": str(document.get("_id") or "")})
        db.knowledge_records.delete_many({"file_id": str(document.get("_id") or "")})
        db.knowledge_bases.update_one(
            {"_id": cls._to_object_id(str(document.get("kb_id")))},
            {"$set": {"updated_at": cls._now()}},
        )
        return True
