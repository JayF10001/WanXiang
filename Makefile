PYTHON ?= python3

.PHONY: \
	benchmark \
	benchmark-validate \
	benchmark-score \
	benchmark-retrieval \
	benchmark-citation \
	benchmark-report \
	benchmark-test \
	benchmark-v1-build \
	benchmark-v1-release \
	benchmark-v1-public-export \
	benchmark-v1-public-validate

benchmark:
	$(PYTHON) scripts/benchmark/run_all_benchmarks.py

benchmark-validate:
	$(PYTHON) scripts/benchmark/validate_dataset.py

benchmark-score: benchmark-retrieval benchmark-citation benchmark-report

benchmark-retrieval:
	$(PYTHON) scripts/benchmark/retrieval_scorer.py

benchmark-citation:
	$(PYTHON) scripts/benchmark/citation_scorer.py

benchmark-report:
	$(PYTHON) scripts/benchmark/report_faithfulness_scorer.py

benchmark-test:
	$(PYTHON) -m unittest discover -s scripts/benchmark/tests -p 'test_*.py'

benchmark-v1-build:
	$(PYTHON) scripts/benchmark/build_benchmark_v1.py

benchmark-v1-release:
	$(PYTHON) scripts/benchmark/run_benchmark_v1_release.py

benchmark-v1-public-export:
	$(PYTHON) scripts/benchmark/export_public_v1.py

benchmark-v1-public-validate:
	$(PYTHON) scripts/benchmark/validate_public_v1.py
