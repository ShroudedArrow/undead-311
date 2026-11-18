# Nightly refresh template (`ShroudedArrow/undead-311-data`)

Requirement IDs: REQ-OPS-NIGHTLY.1 to .4, REQ-OPS-ALERT.1.

This folder is a template. A person copies it into the separate data repo, because the agents have no access there. Hosting is Netlify's free plan (see `docs/DEPLOY.md` in the judged repo).

## What the job does each night (03:41 UTC)

The pipeline does not run in this repo. Each full-data run (`.kiro/workflows/fulldata.workflow.yaml`, or `run_full.py` by hand) ends with its exports in `$DATA_DIR/exports/<run-id>`. A person (or the run's last step, with the token below) publishes them: `python pipeline/scripts/exports_release.py publish --run-id <run-id>` packs the folder into `exports-<run-id>.tar.gz` with a `MANIFEST.json` and a SHA-256 file, and attaches both to the release `exports-<run-id>` of `ShroudedArrow/undead-311-data`. `pack` refuses an export whose `status.json` is not `ok: true` or carries a `DRY RUN ONLY` anomaly, so a dry run such as full-1 is never published. `--dry-run` prints the `gh` commands and uploads nothing.

1. Checks out the judged repo `ShroudedArrow/undead-311` at the frozen release tag (`JUDGED_TAG`). The code never changes after the freeze. Only the data does.
2. `make setup`, then copies the judge-mode files (tour, points, the tour zombies' card shards) from `data/judging/` in the tag into `web/public/data/frozen/`, refusing any file that differs from the judging table in `data/SNAPSHOT.md`.
3. Downloads the newest `exports-*` release asset of this repo with the job's own token, checks its SHA-256, checks that the archive holds only files the pipeline owns and that its manifest matches, and unpacks it into `web/public/data/` (the `frozen/` folder is never touched).
4. Refuses to go on unless `web/public/data/status.json` says `ok: true`.
5. Copies the failure entries from earlier nights into `status.json` under `history` (validated against `schemas/status.schema.json`), so the site shows that a night failed even after a good deploy follows.
6. `make build`, a check that the built site's `frozen/` files still equal the judging table (`snapshot.py --check-frozen`), then deploys the whole site with the Netlify CLI (`netlify deploy --prod`). Data is served from the site's own origin, so the Content Security Policy and the no-third-party-requests rule hold.

If any step fails, the deploy step is never reached, so Netlify keeps the last good deploy. The job then writes a failure entry (`{at, ok: false, stage, run_url}`) to the release `nightly-state`, opens a `needs-human` issue in `ShroudedArrow/undead-311-ops` and ends red, so GitHub's own failure email also goes out.

## Setup (human steps)

1. In `ShroudedArrow/undead-311-data`, create `.github/workflows/nightly.yml` with the contents of `ops/undead-311-data/.github/workflows/nightly.yml` from the judged repo. Keep the pinned action versions.
2. Secrets (Settings, Secrets and variables, Actions, New repository secret): `NETLIFY_AUTH_TOKEN`, `NETLIFY_SITE_ID`, `CHANNEL_TOKEN`. The click-by-click steps for each are in `docs/DEPLOY.md`. The workflow maps `CHANNEL_TOKEN` to `GITHUB_CHANNEL_TOKEN`, because a secret name cannot start with `GITHUB_`.
3. Variable (same page, Variables tab): `JUDGED_TAG`, the freeze tag in the judged repo (created by the owner after `make snapshot`; see `data/SNAPSHOT.md`).
4. The judged repo must be readable by the workflow. If it is private, add a token with read access to it and pass it as `token:` to the checkout step.
5. Publish one run's exports first (`exports_release.py publish`, see above), then Actions, Run workflow, once by hand. Check the Netlify deploy list and that the site's footer shows the new "Data as of" date.

## Checks

- `pipeline/tests/unit/test_nightly_template.py` parses the workflow (pinned actions, permissions, step order, no secret outside the steps that need it) and tests `status_history.py`.
- Failure drill: set `JUDGED_TAG` to a missing tag and run once. Expect a red run, no new Netlify deploy and no alert (the failure is before the checkout). Then break `make pipeline` on a throwaway tag. Expect a red run, an alert issue in the channel, and a `history` entry in the next good deploy's `status.json`.

## Secrets and variables (complete list)

| Where | Name | Kind | Used by | What it needs |
|---|---|---|---|---|
| `undead-311-data` Actions | `NETLIFY_AUTH_TOKEN` | secret | deploy step only | Netlify personal access token (docs/DEPLOY.md step 4) |
| `undead-311-data` Actions | `NETLIFY_SITE_ID` | secret | deploy step only | the site's API ID (docs/DEPLOY.md step 5) |
| `undead-311-data` Actions | `CHANNEL_TOKEN` | secret | the failure alert only | fine-grained token, `undead-311-ops` only, Issues read and write |
| `undead-311-data` Actions | `JUDGED_TAG` | variable | checkout | the freeze tag in the judged repo |
| where `exports_release.py publish` runs (the Kiro Web sandbox or your machine) | `DATA_RELEASE_TOKEN` | secret | publish only | fine-grained token limited to `undead-311-data`, **Contents: read and write**, nothing else |
| `undead-311` Actions | `CHANNEL_TOKEN` | secret | the CI result line | same token as above (already in docs/DEPLOY.md step 6) |

The nightly job downloads the release with its own `github.token` (`contents: write` on its own repo), so the download needs no secret. If `undead-311` is private, the checkout step also needs a read token (setup step 4).
