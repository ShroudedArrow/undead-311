# Targets from .kiro/steering/structure.md. Stubs print a message until the code exists.
SHELL := /bin/bash
REPO_ROOT := $(shell git rev-parse --show-toplevel)
export DATA_DIR ?= $(REPO_ROOT)/.local-data/data
export UV_CACHE_DIR ?= $(REPO_ROOT)/.local-data/uv-cache
UV ?= uv
STUB = @echo "[stub] $@: not implemented yet"

.PHONY: cloud-sync-check test-town setup data-download data-sample pipeline test test-fast web build e2e copy-lint validate coroner-eval snapshot channel-export trace kiro-stats capture lint

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

pipeline:
	$(STUB)

lint:
	$(UV) run ruff check pipeline

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
	$(STUB)

copy-lint:
	python3 scripts/copy_lint.py

validate:
	$(STUB)

coroner-eval:
	$(STUB)

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

# Fails when the cloud-cache copies of workflows, agents, hooks and steering differ from the repo copies on main.
cloud-sync-check:
	python3 scripts/cloud_sync.py
