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
RUN_ID ?=
STUB = @echo "[stub] $@: not implemented yet"

.PHONY: records-check snapshot-verify judging-final web-deps cloud-sync-check pipeline-sample validation-sample typecheck schema-check test-town setup data-download data-sample pipeline test test-fast web build e2e copy-lint validate coroner-eval snapshot snapshot-check channel-export trace kiro-stats capture lint

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

# A fresh worktree has no web/node_modules; test and lint need it (ops#121). Installs the locked versions once.
web-deps:
	@test -d web/node_modules/vitest || (cd web && npm ci)

lint: web-deps
	$(UV) run ruff check pipeline
	cd web && npm run typecheck

# Installs the locked dependencies first (runtime + dev group: pytest, hypothesis, ruff). pytest exits non-zero when a test
# file cannot be collected (for example a missing import), so a collection error fails this target; it is never skipped.
test: web-deps
	$(UV) sync --locked --group dev
	$(UV) run pytest
	cd web && npm test

test-fast:
	$(UV) sync --locked --group dev
	$(UV) run pytest -q -x pipeline/tests/unit

web:
	cd web && npm run dev

# REQ-OPS-CACHE.1: after the web build, the cache rules (immutable hashed assets, no-cache entry points and data) are
# added to web/dist/_headers. Plain Node, so the Netlify build image needs no Python or uv.
build:
	cd web && npm run build
	node ops/cache-headers/cache-headers.mjs web/dist

e2e:
	cd web && npm run e2e

copy-lint:
	python3 scripts/copy_lint.py

# REQ-STAT-VAL.2: scores data/labels/validation_labels.csv into docs/VALIDATION.md and stats/validation.json
validate:
	PYTHONPATH=pipeline $(UV) run python -m undead311 validate

coroner-eval:
	PYTHONPATH=pipeline $(UV) run python -m undead311 coroner-eval

# REQ-OPS-SNAP.1, REQ-OPS-SNAP.3: hashes a run's exports ($(DATA_DIR)/exports/<RUN_ID>, never web/public/data), its raw files and
# processed database into the judging section of data/SNAPSHOT.md (stage provisional) and copies the judge-mode files into
# data/judging/. The owner commits both and tags afterwards (the script prints the commands and never tags or pushes).
snapshot:
	@test -n "$(RUN_ID)" || { echo "usage: make snapshot RUN_ID=<run id of the full run to freeze>" >&2; exit 2; }
	PYTHONPATH=pipeline $(UV) run python pipeline/scripts/snapshot.py --run-id $(RUN_ID)

# Exits 1 when the run's files no longer match the committed judging section (RUN_ID optional: without it web/public/data is used).
snapshot-check:
	PYTHONPATH=pipeline $(UV) run python pipeline/scripts/snapshot.py --check $(if $(RUN_ID),--run-id $(RUN_ID))

# REQ-OPS-SNAP.3: re-checks a tag from a plain checkout, no data needed: the table's combined hash, and data/judging/ against its rows.
snapshot-verify:
	PYTHONPATH=pipeline $(UV) run python pipeline/scripts/snapshot.py --verify

# REQ-STAT-VAL.5: no field visits were made, so the 50-site sample is checked against how the city closed each re-report. Run once
# (refuses to overwrite data/labels/validation_records.csv). RAW is a folder with the raw 311 CSVs; EXPORTS is the run's export folder.
records-check:
	@test -n "$(RAW)" && test -n "$(CHECKED_ON)" || { echo "usage: make records-check RAW=<raw csv folder> CHECKED_ON=<YYYY-MM-DD> [EXPORTS=<export folder>]" >&2; exit 2; }
	PYTHONPATH=pipeline $(UV) run python pipeline/scripts/records_check.py --raw $(RAW) --checked-on $(CHECKED_ON) $(if $(EXPORTS),--exports $(EXPORTS))

# REQ-OPS-SNAP.4: after data/labels/validation_labels.csv (field) or data/labels/validation_records.csv (records) exists, regenerates
# ONLY stats/validation.json, stats/judge_tour.json and data/judging/ for the final tag, and amends the judging section (stage
# final). SOURCE is auto (default), field or records. Refuses while neither source scores.
judging-final:
	@test -n "$(RUN_ID)" || { echo "usage: make judging-final RUN_ID=<the run that make snapshot froze> [SOURCE=auto|field|records]" >&2; exit 2; }
	PYTHONPATH=pipeline $(UV) run python pipeline/scripts/judging_final.py --run-id $(RUN_ID) $(if $(SOURCE),--source $(SOURCE))

# REQ-OPS-EVID.1: needs a read-only token in GITHUB_CHANNEL_READ_TOKEN at run time; it is never written to the output.
channel-export:
	python3 scripts/channel_export.py --out docs/AGENT_CHANNEL.md

# REQ-OPS-EVID.1: requirement -> code -> tests -> status, from the specs and the IDs cited in code and test names.
trace:
	python3 scripts/trace.py --out docs/TRACEABILITY.md

# REQ-OPS-EVID.1: commits, files and tests per agent and per run, from the Kiro-Agent and Kiro-Run trailers.
kiro-stats:
	python3 scripts/kiro_stats.py --out docs/KIRO_STATS.md

# REQ-OPS-CAPTURE.1, .2: needs `make build` first. Writes screenshots, the judge-tour video and the time-lapse GIF to docs/media/.
# It first checks the served data against data/SNAPSHOT.md (ops#200); CAPTURE_DEV=1 overrides and writes docs/media/NOT-SNAPSHOT.txt.
capture: web-deps
	PYTHONPATH=pipeline $(UV) run python pipeline/scripts/capture_check.py $(if $(CAPTURE_DEV),--dev)
	node ops/capture/capture.mjs

# Fails when the cloud-cache copies of workflows, agents, hooks and steering differ from the repo copies on main.
cloud-sync-check:
	python3 scripts/cloud_sync.py
