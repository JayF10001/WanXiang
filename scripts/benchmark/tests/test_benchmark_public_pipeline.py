from __future__ import annotations

import json
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[3]
PYTHON = "python3"
INTERNAL_ROOT = REPO_ROOT / "docs" / "benchmark" / "benchmark_v1"
SCHEMA_DIR = REPO_ROOT / "docs" / "benchmark" / "schema"


class BenchmarkPublicPipelineTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = Path(tempfile.mkdtemp(prefix="benchmark_public_"))
        self.public_root = self.temp_dir / "public_v1"

    def tearDown(self) -> None:
        shutil.rmtree(self.temp_dir)

    def _run(self, script: str, *args: str) -> subprocess.CompletedProcess[str]:
        completed = subprocess.run(
            [PYTHON, str(REPO_ROOT / "scripts" / "benchmark" / script), *args],
            text=True,
            capture_output=True,
        )
        if completed.returncode != 0:
            self.fail(completed.stderr or completed.stdout)
        return completed

    def test_export_and_validate_public_v1(self) -> None:
        self._run(
            "export_public_v1.py",
            "--internal-root",
            str(INTERNAL_ROOT),
            "--public-root",
            str(self.public_root),
            "--schema-dir",
            str(SCHEMA_DIR),
        )
        validate_completed = self._run(
            "validate_public_v1.py",
            "--internal-root",
            str(INTERNAL_ROOT),
            "--public-root",
            str(self.public_root),
            "--schema-dir",
            str(SCHEMA_DIR),
        )

        manifest_public = json.loads((self.public_root / "manifest_public.json").read_text(encoding="utf-8"))
        public_cases = [
            json.loads(line)
            for line in (self.public_root / "dataset_public" / "cases.jsonl").read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]

        self.assertEqual(manifest_public["release_target"], "public")
        self.assertEqual(manifest_public["published_splits"], ["dev"])
        self.assertEqual(manifest_public["hidden_splits"], ["test"])
        self.assertTrue(all(row["split"] == "dev" for row in public_cases))
        self.assertFalse((self.public_root / "dataset_public" / "reviews" / "review_records.jsonl").exists())
        self.assertFalse((self.public_root / "baselines").exists())

        validation_summary = json.loads(validate_completed.stdout)
        self.assertEqual(validation_summary["status"], "ok")
        self.assertEqual(validation_summary["published_case_count"], len(public_cases))


if __name__ == "__main__":
    unittest.main()
