# Tasks: nightly-and-deploy

Layer tags drive the build order: all `[demo-critical]` tasks in every spec first, then `[credibility]`, then `[delight]`. Definition of done per task: `make test` passes, `ruff check` clean, tests cite requirement IDs, one line in docs/KIRO_LOG.md. Human-only steps (account linking, secrets) are documented, never attempted.

## Demo-critical

- [x] 1. [demo-critical] CI: core checks
  - `.github/workflows/ci.yml` with jobs `python` (uv, `make test` including the golden check, schema validation of fixtures, `ruff check`) and `web` (`npm ci`, `tsc --noEmit`, vitest); actions pinned to tags; least-privilege `permissions:` per job.
  - [x] 1.1 Check O1: a pytest that parses every workflow YAML and fails on an unpinned `uses:` or a job without `permissions:`. _REQ-OPS-CI.4_
  - _Requirements: REQ-OPS-CI.1, .4_
- [x] 2. [demo-critical] Hosting and previews
  - `netlify.toml` (build `make build`, publish `web/dist`, deploy previews on, headers from the web build); `docs/DEPLOY.md` with the click-by-click human steps from design.md (Netlify account, site import, production branch `main`, previews, the token and Site ID, the three GitHub secrets with `CHANNEL_TOKEN` mapped to `GITHUB_CHANNEL_TOKEN`), no paid plan. GitHub Pages is not used.
  - _Requirements: REQ-OPS-HOST.1–4_

## Credibility

- [x] 3. [credibility] CI: full checks and channel post
  - Add `make copy-lint`, axe scan of judge mode, the bundle budget, `pip-audit`, `npm audit --audit-level=high`; `scripts/ci_channel.py` (standard library, always exits 0) posts the one-line result.
  - [x] 3.1 Check O2: `ci_channel.py` exits 0 for no token, 4xx, 5xx and timeout (mocked). _REQ-OPS-CI.3_
  - _Requirements: REQ-OPS-CI.2–3_
- [x] 4. [credibility] Nightly deep property tests
  - Hypothesis `deep` profile (10× examples, database in `.hypothesis/` cached with `actions/cache`), fast-check 10× runs, finding issues on failure.
  - _Requirements: REQ-OPS-PBT.1–2_
- [x] 5. [credibility] Caching headers
  - Generated headers: immutable for hashed assets, `no-cache` for `index.html`, `status.json` and manifests; `.gz` use.
  - [x] 5.1 Check O3: the header generator never marks an unhashed file immutable (property over generated file lists). _REQ-OPS-CACHE.1_
  - _Requirements: REQ-OPS-CACHE.1_
- [x] 6. [credibility] Nightly refresh template and alerts
  - `ops/undead-311-data/.github/workflows/nightly.yml` and README (checkout at the frozen tag, download, pipeline, build, deploy, Release with Parquet; keep the last good deploy; `needs-human` alert issue).
  - _Requirements: REQ-OPS-NIGHTLY.1–4, REQ-OPS-ALERT.1_
- [x] 7. [credibility] Frozen judging snapshot
  - `pipeline/scripts/snapshot.py` and `make snapshot` (hashes into `data/SNAPSHOT.md` judging section; tag instructions for the owner).
  - [x] 7.1 Check O4: the same input gives the same hashes. _REQ-OPS-SNAP.1_
  - _Requirements: REQ-OPS-SNAP.1–2_
- [x] 8. [credibility] Codespaces dev container
  - `.devcontainer/devcontainer.json` (Python 3.11, uv, Node from `.nvmrc`, `DATA_DIR`, forwarded port; `make setup && make pipeline-sample && make web` works).
  - [x] 8.1 Check O5: the JSON validates and its versions match `.python-version` and `.nvmrc`. _REQ-OPS-DEV.1_
  - _Requirements: REQ-OPS-DEV.1–2_

## Delight

- [x] 9. [delight] `make capture`
  - Playwright video of the judge tour, screenshots of every page (desktop and phone), time-lapse GIF into `docs/media/`, logos excluded.
  - _Requirements: REQ-OPS-CAPTURE.1–2_
- [x] 10. [delight] Evidence commands
  - `make channel-export` (read-only token at run time), `make trace`, `make kiro-stats` (from commit trailers; reuse `scripts/check_trailers.py`).
  - _Requirements: REQ-OPS-EVID.1_
