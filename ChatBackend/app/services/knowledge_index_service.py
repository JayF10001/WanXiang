from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any
import csv
import html
import io
import json
import math
import re

from bson import ObjectId
from flask import current_app

from ..extensions import db
from rag_service.embeddings.embedding_provider import EmbeddingProvider


@dataclass(frozen=True)
class ChunkConfig:
    chunk_size: int = 800
    chunk_overlap: int = 120
    parser_version: str = "phase1-v1"
    splitter_version: str = "phase1-cn-v1"
    embedding_version: str = EmbeddingProvider.version()
    structured_parser_version: str = "phase2-structured-v1"


class KnowledgeIndexService:
    config = ChunkConfig()
    STRUCTURED_SUBJECT_PATTERNS = (
        r"C/C\+\+\s*程序设计",
        r"Java\s*软件开发",
        r"Java\s*程序设计",
        r"Python\s*程序设计",
        r"Web\s*应用开发",
        r"单片机设计与开发",
        r"嵌入式设计与开发",
        r"EDA\s*设计与开发",
        r"软件测试",
        r"大数据",
        r"人工智能",
        r"信息安全",
    )

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
    def _safe_decode(payload: bytes) -> str:
        for encoding in ("utf-8", "utf-8-sig", "gbk", "gb2312"):
            try:
                return payload.decode(encoding)
            except Exception:
                continue
        return payload.decode("utf-8", errors="ignore")

    @staticmethod
    def _normalize_text(text: str) -> str:
        normalized = html.unescape(str(text or ""))
        normalized = re.sub(r"<script[\s\S]*?</script>", " ", normalized, flags=re.IGNORECASE)
        normalized = re.sub(r"<style[\s\S]*?</style>", " ", normalized, flags=re.IGNORECASE)
        normalized = re.sub(r"<[^>]+>", " ", normalized)
        normalized = normalized.replace("\r", "\n")
        normalized = re.sub(r"\n{3,}", "\n\n", normalized)
        normalized = re.sub(r"[ \t]{2,}", " ", normalized)
        return normalized.strip()

    @classmethod
    def _extract_text_from_payload(cls, filename: str, content_type: str, payload: bytes) -> tuple[str, dict[str, Any]]:
        extension = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
        metadata: dict[str, Any] = {
            "fileType": extension or "unknown",
            "contentType": content_type or "application/octet-stream",
            "extractMode": "text",
        }

        if extension in {"txt", "md", "html"}:
            text = cls._normalize_text(cls._safe_decode(payload))
            return text, metadata

        if extension == "json":
            try:
                parsed = json.loads(cls._safe_decode(payload))
                text = json.dumps(parsed, ensure_ascii=False, indent=2)
            except Exception:
                text = cls._safe_decode(payload)
            return cls._normalize_text(text), metadata

        if extension == "csv":
            text = cls._safe_decode(payload)
            reader = csv.reader(io.StringIO(text))
            rows = [" | ".join(cell.strip() for cell in row if str(cell).strip()) for row in reader]
            normalized_rows = [row for row in rows if row.strip()]
            metadata["rowCount"] = len(normalized_rows)
            return cls._normalize_text("\n".join(normalized_rows)), metadata

        if extension == "pdf":
            try:
                from pypdf import PdfReader  # type: ignore
            except Exception as exc:  # pragma: no cover
                raise RuntimeError(f"PDF 解析依赖不可用: {exc}") from exc

            reader = PdfReader(io.BytesIO(payload))
            pages = []
            for page in reader.pages:
                pages.append(page.extract_text() or "")
            metadata["pageCount"] = len(reader.pages)
            metadata["extractMode"] = "pdf"
            return cls._normalize_text("\n".join(pages)), metadata

        if extension == "docx":
            try:
                from docx import Document  # type: ignore
            except Exception as exc:  # pragma: no cover
                raise RuntimeError(f"DOCX 解析依赖不可用: {exc}") from exc

            document = Document(io.BytesIO(payload))
            paragraphs = [paragraph.text for paragraph in document.paragraphs if str(paragraph.text).strip()]
            metadata["paragraphCount"] = len(paragraphs)
            metadata["extractMode"] = "docx"
            return cls._normalize_text("\n".join(paragraphs)), metadata

        raise RuntimeError(f"暂不支持该文件类型的正文解析: .{extension or 'unknown'}")

    @classmethod
    def _split_text(cls, text: str) -> list[str]:
        normalized = cls._normalize_text(text)
        if not normalized:
            return []

        chunk_size = cls.config.chunk_size
        overlap = cls.config.chunk_overlap
        chunks: list[str] = []
        start = 0
        text_length = len(normalized)

        while start < text_length:
            end = min(text_length, start + chunk_size)
            window = normalized[start:end]

            if end < text_length:
                breakpoints = [window.rfind(token) for token in ("\n\n", "\n", "。", "！", "？", "；", "，", " ")]
                split_at = max(breakpoints)
                if split_at >= int(chunk_size * 0.45):
                    end = start + split_at + 1
                    window = normalized[start:end]

            cleaned = window.strip()
            if cleaned:
                chunks.append(cleaned)

            if end >= text_length:
                break

            start = max(end - overlap, start + 1)

        return chunks

    @staticmethod
    def _estimate_tokens(text: str) -> int:
        normalized = str(text or "").strip()
        if not normalized:
            return 0
        return max(1, math.ceil(len(normalized) / 1.8))

    @staticmethod
    def _normalize_inline_whitespace(text: str) -> str:
        return re.sub(r"\s+", " ", str(text or "")).strip()

    @classmethod
    def _find_subject_start(cls, text: str) -> int:
        best_index = -1
        for pattern in cls.STRUCTURED_SUBJECT_PATTERNS:
            match = re.search(pattern, text)
            if not match:
                continue
            if best_index == -1 or match.start() < best_index:
                best_index = match.start()
        return best_index

    @classmethod
    def _derive_group_name(cls, subject_name: str) -> str:
        normalized = cls._normalize_inline_whitespace(subject_name)
        group_match = re.search(r"([ABC])\s*组", normalized, flags=re.IGNORECASE)
        if group_match:
            return f"{group_match.group(1).upper()}组"
        for token in ("大学组", "研究生组", "青少年组", "青少组", "中职组"):
            if token in normalized:
                return token
        return ""

    @classmethod
    def _parse_structured_award_line(cls, line: str) -> dict[str, Any] | None:
        normalized_line = cls._normalize_inline_whitespace(line)
        if not normalized_line:
            return None

        match = re.match(
            r"^(?P<province>[\u4e00-\u9fffA-Za-z]+)\s+(?P<ticket>\d{6,})\s+(?P<body>.+?)\s+"
            r"(?P<award>一等奖|二等奖|三等奖)(?:\s+(?P<qualified>是|否))?$",
            normalized_line,
        )
        if not match:
            return None

        body = cls._normalize_inline_whitespace(match.group("body"))
        subject_start = cls._find_subject_start(body)
        if subject_start <= 0:
            return None

        identity_part = cls._normalize_inline_whitespace(body[:subject_start])
        subject_name = cls._normalize_inline_whitespace(body[subject_start:])
        identity_tokens = identity_part.split(" ")
        if len(identity_tokens) < 2:
            return None

        student_name = identity_tokens[-1]
        school_name = cls._normalize_inline_whitespace(" ".join(identity_tokens[:-1]))
        if not school_name or not student_name or len(student_name) > 10:
            return None

        qualified_value = match.group("qualified") or ""
        return {
            "province": match.group("province"),
            "ticket_no": match.group("ticket"),
            "school_name": school_name,
            "student_name": student_name,
            "subject_name": subject_name,
            "group_name": cls._derive_group_name(subject_name),
            "award": match.group("award"),
            "qualified_for_final": True if qualified_value == "是" else False if qualified_value == "否" else None,
            "qualified_for_final_label": qualified_value,
            "raw_text": normalized_line,
        }

    @classmethod
    def _extract_structured_records(
        cls,
        *,
        text: str,
        file_doc: dict[str, Any],
        extraction_meta: dict[str, Any],
    ) -> list[dict[str, Any]]:
        now = cls._now()
        records: list[dict[str, Any]] = []
        seen_keys: set[tuple[str, ...]] = set()
        lines = [cls._normalize_inline_whitespace(line) for line in str(text or "").splitlines()]

        for line_index, line in enumerate(lines):
            parsed = cls._parse_structured_award_line(line)
            if not parsed:
                continue
            dedupe_key = (
                parsed["province"],
                parsed["ticket_no"],
                parsed["school_name"],
                parsed["student_name"],
                parsed["subject_name"],
                parsed["award"],
            )
            if dedupe_key in seen_keys:
                continue
            seen_keys.add(dedupe_key)
            record_id = ObjectId() if not db.is_in_memory else f"kr_{int(now.timestamp() * 1000)}_{line_index}"
            records.append(
                {
                    "_id": record_id,
                    "kb_id": str(file_doc.get("kb_id") or ""),
                    "file_id": str(file_doc.get("_id") or ""),
                    "owner_user_id": str(file_doc.get("owner_user_id") or ""),
                    "record_type": "competition_award",
                    "schema_version": cls.config.structured_parser_version,
                    "province": parsed["province"],
                    "ticket_no": parsed["ticket_no"],
                    "school_name": parsed["school_name"],
                    "student_name": parsed["student_name"],
                    "subject_name": parsed["subject_name"],
                    "group_name": parsed["group_name"],
                    "award": parsed["award"],
                    "qualified_for_final": parsed["qualified_for_final"],
                    "qualified_for_final_label": parsed["qualified_for_final_label"],
                    "raw_text": parsed["raw_text"],
                    "line_index": line_index,
                    "metadata": {
                        "originalFilename": str(file_doc.get("original_filename") or ""),
                        "contentType": str(file_doc.get("content_type") or ""),
                        "sourcePath": str(file_doc.get("storage_path") or ""),
                        **extraction_meta,
                    },
                    "created_at": now,
                    "updated_at": now,
                }
            )

        return records

    @classmethod
    def _build_chunk_documents(cls, file_doc: dict[str, Any], chunks: list[str], extraction_meta: dict[str, Any]) -> list[dict[str, Any]]:
        now = cls._now()
        documents = []
        for index, chunk in enumerate(chunks):
            embedding = EmbeddingProvider.embed_text(chunk)
            documents.append({
                "_id": ObjectId() if not db.is_in_memory else f"kc_{int(now.timestamp() * 1000)}_{index}",
                "kb_id": str(file_doc.get("kb_id") or ""),
                "file_id": str(file_doc.get("_id") or ""),
                "owner_user_id": str(file_doc.get("owner_user_id") or ""),
                "chunk_index": index,
                "content": chunk,
                "content_length": len(chunk),
                "token_estimate": cls._estimate_tokens(chunk),
                "metadata": {
                    "originalFilename": str(file_doc.get("original_filename") or ""),
                    "contentType": str(file_doc.get("content_type") or ""),
                    "sourcePath": str(file_doc.get("storage_path") or ""),
                    **extraction_meta,
                },
                "embedding": embedding,
                "embedding_dimensions": len(embedding),
                "embedding_version": cls.config.embedding_version,
                "parser_version": cls.config.parser_version,
                "splitter_version": cls.config.splitter_version,
                "created_at": now,
                "updated_at": now,
            })
        return documents

    @classmethod
    def index_file(cls, file_id: str) -> dict[str, Any]:
        file_doc = db.knowledge_files.find_one({"_id": cls._to_object_id(file_id)})
        if not file_doc:
            raise ValueError("知识库文件不存在")

        storage_path = str(file_doc.get("storage_path") or "")
        if not storage_path:
            raise ValueError("文件缺少 storage_path")

        absolute_path = cls._absolute_storage_path(storage_path)
        if not absolute_path.exists():
            raise FileNotFoundError("原始文件不存在")

        db.knowledge_files.update_one(
            {"_id": file_doc.get("_id")},
            {
                "$set": {
                    "index_status": "processing",
                    "index_error": None,
                    "updated_at": cls._now(),
                }
            },
        )

        payload = absolute_path.read_bytes()
        text, extraction_meta = cls._extract_text_from_payload(
            str(file_doc.get("original_filename") or ""),
            str(file_doc.get("content_type") or ""),
            payload,
        )
        chunks = cls._split_text(text)
        structured_records = cls._extract_structured_records(text=text, file_doc=file_doc, extraction_meta=extraction_meta)

        db.knowledge_chunks.delete_many({"file_id": str(file_doc.get("_id") or "")})
        db.knowledge_records.delete_many({"file_id": str(file_doc.get("_id") or "")})
        chunk_documents = cls._build_chunk_documents(file_doc, chunks, extraction_meta)
        if chunk_documents:
            db.knowledge_chunks.insert_many(chunk_documents)
        if structured_records:
            db.knowledge_records.insert_many(structured_records)

        indexed_at = cls._now()
        db.knowledge_files.update_one(
            {"_id": file_doc.get("_id")},
            {
                "$set": {
                    "index_status": "ready",
                    "index_error": None,
                    "chunk_count": len(chunk_documents),
                    "structured_record_count": len(structured_records),
                    "indexed_at": indexed_at,
                    "parser_version": cls.config.parser_version,
                    "splitter_version": cls.config.splitter_version,
                    "embedding_version": cls.config.embedding_version,
                    "structured_parser_version": cls.config.structured_parser_version,
                    "updated_at": indexed_at,
                }
            },
        )

        return {
            "fileId": str(file_doc.get("_id") or ""),
            "chunkCount": len(chunk_documents),
            "indexedAt": indexed_at.isoformat(),
            "parserVersion": cls.config.parser_version,
            "splitterVersion": cls.config.splitter_version,
            "embeddingVersion": cls.config.embedding_version,
        }
