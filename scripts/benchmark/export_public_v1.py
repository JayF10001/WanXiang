#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import shutil
from pathlib import Path
from typing import Any


PUBLIC_BENCHMARK_VERSION = "v1-public"
PUBLIC_SCHEMA_FILES = [
    "cases.schema.json",
    "sources.schema.json",
    "retrieval-labels.schema.json",
    "citation-labels.schema.json",
    "report-labels.schema.json",
    "predictions.schema.json",
    "score-results.schema.json",
    "benchmark-public-manifest.schema.json",
]

MIT_LICENSE_TEXT = """MIT License

Copyright (c) 2026 WanXiang Benchmark Contributors

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
"""

CC_BY_LICENSE_TEXT = """Creative Commons Attribution 4.0 International

This dataset is licensed under the Creative Commons Attribution 4.0 International License.

You are free to:
- Share — copy and redistribute the material in any medium or format
- Adapt — remix, transform, and build upon the material for any purpose

Under the following terms:
- Attribution — You must give appropriate credit, provide a link to the license,
  and indicate if changes were made.

License text:
https://creativecommons.org/licenses/by/4.0/
"""


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


def _write_json(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        json.dump(value, f, ensure_ascii=False, indent=2)


def _write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")


def _copy_schema_files(schema_dir: Path, public_schema_dir: Path) -> None:
    public_schema_dir.mkdir(parents=True, exist_ok=True)
    for filename in PUBLIC_SCHEMA_FILES:
        shutil.copy2(schema_dir / filename, public_schema_dir / filename)


def _stats_for_split(case_rows: list[dict[str, Any]], source_rows: list[dict[str, Any]], split: str) -> dict[str, int]:
    split_cases = [row for row in case_rows if row["split"] == split]
    split_event_ids = {str(row["event_id"]) for row in split_cases}
    return {
        "event_count": len(split_event_ids),
        "retrieval_case_count": sum(1 for row in split_cases if row["task_type"] == "retrieval"),
        "citation_case_count": sum(1 for row in split_cases if row["task_type"] == "citation"),
        "report_case_count": sum(1 for row in split_cases if row["task_type"] == "report"),
        "source_count": sum(1 for row in source_rows if str(row["event_id"]) in split_event_ids),
    }


def _build_public_manifest(
    internal_manifest: dict[str, Any],
    release_summary: dict[str, Any],
    dev_case_rows: list[dict[str, Any]],
    dev_source_rows: list[dict[str, Any]],
    all_case_rows: list[dict[str, Any]],
    all_source_rows: list[dict[str, Any]],
) -> dict[str, Any]:
    baseline_results = []
    for baseline_id, row in release_summary["baseline_results"].items():
        scores = row["official_scores"]
        baseline_results.append(
            {
                "baseline_id": baseline_id,
                "display_name": row["display_name"],
                "retrieval": scores["retrieval"],
                "citation": scores["citation"],
                "report_faithfulness": scores["report_faithfulness"],
                "overall": scores["overall"],
                "stable": bool(row["stable"]),
            }
        )

    return {
        "benchmark_name": "WanXiang Benchmark",
        "benchmark_version": PUBLIC_BENCHMARK_VERSION,
        "source_benchmark_version": internal_manifest["benchmark_version"],
        "release_target": "public",
        "language": internal_manifest["language"],
        "official_task_types": internal_manifest["official_task_types"],
        "published_splits": ["dev"],
        "hidden_splits": ["test"],
        "split_stats": {
            "dev": _stats_for_split(dev_case_rows, dev_source_rows, "dev"),
        },
        "hidden_test_stats": _stats_for_split(all_case_rows, all_source_rows, "test"),
        "baseline_results": baseline_results,
        "official_score_formula": internal_manifest["official_score_formula"],
        "data_freeze_date": internal_manifest["data_freeze_date"],
        "public_assets": {
            "includes_dev_dataset": True,
            "includes_test_dataset": False,
            "includes_review_records": False,
            "includes_baseline_prediction_packs": False,
            "includes_minimal_sample_path": "docs/benchmark/benchmark_dataset",
        },
        "notes": [
            "This public package exposes methodology, scores, schema, dev split data, and examples.",
            "The hidden test split remains internal to reduce overfitting and leaderboard gaming.",
            "Baseline scores are frozen release results, not a live API leaderboard.",
        ],
    }


def _example_bundle(
    case_row: dict[str, Any],
    label_row: dict[str, Any],
    source_rows: list[dict[str, Any]],
) -> dict[str, Any]:
    return {
        "case": case_row,
        "label": label_row,
        "sources": source_rows,
    }


def _build_readme_zh(manifest: dict[str, Any]) -> str:
    dev_stats = manifest["split_stats"]["dev"]
    baseline_lines = []
    for row in manifest["baseline_results"]:
        baseline_lines.append(
            f"- `{row['display_name']}`: retrieval `{row['retrieval']:.6f}`, "
            f"citation `{row['citation']:.6f}`, report `{row['report_faithfulness']:.6f}`, "
            f"overall `{row['overall']:.6f}`"
        )
    return f"""# WanXiang Benchmark Public v1

面向 `zh-CN` 公网舆情研究场景的公开 benchmark 包，聚焦三类核心能力：

- `retrieval`
- `citation attribution`
- `report faithfulness`

## 一眼看懂

这份公开包适合用来：

- 快速理解 WanXiang benchmark v1 评什么、怎么计分
- 复用公开的 `dev` 数据、schema 和样例做本地对接
- 查看 `WanXiang / Qwen / DeepSeek` 的冻结阶段分与总分
- 在不暴露完整 `test` 集的前提下复现公开部分

## 当前公开内容

- 方法说明与评分公式
- `dev` split 全量数据
- schema 与完整输入输出契约
- retrieval / citation / report 公开样例
- `WanXiang / Qwen / DeepSeek` 精确分数
- 公开复现与校验命令

## 当前不公开内容

- 完整隐藏 `test` 数据
- review records 明细
- baseline prediction packs
- 内部 release 中间运行产物

## 公开数据规模

- `dev` events: `{dev_stats['event_count']}`
- `dev` retrieval cases: `{dev_stats['retrieval_case_count']}`
- `dev` citation cases: `{dev_stats['citation_case_count']}`
- `dev` report cases: `{dev_stats['report_case_count']}`
- `dev` sources: `{dev_stats['source_count']}`

## 当前公开分数

{chr(10).join(baseline_lines)}

## 快速开始

1. 先看 `methodology.zh-CN.md`
2. 再看 `results.zh-CN.md`
3. 如需接数据，读取 `dataset_public/` 与 `schema/`
4. 如需校验公开包，执行 `make benchmark-v1-public-validate`

## 目录入口

- `methodology.zh-CN.md`
- `results.zh-CN.md`
- `reproduce_public.md`
- `dataset_public/`
- `schema/`
- `examples/`

## 说明

- 当前公开结果基于内部冻结版 `v1`
- `search persistence` 不在本轮外部版正式范围
- 最小样例仍保留在 `docs/benchmark/benchmark_dataset`
- 代码许可见 `LICENSE_CODE`
- 数据许可见 `LICENSE_DATASET`
"""


def _build_readme_en(manifest: dict[str, Any]) -> str:
    dev_stats = manifest["split_stats"]["dev"]
    baseline_lines = []
    for row in manifest["baseline_results"]:
        baseline_lines.append(
            f"- `{row['display_name']}`: retrieval `{row['retrieval']:.6f}`, "
            f"citation `{row['citation']:.6f}`, report `{row['report_faithfulness']:.6f}`, "
            f"overall `{row['overall']:.6f}`"
        )
    return f"""# WanXiang Benchmark Public v1

Public benchmark assets for `zh-CN` open-web monitoring and research workflows, centered on:

- `retrieval`
- `citation attribution`
- `report faithfulness`

## At a Glance

This package is designed to help external readers:

- understand what WanXiang benchmark v1 measures and how it is scored
- reuse the public `dev` split, schema, and examples for local integration
- inspect frozen stage scores and overall scores for `WanXiang / Qwen / DeepSeek`
- reproduce the public-facing package without exposing the full hidden `test` set

## What Is Included

- methodology and scoring rules
- the full public `dev` split
- schema files and I/O contracts
- public retrieval / citation / report examples
- exact scores for `WanXiang / Qwen / DeepSeek`
- lightweight export and validation instructions

## What Is Not Included

- the full hidden `test` split
- detailed review records
- frozen baseline prediction packs
- internal release intermediates

## Public Data Size

- `dev` events: `{dev_stats['event_count']}`
- `dev` retrieval cases: `{dev_stats['retrieval_case_count']}`
- `dev` citation cases: `{dev_stats['citation_case_count']}`
- `dev` report cases: `{dev_stats['report_case_count']}`
- `dev` sources: `{dev_stats['source_count']}`

## Frozen Public Scores

{chr(10).join(baseline_lines)}

## Quick Start

1. Read `methodology.md`
2. Review `results.md`
3. Load `dataset_public/` together with `schema/`
4. Run `make benchmark-v1-public-validate` to validate the package

## Entry Points

- `methodology.md`
- `results.md`
- `reproduce_public.md`
- `dataset_public/`
- `schema/`
- `examples/`

## Notes

- This public package is derived from the frozen internal `v1` release.
- `search persistence` is not part of the formal public scope in this release.
- The minimal sample dataset remains available at `docs/benchmark/benchmark_dataset`.
- Code license: `LICENSE_CODE`
- Dataset license: `LICENSE_DATASET`
"""


def _build_release_checklist() -> str:
    return """# Public v1 Release Checklist

这份 checklist 面向维护者，用于后续再次导出或刷新 `public_v1`。

## 1. 刷新内部冻结版

- [ ] 执行 `make benchmark-v1-build`
- [ ] 执行 `make benchmark-test`
- [ ] 执行 `make benchmark-v1-release`
- [ ] 确认 `docs/benchmark/benchmark_v1/release/release_summary.json` 已更新

## 2. 导出公开包

- [ ] 执行 `make benchmark-v1-public-export`
- [ ] 确认生成目录为 `docs/benchmark/public_v1/`
- [ ] 确认存在：
  - [ ] `README.md`
  - [ ] `README.zh-CN.md`
  - [ ] `methodology.md`
  - [ ] `methodology.zh-CN.md`
  - [ ] `results.md`
  - [ ] `results.zh-CN.md`
  - [ ] `manifest_public.json`
  - [ ] `dataset_public/`
  - [ ] `schema/`
  - [ ] `examples/`
  - [ ] `LICENSE_CODE`
  - [ ] `LICENSE_DATASET`

## 3. 校验公开边界

- [ ] 执行 `make benchmark-v1-public-validate`
- [ ] 确认 `dataset_public/cases.jsonl` 仅包含 `dev`
- [ ] 确认 `public_v1/` 不包含完整 `test` JSONL
- [ ] 确认 `public_v1/` 不包含 `review_records.jsonl`
- [ ] 确认 `public_v1/` 不包含 baseline prediction packs

## 4. 核对公开结果

- [ ] 打开 `docs/benchmark/public_v1/results.md`
- [ ] 打开 `docs/benchmark/public_v1/results.zh-CN.md`
- [ ] 对照 `docs/benchmark/benchmark_v1/release/release_summary.json`
- [ ] 确认 `WanXiang / Qwen / DeepSeek` 的 Retrieval / Citation / Report / Overall 分数完全一致

## 5. 核对对外文案

- [ ] README 中已说明“公开的是方法与结果，不是完整公开 leaderboard”
- [ ] README 中已说明 `search persistence` 不在当前正式公开范围
- [ ] README 中已写明代码与数据许可
- [ ] `reproduce_public.md` 中的命令与当前 Makefile 一致

## 6. 准备发布

- [ ] `git diff` 检查只包含预期变更
- [ ] 如需对外 announce，优先引用 `docs/benchmark/public_v1/README.md`
- [ ] 如需给合作方分享入口，优先给 `docs/benchmark/public_v1/`
"""


def _build_release_checklist_short_zh() -> str:
    return """# Public v1 Release Template (Short)

这是一版更适合直接贴进 PR 描述或发版说明的简版模板。

## 可直接复制

```md
## Benchmark Public v1 Release

### 变更摘要

- [ ] 刷新了内部 benchmark v1 release
- [ ] 导出了最新 `public_v1`
- [ ] 校验了公开包边界与分数一致性

### 已执行命令

- [ ] `make benchmark-v1-build`
- [ ] `make benchmark-test`
- [ ] `make benchmark-v1-release`
- [ ] `make benchmark-v1-public-export`
- [ ] `make benchmark-v1-public-validate`

### 公开范围确认

- [ ] 仅公开 `dev` split
- [ ] 未公开完整 `test` 数据
- [ ] 未公开 `review_records.jsonl`
- [ ] 未公开 baseline prediction packs

### 分数核对

- [ ] 已对照 `docs/benchmark/benchmark_v1/release/release_summary.json`
- [ ] `WanXiang / Qwen / DeepSeek` 的 Retrieval / Citation / Report / Overall 分数一致

### 文案核对

- [ ] README 已说明“公开的是方法与结果，不是完整公开 leaderboard”
- [ ] README 已说明 `search persistence` 暂不在当前公开评分范围
- [ ] README 已写明代码与数据许可

### 发布入口

- Public package: `docs/benchmark/public_v1/`
- Public README: `docs/benchmark/public_v1/README.md`
- Public results: `docs/benchmark/public_v1/results.md`
```
"""


def _build_release_checklist_short_en() -> str:
    return """# Public v1 Release Template (Short)

This is a compact template intended for PR descriptions or release notes.

## Copy-Paste Template

```md
## Benchmark Public v1 Release

### Change Summary

- [ ] Refreshed the internal benchmark v1 release
- [ ] Exported the latest `public_v1`
- [ ] Validated package boundaries and score consistency

### Commands Run

- [ ] `make benchmark-v1-build`
- [ ] `make benchmark-test`
- [ ] `make benchmark-v1-release`
- [ ] `make benchmark-v1-public-export`
- [ ] `make benchmark-v1-public-validate`

### Public Boundary Checks

- [ ] Only the `dev` split is public
- [ ] The full hidden `test` split is not exposed
- [ ] `review_records.jsonl` is not exposed
- [ ] Baseline prediction packs are not exposed

### Score Verification

- [ ] Compared against `docs/benchmark/benchmark_v1/release/release_summary.json`
- [ ] Retrieval / Citation / Report / Overall scores match for `WanXiang / Qwen / DeepSeek`

### Copy Review

- [ ] README states that this package exposes methods and results, not a fully open leaderboard
- [ ] README states that `search persistence` is outside the current public scoring scope
- [ ] README states the code and dataset licenses

### Release Entry Points

- Public package: `docs/benchmark/public_v1/`
- Public README: `docs/benchmark/public_v1/README.md`
- Public results: `docs/benchmark/public_v1/results.md`
```
"""


def _build_methodology_zh(manifest: dict[str, Any]) -> str:
    hidden = manifest["hidden_test_stats"]
    return f"""# 方法说明

## 任务范围

当前公开版仅覆盖：

- `retrieval`
- `citation`
- `report`

`search persistence` 预留到后续版本。

## 评分公式

- Retrieval Stage Score = `{manifest['official_score_formula']['retrieval_stage_score']}`
- Citation Stage Score = `{manifest['official_score_formula']['citation_stage_score']}`
- Report Stage Score = `{manifest['official_score_formula']['report_stage_score']}`
- Overall = `{manifest['official_score_formula']['overall_formula']}`

## 数据构造原则

- 数据源以 `zh-CN` 公网舆情材料为主
- 每个事件包含多来源 source pool
- retrieval 评排序质量
- citation 评 claim-to-source attribution
- report 评 atomic claim faithfulness

## 公开边界

- 公开：完整 `dev` split
- 不公开：完整 `test` split
- 不公开：review 记录明细
- 不公开：baseline prediction packs

隐藏测试集统计：

- events: `{hidden['event_count']}`
- retrieval cases: `{hidden['retrieval_case_count']}`
- citation cases: `{hidden['citation_case_count']}`
- report cases: `{hidden['report_case_count']}`
- sources: `{hidden['source_count']}`

## Review Policy 摘要

- 所有样本至少完成一次 self review
- 至少 `20%` 事件进入 second review
- `all_of` citation 与 `multi_source_supported` report claim 必须进入 adjudication
"""


def _build_methodology_en(manifest: dict[str, Any]) -> str:
    hidden = manifest["hidden_test_stats"]
    return f"""# Methodology

## Task Scope

The current public release covers:

- `retrieval`
- `citation`
- `report`

`search persistence` is reserved for a later release.

## Official Score Formula

- Retrieval Stage Score = `{manifest['official_score_formula']['retrieval_stage_score']}`
- Citation Stage Score = `{manifest['official_score_formula']['citation_stage_score']}`
- Report Stage Score = `{manifest['official_score_formula']['report_stage_score']}`
- Overall = `{manifest['official_score_formula']['overall_formula']}`

## Data Construction Principles

- The benchmark focuses on `zh-CN` public-facing monitoring and research scenarios.
- Each event is built around a multi-source pool.
- Retrieval evaluates ranking quality.
- Citation evaluates claim-to-source attribution.
- Report evaluates atomic-claim faithfulness.

## Public Boundary

- Public: the full `dev` split
- Hidden: the full `test` split
- Hidden: detailed review records
- Hidden: baseline prediction packs

Hidden test split statistics:

- events: `{hidden['event_count']}`
- retrieval cases: `{hidden['retrieval_case_count']}`
- citation cases: `{hidden['citation_case_count']}`
- report cases: `{hidden['report_case_count']}`
- sources: `{hidden['source_count']}`

## Review Policy Summary

- Every sample receives at least one self review.
- At least `20%` of events receive a second review.
- `all_of` citation cases and `multi_source_supported` report claims always go through adjudication.
"""


def _build_results_zh(manifest: dict[str, Any]) -> str:
    lines = [
        "# 结果",
        "",
        "## Baseline Scores",
        "",
        "| Baseline | Retrieval | Citation | Report | Overall | Stable |",
        "| --- | ---: | ---: | ---: | ---: | --- |",
    ]
    for row in manifest["baseline_results"]:
        lines.append(
            f"| {row['display_name']} | {row['retrieval']:.6f} | {row['citation']:.6f} | "
            f"{row['report_faithfulness']:.6f} | {row['overall']:.6f} | {'yes' if row['stable'] else 'no'} |"
        )
    lines.extend(
        [
            "",
            "## 结果口径",
            "",
            "- 结果直接来自内部冻结版 `v1` release summary",
            "- 当前公开的是方法与结果，不是完整公开 benchmark leaderboard",
            "- `Qwen / DeepSeek` 当前是 frozen run 结果，不是在线 API 实时榜单",
            "- `search persistence` 不在当前公开评分范围内",
        ]
    )
    return "\n".join(lines) + "\n"


def _build_results_en(manifest: dict[str, Any]) -> str:
    lines = [
        "# Results",
        "",
        "## Baseline Scores",
        "",
        "| Baseline | Retrieval | Citation | Report | Overall | Stable |",
        "| --- | ---: | ---: | ---: | ---: | --- |",
    ]
    for row in manifest["baseline_results"]:
        lines.append(
            f"| {row['display_name']} | {row['retrieval']:.6f} | {row['citation']:.6f} | "
            f"{row['report_faithfulness']:.6f} | {row['overall']:.6f} | {'yes' if row['stable'] else 'no'} |"
        )
    lines.extend(
        [
            "",
            "## Interpretation",
            "",
            "- These scores are taken directly from the frozen internal `v1` release summary.",
            "- This public package exposes methods and results, not a fully open benchmark leaderboard.",
            "- `Qwen / DeepSeek` are currently frozen runs rather than live API leaderboard entries.",
            "- `search persistence` is outside the current public scoring scope.",
        ]
    )
    return "\n".join(lines) + "\n"


def _build_reproduce_doc() -> str:
    return """# Reproduce Public v1

## Export the public package

```bash
make benchmark-v1-public-export
```

## Validate the public package

```bash
make benchmark-v1-public-validate
```

## What this validates

- only `dev` data is published
- no hidden `test` JSONL is exposed
- no detailed review records are exposed
- no frozen baseline prediction packs are exposed
- public results stay consistent with the internal frozen `release_summary.json`
"""


def main() -> int:
    parser = argparse.ArgumentParser(description="Export a public benchmark package from the internal v1 release.")
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
        help="Output directory for the public package.",
    )
    parser.add_argument(
        "--schema-dir",
        type=Path,
        default=Path("docs/benchmark/schema"),
        help="Schema source directory.",
    )
    args = parser.parse_args()

    internal_manifest = _load_json(args.internal_root / "manifest.json")
    release_summary = _load_json(args.internal_root / "release" / "release_summary.json")
    case_rows = _iter_jsonl(args.internal_root / "dataset" / "cases.jsonl")
    source_rows = _iter_jsonl(args.internal_root / "dataset" / "sources.jsonl")
    retrieval_labels = _iter_jsonl(args.internal_root / "dataset" / "labels" / "retrieval_labels.jsonl")
    citation_labels = _iter_jsonl(args.internal_root / "dataset" / "labels" / "citation_labels.jsonl")
    report_labels = _iter_jsonl(args.internal_root / "dataset" / "labels" / "report_labels.jsonl")

    if args.public_root.exists():
        shutil.rmtree(args.public_root)
    args.public_root.mkdir(parents=True, exist_ok=True)

    dev_case_rows = [row for row in case_rows if row["split"] == "dev"]
    dev_case_ids = {str(row["case_id"]) for row in dev_case_rows}
    dev_event_ids = {str(row["event_id"]) for row in dev_case_rows}
    dev_source_rows = [row for row in source_rows if str(row["event_id"]) in dev_event_ids]
    dev_source_ids = {str(row["source_id"]) for row in dev_source_rows}
    dev_retrieval_labels = [row for row in retrieval_labels if str(row["case_id"]) in dev_case_ids]
    dev_citation_labels = [row for row in citation_labels if str(row["case_id"]) in dev_case_ids]
    dev_report_labels = [row for row in report_labels if str(row["case_id"]) in dev_case_ids]

    _write_jsonl(args.public_root / "dataset_public" / "cases.jsonl", dev_case_rows)
    _write_jsonl(args.public_root / "dataset_public" / "sources.jsonl", dev_source_rows)
    _write_jsonl(args.public_root / "dataset_public" / "labels" / "retrieval_labels.jsonl", dev_retrieval_labels)
    _write_jsonl(args.public_root / "dataset_public" / "labels" / "citation_labels.jsonl", dev_citation_labels)
    _write_jsonl(args.public_root / "dataset_public" / "labels" / "report_labels.jsonl", dev_report_labels)

    _copy_schema_files(args.schema_dir, args.public_root / "schema")

    public_manifest = _build_public_manifest(
        internal_manifest,
        release_summary,
        dev_case_rows,
        dev_source_rows,
        case_rows,
        source_rows,
    )
    _write_json(args.public_root / "manifest_public.json", public_manifest)

    source_map = {str(row["source_id"]): row for row in dev_source_rows}
    retrieval_case = next(row for row in dev_case_rows if row["task_type"] == "retrieval")
    citation_case = next(row for row in dev_case_rows if row["task_type"] == "citation")
    report_case = next(row for row in dev_case_rows if row["task_type"] == "report")
    retrieval_label_map = {str(row["case_id"]): row for row in dev_retrieval_labels}
    citation_label_map = {str(row["case_id"]): row for row in dev_citation_labels}
    report_label_map = {str(row["case_id"]): row for row in dev_report_labels}

    for name, case_row, label_map in (
        ("retrieval_example.json", retrieval_case, retrieval_label_map),
        ("citation_example.json", citation_case, citation_label_map),
        ("report_example.json", report_case, report_label_map),
    ):
        source_rows_for_case = [source_map[source_id] for source_id in case_row["source_pool_ids"] if source_id in dev_source_ids]
        _write_json(
            args.public_root / "examples" / name,
            _example_bundle(case_row, label_map[case_row["case_id"]], source_rows_for_case),
        )

    (args.public_root / "LICENSE_CODE").write_text(MIT_LICENSE_TEXT, encoding="utf-8")
    (args.public_root / "LICENSE_DATASET").write_text(CC_BY_LICENSE_TEXT, encoding="utf-8")
    (args.public_root / "README.zh-CN.md").write_text(_build_readme_zh(public_manifest), encoding="utf-8")
    (args.public_root / "README.md").write_text(_build_readme_en(public_manifest), encoding="utf-8")
    (args.public_root / "methodology.zh-CN.md").write_text(_build_methodology_zh(public_manifest), encoding="utf-8")
    (args.public_root / "methodology.md").write_text(_build_methodology_en(public_manifest), encoding="utf-8")
    (args.public_root / "results.zh-CN.md").write_text(_build_results_zh(public_manifest), encoding="utf-8")
    (args.public_root / "results.md").write_text(_build_results_en(public_manifest), encoding="utf-8")
    (args.public_root / "reproduce_public.md").write_text(_build_reproduce_doc(), encoding="utf-8")
    (args.public_root / "release_checklist.md").write_text(_build_release_checklist(), encoding="utf-8")
    (args.public_root / "release_checklist_short.md").write_text(_build_release_checklist_short_en(), encoding="utf-8")
    (args.public_root / "release_checklist_short.zh-CN.md").write_text(_build_release_checklist_short_zh(), encoding="utf-8")

    summary = {
        "public_root": str(args.public_root),
        "published_event_count": public_manifest["split_stats"]["dev"]["event_count"],
        "published_case_count": len(dev_case_rows),
        "published_source_count": len(dev_source_rows),
        "baseline_count": len(public_manifest["baseline_results"]),
        "status": "ok",
    }
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
