#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, List, Sequence

from jsonschema import validate

SCORER_VERSION = "retrieval_scorer_v1"


@dataclass(frozen=True)
class RetrievalCase:
    case_id: str
    title: str


@dataclass(frozen=True)
class RetrievalLabel:
    case_id: str
    gold_source_ids: list[str]
    preferred_source_ids: list[str]
    excluded_source_ids: list[str]


@dataclass(frozen=True)
class RankedSource:
    source_id: str
    rank: int
    score: float


@dataclass(frozen=True)
class RetrievalPrediction:
    case_id: str
    ranked_sources: list[RankedSource]


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
    rows = []
    for row in _iter_jsonl(path):
        validate(instance=row, schema=schema)
        rows.append(row)
    return rows


def _discount(rank_index: int) -> float:
    return 1.0 / math.log2(rank_index + 2.0)


def _dcg(relevances: Sequence[int], k: int) -> float:
    return sum(rel * _discount(idx) for idx, rel in enumerate(relevances[:k]))


def _ndcg_at_k(ranked_source_ids: Sequence[str], gold_source_ids: set[str], k: int) -> float:
    actual = [1 if source_id in gold_source_ids else 0 for source_id in ranked_source_ids[:k]]
    ideal_len = min(len(gold_source_ids), k)
    ideal = [1] * ideal_len
    ideal_dcg = _dcg(ideal, k)
    if ideal_dcg == 0:
        return 0.0
    return _dcg(actual, k) / ideal_dcg


def _recall_at_k(ranked_source_ids: Sequence[str], gold_source_ids: set[str], k: int) -> float:
    if not gold_source_ids:
        return 0.0
    hits = sum(1 for source_id in ranked_source_ids[:k] if source_id in gold_source_ids)
    return hits / len(gold_source_ids)


def _mrr(ranked_source_ids: Sequence[str], gold_source_ids: set[str]) -> float:
    for idx, source_id in enumerate(ranked_source_ids, start=1):
        if source_id in gold_source_ids:
            return 1.0 / idx
    return 0.0


def _preferred_hit_rate(ranked_source_ids: Sequence[str], preferred_source_ids: set[str], k: int = 5) -> float | None:
    if not preferred_source_ids:
        return None
    top_k = ranked_source_ids[:k]
    return 1.0 if any(source_id in preferred_source_ids for source_id in top_k) else 0.0


def _as_case(row: dict[str, Any]) -> RetrievalCase:
    return RetrievalCase(case_id=str(row["case_id"]), title=str(row["title"]))


def _as_label(row: dict[str, Any]) -> RetrievalLabel:
    return RetrievalLabel(
        case_id=str(row["case_id"]),
        gold_source_ids=[str(item) for item in row.get("gold_source_ids", [])],
        preferred_source_ids=[str(item) for item in row.get("preferred_source_ids", [])],
        excluded_source_ids=[str(item) for item in row.get("excluded_source_ids", [])],
    )


def _as_prediction(row: dict[str, Any]) -> RetrievalPrediction:
    ranked_sources = [
        RankedSource(
            source_id=str(item["source_id"]),
            rank=int(item["rank"]),
            score=float(item["score"]),
        )
        for item in row.get("ranked_sources", [])
    ]
    ranked_sources.sort(key=lambda item: (item.rank, -item.score, item.source_id))
    return RetrievalPrediction(case_id=str(row["case_id"]), ranked_sources=ranked_sources)


def _load_retrieval_cases(rows: list[dict[str, Any]]) -> dict[str, RetrievalCase]:
    cases: dict[str, RetrievalCase] = {}
    for row in rows:
        if row.get("task_type") != "retrieval":
            continue
        case = _as_case(row)
        cases[case.case_id] = case
    return cases


def _load_retrieval_labels(rows: list[dict[str, Any]]) -> dict[str, RetrievalLabel]:
    labels: dict[str, RetrievalLabel] = {}
    for row in rows:
        label = _as_label(row)
        labels[label.case_id] = label
    return labels


def _load_retrieval_predictions(rows: list[dict[str, Any]]) -> dict[str, RetrievalPrediction]:
    predictions: dict[str, RetrievalPrediction] = {}
    for row in rows:
        if row.get("task_type") != "retrieval":
            continue
        prediction = _as_prediction(row)
        predictions[prediction.case_id] = prediction
    return predictions


def _round_metric(value: float | None) -> float | None:
    if value is None:
        return None
    return round(value, 6)


