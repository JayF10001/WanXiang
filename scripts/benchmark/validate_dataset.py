#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import math
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Iterable, Sequence

from jsonschema import validate


TASK_TYPES = ("retrieval", "citation", "report")


def _load_json(path: Path) -> dict[str, Any]:
    with path.open(encoding="utf-8") as f:
        return json.load(f)


def _iter_jsonl(path: Path) -> Iterable[dict[str, Any]]:
    with path.open(encoding="utf-8") as f:
        for line_no, line in enumerate(f, start=1):
            raw = line.strip()
            if not raw:
                continue
            try:
                yield json.loads(raw)
            except json.JSONDecodeError as exc:
                raise ValueError(f"{path}:{line_no} JSON 解析失败: {exc}") from exc


def _validate_jsonl(path: Path, schema: dict[str, Any]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for row in _iter_jsonl(path):
        validate(instance=row, schema=schema)
        rows.append(row)
    return rows


def _ensure_unique(rows: Sequence[dict[str, Any]], key: str, label: str) -> None:
    values = [str(row[key]) for row in rows]
    duplicates = sorted(item for item, count in Counter(values).items() if count > 1)
    if duplicates:
        raise ValueError(f"{label} 存在重复 {key}: {', '.join(duplicates)}")


def _check_source_refs(refs: Sequence[str], source_ids: set[str], context: str) -> None:
    missing = sorted(set(refs) - source_ids)
    if missing:
        raise ValueError(f"{context} 引用了不存在的 source_id: {', '.join(missing)}")


def _check_case_refs(refs: Sequence[str], case_ids: set[str], context: str) -> None:
    missing = sorted(set(refs) - case_ids)
    if missing:
        raise ValueError(f"{context} 引用了不存在的 case_id: {', '.join(missing)}")


def _expected_case_ids(case_rows: Sequence[dict[str, Any]], task_type: str) -> set[str]:
    return {str(row["case_id"]) for row in case_rows if row.get("task_type") == task_type}


def _resolve_optional_path(provided: Path | None, fallback: Path) -> Path | None:
    if provided is not None:
        return provided
    if fallback.exists():
        return fallback
    return None


def _has_complete_prediction_pack(dataset_dir: Path) -> bool:
    prediction_paths = [
        dataset_dir / "predictions" / "retrieval_predictions.jsonl",
        dataset_dir / "predictions" / "citation_predictions.jsonl",
        dataset_dir / "predictions" / "report_predictions.jsonl",
    ]
    return all(path.exists() for path in prediction_paths)


def _validate_source_rows(source_rows: Sequence[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    _ensure_unique(source_rows, "source_id", "sources")
    source_map = {str(row["source_id"]): row for row in source_rows}

    for row in source_rows:
        source_id = str(row["source_id"])
        for optional_ref in ("canonical_source_id", "parent_source_id"):
            ref = row.get(optional_ref)
            if ref and str(ref) not in source_map:
                raise ValueError(f"source {source_id} 的 {optional_ref} 不存在: {ref}")

    return source_map


def _validate_case_rows(
    case_rows: Sequence[dict[str, Any]],
    source_map: dict[str, dict[str, Any]],
) -> tuple[dict[str, set[str]], dict[str, dict[str, Any]], dict[str, str], dict[str, set[str]], dict[str, set[str]]]:
    _ensure_unique(case_rows, "case_id", "cases")
    case_ids_by_task: dict[str, set[str]] = {}
    case_map = {str(row["case_id"]): row for row in case_rows}
    event_to_split: dict[str, str] = {}
    event_to_cases: dict[str, set[str]] = defaultdict(set)
    split_to_events: dict[str, set[str]] = defaultdict(set)

    for task_type in TASK_TYPES:
        case_ids_by_task[task_type] = _expected_case_ids(case_rows, task_type)

    source_ids = set(source_map)
    for row in case_rows:
        case_id = str(row["case_id"])
        event_id = str(row["event_id"])
        split = str(row["split"])
        source_pool_ids = [str(item) for item in row.get("source_pool_ids", [])]

        _check_source_refs(source_pool_ids, source_ids, f"case {case_id}")
        for source_id in source_pool_ids:
            source_event_id = str(source_map[source_id]["event_id"])
            if source_event_id != event_id:
                raise ValueError(f"case {case_id} 使用了跨事件 source {source_id}: {source_event_id} != {event_id}")

        existing_split = event_to_split.get(event_id)
        if existing_split is None:
            event_to_split[event_id] = split
        elif existing_split != split:
            raise ValueError(f"event {event_id} 跨 split 泄漏: {existing_split} 与 {split}")

        event_to_cases[event_id].add(case_id)
        split_to_events[split].add(event_id)

    return case_ids_by_task, case_map, event_to_split, event_to_cases, split_to_events


def _validate_retrieval_labels(
    label_rows: Sequence[dict[str, Any]],
    case_ids: set[str],
    source_ids: set[str],
) -> None:
    _ensure_unique(label_rows, "case_id", "retrieval_labels")
    _check_case_refs([str(row["case_id"]) for row in label_rows], case_ids, "retrieval_labels")

    label_case_ids = {str(row["case_id"]) for row in label_rows}
    missing = sorted(case_ids - label_case_ids)
    if missing:
        raise ValueError(f"缺少 retrieval labels: {', '.join(missing)}")

    for row in label_rows:
        case_id = str(row["case_id"])
        for key in ("gold_source_ids", "preferred_source_ids", "excluded_source_ids", "hard_negative_source_ids"):
            _check_source_refs(row.get(key, []), source_ids, f"retrieval label {case_id}.{key}")
        for fact in row.get("gold_facts", []):
            claim_id = str(fact["claim_id"])
            _check_source_refs(
                fact.get("support_source_ids", []),
                source_ids,
                f"retrieval label {case_id}.gold_fact {claim_id}",
            )


def _validate_citation_labels(
    label_rows: Sequence[dict[str, Any]],
    case_ids: set[str],
    source_ids: set[str],
) -> dict[str, dict[str, Any]]:
    _ensure_unique(label_rows, "case_id", "citation_labels")
    _check_case_refs([str(row["case_id"]) for row in label_rows], case_ids, "citation_labels")

    label_case_ids = {str(row["case_id"]) for row in label_rows}
    missing = sorted(case_ids - label_case_ids)
    if missing:
        raise ValueError(f"缺少 citation labels: {', '.join(missing)}")

    citation_map = {str(row["case_id"]): row for row in label_rows}
    for row in label_rows:
        case_id = str(row["case_id"])
        _check_source_refs(row.get("gold_source_ids", []), source_ids, f"citation label {case_id}")
    return citation_map


def _validate_report_labels(
    label_rows: Sequence[dict[str, Any]],
    case_ids: set[str],
    source_ids: set[str],
) -> dict[str, dict[str, Any]]:
    _ensure_unique(label_rows, "case_id", "report_labels")
    _check_case_refs([str(row["case_id"]) for row in label_rows], case_ids, "report_labels")

    label_case_ids = {str(row["case_id"]) for row in label_rows}
    missing = sorted(case_ids - label_case_ids)
    if missing:
        raise ValueError(f"缺少 report labels: {', '.join(missing)}")

    report_map = {str(row["case_id"]): row for row in label_rows}
    for row in label_rows:
        case_id = str(row["case_id"])
        atomic_claim_ids = {str(item["claim_id"]) for item in row.get("gold_atomic_claims", [])}
        if len(atomic_claim_ids) != len(row.get("gold_atomic_claims", [])):
            raise ValueError(f"report label {case_id} 存在重复 claim_id")

        for item in row.get("gold_atomic_claims", []):
            claim_id = str(item["claim_id"])
            _check_source_refs(
                item.get("gold_source_ids", []),
                source_ids,
                f"report label {case_id}.gold_atomic_claim {claim_id}",
            )

        for item in row.get("gold_citation_map", []):
            claim_id = str(item["claim_id"])
            if claim_id not in atomic_claim_ids:
                raise ValueError(f"report label {case_id}.gold_citation_map 引用了不存在的 claim_id: {claim_id}")
            _check_source_refs(
                item.get("source_ids", []),
                source_ids,
                f"report label {case_id}.gold_citation_map {claim_id}",
            )
    return report_map


def _validate_prediction_rows(
    prediction_rows: Sequence[dict[str, Any]],
    case_ids_by_task: dict[str, set[str]],
    source_ids: set[str],
) -> None:
    expected_total = sum(len(case_ids_by_task[task_type]) for task_type in TASK_TYPES)
    if len(prediction_rows) != expected_total:
        raise ValueError(f"prediction 总数异常: 期望 {expected_total}，实际 {len(prediction_rows)}")

    by_task: dict[str, list[dict[str, Any]]] = {task_type: [] for task_type in TASK_TYPES}
    for row in prediction_rows:
        task_type = str(row["task_type"])
        if task_type not in TASK_TYPES:
            raise ValueError(f"未知 prediction task_type: {task_type}")
        by_task[task_type].append(row)

    for task_type in TASK_TYPES:
        rows = by_task[task_type]
        _ensure_unique(rows, "case_id", f"{task_type}_predictions")
        _check_case_refs([str(row["case_id"]) for row in rows], case_ids_by_task[task_type], f"{task_type}_predictions")
        row_case_ids = {str(row["case_id"]) for row in rows}
        missing = sorted(case_ids_by_task[task_type] - row_case_ids)
        if missing:
            raise ValueError(f"缺少 {task_type} predictions: {', '.join(missing)}")

        for row in rows:
            case_id = str(row["case_id"])
            if task_type == "retrieval":
                refs = [str(item["source_id"]) for item in row.get("ranked_sources", [])]
                _check_source_refs(refs, source_ids, f"retrieval prediction {case_id}")
            elif task_type == "citation":
                _check_source_refs(
                    row.get("predicted_source_ids", []),
                    source_ids,
                    f"citation prediction {case_id}.predicted_source_ids",
                )
                refs = [str(item["source_id"]) for item in row.get("ranked_sources", [])]
                _check_source_refs(refs, source_ids, f"citation prediction {case_id}.ranked_sources")
            elif task_type == "report":
                refs = [str(item["source_id"]) for item in row.get("citations", [])]
                _check_source_refs(refs, source_ids, f"report prediction {case_id}.citations")


def _validate_manifest(
    manifest_path: Path,
    schema_dir: Path,
    case_rows: Sequence[dict[str, Any]],
    source_rows: Sequence[dict[str, Any]],
    split_to_events: dict[str, set[str]],
) -> dict[str, Any]:
    manifest = _load_json(manifest_path)
    validate(instance=manifest, schema=_load_json(schema_dir / "benchmark-manifest.schema.json"))

    split_stats = manifest["split_stats"]
    for split in ("dev", "test"):
        expected = {
            "event_count": len(split_to_events.get(split, set())),
            "retrieval_case_count": sum(1 for row in case_rows if row["task_type"] == "retrieval" and row["split"] == split),
            "citation_case_count": sum(1 for row in case_rows if row["task_type"] == "citation" and row["split"] == split),
            "report_case_count": sum(1 for row in case_rows if row["task_type"] == "report" and row["split"] == split),
            "source_count": len(
                {
                    str(source["source_id"])
                    for source in source_rows
                    if str(source["event_id"]) in split_to_events.get(split, set())
                }
            ),
        }
        if split_stats[split] != expected:
            raise ValueError(f"manifest split_stats.{split} 与数据集统计不一致: {split_stats[split]} != {expected}")

    return manifest


def _validate_review_records(
    review_records_path: Path,
    schema_dir: Path,
    case_map: dict[str, dict[str, Any]],
    citation_label_map: dict[str, dict[str, Any]],
    report_label_map: dict[str, dict[str, Any]],
    event_to_cases: dict[str, set[str]],
) -> dict[str, Any]:
    rows = _validate_jsonl(review_records_path, _load_json(schema_dir / "review-records.schema.json"))
    _ensure_unique(rows, "record_id", "review_records")

    case_ids = set(case_map)
    _check_case_refs([str(row["case_id"]) for row in rows], case_ids, "review_records")

    by_case: dict[str, list[dict[str, Any]]] = defaultdict(list)
    second_review_events: set[str] = set()
    for row in rows:
        case_id = str(row["case_id"])
        event_id = str(row["event_id"])
        case = case_map[case_id]
        if str(case["event_id"]) != event_id:
            raise ValueError(f"review record {row['record_id']} 的 event_id 与 case 不一致")
        if str(case["task_type"]) != str(row["task_type"]):
            raise ValueError(f"review record {row['record_id']} 的 task_type 与 case 不一致")
        if str(case["split"]) != str(row["split"]):
            raise ValueError(f"review record {row['record_id']} 的 split 与 case 不一致")
        by_case[case_id].append(row)
        if row["review_status"] == "second_reviewed":
            second_review_events.add(event_id)

    missing_self_review = sorted(case_id for case_id in case_ids if not any(r["review_status"] == "self_reviewed" for r in by_case[case_id]))
    if missing_self_review:
        raise ValueError(f"以下 case 缺少 self_reviewed 记录: {', '.join(missing_self_review)}")

    minimum_second_review_events = math.ceil(len(event_to_cases) * 0.2)
    if len(second_review_events) < minimum_second_review_events:
        raise ValueError(
            f"第二人复核事件数不足: 期望至少 {minimum_second_review_events}，实际 {len(second_review_events)}"
        )

    for case_id, row in citation_label_map.items():
        if row["match_policy"] == "all_of":
            if not any(record["review_status"] == "adjudicated" for record in by_case[case_id]):
                raise ValueError(f"all_of citation case 缺少 adjudicated 记录: {case_id}")

    for case_id, row in report_label_map.items():
        has_multi_source = any(item["support_label"] == "multi_source_supported" for item in row.get("gold_atomic_claims", []))
        if has_multi_source and not any(record["review_status"] == "adjudicated" for record in by_case[case_id]):
            raise ValueError(f"multi_source_supported report case 缺少 adjudicated 记录: {case_id}")

    return {
        "review_record_count": len(rows),
        "second_review_event_count": len(second_review_events),
        "minimum_second_review_event_count": minimum_second_review_events,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate WanXiang benchmark dataset structure and cross-file references.")
    parser.add_argument(
        "--dataset-dir",
        type=Path,
        default=Path("docs/benchmark/benchmark_dataset"),
        help="Directory containing cases.jsonl, sources.jsonl, labels/ and predictions/.",
    )
    parser.add_argument(
        "--schema-dir",
        type=Path,
        default=Path("docs/benchmark/schema"),
        help="Directory containing JSON Schema files.",
    )
    parser.add_argument(
        "--manifest-path",
        type=Path,
        default=None,
        help="Optional benchmark manifest path. Defaults to <dataset-dir>/../manifest.json when present.",
    )
    parser.add_argument(
        "--review-records-path",
        type=Path,
        default=None,
        help="Optional review records path. Defaults to <dataset-dir>/reviews/review_records.jsonl when present.",
    )
    args = parser.parse_args()

    cases_schema = _load_json(args.schema_dir / "cases.schema.json")
    sources_schema = _load_json(args.schema_dir / "sources.schema.json")
    retrieval_schema = _load_json(args.schema_dir / "retrieval-labels.schema.json")
    citation_schema = _load_json(args.schema_dir / "citation-labels.schema.json")
    report_schema = _load_json(args.schema_dir / "report-labels.schema.json")
    predictions_schema = _load_json(args.schema_dir / "predictions.schema.json")

    case_rows = _validate_jsonl(args.dataset_dir / "cases.jsonl", cases_schema)
    source_rows = _validate_jsonl(args.dataset_dir / "sources.jsonl", sources_schema)
    retrieval_rows = _validate_jsonl(args.dataset_dir / "labels" / "retrieval_labels.jsonl", retrieval_schema)
    citation_rows = _validate_jsonl(args.dataset_dir / "labels" / "citation_labels.jsonl", citation_schema)
    report_rows = _validate_jsonl(args.dataset_dir / "labels" / "report_labels.jsonl", report_schema)
    retrieval_prediction_rows: list[dict[str, Any]] = []
    citation_prediction_rows: list[dict[str, Any]] = []
    report_prediction_rows: list[dict[str, Any]] = []
    has_predictions = _has_complete_prediction_pack(args.dataset_dir)
    if has_predictions:
        retrieval_prediction_rows = _validate_jsonl(
            args.dataset_dir / "predictions" / "retrieval_predictions.jsonl",
            predictions_schema,
        )
        citation_prediction_rows = _validate_jsonl(
            args.dataset_dir / "predictions" / "citation_predictions.jsonl",
            predictions_schema,
        )
        report_prediction_rows = _validate_jsonl(
            args.dataset_dir / "predictions" / "report_predictions.jsonl",
            predictions_schema,
        )

    source_map = _validate_source_rows(source_rows)
    case_ids_by_task, case_map, event_to_split, event_to_cases, split_to_events = _validate_case_rows(case_rows, source_map)
    _validate_retrieval_labels(retrieval_rows, case_ids_by_task["retrieval"], set(source_map))
    citation_label_map = _validate_citation_labels(citation_rows, case_ids_by_task["citation"], set(source_map))
    report_label_map = _validate_report_labels(report_rows, case_ids_by_task["report"], set(source_map))
    if has_predictions:
        _validate_prediction_rows(
            retrieval_prediction_rows + citation_prediction_rows + report_prediction_rows,
            case_ids_by_task,
            set(source_map),
        )

    manifest_path = _resolve_optional_path(args.manifest_path, args.dataset_dir.parent / "manifest.json")
    review_records_path = _resolve_optional_path(args.review_records_path, args.dataset_dir / "reviews" / "review_records.jsonl")

    manifest_summary: dict[str, Any] | None = None
    if manifest_path is not None:
        manifest = _validate_manifest(manifest_path, args.schema_dir, case_rows, source_rows, split_to_events)
        manifest_summary = {
            "benchmark_version": manifest["benchmark_version"],
            "baseline_count": len(manifest["baseline_roster"]),
            "data_freeze_date": manifest["data_freeze_date"],
        }

    review_summary: dict[str, Any] | None = None
    if review_records_path is not None:
        review_summary = _validate_review_records(
            review_records_path,
            args.schema_dir,
            case_map,
            citation_label_map,
            report_label_map,
            event_to_cases,
        )

    summary = {
        "case_count": len(case_rows),
        "event_count": len(event_to_split),
        "source_count": len(source_rows),
        "retrieval_case_count": len(case_ids_by_task["retrieval"]),
        "citation_case_count": len(case_ids_by_task["citation"]),
        "report_case_count": len(case_ids_by_task["report"]),
        "retrieval_prediction_count": len(retrieval_prediction_rows),
        "citation_prediction_count": len(citation_prediction_rows),
        "report_prediction_count": len(report_prediction_rows),
        "dev_event_count": len(split_to_events.get("dev", set())),
        "test_event_count": len(split_to_events.get("test", set())),
        "has_predictions": has_predictions,
        "status": "ok",
    }
    if manifest_summary is not None:
        summary["manifest"] = manifest_summary
    if review_summary is not None:
        summary["review_records"] = review_summary

    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
