# Targets from .kiro/steering/structure.md. Stubs print a message until the code exists.
SHELL := /bin/bash
REPO_ROOT := $(shell git rev-parse --show-toplevel)
export DATA_DIR ?= $(REPO_ROOT)/.local-data/data
export UV_CACHE_DIR ?= $(REPO_ROOT)/.local-data/uv-cache
UV ?= uv
STUB = @echo "[stub] $@: not implemented yet"

.PHONY: setup data-download data-sample pipeline test test-fast web build e2e copy-lint validate coroner-eval snapshot channel-export trace kiro-stats capture lint

setup:
	$(UV) sync
	cd web && npm install

data-download:
	$(UV) run python pipeline/scripts/download.py

# data/sample/sample_311.csv was built during kickoff; a reproducible builder comes with the ingest spec
data-sample:
	$(STUB)

pipeline:
	$(STUB)

lint:
	$(UV) run ruff check pipeline

test:
	$(UV) run pytest
	cd web && npm test

test-fast:
	$(UV) run pytest -q -x pipeline/tests/unit

web:
	cd web && npm run dev

build:
	cd web && npm run build

e2e:
	$(STUB)

copy-lint:
	$(STUB)

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
