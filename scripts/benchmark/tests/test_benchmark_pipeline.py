from __future__ import annotations

import json
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[3]
SCHEMA_DIR = REPO_ROOT / "docs" / "benchmark" / "schema"
PYTHON = "python3"


def _write_jsonl(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")


def _base_dataset() -> tuple[list[dict], list[dict], list[dict], list[dict], list[dict], list[dict], list[dict], list[dict]]:
    event_id = "event_fixture"
    source_ids = {
        "official": "source_fixture_official_notice",
        "third": "source_fixture_regulator_notice",
        "factcheck": "source_fixture_factcheck",
        "rumor": "source_fixture_rumor_post",
        "media": "source_fixture_media_timeline",
    }
    sources = [
        {
            "source_id": source_ids["official"],
            "event_id": event_id,
            "title": "官方说明",
            "url": "https://benchmark.local/official",
            "domain": "benchmark.local",
            "source_type": "official_notice",
            "credibility_label": "high",
            "published_at": "2026-04-25T10:00:00+08:00",
            "language": "zh-CN",
            "summary": "已发布说明。",
            "content": {"raw_text": "机构已发布说明，并完成整改。", "snippet": "机构已发布说明。"},
        },
        {
            "source_id": source_ids["third"],
            "event_id": event_id,
            "title": "主管部门通报",
            "url": "https://benchmark.local/regulator",
            "domain": "benchmark.local",
            "source_type": "regulator_notice",
            "credibility_label": "high",
            "published_at": "2026-04-25T10:10:00+08:00",
            "language": "zh-CN",
            "summary": "已启动核查。",
            "content": {"raw_text": "主管部门已启动联合核查。", "snippet": "主管部门已启动联合核查。"},
        },
        {
            "source_id": source_ids["factcheck"],
            "event_id": event_id,
            "title": "事实核查",
            "url": "https://benchmark.local/factcheck",
            "domain": "benchmark.local",
            "source_type": "fact_check",
            "credibility_label": "high",
            "published_at": "2026-04-25T10:20:00+08:00",
            "language": "zh-CN",
            "summary": "传言暂无依据。",
            "content": {"raw_text": "传言暂无公开依据。", "snippet": "传言暂无公开依据。"},
        },
        {
            "source_id": source_ids["rumor"],
            "event_id": event_id,
            "title": "网传说法",
            "url": "https://benchmark.local/rumor",
            "domain": "benchmark.local",
            "source_type": "self_media",
            "credibility_label": "low",
            "published_at": "2026-04-25T10:30:00+08:00",
            "language": "zh-CN",
            "summary": "网传已被处罚。",
            "content": {"raw_text": "网传机构已被处罚。", "snippet": "网传机构已被处罚。"},
        },
        {
            "source_id": source_ids["media"],
            "event_id": event_id,
            "title": "媒体时间线",
            "url": "https://benchmark.local/media",
            "domain": "benchmark.local",
            "source_type": "mainstream_media",
            "credibility_label": "high",
            "published_at": "2026-04-25T10:40:00+08:00",
            "language": "zh-CN",
            "summary": "媒体梳理说明与核查进展。",
            "content": {"raw_text": "媒体梳理了说明与核查进展。", "snippet": "媒体梳理了说明与核查进展。"},
        },
    ]
    cases = [
        {
            "case_id": "case_fixture_retrieval",
            "event_id": event_id,
            "task_type": "retrieval",
            "split": "dev",
            "title": "检索核心证据",
            "language": "zh-CN",
            "difficulty": "medium",
            "tags": ["fixture"],
            "source_pool_ids": list(source_ids.values()),
            "expected_output_contract": "retrieval_ranked_sources",
            "input": {"query": "哪些来源能支持整改与核查？", "query_context": "优先找官方与主管部门来源。"},
        },
        {
            "case_id": "case_fixture_citation_exact",
            "event_id": event_id,
            "task_type": "citation",
            "split": "dev",
            "title": "唯一来源归因",
            "language": "zh-CN",
            "difficulty": "easy",
            "tags": ["fixture"],
            "source_pool_ids": list(source_ids.values()),
            "expected_output_contract": "citation_source_selection",
            "input": {"claim_text": "机构已发布说明并完成整改。", "context_text": "需要映射到唯一官方来源。"},
        },
        {
            "case_id": "case_fixture_citation_allof",
            "event_id": event_id,
            "task_type": "citation",
            "split": "dev",
            "title": "多源归因",
            "language": "zh-CN",
            "difficulty": "medium",
            "tags": ["fixture"],
            "source_pool_ids": list(source_ids.values()),
            "expected_output_contract": "citation_source_selection",
            "input": {"claim_text": "公开来源显示机构已发布说明，且主管部门已启动联合核查。", "context_text": "需要完整证据集。"},
        },
        {
            "case_id": "case_fixture_report",
            "event_id": event_id,
            "task_type": "report",
            "split": "dev",
            "title": "报告评测",
            "language": "zh-CN",
            "difficulty": "medium",
            "tags": ["fixture"],
            "source_pool_ids": list(source_ids.values()),
            "expected_output_contract": "report_bundle",
            "input": {"user_query": "整理事实与待验证信息。", "report_instruction": "分成事实、待验证、分析。"},
        },
    ]
    retrieval_labels = [
        {
            "case_id": "case_fixture_retrieval",
            "gold_source_ids": [source_ids["official"], source_ids["third"], source_ids["factcheck"]],
            "preferred_source_ids": [source_ids["official"], source_ids["third"]],
            "excluded_source_ids": [],
            "hard_negative_source_ids": [source_ids["rumor"]],
            "gold_facts": [
                {"claim_id": "claim_fixture_fact1", "text": "机构已发布说明。", "support_source_ids": [source_ids["official"]]},
                {"claim_id": "claim_fixture_fact2", "text": "主管部门已启动联合核查。", "support_source_ids": [source_ids["third"]]},
            ],
        }
    ]
    citation_labels = [
        {
            "case_id": "case_fixture_citation_exact",
            "claim_id": "claim_fixture_exact",
            "claim_text": "机构已发布说明并完成整改。",
            "claim_level": "fact",
            "match_policy": "exact_single",
            "gold_source_ids": [source_ids["official"]],
            "support_span_text": "机构已发布说明并完成整改。",
        },
        {
            "case_id": "case_fixture_citation_allof",
            "claim_id": "claim_fixture_allof",
            "claim_text": "公开来源显示机构已发布说明，且主管部门已启动联合核查。",
            "claim_level": "fact",
            "match_policy": "all_of",
            "gold_source_ids": [source_ids["official"], source_ids["third"]],
            "support_span_text": "机构已发布说明，且主管部门已启动联合核查。",
        },
    ]
    report_labels = [
        {
            "case_id": "case_fixture_report",
            "gold_facts": ["机构已发布说明。", "主管部门已启动联合核查。", "公开来源显示机构已发布说明，且主管部门已启动联合核查。"],
            "gold_to_verify": ["公开来源尚不足以证实机构已被处罚。"],
            "gold_analysis": ["该争议会损伤机构公信力。"],
            "gold_atomic_claims": [
                {"claim_id": "claim_fixture_report_fact1", "text": "机构已发布说明。", "claim_kind": "fact", "support_label": "direct_supported", "gold_source_ids": [source_ids["official"]], "must_be_cited": True},
                {"claim_id": "claim_fixture_report_fact2", "text": "主管部门已启动联合核查。", "claim_kind": "fact", "support_label": "direct_supported", "gold_source_ids": [source_ids["third"]], "must_be_cited": True},
                {"claim_id": "claim_fixture_report_fact3", "text": "公开来源显示机构已发布说明，且主管部门已启动联合核查。", "claim_kind": "fact", "support_label": "multi_source_supported", "gold_source_ids": [source_ids["official"], source_ids["third"]], "must_be_cited": True},
                {"claim_id": "claim_fixture_report_verify", "text": "公开来源尚不足以证实机构已被处罚。", "claim_kind": "to_verify", "support_label": "unverifiable", "gold_source_ids": [source_ids["rumor"], source_ids["factcheck"]], "must_be_cited": False},
                {"claim_id": "claim_fixture_report_analysis", "text": "该争议会损伤机构公信力。", "claim_kind": "analysis", "support_label": "analysis_only", "gold_source_ids": [], "must_be_cited": False},
            ],
            "gold_citation_map": [
                {"claim_id": "claim_fixture_report_fact1", "source_ids": [source_ids["official"]]},
                {"claim_id": "claim_fixture_report_fact2", "source_ids": [source_ids["third"]]},
                {"claim_id": "claim_fixture_report_fact3", "source_ids": [source_ids["official"], source_ids["third"]]},
                {"claim_id": "claim_fixture_report_verify", "source_ids": [source_ids["factcheck"], source_ids["rumor"]]},
                {"claim_id": "claim_fixture_report_analysis", "source_ids": []},
            ],
        }
    ]
    retrieval_predictions = [
        {
            "case_id": "case_fixture_retrieval",
            "task_type": "retrieval",
            "ranked_sources": [
                {"source_id": source_ids["rumor"], "rank": 1, "score": 0.98},
                {"source_id": source_ids["official"], "rank": 2, "score": 0.91},
                {"source_id": source_ids["third"], "rank": 3, "score": 0.88},
                {"source_id": source_ids["factcheck"], "rank": 4, "score": 0.84},
            ],
        }
    ]
    citation_predictions = [
        {
            "case_id": "case_fixture_citation_exact",
            "task_type": "citation",
            "predicted_source_ids": [source_ids["official"]],
            "ranked_sources": [
                {"source_id": source_ids["official"], "rank": 1, "score": 0.99},
                {"source_id": source_ids["third"], "rank": 2, "score": 0.91},
            ],
        },
        {
            "case_id": "case_fixture_citation_allof",
            "task_type": "citation",
            "predicted_source_ids": [source_ids["official"], source_ids["third"]],
            "ranked_sources": [
                {"source_id": source_ids["official"], "rank": 1, "score": 0.99},
                {"source_id": source_ids["third"], "rank": 2, "score": 0.97},
            ],
        },
    ]
    report_predictions = [
        {
            "case_id": "case_fixture_report",
            "task_type": "report",
            "report_text": "事实、待验证和分析已输出。",
            "facts": ["机构已发布说明。", "公开来源显示机构已发布说明，且主管部门已启动联合核查。"],
            "to_verify": ["公开来源尚不足以证实机构已被处罚。"],
            "analysis": ["主管部门已启动联合核查。", "该争议会损伤机构公信力。"],
            "citations": [
                {"source_id": source_ids["official"], "title": "官方说明", "url": "https://benchmark.local/official", "quote": "机构已发布说明。", "claim_refs": ["claim_fixture_report_fact1", "claim_fixture_report_fact3"]},
                {"source_id": source_ids["rumor"], "title": "网传说法", "url": "https://benchmark.local/rumor", "quote": "网传已被处罚。", "claim_refs": ["claim_fixture_report_fact2"]},
                {"source_id": source_ids["factcheck"], "title": "事实核查", "url": "https://benchmark.local/factcheck", "quote": "传言暂无依据。", "claim_refs": ["claim_fixture_report_verify"]},
            ],
        }
    ]
    return (
        cases,
        sources,
        retrieval_labels,
        citation_labels,
        report_labels,
        retrieval_predictions,
        citation_predictions,
        report_predictions,
    )


class BenchmarkPipelineTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = Path(tempfile.mkdtemp(prefix="benchmark_fixture_"))
        self.dataset_dir = self.temp_dir / "dataset"
        self.dataset_dir.mkdir(parents=True, exist_ok=True)
        (
            cases,
            sources,
            retrieval_labels,
            citation_labels,
            report_labels,
            retrieval_predictions,
            citation_predictions,
            report_predictions,
        ) = _base_dataset()
        _write_jsonl(self.dataset_dir / "cases.jsonl", cases)
        _write_jsonl(self.dataset_dir / "sources.jsonl", sources)
        _write_jsonl(self.dataset_dir / "labels" / "retrieval_labels.jsonl", retrieval_labels)
        _write_jsonl(self.dataset_dir / "labels" / "citation_labels.jsonl", citation_labels)
        _write_jsonl(self.dataset_dir / "labels" / "report_labels.jsonl", report_labels)
        _write_jsonl(self.dataset_dir / "predictions" / "retrieval_predictions.jsonl", retrieval_predictions)
        _write_jsonl(self.dataset_dir / "predictions" / "citation_predictions.jsonl", citation_predictions)
        _write_jsonl(self.dataset_dir / "predictions" / "report_predictions.jsonl", report_predictions)
        manifest = {
            "benchmark_name": "Fixture Benchmark",
            "benchmark_version": "v1",
            "release_target": "internal",
            "language": "zh-CN",
            "official_task_types": ["retrieval", "citation", "report"],
            "split_stats": {
                "dev": {"event_count": 1, "retrieval_case_count": 1, "citation_case_count": 2, "report_case_count": 1, "source_count": 5},
                "test": {"event_count": 0, "retrieval_case_count": 0, "citation_case_count": 0, "report_case_count": 0, "source_count": 0},
            },
            "baseline_roster": [{"baseline_id": "fixture", "display_name": "Fixture", "run_count": 2, "prediction_dir": "predictions"}],
            "official_score_formula": {
                "retrieval_stage_score": "nDCG@10",
                "citation_stage_score": "Attribution Accuracy@1",
                "report_stage_score": "Claim Support Rate",
                "overall_formula": "0.3 * retrieval + 0.3 * citation + 0.4 * report",
            },
            "data_freeze_date": "2026-04-25",
        }
        with (self.temp_dir / "manifest.json").open("w", encoding="utf-8") as f:
            json.dump(manifest, f, ensure_ascii=False, indent=2)
        review_rows = [
            {"record_id": "review_case_fixture_retrieval_self", "case_id": "case_fixture_retrieval", "event_id": "event_fixture", "task_type": "retrieval", "split": "dev", "review_status": "self_reviewed", "reviewer": "annotator", "review_round": 1, "issue_flags": ["none"], "adjudication_note": "", "reviewed_at": "2026-04-25"},
            {"record_id": "review_case_fixture_citation_exact_self", "case_id": "case_fixture_citation_exact", "event_id": "event_fixture", "task_type": "citation", "split": "dev", "review_status": "self_reviewed", "reviewer": "annotator", "review_round": 1, "issue_flags": ["none"], "adjudication_note": "", "reviewed_at": "2026-04-25"},
            {"record_id": "review_case_fixture_citation_allof_self", "case_id": "case_fixture_citation_allof", "event_id": "event_fixture", "task_type": "citation", "split": "dev", "review_status": "self_reviewed", "reviewer": "annotator", "review_round": 1, "issue_flags": ["none"], "adjudication_note": "", "reviewed_at": "2026-04-25"},
            {"record_id": "review_case_fixture_report_self", "case_id": "case_fixture_report", "event_id": "event_fixture", "task_type": "report", "split": "dev", "review_status": "self_reviewed", "reviewer": "annotator", "review_round": 1, "issue_flags": ["none"], "adjudication_note": "", "reviewed_at": "2026-04-25"},
            {"record_id": "review_case_fixture_retrieval_second", "case_id": "case_fixture_retrieval", "event_id": "event_fixture", "task_type": "retrieval", "split": "dev", "review_status": "second_reviewed", "reviewer": "reviewer", "review_round": 2, "issue_flags": ["none"], "adjudication_note": "", "reviewed_at": "2026-04-25"},
            {"record_id": "review_case_fixture_citation_allof_adjudicated", "case_id": "case_fixture_citation_allof", "event_id": "event_fixture", "task_type": "citation", "split": "dev", "review_status": "adjudicated", "reviewer": "adjudicator", "review_round": 3, "issue_flags": ["all_of_citation"], "adjudication_note": "frozen", "reviewed_at": "2026-04-25"},
            {"record_id": "review_case_fixture_report_adjudicated", "case_id": "case_fixture_report", "event_id": "event_fixture", "task_type": "report", "split": "dev", "review_status": "adjudicated", "reviewer": "adjudicator", "review_round": 3, "issue_flags": ["multi_source_claim"], "adjudication_note": "frozen", "reviewed_at": "2026-04-25"},
        ]
        _write_jsonl(self.dataset_dir / "reviews" / "review_records.jsonl", review_rows)

    def tearDown(self) -> None:
        shutil.rmtree(self.temp_dir)

    def _run(self, script: str, *args: str, expect_ok: bool = True) -> subprocess.CompletedProcess[str]:
        completed = subprocess.run(
            [PYTHON, str(REPO_ROOT / "scripts" / "benchmark" / script), *args],
            text=True,
            capture_output=True,
        )
        if expect_ok and completed.returncode != 0:
            self.fail(completed.stderr or completed.stdout)
        return completed

    def test_validate_dataset_rejects_cross_split_event(self) -> None:
        case_rows = [json.loads(line) for line in (self.dataset_dir / "cases.jsonl").read_text(encoding="utf-8").splitlines()]
        case_rows[1]["split"] = "test"
        _write_jsonl(self.dataset_dir / "cases.jsonl", case_rows)
        completed = self._run(
            "validate_dataset.py",
            "--dataset-dir",
            str(self.dataset_dir),
            "--schema-dir",
            str(SCHEMA_DIR),
            "--manifest-path",
            str(self.temp_dir / "manifest.json"),
            "--review-records-path",
            str(self.dataset_dir / "reviews" / "review_records.jsonl"),
            expect_ok=False,
        )
        self.assertNotEqual(completed.returncode, 0)
        self.assertIn("跨 split 泄漏", completed.stderr)

    def test_citation_scorer_handles_all_of(self) -> None:
        summary_path = self.temp_dir / "citation_summary.json"
        self._run(
            "citation_scorer.py",
            "--dataset-dir",
            str(self.dataset_dir),
            "--schema-dir",
            str(SCHEMA_DIR),
            "--summary-path",
            str(summary_path),
        )
        summary = json.loads(summary_path.read_text(encoding="utf-8"))
        self.assertEqual(summary["attribution_accuracy@1"], 1.0)

    def test_retrieval_and_report_edge_metrics(self) -> None:
        retrieval_summary_path = self.temp_dir / "retrieval_summary.json"
        report_summary_path = self.temp_dir / "report_summary.json"
        self._run(
            "retrieval_scorer.py",
            "--dataset-dir",
            str(self.dataset_dir),
            "--schema-dir",
            str(SCHEMA_DIR),
            "--summary-path",
            str(retrieval_summary_path),
        )
        self._run(
            "report_faithfulness_scorer.py",
            "--dataset-dir",
            str(self.dataset_dir),
            "--schema-dir",
            str(SCHEMA_DIR),
            "--summary-path",
            str(report_summary_path),
        )
        retrieval_summary = json.loads(retrieval_summary_path.read_text(encoding="utf-8"))
        report_summary = json.loads(report_summary_path.read_text(encoding="utf-8"))
        self.assertLess(retrieval_summary["mrr"], 1.0)
        self.assertLess(report_summary["layer_separation_accuracy"], 1.0)
        self.assertLess(report_summary["citation_backed_claim_rate"], 1.0)

    def test_run_all_benchmarks_computes_official_scores(self) -> None:
        summary_path = self.temp_dir / "benchmark_summary.json"
        self._run(
            "run_all_benchmarks.py",
            "--dataset-dir",
            str(self.dataset_dir),
            "--schema-dir",
            str(SCHEMA_DIR),
            "--summary-path",
            str(summary_path),
            "--manifest-path",
            str(self.temp_dir / "manifest.json"),
            "--review-records-path",
            str(self.dataset_dir / "reviews" / "review_records.jsonl"),
        )
        summary = json.loads(summary_path.read_text(encoding="utf-8"))
        self.assertIn("official_overall_score", summary)
        self.assertIn("scorer_versions", summary)
        self.assertEqual(summary["benchmark_version"], "v1")


if __name__ == "__main__":
    unittest.main()
