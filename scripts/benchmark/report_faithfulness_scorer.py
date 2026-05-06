#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
from collections import Counter
from dataclasses import dataclass
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any, Iterable, Sequence

from jsonschema import validate

SCORER_VERSION = "report_faithfulness_scorer_v1"


def _normalize_text(text: str) -> str:
    value = str(text or "").strip()
    value = re.sub(r"\s+", "", value)
    return value


@dataclass(frozen=True)
class ReportCase:
    case_id: str
    title: str


@dataclass(frozen=True)
class GoldAtomicClaim:
    claim_id: str
    text: str
    normalized_text: str
    claim_kind: str
    support_label: str
    gold_source_ids: list[str]
    must_be_cited: bool


@dataclass(frozen=True)
class ReportLabel:
    case_id: str
    gold_atomic_claims: list[GoldAtomicClaim]
    gold_citation_map: dict[str, list[str]]


@dataclass(frozen=True)
class ReportCitation:
    source_id: str
    claim_refs: list[str]


@dataclass(frozen=True)
class PredictedClaim:
    text: str
    normalized_text: str
    predicted_layer: str


@dataclass(frozen=True)
class ReportPrediction:
    case_id: str
    report_text: str
    predicted_claims: list[PredictedClaim]
    citations: list[ReportCitation]


@dataclass(frozen=True)
class MatchedClaim:
    predicted_claim: PredictedClaim
    gold_claim: GoldAtomicClaim | None
    match_score: float


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


def _as_case(row: dict[str, Any]) -> ReportCase:
    return ReportCase(case_id=str(row["case_id"]), title=str(row["title"]))


def _as_label(row: dict[str, Any]) -> ReportLabel:
    claims = [
        GoldAtomicClaim(
            claim_id=str(item["claim_id"]),
            text=str(item["text"]),
            normalized_text=_normalize_text(item["text"]),
            claim_kind=str(item["claim_kind"]),
            support_label=str(item["support_label"]),
            gold_source_ids=[str(source_id) for source_id in item.get("gold_source_ids", [])],
            must_be_cited=bool(item["must_be_cited"]),
        )
        for item in row.get("gold_atomic_claims", [])
    ]
    citation_map = {
        str(item["claim_id"]): [str(source_id) for source_id in item.get("source_ids", [])]
        for item in row.get("gold_citation_map", [])
    }
    return ReportLabel(case_id=str(row["case_id"]), gold_atomic_claims=claims, gold_citation_map=citation_map)


def _claims_from_layer(items: Sequence[str], layer_name: str) -> list[PredictedClaim]:
    return [
        PredictedClaim(
            text=str(item),
            normalized_text=_normalize_text(item),
            predicted_layer=layer_name,
        )
        for item in items
        if _normalize_text(item)
    ]


def _as_prediction(row: dict[str, Any]) -> ReportPrediction:
    predicted_claims = []
    predicted_claims.extend(_claims_from_layer(row.get("facts", []), "fact"))
    predicted_claims.extend(_claims_from_layer(row.get("to_verify", []), "to_verify"))
    predicted_claims.extend(_claims_from_layer(row.get("analysis", []), "analysis"))
    citations = [
        ReportCitation(
            source_id=str(item["source_id"]),
            claim_refs=[str(claim_id) for claim_id in item.get("claim_refs", [])],
        )
        for item in row.get("citations", [])
    ]
    return ReportPrediction(
        case_id=str(row["case_id"]),
        report_text=str(row.get("report_text") or ""),
        predicted_claims=predicted_claims,
        citations=citations,
    )


def _load_report_cases(rows: list[dict[str, Any]]) -> dict[str, ReportCase]:
    cases: dict[str, ReportCase] = {}
    for row in rows:
        if row.get("task_type") != "report":
            continue
        case = _as_case(row)
        cases[case.case_id] = case
    return cases


def _load_report_labels(rows: list[dict[str, Any]]) -> dict[str, ReportLabel]:
    labels: dict[str, ReportLabel] = {}
    for row in rows:
        label = _as_label(row)
        labels[label.case_id] = label
    return labels


def _load_report_predictions(rows: list[dict[str, Any]]) -> dict[str, ReportPrediction]:
    predictions: dict[str, ReportPrediction] = {}
    for row in rows:
        if row.get("task_type") != "report":
            continue
        prediction = _as_prediction(row)
        predictions[prediction.case_id] = prediction
    return predictions


