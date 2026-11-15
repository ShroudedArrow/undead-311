# Deploying The Undead 311 (human steps)

Hosting is Netlify's free plan (owner decision, 2026-11-13). GitHub Pages is not used. Agents never do these steps: they involve your accounts and secrets. Nothing here costs money, and no secret goes into the repo.

Requirement IDs: REQ-OPS-HOST.1 to .4, REQ-OPS-NIGHTLY.2.

## How the pieces fit

- **Netlify's GitHub app** builds the production site from `main` and a deploy preview for each pull request. Settings come from `netlify.toml` (build `npm --prefix web ci && make build`, publish `web/dist`). The build is web-only: Netlify's build image has Node (taken from `.nvmrc`) and `make`, but not `uv`, so it never runs the Python pipeline.
- **The data repo's nightly job** (`ShroudedArrow/undead-311-data`, template in `ops/undead-311-data/`, added in the credibility layer) rebuilds the whole site with fresh data and deploys it with the Netlify CLI. The judged repo needs no Netlify secret.
- The site is served from one origin, so the Content Security Policy and the "no third-party requests" rule hold.

## Steps

### 1. Netlify account
1. Open <https://app.netlify.com/signup>.
2. Choose **Sign up with GitHub** and authorize it. Stay on the **Free** plan. Do not enter a card.

### 2. Import the site
1. In Netlify: **Add new project**, then **Import an existing project**.
2. Choose **GitHub**. When asked, install the Netlify GitHub app on **only** the repository `ShroudedArrow/undead-311` (choose "Only select repositories").
3. Pick `ShroudedArrow/undead-311`.
4. On the settings screen, leave the build command, publish directory and base directory exactly as `netlify.toml` fills them in (build `npm --prefix web ci && make build`, publish `web/dist`, no base directory). If Netlify shows different values, the file wins: do not edit them in the UI.
5. Click **Deploy**.

### 3. Branches and previews
1. Open the site, then **Site configuration**, then **Build & deploy**, then **Continuous deployment**, then **Branches and deploy contexts**.
2. Set **Production branch** to `main`.
3. Set **Deploy Previews** to **Automatically build deploy previews for all pull requests** (against `main`).
4. Set **Branch deploys** to **None**.
5. Keep **Deploy Preview comments** (the pull request comment with the preview URL) on, under the same page's notifications section. This provides the preview URL on each PR (REQ-OPS-HOST.2).

### 4. Personal access token (becomes `NETLIFY_AUTH_TOKEN`)
1. Click your avatar, then **User settings**, then **Applications**, then **Personal access tokens**, then **New access token**.
2. Name it `undead-311-nightly`, set the longest expiry offered, and click **Generate token**.
3. Copy it now. Netlify shows it once. Paste it into the secret in step 6, nowhere else.

### 5. Site ID (becomes `NETLIFY_SITE_ID`)
1. Open the site, then **Site configuration**, then **General**, then **Site details**.
2. Copy the value labelled **Site ID** (also called API ID).

### 6. GitHub secrets
1. Open `ShroudedArrow/undead-311-data`, then **Settings**, then **Secrets and variables**, then **Actions**, then **New repository secret**. Add three secrets:
   - `NETLIFY_AUTH_TOKEN` (from step 4)
   - `NETLIFY_SITE_ID` (from step 5)
   - `CHANNEL_TOKEN`: a fine-grained personal access token limited to the repository `ShroudedArrow/undead-311-ops`, with **Issues: read and write** and nothing else.
2. Open `ShroudedArrow/undead-311`, then the same **Secrets and variables**, **Actions** page, and add `CHANNEL_TOKEN` again (the CI result post uses it).
3. GitHub does not allow an Actions secret name that starts with `GITHUB_`, so the secret is called `CHANNEL_TOKEN`. Each workflow maps it to the name the scripts read: `env: GITHUB_CHANNEL_TOKEN: ${{ secrets.CHANNEL_TOKEN }}` (the scripts `scripts/hooklib.py` and `scripts/ci_channel.py` read `GITHUB_CHANNEL_TOKEN`).
4. The judged repo never needs `NETLIFY_AUTH_TOKEN` or `NETLIFY_SITE_ID`.
5. In `ShroudedArrow/undead-311-data`, on the same page, open the **Variables** tab and add the variable `JUDGED_TAG`: the freeze tag in the judged repo. The nightly job checks out that tag. The workflow template and its setup steps are in `ops/undead-311-data/README.md` (REQ-OPS-NIGHTLY.1).

### 7. Production URL
Copy the site URL from the top of the Netlify site page (`https://<name>.netlify.app`; rename it under **Site configuration**, **Change site name**). Put it in `README.md`.

## Checks after the first deploy
- The production URL loads with no login.
- A test pull request shows a **Deploy Preview** check and a comment with the preview URL.
- The page footer reads "Independent project. Not affiliated with the City of Boston." and the browser console shows no blocked requests.

## Caching and routes
`make build` ends by adding cache rules to `web/dist/_headers` (`ops/cache-headers/cache-headers.mjs`): hashed files under `assets/` are cached for a year as immutable, and `index.html`, `status.json` and everything under `data/` must be revalidated on each visit (REQ-OPS-CACHE.1). Netlify compresses text files itself, so no precompressed files are built. `netlify.toml` serves `index.html` for the app's own routes (`/judge`, `/methods` and the rest), so a shared link opens on a first visit.

## Pull request checks that need nothing from you
`.github/workflows/ci.yml` runs the tests, copy-lint, an axe scan of judge mode, the first-view budget, `pip-audit` and `npm audit --audit-level=high`, then posts one line to the channel when `CHANNEL_TOKEN` is set (it posts nothing and still passes when it is not). `.github/workflows/deep-pbt.yml` runs the property tests at ten times the examples every night.

## Codespaces
`.devcontainer/devcontainer.json` opens the repo in GitHub Codespaces with Python 3.11 and Node 22 (the versions in `.python-version` and `.nvmrc`), `uv` pinned, `DATA_DIR` set to the gitignored `.local-data/data`, and port 5173 forwarded. After the container builds, run `make pipeline-sample` (no network needed) and then `make web`. Codespaces is free for a limited number of core hours per month on a personal account (REQ-OPS-DEV.1, .2).

## Known interaction
The nightly job deploys the whole site with fresh data from the CLI. A later push to `main` triggers Netlify's own build from the data committed in the repo. After the freeze tag no more pushes land, so the nightly deploy is the last one. Before the freeze, the next nightly run replaces such a build. The generated data files under `web/public/data/` are built by the pipeline: a Netlify build serves whatever is committed there, so commit a current export before relying on a production build from `main`.

## If a step fails
Nothing here blocks the project. Without these steps, run `make build` and open `web/dist` with any static file server (`npx vite preview --root web`) as a local preview. The agents' runs continue either way and report the missing Netlify secrets as `needs-human`.
