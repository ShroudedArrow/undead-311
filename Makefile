# Targets from .kiro/steering/structure.md. Stubs print a message until the code exists.
SHELL := /bin/bash
REPO_ROOT := $(shell git rev-parse --show-toplevel)
# tech.md self-correcting fallback (ops#9): use the given DATA_DIR / UV_CACHE_DIR only when it is an existing, writable
# directory; otherwise fall back to <repo root>/.local-data/... Command-line overrides (make DATA_DIR=x) still win.
DATA_DIR := $(shell d="$$DATA_DIR"; if [ -n "$$d" ] && [ -d "$$d" ] && [ -w "$$d" ]; then echo "$$d"; else echo "$(REPO_ROOT)/.local-data/data"; fi)
UV_CACHE_DIR := $(shell d="$$UV_CACHE_DIR"; if [ -n "$$d" ] && [ -d "$$d" ] && [ -w "$$d" ]; then echo "$$d"; else echo "$(REPO_ROOT)/.local-data/uv-cache"; fi)
export DATA_DIR
export UV_CACHE_DIR
UV ?= uv
STUB = @echo "[stub] $@: not implemented yet"

.PHONY: pipeline-sample validation-sample typecheck schema-check test-town setup data-download data-sample pipeline test test-fast web build e2e copy-lint validate coroner-eval snapshot channel-export trace kiro-stats capture lint

setup:
	$(UV) sync
	cd web && npm install

data-download:
	$(UV) run python pipeline/scripts/download.py

# Rebuilds data/sample/sample_311.csv (core scope, UTC + local columns) from $(DATA_DIR)/processed/undead311.duckdb
data-sample:
	$(UV) run python pipeline/scripts/build_sample.py

# Regenerates the test-town CASES (never the hand-written expected_zombies.json)
test-town:
	$(UV) run python pipeline/scripts/build_test_town.py

# Full run on $(DATA_DIR)/raw (REQ-ING-NIGHTLY.1); the sample run needs no network (REQ-ING-NIGHTLY.2)
pipeline:
	PYTHONPATH=pipeline $(UV) run python -m undead311 pipeline

pipeline-sample:
	PYTHONPATH=pipeline $(UV) run python -m undead311 pipeline --sample

# REQ-STAT-VAL.1: draws data/labels/validation_sample.csv once (needs the owner's data/labels/validation_config.json)
validation-sample:
	PYTHONPATH=pipeline $(UV) run python -m undead311 validation-sample

typecheck:
	cd web && npm run typecheck

# Validates every file in schemas/ against the JSON Schema meta-schema, the golden answer key against its schema, and every
# committed web/public/data file against its schema (REQ-OPS-CI.1).
schema-check:
	$(UV) run pytest -q pipeline/tests/unit/test_schemas.py pipeline/tests/unit/test_web_data_schemas.py

lint:
	$(UV) run ruff check pipeline
	cd web && npm run typecheck

# Installs the locked dependencies first (runtime + dev group: pytest, hypothesis, ruff). pytest exits non-zero when a test
# file cannot be collected (for example a missing import), so a collection error fails this target; it is never skipped.
test:
	$(UV) sync --locked --group dev
	$(UV) run pytest
	cd web && npm test

test-fast:
	$(UV) sync --locked --group dev
	$(UV) run pytest -q -x pipeline/tests/unit

web:
	cd web && npm run dev

build:
	cd web && npm run build

e2e:
	cd web && npm run e2e

copy-lint:
	python3 scripts/copy_lint.py

# REQ-STAT-VAL.2: scores data/labels/validation_labels.csv into docs/VALIDATION.md and stats/validation.json
validate:
	PYTHONPATH=pipeline $(UV) run python -m undead311 validate

coroner-eval:
	PYTHONPATH=pipeline $(UV) run python -m undead311 coroner-eval

snapshot:
	$(STUB)

channel-export:
	$(STUB)

trace:
	$(STUB)

kiro-stats:
	$(STUB)

capture:
	$(STUB)