def _claim_match_score(predicted_text: str, gold_text: str) -> float:
    if not predicted_text or not gold_text:
        return 0.0
    if predicted_text == gold_text:
        return 1.0
    if predicted_text in gold_text or gold_text in predicted_text:
        shorter = min(len(predicted_text), len(gold_text))
        longer = max(len(predicted_text), len(gold_text))
        return 0.9 + (shorter / longer) * 0.09
    return SequenceMatcher(a=predicted_text, b=gold_text).ratio()


def _match_predicted_claims(
    predicted_claims: Sequence[PredictedClaim],
    gold_claims: Sequence[GoldAtomicClaim],
    threshold: float = 0.72,
) -> list[MatchedClaim]:
    unmatched_gold = {claim.claim_id: claim for claim in gold_claims}
    matched: list[MatchedClaim] = []

    for predicted_claim in predicted_claims:
        best_claim: GoldAtomicClaim | None = None
        best_score = 0.0
        for gold_claim in unmatched_gold.values():
            score = _claim_match_score(predicted_claim.normalized_text, gold_claim.normalized_text)
            if score > best_score:
                best_score = score
                best_claim = gold_claim

        if best_claim is not None and best_score >= threshold:
            matched.append(MatchedClaim(predicted_claim=predicted_claim, gold_claim=best_claim, match_score=best_score))
            unmatched_gold.pop(best_claim.claim_id, None)
        else:
            matched.append(MatchedClaim(predicted_claim=predicted_claim, gold_claim=None, match_score=best_score))

    return matched


def _citation_backed(
    claim: GoldAtomicClaim,
    label: ReportLabel,
    prediction: ReportPrediction,
) -> bool:
    if not claim.must_be_cited:
        return True

    gold_sources = set(label.gold_citation_map.get(claim.claim_id) or claim.gold_source_ids)
    if not gold_sources:
        return False

    for citation in prediction.citations:
        if claim.claim_id in citation.claim_refs:
            if not gold_sources or citation.source_id in gold_sources:
                return True

    predicted_source_ids = {citation.source_id for citation in prediction.citations}
    return bool(predicted_source_ids & gold_sources)


def score_case(case: ReportCase, label: ReportLabel, prediction: ReportPrediction | None) -> dict[str, Any]:
    errors: list[str] = []
    predicted_claims: list[PredictedClaim] = []
    report_text = ""
    citations: list[ReportCitation] = []

    if prediction is None:
        errors.append("missing_prediction")
    else:
        predicted_claims = prediction.predicted_claims
        report_text = prediction.report_text
        citations = prediction.citations

    supported = 0
    unsupported = 0
    unverifiable = 0
    analysis_only = 0
    layer_correct = 0
    citation_required_count = 0
    citation_backed_count = 0

    matched_claims = _match_predicted_claims(predicted_claims, label.gold_atomic_claims)
    matched_claim_details: list[dict[str, Any]] = []

    for matched_claim in matched_claims:
        predicted_claim = matched_claim.predicted_claim
        gold_claim = matched_claim.gold_claim
        classification = "unsupported"
        if gold_claim is None:
            unsupported += 1
            matched_claim_details.append(
                {
                    "predicted_text": predicted_claim.text,
                    "predicted_layer": predicted_claim.predicted_layer,
                    "matched": False,
                    "matched_claim_id": None,
                    "matched_gold_text": None,
                    "matched_gold_kind": None,
                    "matched_support_label": None,
                    "match_score": _round_metric(matched_claim.match_score),
                    "classification": classification,
                    "citation_backed": None,
                }
            )
            continue

        if predicted_claim.predicted_layer == gold_claim.claim_kind:
            layer_correct += 1

        citation_backed = None
        if gold_claim.must_be_cited:
            citation_required_count += 1
            if prediction is not None and _citation_backed(gold_claim, label, prediction):
                citation_backed_count += 1
                citation_backed = True
            else:
                citation_backed = False

        if gold_claim.support_label in {"direct_supported", "multi_source_supported"}:
            supported += 1
            classification = "supported"
        elif gold_claim.support_label == "unverifiable":
            unverifiable += 1
            classification = "unverifiable"
        elif gold_claim.support_label == "analysis_only":
            analysis_only += 1
            classification = "analysis_only"
        else:
            unsupported += 1
            classification = "unsupported"

        matched_claim_details.append(
            {
                "predicted_text": predicted_claim.text,
                "predicted_layer": predicted_claim.predicted_layer,
                "matched": True,
                "matched_claim_id": gold_claim.claim_id,
                "matched_gold_text": gold_claim.text,
                "matched_gold_kind": gold_claim.claim_kind,
                "matched_support_label": gold_claim.support_label,
                "match_score": _round_metric(matched_claim.match_score),
                "classification": classification,
                "citation_backed": citation_backed,
            }
        )

    total_claims = len(predicted_claims)
    claim_support_rate = supported / total_claims if total_claims else 0.0
    unsupported_claim_rate = unsupported / total_claims if total_claims else 0.0
    unverifiable_claim_rate = unverifiable / total_claims if total_claims else 0.0
    layer_separation_accuracy = layer_correct / total_claims if total_claims else 0.0
    citation_backed_claim_rate = (
        citation_backed_count / citation_required_count if citation_required_count else None
    )
    respond_ratio = 1.0 if report_text.strip() else 0.0

    claim_counter = Counter(claim.normalized_text for claim in predicted_claims)
    duplicate_claims = {text for text, count in claim_counter.items() if count > 1}
    if duplicate_claims:
        errors.append("duplicate_predicted_claims")

    metrics = {
        "claim_support_rate": _round_metric(claim_support_rate),
        "unsupported_claim_rate": _round_metric(unsupported_claim_rate),
        "unverifiable_claim_rate": _round_metric(unverifiable_claim_rate),
        "citation_backed_claim_rate": _round_metric(citation_backed_claim_rate),
        "layer_separation_accuracy": _round_metric(layer_separation_accuracy),
        "respond_ratio": _round_metric(respond_ratio),
        "claims_per_report": total_claims,
        "analysis_only_claim_count": analysis_only,
        "citation_count": len(citations),
        "matched_claim_count": sum(1 for item in matched_claims if item.gold_claim is not None),
        "mean_claim_match_score": _round_metric(
            sum(item.match_score for item in matched_claims) / len(matched_claims) if matched_claims else None
        ),
    }

    return {
        "case_id": case.case_id,
        "task_type": "report",
        "scorer_version": SCORER_VERSION,
        "metrics": metrics,
        "matched_claims": matched_claim_details,
        "errors": errors,
    }


