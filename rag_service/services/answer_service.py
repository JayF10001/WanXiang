from __future__ import annotations

from typing import Any, Dict, List
from collections import Counter

from ChatBackend.app.services.chat_service import ChatService
from ..chains.chat_chain import ChatChain


class AnswerService:
    @staticmethod
    def _is_structured_source(item: Dict[str, Any]) -> bool:
        return str(item.get("sourceType") or "") == "knowledge_record" and isinstance(item.get("record"), dict)

    @staticmethod
    def _source_group_key(item: Dict[str, Any]) -> str:
        return "||".join([
            str(item.get("sourceType") or ""),
            str(item.get("fileId") or ""),
            str(item.get("url") or ""),
            str(item.get("title") or ""),
        ])

    @classmethod
    def _group_sources(cls, sources: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        grouped: Dict[str, Dict[str, Any]] = {}
        for item in sources:
            key = cls._source_group_key(item)
            summary = str(item.get("summary") or item.get("content") or "").strip()
            current = grouped.get(key)
            if not current:
                grouped[key] = {
                    **item,
                    "summary": summary[:220],
                    "snippet": summary[:220],
                    "content": "",
                    "score": float(item.get("score") or 0),
                    "citationCount": 1,
                }
                continue

            current["score"] = max(float(current.get("score") or 0), float(item.get("score") or 0))
            current["keywordScore"] = max(float(current.get("keywordScore") or 0), float(item.get("keywordScore") or 0))
            current["vectorScore"] = max(float(current.get("vectorScore") or 0), float(item.get("vectorScore") or 0))
            current["citationCount"] = int(current.get("citationCount") or 1) + 1

        items = list(grouped.values())
        items.sort(key=lambda item: float(item.get("score") or 0), reverse=True)
        return items

    @classmethod
    def _build_citations(cls, sources: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        grouped: Dict[str, List[Dict[str, Any]]] = {}
        for item in sources:
            grouped.setdefault(cls._source_group_key(item), []).append(item)

        selected: List[Dict[str, Any]] = []
        for items in grouped.values():
            items.sort(key=lambda item: float(item.get("score") or 0), reverse=True)
            selected.extend(items[:4])

        selected.sort(key=lambda item: float(item.get("score") or 0), reverse=True)

        citations = []
        for index, item in enumerate(selected[:8], start=1):
            title = str(item.get("title") or item.get("sourceTitle") or f"来源 {index}")
            url = str(item.get("url") or item.get("sourceUrl") or "")
            quote = str(item.get("summary") or item.get("content") or "").strip()[:220]
            citations.append(
                {
                    "id": f"citation-{index}",
                    "title": title,
                    "url": url,
                    "sourceTitle": title,
                    "sourceUrl": url,
                    "quote": quote,
                    "sourceType": str(item.get("sourceType") or "web"),
                    "credibility": str(item.get("credibility") or "unknown"),
                    "publishedAt": str(item.get("publishedAt") or ""),
                    "sourceId": str(item.get("sourceId") or ""),
                    "fileId": str(item.get("fileId") or ""),
                    "score": float(item.get("score") or 0),
                    "keywordScore": float(item.get("keywordScore") or 0),
                    "vectorScore": float(item.get("vectorScore") or 0),
                }
            )
        return citations

    @staticmethod
    def _build_fact_layers(sources: List[Dict[str, Any]]) -> tuple[list[str], list[str], list[str]]:
        facts: List[str] = []
        to_verify: List[str] = []
        analysis: List[str] = []
        seen_summaries = set()

        for item in sources[:4]:
            summary = str(item.get("summary") or item.get("content") or "").strip()
            if not summary:
                continue
            normalized_summary = summary[:180]
            if normalized_summary in seen_summaries:
                continue
            seen_summaries.add(normalized_summary)
            credibility = str(item.get("credibility") or "unknown")
            if credibility == "high":
                facts.append(normalized_summary)
            elif credibility == "medium":
                to_verify.append(normalized_summary)
            else:
                analysis.append(normalized_summary)

        return facts[:3], to_verify[:3], analysis[:3]

    @staticmethod
    def _dedupe_structured_records(sources: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        seen = set()
        items: List[Dict[str, Any]] = []
        for item in sources:
            record = item.get("record") or {}
            dedupe_key = (
                str(item.get("fileId") or ""),
                str(record.get("ticketNo") or ""),
                str(record.get("schoolName") or ""),
                str(record.get("studentName") or ""),
                str(record.get("subjectName") or ""),
                str(record.get("award") or ""),
            )
            if dedupe_key in seen:
                continue
            seen.add(dedupe_key)
            items.append(item)
        return items

    @staticmethod
    def _format_record_brief(record: Dict[str, Any]) -> str:
        school = str(record.get("schoolName") or "")
        student = str(record.get("studentName") or "")
        subject = str(record.get("subjectName") or "")
        award = str(record.get("award") or "")
        qualified = str(record.get("qualifiedForFinalLabel") or "")
        suffix = "，进入决赛" if qualified == "是" else ""
        return f"{school}{student}获{subject}{award}{suffix}".strip()

    @classmethod
    def _build_structured_fact_layers(cls, sources: List[Dict[str, Any]]) -> tuple[list[str], list[str], list[str]]:
        facts: List[str] = []
        for item in cls._dedupe_structured_records(sources)[:5]:
            record = item.get("record") or {}
            brief = cls._format_record_brief(record)
            if brief:
                facts.append(brief)
        return facts[:3], [], []

    @classmethod
    def _build_structured_answer(cls, query: str, sources: List[Dict[str, Any]], retrieval_result: Dict[str, Any]) -> str:
        records = [item.get("record") or {} for item in cls._dedupe_structured_records(sources)]
        if not records:
            return "当前没有命中可用的结构化记录，建议改用原始片段继续核对。"

        filters = retrieval_result.get("structuredFilters") or {}
        aggregations = retrieval_result.get("structuredAggregations") or {}
        total_matched_count = int(aggregations.get("totalMatchedCount") or len(records))
        finalist_total = int(aggregations.get("finalistCount") or 0)
        unique_school_count = int(aggregations.get("uniqueSchoolCount") or 0)
        counts_by_school = aggregations.get("countsBySchool") or []
        counts_by_award = aggregations.get("countsByAward") or []
        counts_by_subject = aggregations.get("countsBySubject") or []
        counts_by_group = aggregations.get("countsByGroup") or []
        schools = [str(record.get("schoolName") or "") for record in records if str(record.get("schoolName") or "")]
        awards = [str(record.get("award") or "") for record in records if str(record.get("award") or "")]
        subjects = [str(record.get("subjectName") or "") for record in records if str(record.get("subjectName") or "")]
        finalist_count = sum(1 for record in records if record.get("qualifiedForFinal") is True)
        unique_schools = list(dict.fromkeys(schools))
        award_counter = Counter(awards)
        subject_counter = Counter(subjects)

        lines = ["根据当前命中的结构化记录，可确认以下信息：", "", "### 【已知事实】"]
        lines.append(f"- 当前共命中 **{total_matched_count}** 条结构化获奖记录。")

        if filters.get("schools"):
            lines.append(f"- 查询明确命中了学校：**{'、'.join(filters['schools'])}**。")

        if filters.get("awards"):
            lines.append(f"- 记录集中在奖项：**{'、'.join(filters['awards'])}**。")

        if filters.get("groups"):
            normalized_groups = "、".join(str(item) for item in filters.get("groups") or [])
            lines.append(f"- 记录涉及组别：**{normalized_groups}**。")

        if unique_schools:
            lines.append(f"- 当前片段涉及院校包括：**{'、'.join(unique_schools[:8])}**。")

        if finalist_total:
            lines.append(f"- 其中可直接确认 **{finalist_total}** 条记录标注为“进入决赛”。")

        top_subjects = [name for name, _ in subject_counter.most_common(3) if name]
        if counts_by_subject:
            top_subjects = [str(item.get("name") or "") for item in counts_by_subject[:3] if str(item.get("name") or "")]
        if top_subjects:
            lines.append(f"- 命中的主要科目/组别包括：**{'、'.join(top_subjects)}**。")

        if unique_school_count:
            lines.append(f"- 当前命中记录覆盖 **{unique_school_count}** 所院校。")

        if filters.get("asksCount"):
            if len(filters.get("schools") or []) == 1:
                school_name = str((filters.get("schools") or [""])[0])
                school_count = next((int(item.get("count") or 0) for item in counts_by_school if str(item.get("name") or "") == school_name), total_matched_count)
                lines.append(f"- 按当前筛选条件，**{school_name}** 共命中 **{school_count}** 条记录。")
            else:
                lines.append(f"- 按当前筛选条件，合计命中 **{total_matched_count}** 条记录。")

        scope_parts: List[str] = []
        if filters.get("schools"):
            scope_parts.append(f"学校：{'、'.join(filters['schools'])}")
        if filters.get("awards"):
            scope_parts.append(f"奖项：{'、'.join(filters['awards'])}")
        if filters.get("groups"):
            scope_parts.append(f"组别：{'、'.join(str(item) for item in filters['groups'])}")
        elif counts_by_group:
            scope_parts.append("组别：未额外限定，按当前命中结果覆盖的组别统计")
        if filters.get("subjects"):
            scope_parts.append(f"科目：{'、'.join(filters['subjects'])}")
        elif counts_by_subject:
            scope_parts.append("科目：未额外限定，按当前命中结果覆盖的科目统计")
        if filters.get("qualifiedOnly"):
            scope_parts.append("晋级条件：仅统计已进入决赛记录")

        if scope_parts:
            lines.append(f"- 本次统计口径为：**{'；'.join(scope_parts)}**。")

        sample_records = records[:5]
        if sample_records:
            lines.append("- 代表性记录示例：")
            for record in sample_records:
                lines.append(f"  {cls._format_record_brief(record)}")

        lines.extend(["", "### 【说明】"])
        lines.append("- 当前回答优先基于结构化记录作答，适合核对学校、姓名、组别、奖项和是否晋级。")
        lines.append("- 若需全省总人数、完整名单或跨页全量统计，仍建议结合原始 PDF 或后续结构化导出结果复核。")
        lines.append("- 若问题未显式限定科目或组别，系统会按当前命中的全部相关结构化记录统计。")

        if counts_by_award:
            top_awards = "、".join(f"{str(item.get('name') or '')}{int(item.get('count') or 0)}条" for item in counts_by_award[:3] if str(item.get("name") or ""))
            lines.extend(["", "### 【快速观察】", f"- 当前命中记录的奖项分布以：**{top_awards}** 为主。"])
        elif award_counter:
            top_awards = "、".join(f"{name}{count}条" for name, count in award_counter.most_common(3))
            lines.extend(["", "### 【快速观察】", f"- 当前命中记录的奖项分布以：**{top_awards}** 为主。"])

        if counts_by_school:
            top_schools = "、".join(f"{str(item.get('name') or '')}{int(item.get('count') or 0)}条" for item in counts_by_school[:3] if str(item.get("name") or ""))
            lines.append(f"- 院校分布前列包括：**{top_schools}**。")

        if counts_by_group:
            top_groups = "、".join(f"{str(item.get('name') or '')}{int(item.get('count') or 0)}条" for item in counts_by_group[:3] if str(item.get("name") or ""))
            lines.append(f"- 组别分布前列包括：**{top_groups}**。")

        if any(token in query for token in ("几人", "多少人", "人数", "总数", "统计")):
            lines.append("- 本次人数结论仅针对当前命中的结构化记录，不默认代表完整全量名单。")

        return "\n".join(lines).strip()

    @classmethod
    def answer(cls, *, query: str, retrieval_result: Dict[str, Any], settings: Dict[str, Any] | None = None) -> Dict[str, Any]:
        raw_sources = retrieval_result.get("sources") or []
        grouped_sources = cls._group_sources(raw_sources)
        citations = cls._build_citations(raw_sources)
        if raw_sources and all(cls._is_structured_source(item) for item in raw_sources):
            facts, to_verify, analysis = cls._build_structured_fact_layers(raw_sources)
            answer_text = cls._build_structured_answer(query, raw_sources, retrieval_result)
        else:
            facts, to_verify, analysis = cls._build_fact_layers(raw_sources)
            prompt_messages = ChatChain.build_messages(
                query=query,
                retrieval_result={
                    **retrieval_result,
                    "citations": citations,
                },
            )
            answer_text = ChatService.get_model_response(prompt_messages, settings=settings or {"enable_search": False, "temperature": 0.2})

        confidence = "low"
        if any(str(item.get("credibility")) == "high" for item in raw_sources):
            confidence = "high"
        elif raw_sources:
            confidence = "medium"

        return {
            "answer": answer_text,
            "facts": facts,
            "toVerify": to_verify,
            "analysis": analysis,
            "sources": grouped_sources,
            "citations": citations,
            "confidence": confidence,
            "groundingStatus": retrieval_result.get("groundingStatus") or "ungrounded",
            "usedRealtimeRetrieval": bool(retrieval_result.get("usedRealtimeRetrieval")),
            "structuredRecordCount": int(retrieval_result.get("structuredRecordCount") or 0),
            "structuredAggregations": retrieval_result.get("structuredAggregations") or {},
            "structuredRecords": retrieval_result.get("structuredRecords") or [],
        }