def score_case(case: RetrievalCase, label: RetrievalLabel, prediction: RetrievalPrediction | None) -> dict[str, Any]:
    errors: list[str] = []
    ranked_source_ids: list[str] = []

    if prediction is None:
        errors.append("missing_prediction")
    else:
        ranked_source_ids = [item.source_id for item in prediction.ranked_sources]
        duplicates = {source_id for source_id in ranked_source_ids if ranked_source_ids.count(source_id) > 1}
        if duplicates:
            errors.append(f"duplicate_ranked_sources:{','.join(sorted(duplicates))}")
        excluded_hits = sorted(set(ranked_source_ids) & set(label.excluded_source_ids))
        if excluded_hits:
            errors.append(f"excluded_sources_ranked:{','.join(excluded_hits)}")

    gold_source_ids = set(label.gold_source_ids)
    preferred_source_ids = set(label.preferred_source_ids)

    metrics = {
        "ndcg@10": _round_metric(_ndcg_at_k(ranked_source_ids, gold_source_ids, 10)),
        "recall@5": _round_metric(_recall_at_k(ranked_source_ids, gold_source_ids, 5)),
        "recall@20": _round_metric(_recall_at_k(ranked_source_ids, gold_source_ids, 20)),
        "mrr": _round_metric(_mrr(ranked_source_ids, gold_source_ids)),
        "preferred_source_hit_rate": _round_metric(_preferred_hit_rate(ranked_source_ids, preferred_source_ids, k=5)),
        "ranked_count": len(ranked_source_ids),
        "gold_count": len(gold_source_ids),
    }

    return {
        "case_id": case.case_id,
        "task_type": "retrieval",
        "scorer_version": SCORER_VERSION,
        "metrics": metrics,
        "errors": errors,
    }


def aggregate_results(score_rows: Sequence[dict[str, Any]]) -> dict[str, Any]:
    metric_keys = ["ndcg@10", "recall@5", "recall@20", "mrr", "preferred_source_hit_rate"]
    aggregate: dict[str, Any] = {"case_count": len(score_rows), "scorer_version": SCORER_VERSION}

    for key in metric_keys:
        values = [row["metrics"].get(key) for row in score_rows if row["metrics"].get(key) is not None]
        aggregate[key] = _round_metric(sum(values) / len(values)) if values else None

    aggregate["error_case_count"] = sum(1 for row in score_rows if row["errors"])
    return aggregate


def write_jsonl(path: Path, rows: Sequence[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")


def main() -> int:
    parser = argparse.ArgumentParser(description="Score retrieval benchmark predictions for WanXiang benchmark_dataset.")
    parser.add_argument(
        "--dataset-dir",
        type=Path,
        default=Path("docs/benchmark/benchmark_dataset"),
        help="Directory containing cases.jsonl, labels/, predictions/ and scores/.",
    )
    parser.add_argument(
        "--schema-dir",
        type=Path,
        default=Path("docs/benchmark/schema"),
        help="Directory containing JSON Schema files.",
    )
    parser.add_argument(
        "--output-path",
        type=Path,
        default=None,
        help="Path to write retrieval_scores.jsonl. Defaults to <dataset-dir>/scores/retrieval_scores.jsonl.",
    )
    parser.add_argument(
        "--summary-path",
        type=Path,
        default=None,
        help="Path to write aggregate summary JSON. Defaults to <dataset-dir>/scores/retrieval_summary.json.",
    )
    parser.add_argument(
        "--predictions-path",
        type=Path,
        default=None,
        help="Path to retrieval_predictions.jsonl. Defaults to <dataset-dir>/predictions/retrieval_predictions.jsonl.",
    )
    args = parser.parse_args()

    output_path = args.output_path or (args.dataset_dir / "scores" / "retrieval_scores.jsonl")
    summary_path = args.summary_path or (args.dataset_dir / "scores" / "retrieval_summary.json")
    predictions_path = args.predictions_path or (args.dataset_dir / "predictions" / "retrieval_predictions.jsonl")

    case_rows = _validate_jsonl(args.dataset_dir / "cases.jsonl", _load_json(args.schema_dir / "cases.schema.json"))
    label_rows = _validate_jsonl(
        args.dataset_dir / "labels" / "retrieval_labels.jsonl",
        _load_json(args.schema_dir / "retrieval-labels.schema.json"),
    )
    prediction_rows = _validate_jsonl(
        predictions_path,
        _load_json(args.schema_dir / "predictions.schema.json"),
    )

    cases = _load_retrieval_cases(case_rows)
    labels = _load_retrieval_labels(label_rows)
    predictions = _load_retrieval_predictions(prediction_rows)

    missing_labels = sorted(set(cases) - set(labels))
    if missing_labels:
        raise ValueError(f"缺少 retrieval label: {', '.join(missing_labels)}")

    score_rows = [score_case(case=case, label=labels[case_id], prediction=predictions.get(case_id)) for case_id, case in sorted(cases.items())]
    summary = aggregate_results(score_rows)

    write_jsonl(output_path, score_rows)
    summary_path.parent.mkdir(parents=True, exist_ok=True)
    with summary_path.open("w", encoding="utf-8") as f:
        json.dump(summary, f, ensure_ascii=False, indent=2)

    print(f"Wrote case scores to {output_path}")
    print(f"Wrote summary to {summary_path}")
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