def aggregate_results(score_rows: Sequence[dict[str, Any]]) -> dict[str, Any]:
    metric_keys = [
        "claim_support_rate",
        "unsupported_claim_rate",
        "unverifiable_claim_rate",
        "citation_backed_claim_rate",
        "layer_separation_accuracy",
        "respond_ratio",
        "claims_per_report",
        "matched_claim_count",
        "mean_claim_match_score",
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
    parser = argparse.ArgumentParser(description="Score report benchmark predictions for WanXiang benchmark_dataset.")
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
        help="Path to write report_scores.jsonl. Defaults to <dataset-dir>/scores/report_scores.jsonl.",
    )
    parser.add_argument(
        "--summary-path",
        type=Path,
        default=None,
        help="Path to write aggregate summary JSON. Defaults to <dataset-dir>/scores/report_summary.json.",
    )
    parser.add_argument(
        "--predictions-path",
        type=Path,
        default=None,
        help="Path to report_predictions.jsonl. Defaults to <dataset-dir>/predictions/report_predictions.jsonl.",
    )
    args = parser.parse_args()

    output_path = args.output_path or (args.dataset_dir / "scores" / "report_scores.jsonl")
    summary_path = args.summary_path or (args.dataset_dir / "scores" / "report_summary.json")
    predictions_path = args.predictions_path or (args.dataset_dir / "predictions" / "report_predictions.jsonl")

    case_rows = _validate_jsonl(args.dataset_dir / "cases.jsonl", _load_json(args.schema_dir / "cases.schema.json"))
    label_rows = _validate_jsonl(
        args.dataset_dir / "labels" / "report_labels.jsonl",
        _load_json(args.schema_dir / "report-labels.schema.json"),
    )
    prediction_rows = _validate_jsonl(
        predictions_path,
        _load_json(args.schema_dir / "predictions.schema.json"),
    )

    cases = _load_report_cases(case_rows)
    labels = _load_report_labels(label_rows)
    predictions = _load_report_predictions(prediction_rows)

    missing_labels = sorted(set(cases) - set(labels))
    if missing_labels:
        raise ValueError(f"缺少 report label: {', '.join(missing_labels)}")

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
