from __future__ import annotations

from typing import Any, Dict, List
from collections import Counter
import re

from ..config import DEFAULT_RAG_CONFIG
from ..loaders.file_loader import FileLoader
from ..splitters.chinese_splitter import ChineseSplitter


class StructuredRetriever:
    AWARDS = ("一等奖", "二等奖", "三等奖")
    GROUPS = ("A组", "B组", "C组", "大学组", "研究生组", "青少年组", "中职组")

    @staticmethod
    def _normalize_group_name(value: str) -> str:
        normalized = re.sub(r"\s+", "", str(value or "")).upper()
        for token in ("A组", "B组", "C组"):
            if token in normalized:
                return token
        for token in StructuredRetriever.GROUPS:
            if token in str(value or ""):
                return token
        return ""

    @classmethod
    def _parse_query_filters(cls, query: str, records: List[Dict[str, Any]]) -> Dict[str, Any]:
        normalized = str(query or "")
        schools = sorted({str(item.get("school_name") or "").strip() for item in records if str(item.get("school_name") or "").strip()}, key=len, reverse=True)
        students = sorted({str(item.get("student_name") or "").strip() for item in records if str(item.get("student_name") or "").strip()}, key=len, reverse=True)
        subjects = sorted({str(item.get("subject_name") or "").strip() for item in records if str(item.get("subject_name") or "").strip()}, key=len, reverse=True)

        matched_schools = [school for school in schools if school and school in normalized][:5]
        matched_students = [student for student in students if student and student in normalized][:5]
        matched_awards = [award for award in cls.AWARDS if award in normalized]
        matched_groups = [group for group in cls.GROUPS if group in normalized.replace(" ", "")]
        matched_subjects = [subject for subject in subjects if subject and len(subject) >= 4 and subject in normalized][:5]

        asks_finalists = any(token in normalized for token in ("晋级", "进入决赛", "进决赛", "决赛"))
        asks_count = any(token in normalized for token in ("几人", "多少人", "人数", "总数", "数量"))
        asks_schools = any(token in normalized for token in ("哪些学校", "哪些院校", "哪些高校", "学校", "院校", "高校"))
        asks_students = any(token in normalized for token in ("哪些人", "名单", "获奖名单", "学生", "姓名"))

        return {
            "schools": matched_schools,
            "students": matched_students,
            "awards": matched_awards,
            "groups": matched_groups,
            "subjects": matched_subjects,
            "qualifiedOnly": asks_finalists,
            "asksCount": asks_count,
            "asksSchools": asks_schools,
            "asksStudents": asks_students,
        }

    @staticmethod
    def _keyword_score(query: str, text: str) -> float:
        query_terms = ChineseSplitter.tokenize(query)
        text_terms = ChineseSplitter.tokenize(text)
        if not query_terms or not text_terms:
            return 0.0
        text_term_set = set(text_terms)
        matched = sum(1 for term in query_terms if term in text_term_set)
        return matched / max(len(set(query_terms)), 1)

    @classmethod
    def _explicit_match_score(cls, *, record: Dict[str, Any], filters: Dict[str, Any]) -> float:
        score = 0.0
        if filters.get("schools") and str(record.get("school_name") or "") in filters["schools"]:
            score += 0.45
        if filters.get("students") and str(record.get("student_name") or "") in filters["students"]:
            score += 0.5
        if filters.get("awards") and str(record.get("award") or "") in filters["awards"]:
            score += 0.3
        if filters.get("groups") and cls._normalize_group_name(str(record.get("group_name") or record.get("subject_name") or "")) in {cls._normalize_group_name(item) for item in filters["groups"]}:
            score += 0.25
        if filters.get("subjects") and str(record.get("subject_name") or "") in filters["subjects"]:
            score += 0.35
        if filters.get("qualifiedOnly") and record.get("qualified_for_final") is True:
            score += 0.12
        return round(min(score, 1.0), 4)

    @classmethod
    def _build_record_text(cls, record: Dict[str, Any]) -> str:
        return " ".join(
            [
                str(record.get("province") or ""),
                str(record.get("school_name") or ""),
                str(record.get("student_name") or ""),
                str(record.get("subject_name") or ""),
                str(record.get("group_name") or ""),
                str(record.get("award") or ""),
                "进入决赛" if record.get("qualified_for_final") is True else "",
            ]
        ).strip()

    @classmethod
    def _passes_explicit_filters(cls, record: Dict[str, Any], filters: Dict[str, Any]) -> bool:
        school_name = str(record.get("school_name") or "")
        student_name = str(record.get("student_name") or "")
        subject_name = str(record.get("subject_name") or "")
        group_name = cls._normalize_group_name(str(record.get("group_name") or subject_name))
        award = str(record.get("award") or "")

        if filters.get("schools") and school_name not in filters["schools"]:
            return False
        if filters.get("students") and student_name not in filters["students"]:
            return False
        if filters.get("awards") and award not in filters["awards"]:
            return False
        if filters.get("groups") and group_name not in {cls._normalize_group_name(item) for item in filters["groups"]}:
            return False
        if filters.get("subjects") and subject_name not in filters["subjects"]:
            return False
        if filters.get("qualifiedOnly") and record.get("qualified_for_final") is not True:
            return False
        return True

    @classmethod
    def _score_record(cls, *, query: str, record: Dict[str, Any], filters: Dict[str, Any]) -> float:
        base_text = cls._build_record_text(record)
        keyword_score = cls._keyword_score(query, base_text)
        filter_score = cls._filter_score(record=record, filters=filters)

        return round(keyword_score + filter_score, 4)

    @classmethod
    def _filter_score(cls, *, record: Dict[str, Any], filters: Dict[str, Any]) -> float:
        filter_score = 0.0

        if filters.get("schools") and str(record.get("school_name") or "") in filters["schools"]:
            filter_score += 0.5
        if filters.get("students") and str(record.get("student_name") or "") in filters["students"]:
            filter_score += 0.6
        if filters.get("awards") and str(record.get("award") or "") in filters["awards"]:
            filter_score += 0.35
        if filters.get("groups") and cls._normalize_group_name(str(record.get("group_name") or record.get("subject_name") or "")) in {cls._normalize_group_name(item) for item in filters["groups"]}:
            filter_score += 0.35
        if filters.get("subjects") and str(record.get("subject_name") or "") in filters["subjects"]:
            filter_score += 0.4
        if filters.get("qualifiedOnly") and record.get("qualified_for_final") is True:
            filter_score += 0.2

        award = str(record.get("award") or "")
        if award == "一等奖":
            filter_score += 0.08

        return filter_score

    @classmethod
    def retrieve(
        cls,
        *,
        query: str,
        kb_id: str | None = None,
        user_id: str | None = None,
        top_k: int | None = None,
    ) -> Dict[str, Any]:
        records = FileLoader.load_knowledge_records(kb_id=kb_id, user_id=user_id)
        if not records:
            return {"sources": [], "filters": {}, "recordCount": 0, "aggregations": {}}

        filters = cls._parse_query_filters(query, records)
        scored: List[Dict[str, Any]] = []

        for record in records:
            if not cls._passes_explicit_filters(record, filters):
                continue
            raw_text = str(record.get("raw_text") or cls._build_record_text(record))
            token_keyword_score = cls._keyword_score(query, raw_text)
            explicit_match_score = cls._explicit_match_score(record=record, filters=filters)
            keyword_score = round(max(token_keyword_score, explicit_match_score), 4)
            filter_score = cls._filter_score(record=record, filters=filters)
            score = round(keyword_score + filter_score, 4)
            if score <= 0 and any(filters.get(key) for key in ("schools", "students", "awards", "groups", "subjects")):
                continue
            scored.append(
                {
                    "sourceType": "knowledge_record",
                    "sourceId": str(record.get("_id") or ""),
                    "fileId": str(record.get("file_id") or ""),
                    "kbId": str(record.get("kb_id") or ""),
                    "title": str((record.get("metadata") or {}).get("originalFilename") or "结构化记录"),
                    "content": raw_text,
                    "summary": raw_text[: DEFAULT_RAG_CONFIG.chunk_preview_length],
                    "url": "",
                    "publishedAt": "",
                    "credibility": "high",
                    "score": score,
                    "keywordScore": round(keyword_score, 4),
                    "vectorScore": 0.0,
                    "metadata": record.get("metadata") or {},
                    "record": {
                        "province": str(record.get("province") or ""),
                        "ticketNo": str(record.get("ticket_no") or ""),
                        "schoolName": str(record.get("school_name") or ""),
                        "studentName": str(record.get("student_name") or ""),
                        "subjectName": str(record.get("subject_name") or ""),
                        "groupName": str(record.get("group_name") or ""),
                        "award": str(record.get("award") or ""),
                        "qualifiedForFinal": record.get("qualified_for_final"),
                        "qualifiedForFinalLabel": str(record.get("qualified_for_final_label") or ""),
                    },
                }
            )

        scored.sort(key=lambda item: float(item.get("score") or 0), reverse=True)
        aggregations = cls._build_aggregations(scored)
        limited = scored[: (top_k or DEFAULT_RAG_CONFIG.structured_top_k)]
        return {
            "sources": limited,
            "records": scored,
            "filters": filters,
            "recordCount": len(scored),
            "aggregations": aggregations,
        }

    @classmethod
    def _build_aggregations(cls, scored: List[Dict[str, Any]]) -> Dict[str, Any]:
        records = [item.get("record") or {} for item in scored]
        school_counter = Counter(str(record.get("schoolName") or "").strip() for record in records if str(record.get("schoolName") or "").strip())
        award_counter = Counter(str(record.get("award") or "").strip() for record in records if str(record.get("award") or "").strip())
        subject_counter = Counter(str(record.get("subjectName") or "").strip() for record in records if str(record.get("subjectName") or "").strip())
        group_counter = Counter(str(record.get("groupName") or "").strip() for record in records if str(record.get("groupName") or "").strip())
        finalist_count = sum(1 for record in records if record.get("qualifiedForFinal") is True)

        def _counter_items(counter: Counter[str]) -> List[Dict[str, Any]]:
            return [{"name": name, "count": count} for name, count in counter.most_common(10)]

        return {
            "totalMatchedCount": len(records),
            "finalistCount": finalist_count,
            "uniqueSchoolCount": len(school_counter),
            "countsBySchool": _counter_items(school_counter),
            "countsByAward": _counter_items(award_counter),
            "countsBySubject": _counter_items(subject_counter),
            "countsByGroup": _counter_items(group_counter),
        }
