# Design: nightly-and-deploy

## Overview
GitHub Actions for checks, Netlify (recommended; GitHub Pages is the fallback) for hosting and previews, a dev container for Codespaces, and Playwright scripts for media. The judged repo holds `ci.yml`, `deep-pbt.yml`, `.devcontainer/`, `docs/DEPLOY.md` and the template for the data repo's `nightly.yml`. The data repo runs the nightly refresh by checking out the judged repo at a frozen tag. Code never changes after the deadline, and data is always served from the site's own origin. That resolves the tension between "nightly data from a separate repo" and "no runtime third-party requests / CSP same-origin".

## Architecture
```
PR ──► ci.yml: setup → test (golden, PBT fast) → schema check → ruff/tsc → copy-lint → build → axe(judge) → budget ──► channel post (never fails)
         └─► host deploy preview (Netlify GitHub app) ──► URL comment on PR
nightly ─► deep-pbt.yml (10× Hypothesis + fast-check, cached example DB) ──► finding issue on failure
nightly ─► undead-311-data/nightly.yml: checkout judged repo @ tag → data-download → pipeline → build → deploy site → Release(Parquet)
                                        └─ failure: keep last deploy, needs-human issue
make snapshot → data/SNAPSHOT.md (judging section) + tag;  make capture → docs/media/
```

### Files
| File | Purpose | Requirements |
|---|---|---|
| `.github/workflows/ci.yml` | PR checks; jobs `python`, `web`, `e2e-axe`, `budget`, `channel` | REQ-OPS-CI |
| `.github/workflows/deep-pbt.yml` | Nightly deep properties with `actions/cache` for `.hypothesis/` | REQ-OPS-PBT |
| `scripts/ci_channel.py` | Standard library only: post the CI result and open finding or alert issues; always exits 0 | REQ-OPS-CI.3, REQ-OPS-PBT.2, REQ-OPS-ALERT |
| `netlify.toml` | Build command `make build`, publish `web/dist`, headers from the web build, previews on | REQ-OPS-HOST, REQ-OPS-CACHE |
| `docs/DEPLOY.md` | Human steps: link the Netlify site to the repo, set the production branch, secrets for the data repo | REQ-OPS-HOST.4 |
| `ops/undead-311-data/` | `nightly.yml` template plus README for the data repo | REQ-OPS-NIGHTLY |
| `.devcontainer/devcontainer.json` | Python 3.11 + Node feature, `postCreateCommand: pip install uv && make setup`, `DATA_DIR` | REQ-OPS-DEV |
| `pipeline/scripts/snapshot.py` | `make snapshot` | REQ-OPS-SNAP |
| `web/scripts/capture.ts` | `make capture` | REQ-OPS-CAPTURE |
| `scripts/channel_export.py`, `scripts/trace.py`, `scripts/kiro_stats.py` | Evidence commands | REQ-OPS-EVID |

Secrets: `GITHUB_CHANNEL_TOKEN` (issues on `undead-311-ops` only) in the judged repo for the CI post, and in the data repo for alerts. The data repo also needs `NETLIFY_AUTH_TOKEN` and `NETLIFY_SITE_ID` for deploys. These are human-created and documented in DEPLOY.md, never committed.

## Correctness properties
This spec is mostly configuration, so its checks are example-based and structural rather than Hypothesis properties:

| # | Check | Requirements |
|---|---|---|
| O1 | Every `uses:` in `.github/workflows/*.yml` and the template is pinned to a tag or SHA; every job declares `permissions:` (unit test parses the YAML) | REQ-OPS-CI.4 |
| O2 | `ci_channel.py` exits 0 for every simulated failure (no token, 4xx, 5xx, timeout) | REQ-OPS-CI.3, REQ-OPS-ALERT |
| O3 | The generated headers file sets immutable caching only on hashed assets, and `no-cache` on `index.html` and `status.json` (property over generated file lists) | REQ-OPS-CACHE |
| O4 | `make snapshot` is reproducible: the same input gives the same hashes | REQ-OPS-SNAP |
| O5 | The dev container JSON validates and names the pinned versions from `.python-version` and `.nvmrc` | REQ-OPS-DEV |

The deep-PBT job runs testing.md's required properties (engine P1–P20, stats P1–P9, web W1–W8) with 10× examples. That is the nightly CI job testing.md asks for.

## Error handling
Channel posts and alerts are fail-open. A failed nightly keeps the last good deploy. Preview failures don't block merges, but the owner sees them on the PR.

## Testing strategy
pytest for O1–O5, plus a dry run of `ci.yml` steps through `make` targets locally. New dependencies: `pyyaml` (dev, for O1).
