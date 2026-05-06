#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path
from typing import Any


DRIFT_THRESHOLD = 0.005


def _run_command(cmd: list[str], name: str) -> str:
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


def _round_metric(value: float) -> float:
    return round(value, 6)


def _stage_score_table(summary: dict[str, Any]) -> dict[str, float | None]:
    return {
        "retrieval": summary["official_stage_scores"]["retrieval"],
        "citation": summary["official_stage_scores"]["citation"],
        "report_faithfulness": summary["official_stage_scores"]["report_faithfulness"],
        "overall": summary["official_overall_score"],
    }


def _build_release_report(
    manifest: dict[str, Any],
    dataset_summary: dict[str, Any],
    baseline_results: dict[str, Any],
) -> str:
    lines = [
        "# WanXiang Benchmark v1 Release Report",
        "",
        "## Summary",
        "",
        f"- Benchmark version: `{manifest['benchmark_version']}`",
        f"- Release target: `{manifest['release_target']}`",
        f"- Freeze date: `{manifest['data_freeze_date']}`",
        f"- Official task types: `{', '.join(manifest['official_task_types'])}`",
        f"- Dataset size: `{dataset_summary['event_count']}` events / `{dataset_summary['case_count']}` cases / `{dataset_summary['source_count']}` sources",
        "",
        "## Review Policy",
        "",
        "- `100%` 样本完成 self review",
        "- 至少 `20%` 事件完成 second review",
        "- `all_of` citation 与 `multi_source_supported` report 样本全部进入 adjudication",
        "",
        "## Score Formula",
        "",
        f"- Retrieval Stage Score = `{manifest['official_score_formula']['retrieval_stage_score']}`",
        f"- Citation Stage Score = `{manifest['official_score_formula']['citation_stage_score']}`",
        f"- Report Stage Score = `{manifest['official_score_formula']['report_stage_score']}`",
        f"- Overall = `{manifest['official_score_formula']['overall_formula']}`",
        "",
        "## Baseline Results",
        "",
        "| Baseline | Retrieval | Citation | Report | Overall | Stable |",
        "| --- | ---: | ---: | ---: | ---: | --- |",
    ]

    for baseline_id, result in baseline_results.items():
        lines.append(
            f"| {result['display_name']} | {result['official_scores']['retrieval']:.6f} | "
            f"{result['official_scores']['citation']:.6f} | "
            f"{result['official_scores']['report_faithfulness']:.6f} | "
            f"{result['official_scores']['overall']:.6f} | "
            f"{'yes' if result['stable'] else 'no'} |"
        )

    lines.extend(
        [
            "",
            "## Main Findings",
            "",
            "- 当前 frozen prediction packs 下，检索阶段整体更稳定，citation 与 report 更能拉开模型差异。",
            "- `all_of` citation 与 `multi_source_supported` report claim 是最容易导致阶段分下降的两个位置。",
            "- report 阶段的主要风险仍然集中在 claim 覆盖、claim 层级放置和 citation 对齐。",
            "",
            "## Known Limits",
            "",
            "- 当前 baseline 结果基于仓库内冻结 prediction packs，可用于离线复现与回归比较。",
            "- `Qwen` / `DeepSeek` 的在线 API 实时重放结果仍待后续补充验证。",
            "- `search persistence` 尚未纳入 v1 正式评分。",
            "",
            "## v1.1 Preview",
            "",
            "- 增补 `search persistence` 正式题型与 grader",
            "- 将 frozen baselines 升级为真实 API 重放结果",
            "- 在 report scorer 上增加更细的错误原因聚合",
        ]
    )
    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description="Run benchmark v1 release baselines and generate release artifacts.")
    parser.add_argument(
        "--root-dir",
        type=Path,
        default=Path("docs/benchmark/benchmark_v1"),
        help="Root directory containing manifest.json, dataset/ and baselines/.",
    )
    parser.add_argument(
        "--schema-dir",
        type=Path,
        default=Path("docs/benchmark/schema"),
        help="Directory containing JSON Schema files.",
    )
    args = parser.parse_args()

    manifest_path = args.root_dir / "manifest.json"
    dataset_dir = args.root_dir / "dataset"
    review_records_path = dataset_dir / "reviews" / "review_records.jsonl"
    manifest = _load_json(manifest_path)

    release_dir = args.root_dir / "release"
    release_dir.mkdir(parents=True, exist_ok=True)

    baseline_results: dict[str, Any] = {}
    runner = Path("scripts/benchmark/run_all_benchmarks.py")

    dataset_validation_cmd = [
        sys.executable,
        "scripts/benchmark/validate_dataset.py",
        "--dataset-dir",
        str(dataset_dir),
        "--schema-dir",
        str(args.schema_dir),
        "--manifest-path",
        str(manifest_path),
        "--review-records-path",
        str(review_records_path),
    ]
    validation_output = _run_command(dataset_validation_cmd, "validate_release_dataset")
    dataset_summary = json.loads(validation_output)
    with (release_dir / "dataset_validation.json").open("w", encoding="utf-8") as f:
        json.dump(dataset_summary, f, ensure_ascii=False, indent=2)

    for baseline in manifest["baseline_roster"]:
        baseline_id = baseline["baseline_id"]
        display_name = baseline["display_name"]
        prediction_dir = args.root_dir / baseline["prediction_dir"]
        run_summaries: list[dict[str, Any]] = []

        for run_index in range(1, baseline["run_count"] + 1):
            scores_dir = args.root_dir / "baselines" / baseline_id / "runs" / f"run{run_index}"
            summary_path = scores_dir / "benchmark_summary.json"
            cmd = [
                sys.executable,
                str(runner),
                "--dataset-dir",
                str(dataset_dir),
                "--schema-dir",
                str(args.schema_dir),
                "--predictions-dir",
                str(prediction_dir),
                "--scores-dir",
                str(scores_dir),
                "--summary-path",
                str(summary_path),
                "--manifest-path",
                str(manifest_path),
                "--review-records-path",
                str(review_records_path),
            ]
            _run_command(cmd, f"{baseline_id}_run{run_index}")
            run_summaries.append(_load_json(summary_path))

        first_scores = _stage_score_table(run_summaries[0])
        second_scores = _stage_score_table(run_summaries[1])
        drift = {
            key: _round_metric(abs(float(first_scores[key]) - float(second_scores[key])))
            for key in first_scores
            if first_scores[key] is not None and second_scores[key] is not None
        }
        stable = all(value <= DRIFT_THRESHOLD for value in drift.values())
        if not stable:
            raise ValueError(f"{baseline_id} 两次跑分波动超过阈值: {drift}")

        baseline_results[baseline_id] = {
            "display_name": display_name,
            "official_scores": first_scores,
            "run_count": len(run_summaries),
            "drift": drift,
            "stable": stable,
            "summary_path": str(args.root_dir / "baselines" / baseline_id / "runs" / "run1" / "benchmark_summary.json"),
        }

    release_summary = {
        "benchmark_version": manifest["benchmark_version"],
        "data_freeze_date": manifest["data_freeze_date"],
        "dataset_summary": dataset_summary,
        "baseline_results": baseline_results,
        "official_score_formula": manifest["official_score_formula"],
    }

    with (release_dir / "release_summary.json").open("w", encoding="utf-8") as f:
        json.dump(release_summary, f, ensure_ascii=False, indent=2)

    release_report = _build_release_report(manifest, dataset_summary, baseline_results)
    with (args.root_dir / "release_report.md").open("w", encoding="utf-8") as f:
        f.write(release_report)

    print(json.dumps(release_summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
