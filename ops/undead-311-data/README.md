# Nightly refresh template (`ShroudedArrow/undead-311-data`)

Requirement IDs: REQ-OPS-NIGHTLY.1 to .4, REQ-OPS-ALERT.1.

This folder is a template. A person copies it into the separate data repo, because the agents have no access there. Hosting is Netlify's free plan (see `docs/DEPLOY.md` in the judged repo).

## What the job does each night (03:41 UTC)

1. Checks out the judged repo `ShroudedArrow/undead-311` at the frozen release tag (`JUDGED_TAG`). The code never changes after the freeze. Only the data does.
2. `make setup`, then copies the judge-mode files (tour, points, the tour zombies' card shards) from the tag into `web/public/data/frozen/`, refusing any file that differs from the judging table in `data/SNAPSHOT.md`. Then `make data-download` and `make pipeline`, which rewrite the live files but never `frozen/`. Judge mode reads `frozen/` once the web app is updated (ops#161), so it stays on the judging snapshot.
3. Refuses to go on unless `web/public/data/status.json` says `ok: true`.
4. Copies the failure entries from earlier nights into `status.json` under `history` (validated against `schemas/status.schema.json`), so the site shows that a night failed even after a good deploy follows.
5. `make build`, a check that the built site's `frozen/` files still equal the judging table (`snapshot.py --check-frozen`), then deploys the whole site with the Netlify CLI (`netlify deploy --prod`). Data is served from the site's own origin, so the Content Security Policy and the no-third-party-requests rule hold.
6. Attaches the processed data (`processed-YYYY-MM-DD.tar.gz` and its SHA-256) to a GitHub Release `data-YYYY-MM-DD` in the data repo. A new sandbox downloads one file instead of rebuilding.

If any step fails, the deploy step is never reached, so Netlify keeps the last good deploy. The job then writes a failure entry (`{at, ok: false, stage, run_url}`) to the release `nightly-state`, opens a `needs-human` issue in `ShroudedArrow/undead-311-ops` and ends red, so GitHub's own failure email is the fallback. If the failure is before the checkout (a missing `JUDGED_TAG` or a bad tag), only that email goes out, because the alert script lives in the checkout.

## Setup (human steps)

1. In `ShroudedArrow/undead-311-data`, create `.github/workflows/nightly.yml` with the contents of `ops/undead-311-data/.github/workflows/nightly.yml` from the judged repo. Keep the pinned action versions.
2. Secrets (Settings, Secrets and variables, Actions, New repository secret): `NETLIFY_AUTH_TOKEN`, `NETLIFY_SITE_ID`, `CHANNEL_TOKEN`. The click-by-click steps for each are in `docs/DEPLOY.md`. The workflow maps `CHANNEL_TOKEN` to `GITHUB_CHANNEL_TOKEN`, because a secret name cannot start with `GITHUB_`.
3. Variable (same page, Variables tab): `JUDGED_TAG`, the freeze tag in the judged repo (created by the owner after `make snapshot`; see `data/SNAPSHOT.md`).
4. The judged repo must be readable by the workflow. If it is private, add a token with read access to it and pass it as `token:` to the checkout step.
5. Actions, Run workflow, once by hand. Check the Netlify deploy list, the new `data-YYYY-MM-DD` release, and that the site's footer shows the new "Data as of" date.

## Checks

- `pipeline/tests/unit/test_nightly_template.py` parses the workflow (pinned actions, permissions, step order, no secret outside the steps that need it) and tests `status_history.py`.
- Failure drill: set `JUDGED_TAG` to a missing tag and run once. Expect a red run, no new Netlify deploy and no alert (the failure is before the checkout). Then break `make pipeline` on a throwaway tag. Expect a red run, an alert issue in the channel, and a `history` entry in the next good deploy's `status.json`.
