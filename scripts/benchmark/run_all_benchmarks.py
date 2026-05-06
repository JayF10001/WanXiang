#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path
from typing import Any


DEFAULT_STAGE_SCORE_KEYS = {
    "retrieval": "ndcg@10",
    "citation": "attribution_accuracy@1",
    "report_faithfulness": "claim_support_rate",
}

DEFAULT_OVERALL_WEIGHTS = {
    "retrieval": 0.3,
    "citation": 0.3,
    "report_faithfulness": 0.4,
}


def _run_step(name: str, cmd: list[str]) -> str:
    print(f"[run] {name}: {' '.join(cmd)}", flush=True)
    completed = subprocess.run(cmd, check=True, text=True, capture_output=True)
    if completed.stdout:
        print(completed.stdout, end="")
    if completed.stderr:
        print(completed.stderr, end="", file=sys.stderr)
    return completed.stdout


def _load_json(path: Path) -> dict[str, Any]:
    with path.open(encoding="utf-8") as f:
        return json.load(f)


def _load_last_json_block(output: str) -> dict[str, Any]:
    lines = [line for line in output.splitlines() if line.strip()]
    for index in range(len(lines)):
        candidate = "\n".join(lines[index:])
        try:
            return json.loads(candidate)
        except json.JSONDecodeError:
            continue
    raise ValueError("无法从脚本输出中解析 JSON 结果")


def _round_metric(value: float) -> float:
    return round(value, 6)


def _build_command(
    script_path: Path,
    dataset_dir: Path,
    schema_dir: Path,
    *,
    predictions_path: Path | None = None,
    output_path: Path | None = None,
    summary_path: Path | None = None,
    manifest_path: Path | None = None,
    review_records_path: Path | None = None,
) -> list[str]:
    cmd = [
        sys.executable,
        str(script_path),
        "--dataset-dir",
        str(dataset_dir),
        "--schema-dir",
        str(schema_dir),
    ]
    if predictions_path is not None:
        cmd.extend(["--predictions-path", str(predictions_path)])
    if output_path is not None:
        cmd.extend(["--output-path", str(output_path)])
    if summary_path is not None:
        cmd.extend(["--summary-path", str(summary_path)])
    if manifest_path is not None:
        cmd.extend(["--manifest-path", str(manifest_path)])
    if review_records_path is not None:
        cmd.extend(["--review-records-path", str(review_records_path)])
    return cmd


def _compute_stage_scores(
    retrieval_summary: dict[str, Any],
    citation_summary: dict[str, Any],
    report_summary: dict[str, Any],
) -> dict[str, float | None]:
    return {
        "retrieval": retrieval_summary.get(DEFAULT_STAGE_SCORE_KEYS["retrieval"]),
        "citation": citation_summary.get(DEFAULT_STAGE_SCORE_KEYS["citation"]),
        "report_faithfulness": report_summary.get(DEFAULT_STAGE_SCORE_KEYS["report_faithfulness"]),
    }


