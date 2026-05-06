#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Sequence

from jsonschema import validate

SCORER_VERSION = "citation_scorer_v1"


@dataclass(frozen=True)
class CitationCase:
    case_id: str
    title: str


@dataclass(frozen=True)
class CitationLabel:
    case_id: str
    claim_id: str
    match_policy: str
    gold_source_ids: list[str]


@dataclass(frozen=True)
class RankedSource:
    source_id: str
    rank: int
    score: float


@dataclass(frozen=True)
class CitationPrediction:
    case_id: str
    predicted_source_ids: list[str]
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


def _round_metric(value: float | None) -> float | None:
    if value is None:
        return None
    return round(value, 6)


def _as_case(row: dict[str, Any]) -> CitationCase:
    return CitationCase(case_id=str(row["case_id"]), title=str(row["title"]))


def _as_label(row: dict[str, Any]) -> CitationLabel:
    return CitationLabel(
        case_id=str(row["case_id"]),
        claim_id=str(row["claim_id"]),
        match_policy=str(row["match_policy"]),
        gold_source_ids=[str(item) for item in row.get("gold_source_ids", [])],
    )


def _as_prediction(row: dict[str, Any]) -> CitationPrediction:
    ranked_sources = [
        RankedSource(
            source_id=str(item["source_id"]),
            rank=int(item["rank"]),
            score=float(item["score"]),
        )
        for item in row.get("ranked_sources", [])
    ]
    ranked_sources.sort(key=lambda item: (item.rank, -item.score, item.source_id))
    return CitationPrediction(
        case_id=str(row["case_id"]),
        predicted_source_ids=[str(item) for item in row.get("predicted_source_ids", [])],
        ranked_sources=ranked_sources,
    )


def _load_citation_cases(rows: list[dict[str, Any]]) -> dict[str, CitationCase]:
    cases: dict[str, CitationCase] = {}
    for row in rows:
        if row.get("task_type") != "citation":
            continue
        case = _as_case(row)
        cases[case.case_id] = case
    return cases


def _load_citation_labels(rows: list[dict[str, Any]]) -> dict[str, CitationLabel]:
    labels: dict[str, CitationLabel] = {}
    for row in rows:
        label = _as_label(row)
        labels[label.case_id] = label
    return labels


def _load_citation_predictions(rows: list[dict[str, Any]]) -> dict[str, CitationPrediction]:
    predictions: dict[str, CitationPrediction] = {}
    for row in rows:
        if row.get("task_type") != "citation":
            continue
        prediction = _as_prediction(row)
        predictions[prediction.case_id] = prediction
    return predictions


def _source_set_metrics(predicted: Sequence[str], gold: set[str]) -> tuple[float, float, float]:
    predicted_set = set(predicted)
    if not predicted_set and not gold:
        return 1.0, 1.0, 1.0
    if not predicted_set:
        return 0.0, 0.0, 0.0

    true_positive = len(predicted_set & gold)
    precision = true_positive / len(predicted_set)
    recall = true_positive / len(gold) if gold else 0.0
    if precision + recall == 0:
        f1 = 0.0
    else:
        f1 = 2 * precision * recall / (precision + recall)
    return precision, recall, f1


def _is_correct_top1(predicted: Sequence[str], match_policy: str, gold: set[str]) -> bool:
    if not predicted:
        return False
    top1 = predicted[0]
    if match_policy == "exact_single":
        return len(gold) == 1 and top1 in gold
    if match_policy == "any_of":
        return top1 in gold
    if match_policy == "all_of":
        return set(predicted) == gold
    raise ValueError(f"未知 match_policy: {match_policy}")


def _in_search_rate(ranked_sources: Sequence[RankedSource], gold: set[str]) -> float | None:
    if not ranked_sources:
        return None
    ranked_ids = {item.source_id for item in ranked_sources}
    return 1.0 if ranked_ids & gold else 0.0


def score_case(case: CitationCase, label: CitationLabel, prediction: CitationPrediction | None) -> dict[str, Any]:
    errors: list[str] = []
    predicted_source_ids: list[str] = []
    ranked_sources: list[RankedSource] = []

    if prediction is None:
        errors.append("missing_prediction")
    else:
        predicted_source_ids = prediction.predicted_source_ids
        ranked_sources = prediction.ranked_sources
        duplicates = {source_id for source_id in predicted_source_ids if predicted_source_ids.count(source_id) > 1}
        if duplicates:
            errors.append(f"duplicate_predicted_sources:{','.join(sorted(duplicates))}")

    gold_source_ids = set(label.gold_source_ids)
    precision, recall, f1 = _source_set_metrics(predicted_source_ids, gold_source_ids)

    metrics = {
        "attribution_accuracy@1": _round_metric(
            1.0 if _is_correct_top1(predicted_source_ids, label.match_policy, gold_source_ids) else 0.0
        ),
        "source_set_precision": _round_metric(precision),
        "source_set_recall": _round_metric(recall),
        "source_set_f1": _round_metric(f1),
        "in_search_rate": _round_metric(_in_search_rate(ranked_sources, gold_source_ids)),
        "predicted_count": len(predicted_source_ids),
        "gold_count": len(gold_source_ids),
    }

    return {
        "case_id": case.case_id,
        "task_type": "citation",
        "scorer_version": SCORER_VERSION,
        "metrics": metrics,
        "errors": errors,
    }


def aggregate_results(score_rows: Sequence[dict[str, Any]]) -> dict[str, Any]:
    metric_keys = [
        "attribution_accuracy@1",
        "source_set_precision",
        "source_set_recall",
        "source_set_f1",
        "in_search_rate",
    ]
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
    parser = argparse.ArgumentParser(description="Score citation benchmark predictions for WanXiang benchmark_dataset.")
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
        help="Path to write citation_scores.jsonl. Defaults to <dataset-dir>/scores/citation_scores.jsonl.",
    )
    parser.add_argument(
        "--summary-path",
        type=Path,
        default=None,
        help="Path to write aggregate summary JSON. Defaults to <dataset-dir>/scores/citation_summary.json.",
    )
    parser.add_argument(
        "--predictions-path",
        type=Path,
        default=None,
        help="Path to citation_predictions.jsonl. Defaults to <dataset-dir>/predictions/citation_predictions.jsonl.",
    )
    args = parser.parse_args()

    output_path = args.output_path or (args.dataset_dir / "scores" / "citation_scores.jsonl")
    summary_path = args.summary_path or (args.dataset_dir / "scores" / "citation_summary.json")
    predictions_path = args.predictions_path or (args.dataset_dir / "predictions" / "citation_predictions.jsonl")

    case_rows = _validate_jsonl(args.dataset_dir / "cases.jsonl", _load_json(args.schema_dir / "cases.schema.json"))
    label_rows = _validate_jsonl(
        args.dataset_dir / "labels" / "citation_labels.jsonl",
        _load_json(args.schema_dir / "citation-labels.schema.json"),
    )
    prediction_rows = _validate_jsonl(
        predictions_path,
        _load_json(args.schema_dir / "predictions.schema.json"),
    )

    cases = _load_citation_cases(case_rows)
    labels = _load_citation_labels(label_rows)
    predictions = _load_citation_predictions(prediction_rows)

    missing_labels = sorted(set(cases) - set(labels))
    if missing_labels:
        raise ValueError(f"缺少 citation label: {', '.join(missing_labels)}")

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
