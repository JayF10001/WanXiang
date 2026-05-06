#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any

from jsonschema import validate


REQUIRED_DOCS = [
    "README.md",
    "README.zh-CN.md",
    "methodology.md",
    "methodology.zh-CN.md",
    "results.md",
    "results.zh-CN.md",
    "reproduce_public.md",
    "release_checklist.md",
    "release_checklist_short.md",
    "release_checklist_short.zh-CN.md",
    "LICENSE_CODE",
    "LICENSE_DATASET",
]


def _load_json(path: Path) -> dict[str, Any]:
    with path.open(encoding="utf-8") as f:
        return json.load(f)


def _iter_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    with path.open(encoding="utf-8") as f:
        for line in f:
            raw = line.strip()
            if not raw:
                continue
            rows.append(json.loads(raw))
    return rows


def _validate_jsonl(path: Path, schema: dict[str, Any]) -> list[dict[str, Any]]:
    rows = _iter_jsonl(path)
    for row in rows:
        validate(instance=row, schema=schema)
    return rows


def _assert(cond: bool, message: str) -> None:
    if not cond:
        raise ValueError(message)


def _contains_forbidden_public_content(public_root: Path) -> list[str]:
    forbidden_hits: list[str] = []
    for path in public_root.rglob("*"):
        if not path.is_file():
            continue
        relative = str(path.relative_to(public_root))
        if "review_records" in relative:
            forbidden_hits.append(relative)
        if re.search(r"baselines/.+/predictions", relative):
            forbidden_hits.append(relative)
    return forbidden_hits


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate the public benchmark package exported from benchmark_v1.")
    parser.add_argument(
        "--internal-root",
        type=Path,
        default=Path("docs/benchmark/benchmark_v1"),
        help="Internal benchmark v1 root.",
    )
    parser.add_argument(
        "--public-root",
        type=Path,
        default=Path("docs/benchmark/public_v1"),
        help="Public benchmark package root.",
    )
    parser.add_argument(
        "--schema-dir",
        type=Path,
        default=Path("docs/benchmark/schema"),
        help="Schema directory.",
    )
    args = parser.parse_args()

    manifest_public = _load_json(args.public_root / "manifest_public.json")
    validate(instance=manifest_public, schema=_load_json(args.schema_dir / "benchmark-public-manifest.schema.json"))

    internal_release = _load_json(args.internal_root / "release" / "release_summary.json")

    cases = _validate_jsonl(args.public_root / "dataset_public" / "cases.jsonl", _load_json(args.schema_dir / "cases.schema.json"))
    sources = _validate_jsonl(args.public_root / "dataset_public" / "sources.jsonl", _load_json(args.schema_dir / "sources.schema.json"))
    retrieval_labels = _validate_jsonl(
        args.public_root / "dataset_public" / "labels" / "retrieval_labels.jsonl",
        _load_json(args.schema_dir / "retrieval-labels.schema.json"),
    )
    citation_labels = _validate_jsonl(
        args.public_root / "dataset_public" / "labels" / "citation_labels.jsonl",
        _load_json(args.schema_dir / "citation-labels.schema.json"),
    )
    report_labels = _validate_jsonl(
        args.public_root / "dataset_public" / "labels" / "report_labels.jsonl",
        _load_json(args.schema_dir / "report-labels.schema.json"),
    )

    _assert(all(row["split"] == "dev" for row in cases), "public_v1 中存在非 dev case")

    event_ids = {str(row["event_id"]) for row in cases}
    _assert(all(str(row["event_id"]) in event_ids for row in sources), "dataset_public 中存在跨事件 source")

    expected_dev_stats = {
        "event_count": len(event_ids),
        "retrieval_case_count": sum(1 for row in cases if row["task_type"] == "retrieval"),
        "citation_case_count": sum(1 for row in cases if row["task_type"] == "citation"),
        "report_case_count": sum(1 for row in cases if row["task_type"] == "report"),
        "source_count": len(sources),
    }
    _assert(manifest_public["split_stats"]["dev"] == expected_dev_stats, "manifest_public 的 dev 统计与 dataset_public 不一致")

    internal_hidden_stats = internal_release["dataset_summary"]
    expected_hidden_stats = {
        "event_count": internal_hidden_stats["test_event_count"],
        "retrieval_case_count": internal_hidden_stats["retrieval_case_count"] - expected_dev_stats["retrieval_case_count"],
        "citation_case_count": internal_hidden_stats["citation_case_count"] - expected_dev_stats["citation_case_count"],
        "report_case_count": internal_hidden_stats["report_case_count"] - expected_dev_stats["report_case_count"],
        "source_count": internal_hidden_stats["source_count"] - expected_dev_stats["source_count"],
    }
    _assert(manifest_public["hidden_test_stats"] == expected_hidden_stats, "manifest_public 的 hidden_test_stats 与内部统计不一致")

    forbidden_hits = _contains_forbidden_public_content(args.public_root)
    _assert(not forbidden_hits, f"public_v1 中发现不应公开的路径: {', '.join(forbidden_hits)}")

    _assert(not (args.public_root / "dataset_public" / "reviews" / "review_records.jsonl").exists(), "public_v1 不应包含 review_records.jsonl")
    _assert(not (args.public_root / "baselines").exists(), "public_v1 不应包含 baselines 目录")

    baseline_map = {row["baseline_id"]: row for row in manifest_public["baseline_results"]}
    for baseline_id, row in internal_release["baseline_results"].items():
        public_row = baseline_map.get(baseline_id)
        _assert(public_row is not None, f"public_v1 缺少 baseline 结果: {baseline_id}")
        scores = row["official_scores"]
        _assert(abs(public_row["retrieval"] - scores["retrieval"]) < 1e-9, f"{baseline_id} retrieval 分数不一致")
        _assert(abs(public_row["citation"] - scores["citation"]) < 1e-9, f"{baseline_id} citation 分数不一致")
        _assert(abs(public_row["report_faithfulness"] - scores["report_faithfulness"]) < 1e-9, f"{baseline_id} report 分数不一致")
        _assert(abs(public_row["overall"] - scores["overall"]) < 1e-9, f"{baseline_id} overall 分数不一致")

    for doc_name in REQUIRED_DOCS:
        _assert((args.public_root / doc_name).exists(), f"缺少公开文档: {doc_name}")

    results_en = (args.public_root / "results.md").read_text(encoding="utf-8")
    results_zh = (args.public_root / "results.zh-CN.md").read_text(encoding="utf-8")
    for row in manifest_public["baseline_results"]:
        display_name = row["display_name"]
        _assert(display_name in results_en and display_name in results_zh, f"结果文档缺少 baseline 名称: {display_name}")
        for key in ("retrieval", "citation", "report_faithfulness", "overall"):
            formatted = f"{row[key]:.6f}"
            _assert(formatted in results_en and formatted in results_zh, f"结果文档缺少分数字符串: {display_name} {formatted}")

    examples_dir = args.public_root / "examples"
    for filename in ("retrieval_example.json", "citation_example.json", "report_example.json"):
        bundle = _load_json(examples_dir / filename)
        case_id = bundle["case"]["case_id"]
        _assert(bundle["case"]["split"] == "dev", f"example 中出现非 dev case: {case_id}")
        source_ids = {row["source_id"] for row in sources}
        for source in bundle["sources"]:
            _assert(source["source_id"] in source_ids, f"example 中引用了未公开 source: {source['source_id']}")

    summary = {
        "published_case_count": len(cases),
        "published_event_count": len(event_ids),
        "published_source_count": len(sources),
        "published_retrieval_label_count": len(retrieval_labels),
        "published_citation_label_count": len(citation_labels),
        "published_report_label_count": len(report_labels),
        "status": "ok",
    }
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
