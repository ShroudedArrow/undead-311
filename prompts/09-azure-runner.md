# 09 — Unattended runs on an Azure VM (fallback if Kiro Web isn't available; ~1 hour once)

## 0. Laptop-free bootstrap (if you skip laptop setup entirely)
Your laptop then needs only a browser and Windows' built-in `ssh`/`scp`. No installs.
1. **In the browser:** create the five repos on GitHub (`undead-311`, `undead-311-crew`, `boston-311-power`, `undead-311-data` with an MIT license; `undead-311-ops` private, no license needed) (solo project: no collaborators). Create the channel token (and, for audits, the read-only audit token in `prompts/10-audit.md`). Generate a Kiro API key in your Kiro account.
2. **Copy the kit to the VM** from PowerShell: `scp -i C:\path\to\key.pem $HOME\Downloads\undead-311-starter.zip azureuser@VM_IP:/tmp/`, then `sudo chmod 644 /tmp/undead-311-starter.zip` on the VM.
3. **On the VM as `kiro`** (after steps 1–3 below): clone `undead-311`, unzip the kit into it, replace `OWNER` with your username, make the first commit, and push to `main`. **Then** turn on branch protection for `main` in the browser (so this first push isn't blocked).
4. **Create the channel labels** from the VM with the channel token: `GH_TOKEN=$GITHUB_CHANNEL_TOKEN` plus the label commands in `prompts/08-agent-channel.md`.
5. **Interactive work** (specs, reviews): use Kiro Web (app.kiro.dev) in the browser if your plan includes it; it works from the repo's committed `.kiro/` config. Otherwise use `kiro-cli` interactively over SSH.

Goal: every long run (kickoff, overnight builds, Crew during judging) happens on a disposable cloud machine with no access to your laptop, and runs with no permission prompts. Safety comes from limits Kiro can't switch off: what the machine holds, what its keys can reach, and what GitHub allows.

## 1. Create the VM (Azure portal)
- Ubuntu 24.04 LTS, about 2 vCPUs / 4 GB RAM, 64 GB disk. Check the monthly price before creating it.
- Login: **SSH key only**. Inbound rule: SSH (port 22) from **your IP only**.
- Cost Management → Budgets: alerts at $25, $50, and $75 of your $100 credit.
- Do NOT enable daily auto-shutdown on build nights. Stop the VM on days you aren't using it.

## 2. Prepare it (as your admin user)
```bash
sudo apt update && sudo apt install -y git tmux curl unzip make gh jq
sudo adduser --disabled-password --gecos "" kiro    # the user agents run as: NO sudo
```
Everything else happens as `kiro` (`sudo -iu kiro`). Agents running as `kiro` can't change the operating system or install system packages.

## 3. Set up the `kiro` user
```bash
curl -LsSf https://astral.sh/uv/install.sh | sh && uv python install 3.12
curl -o- https://raw.githubusercontent.com/nvm-sh/nvm/v0.40.1/install.sh | bash   # Node 20+ (Ubuntu's own package is older)
source ~/.nvm/nvm.sh && nvm install --lts
curl -fsSL https://cli.kiro.dev/install | bash
ssh-keygen -t ed25519 -f ~/.ssh/undead311_deploy -N ""
```
- Add `~/.ssh/undead311_deploy.pub` as a **deploy key with write access** on the `undead-311` repo only (repo Settings → Deploy keys). Clone with SSH.
- Secrets file, readable only by `kiro`:
```bash
cat > ~/.undead311.env << 'X'
export KIRO_API_KEY="..."            # Kiro account → API keys (headless mode)
export GITHUB_CHANNEL_TOKEN="..."    # the channel token (undead-311-ops issues only)
export GH_TOKEN="$GITHUB_CHANNEL_TOKEN"
export DATA_DIR="$HOME/undead311-data"
X
chmod 600 ~/.undead311.env && echo 'source ~/.undead311.env' >> ~/.profile
mkdir -p ~/undead311-data/raw ~/undead311-data/processed ~/logs
```
- Point the DuckDB path in `.kiro/settings/mcp.json` at `/home/kiro/undead311-data/processed/undead311.duckdb` (keep this change local to the VM, or make the path configurable).

- Create an empty database file before the first run. With `--require-mcp-startup`, a missing file would make the DuckDB MCP server fail and stop the run:
```bash
source ~/.profile && uv run --with duckdb python -c "import duckdb,os; duckdb.connect(os.environ['DATA_DIR']+'/processed/undead311.duckdb').close()"
```
- Quick headless test: `kiro-cli chat --no-interactive --trust-all-tools --require-mcp-startup "List the MCP servers you can use and the files in this folder."`

## 4. No-prompt permissions
`~/.kiro/settings/permissions.yaml` (user scope, on the VM only):
```yaml
rules:
  - capability: all
    effect: allow
```
Runs also use `--trust-all-tools`. The hard limits live outside Kiro's trust setting:
- **Hooks still run:** the guard (no force pushes; no edits to steering, settings, hooks, agents, or the expected answers; no deleting the repo or data) and the kill switch.
- **GitHub enforces:** branch protection on `main`, so agents can only push `run/...` branches. A person opens and merges the pull request in the morning.
- **Keys are narrow:** a deploy key for one repo, and a channel token for one repo's issues.
- **Time-boxed:** every run is wrapped in `timeout 8h`.

## 5. The nightly run (ask Kiro to write this as `scripts/run_night.sh`)
1. `git pull` on `main`; create branch `run/$(date +%F)`.
2. Run inside `tmux`, so it survives disconnects:
   `timeout 8h kiro-cli chat --no-interactive --trust-all-tools --require-mcp-startup "<the night's prompt>" 2>&1 | tee ~/logs/$(date +%F).log`
   The night's prompt: "Run the workflow recipe .kiro/workflows/build-undead-311.workflow.yaml. This is an unattended run: follow the unattended-run rule in structure.md."
3. Push the branch, then post the outcome and the log location to the run-log issue in the channel.

`--require-mcp-startup` makes the run fail fast if an MCP server didn't start, instead of hanging all night.

## 6. Three ways to stop a run
- **From your phone:** open an issue labeled `stop` in `undead-311-ops`. The kill-switch hook checks it before each step.
- **From a terminal:** SSH in and `touch .kiro/STOP`, or `tmux kill-session`.
- **Last resort:** stop the VM in the Azure portal or app.

## 7. Test before the first real night (pre-flight A33)
With `--trust-all-tools` on, ask Kiro to run a blocked command (for example, a force push to a throwaway branch) and confirm the guard hook still blocks it. Then open a `stop` issue and confirm the next step halts.

## 8. After the hackathon
Revoke the Kiro API key, the channel token, and the deploy key, and delete the VM (or keep it only while Crew runs during judging, through Jan 29).