def _compute_overall_score(stage_scores: dict[str, float | None]) -> float | None:
    if any(stage_scores.get(key) is None for key in DEFAULT_OVERALL_WEIGHTS):
        return None
    value = sum(float(stage_scores[key]) * DEFAULT_OVERALL_WEIGHTS[key] for key in DEFAULT_OVERALL_WEIGHTS)
    return _round_metric(value)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Validate the benchmark dataset and run retrieval, citation, and report scorers."
    )
    parser.add_argument(
        "--dataset-dir",
        type=Path,
        default=Path("docs/benchmark/benchmark_dataset"),
        help="Directory containing benchmark dataset files.",
    )
    parser.add_argument(
        "--schema-dir",
        type=Path,
        default=Path("docs/benchmark/schema"),
        help="Directory containing JSON Schema files.",
    )
    parser.add_argument(
        "--predictions-dir",
        type=Path,
        default=None,
        help="Directory containing retrieval/citation/report prediction JSONL files. Defaults to <dataset-dir>/predictions.",
    )
    parser.add_argument(
        "--scores-dir",
        type=Path,
        default=None,
        help="Directory to write score outputs. Defaults to <dataset-dir>/scores.",
    )
    parser.add_argument(
        "--summary-path",
        type=Path,
        default=None,
        help="Path to write the combined benchmark summary. Defaults to <scores-dir>/benchmark_summary.json.",
    )
    parser.add_argument(
        "--manifest-path",
        type=Path,
        default=None,
        help="Optional benchmark manifest path.",
    )
    parser.add_argument(
        "--review-records-path",
        type=Path,
        default=None,
        help="Optional review records path.",
    )
    args = parser.parse_args()

    base_dir = Path(__file__).resolve().parent
    predictions_dir = args.predictions_dir or (args.dataset_dir / "predictions")
    scores_dir = args.scores_dir or (args.dataset_dir / "scores")
    summary_path = args.summary_path or (scores_dir / "benchmark_summary.json")

    validation_output = _run_step(
        "validate_dataset",
        _build_command(
            base_dir / "validate_dataset.py",
            args.dataset_dir,
            args.schema_dir,
            manifest_path=args.manifest_path,
            review_records_path=args.review_records_path,
        ),
    )

    retrieval_score_path = scores_dir / "retrieval_scores.jsonl"
    retrieval_summary_path = scores_dir / "retrieval_summary.json"
    citation_score_path = scores_dir / "citation_scores.jsonl"
    citation_summary_path = scores_dir / "citation_summary.json"
    report_score_path = scores_dir / "report_scores.jsonl"
    report_summary_path = scores_dir / "report_summary.json"

    _run_step(
        "retrieval",
        _build_command(
            base_dir / "retrieval_scorer.py",
            args.dataset_dir,
            args.schema_dir,
            predictions_path=predictions_dir / "retrieval_predictions.jsonl",
            output_path=retrieval_score_path,
            summary_path=retrieval_summary_path,
        ),
    )
    _run_step(
        "citation",
        _build_command(
            base_dir / "citation_scorer.py",
            args.dataset_dir,
            args.schema_dir,
            predictions_path=predictions_dir / "citation_predictions.jsonl",
            output_path=citation_score_path,
            summary_path=citation_summary_path,
        ),
    )
    _run_step(
        "report_faithfulness",
        _build_command(
            base_dir / "report_faithfulness_scorer.py",
            args.dataset_dir,
            args.schema_dir,
            predictions_path=predictions_dir / "report_predictions.jsonl",
            output_path=report_score_path,
            summary_path=report_summary_path,
        ),
    )

    validation_summary = _load_last_json_block(validation_output)
    retrieval_summary = _load_json(retrieval_summary_path)
    citation_summary = _load_json(citation_summary_path)
    report_summary = _load_json(report_summary_path)

    manifest: dict[str, Any] | None = None
    if args.manifest_path is not None and args.manifest_path.exists():
        manifest = _load_json(args.manifest_path)
    else:
        default_manifest_path = args.dataset_dir.parent / "manifest.json"
        if default_manifest_path.exists():
            manifest = _load_json(default_manifest_path)

    stage_scores = _compute_stage_scores(retrieval_summary, citation_summary, report_summary)
    overall_score = _compute_overall_score(stage_scores)

    combined_summary = {
        "benchmark_version": manifest.get("benchmark_version") if manifest else None,
        "dataset_dir": str(args.dataset_dir),
        "predictions_dir": str(predictions_dir),
        "scores_dir": str(scores_dir),
        "schema_dir": str(args.schema_dir),
        "validate_dataset": validation_summary,
        "retrieval": retrieval_summary,
        "citation": citation_summary,
        "report_faithfulness": report_summary,
        "official_stage_scores": stage_scores,
        "official_score_formula": manifest.get("official_score_formula") if manifest else {
            "retrieval_stage_score": "nDCG@10",
            "citation_stage_score": "Attribution Accuracy@1",
            "report_stage_score": "Claim Support Rate",
            "overall_formula": "0.3 * retrieval + 0.3 * citation + 0.4 * report",
        },
        "official_overall_score": overall_score,
        "scorer_versions": {
            "retrieval": retrieval_summary.get("scorer_version"),
            "citation": citation_summary.get("scorer_version"),
            "report_faithfulness": report_summary.get("scorer_version"),
        },
    }

    summary_path.parent.mkdir(parents=True, exist_ok=True)
    with summary_path.open("w", encoding="utf-8") as f:
        json.dump(combined_summary, f, ensure_ascii=False, indent=2)

    print(f"Wrote combined summary to {summary_path}")
    print(json.dumps(combined_summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
