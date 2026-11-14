#!/usr/bin/env python3
"""Pre-flight checker for The Undead 311. Standard library only; never prints secret values.

Usage:  python3 scripts/preflight_check.py [--json report.json]
Exit code: 0 = no FAILs at or below the current gate, 1 = at least one FAIL.
Checks are grouped by gate:
  G1 setup complete -> ready for the kickoff
  G2 kickoff done   -> ready to create agents, hooks, specs
  G3 specs approved -> ready for the full build run
"""
import json, os, re, shutil, subprocess, sys, urllib.request, urllib.error
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RESULTS = []

def add(gate, status, name, detail="", fix=""):
    RESULTS.append({"gate": gate, "status": status, "check": name, "detail": detail, "fix": fix})

def read(p):
    try: return (ROOT / p).read_text(encoding="utf-8")
    except Exception: return None

def http_json(url, token=None, timeout=15):
    req = urllib.request.Request(url, headers={"User-Agent": "undead311-preflight", "Accept": "application/json"})
    if token: req.add_header("Authorization", f"Bearer {token}")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.status, json.loads(r.read().decode("utf-8") or "null")
    except urllib.error.HTTPError as e:
        return e.code, None
    except Exception as e:
        return None, str(e)

# ---------- G1: files and placeholders ----------
required = ["LICENSE", "README.md", ".gitignore", ".kiroignore", ".kiro/settings/mcp.json",
            ".kiro/steering/zombie-definition.md", ".kiro/steering/agent-channel.md", "docs/PROJECT.md",
            "docs/PREFLIGHT.md", "docs/DECISIONS.md", "docs/KIRO_LOG.md", "prompts/00-kickoff.md"]
missing = [p for p in required if not (ROOT / p).exists()]
add("G1", "FAIL" if missing else "PASS", "Required files present", ", ".join(missing) or "all present",
    "Upload the full starter kit; add a LICENSE when creating the repo (MIT).")

gi = read(".gitignore") or ""
add("G1", "FAIL" if re.search(r"^\s*/?\.kiro/?\s*$", gi, re.M) else "PASS", ".kiro is not gitignored",
    "", "Remove .kiro from .gitignore (the rules can disqualify you otherwise).")

steer_bad = []
modes = {"always", "fileMatch", "manual", "auto"}
for f in sorted((ROOT / ".kiro/steering").glob("*.md")):
    t = f.read_text(encoding="utf-8")
    m = re.match(r"---\n(.*?)\n---\n", t, re.S)
    mode = re.search(r"^inclusion:\s*(\S+)", m.group(1), re.M).group(1) if m and re.search(r"^inclusion:", m.group(1), re.M) else None
    if not m or mode not in modes: steer_bad.append(f.name)
    if mode == "auto" and m and not (re.search(r"^name:", m.group(1), re.M) and re.search(r"^description:", m.group(1), re.M)):
        steer_bad.append(f.name + " (auto needs name+description)")
add("G1", "FAIL" if steer_bad else "PASS", "Steering front matter valid", ", ".join(steer_bad) or "all valid",
    "Front matter must be the first lines, with a valid inclusion mode.")

try:
    json.loads(read(".kiro/settings/mcp.json") or "")
    add("G1", "PASS", "mcp.json is valid JSON")
except Exception as e:
    add("G1", "FAIL", "mcp.json is valid JSON", str(e), "Fix the JSON syntax in .kiro/settings/mcp.json.")

ph = []
for base in [".kiro", "prompts"]:
    for f in (ROOT / base).rglob("*"):
        if f.is_file() and f.suffix in {".md", ".json", ".yaml", ".yml"}:
            t = f.read_text(encoding="utf-8", errors="ignore")
            if re.search(r"\bOWNER/undead-311", t): ph.append(str(f.relative_to(ROOT)))
add("G1", "FAIL" if ph else "PASS", "OWNER placeholder replaced", ", ".join(sorted(set(ph))[:8]) or "none left",
    "Replace OWNER with your GitHub username in .kiro/ and prompts/.")
if "/ABSOLUTE/PATH/TO" in (read(".kiro/settings/mcp.json") or ""):
    add("G1", "WARN", "DuckDB path in mcp.json", "still a placeholder",
        "Set it for your runner, or ignore in Kiro Web (agents use DuckDB via Python there).")

secret_pat = re.compile(r"(ghp_[A-Za-z0-9]{20,}|github_pat_[A-Za-z0-9_]{20,}|ksk_[A-Za-z0-9]{16,}|AKIA[0-9A-Z]{16}|-----BEGIN [A-Z ]*PRIVATE KEY-----)")
hits = []
for f in ROOT.rglob("*"):
    if f.is_file() and ".git" not in f.parts and f.stat().st_size < 2_000_000:
        try:
            if secret_pat.search(f.read_text(encoding="utf-8", errors="ignore")): hits.append(str(f.relative_to(ROOT)))
        except Exception: pass
add("G1", "FAIL" if hits else "PASS", "No secrets committed", ", ".join(hits) or "none found",
    "Remove the secret, rotate it immediately, and store it as a sandbox secret or env var instead.")

dec = read("docs/DECISIONS.md") or ""
add("G1", "PASS" if "Plan frozen" in dec else "WARN", "Plan-freeze entry logged", "",
    "Add the plan-freeze line to docs/DECISIONS.md.")

# ---------- G1: environment ----------
add("G1", "PASS" if os.environ.get("DATA_DIR") else "FAIL", "DATA_DIR is set", os.environ.get("DATA_DIR", ""),
    "Set DATA_DIR (Kiro Web: Settings > Sandbox > Environment variables; locally: setx/export).")
for var, gate, need in [("GITHUB_CHANNEL_TOKEN", "G1", "FAIL"), ("GITHUB_AUDIT_TOKEN", "G1", "WARN")]:
    add(gate, "PASS" if os.environ.get(var) else need, f"{var} available (value not shown)", "",
        f"Add {var} as a secret (Kiro Web) or environment variable.")
tools = {t: bool(shutil.which(t)) for t in ["git", "python3", "uv", "node", "npm", "gh"]}
add("G1", "PASS" if all(tools[t] for t in ["git", "python3", "uv"]) else "WARN", "Core tools available",
    ", ".join(f"{t}={'yes' if ok else 'no'}" for t, ok in tools.items()),
    "Install uv (`pip install uv`), Node 20+, and gh where missing.")

# ---------- G1: network ----------
st, body = http_json("https://data.boston.gov/api/3/action/package_show?id=311-service-requests")
if st == 200 and isinstance(body, dict):
    res = body.get("result", {}).get("resources", [])
    hosts = sorted({re.sub(r"^https?://([^/]+).*$", r"\1", r.get("url", "")) for r in res if r.get("url")})
    add("G1", "PASS", "Boston open data reachable", f"{len(res)} resources; download hosts: {', '.join(hosts)}",
        "Make sure every download host above is on your sandbox allow-list.")
else:
    add("G1", "FAIL", "Boston open data reachable", f"status={st}", "Add data.boston.gov (and its download host) to the sandbox allow-list.")

# ---------- G1: GitHub ----------
owner = None
m = re.search(r"([A-Za-z0-9][A-Za-z0-9-]*)/undead-311-ops", read(".kiro/steering/agent-channel.md") or "")
if m and m.group(1) != "OWNER": owner = m.group(1)
ch = os.environ.get("GITHUB_CHANNEL_TOKEN"); au = os.environ.get("GITHUB_AUDIT_TOKEN")
api = "https://api.github.com"
if owner and ch:
    st, repo = http_json(f"{api}/repos/{owner}/undead-311-ops", ch)
    if st == 200:
        add("G1", "PASS" if repo.get("private") else "FAIL", "Channel repo is private", f"{owner}/undead-311-ops",
            "Make undead-311-ops private (public issues are a prompt-injection risk).")
        st, labels = http_json(f"{api}/repos/{owner}/undead-311-ops/labels?per_page=100", ch)
        have = {l["name"] for l in (labels or [])}
        need = {f"to:{r}" for r in ["coroner","skeptic","cartographer","herald","data-steward","reviewer-stats","reviewer-ux","engine","web","human"]} \
             | {f"type:{t}" for t in ["status","handoff","finding","question","proposal","decision","done"]} | {"needs-human","blocked","approved","stop"}
        miss = sorted(need - have)
        add("G1", "FAIL" if miss else "PASS", "Channel labels exist", ", ".join(miss) or "all present",
            "Create the missing labels (prompts/08-agent-channel.md).")
        st, stops = http_json(f"{api}/repos/{owner}/undead-311-ops/issues?labels=stop&state=open", ch)
        add("G3", "FAIL" if stops else "PASS", "No open 'stop' issue", f"{len(stops or [])} open",
            "Close the stop issue when you're ready to run.")
    else:
        add("G1", "FAIL", "Channel token can reach undead-311-ops", f"status={st}", "Check the token's repository access and Issues permission.")
    st, _ = http_json(f"{api}/repos/{owner}/undead-311", ch)
    add("G1", "PASS" if st in (403, 404) else "WARN", "Channel token is narrow (cannot read the main repo)",
        f"status={st}", "Recreate the channel token with access to undead-311-ops ONLY.")
else:
    add("G1", "WARN", "GitHub channel checks", "skipped (owner or channel token missing)", "Fix OWNER and the channel token first.")

if owner and au:
    for r in ["undead-311", "undead-311-crew", "boston-311-power", "undead-311-data", "undead-311-ops"]:
        st, repo = http_json(f"{api}/repos/{owner}/{r}", au)
        add("G1", "PASS" if st == 200 else "FAIL", f"Repo exists: {r}", "private" if (repo or {}).get("private") else "public" if st == 200 else f"status={st}",
            "Create the repo, and include it in the audit token's access.")
    st, repo = http_json(f"{api}/repos/{owner}/undead-311", au)
    lic = ((repo or {}).get("license") or {}).get("spdx_id")
    add("G1", "PASS" if lic and lic != "NOASSERTION" else "FAIL", "License detected on the main repo", str(lic),
        "Add an OSI license file (MIT) so GitHub shows it in About.")
    st, _ = http_json(f"{api}/repos/{owner}/undead-311/branches/main/protection", au)
    add("G1", "PASS" if st == 200 else "FAIL" if st == 404 else "WARN", "Branch protection on main", f"status={st}",
        "Settings > Branches: require a pull request before merging on main (needs GitHub Pro for private repos).")
else:
    add("G1", "WARN", "Repo, license, and branch-protection checks", "skipped (no audit token)", "Add GITHUB_AUDIT_TOKEN (read-only) for these checks.")

# ---------- G2: kickoff outputs ----------
dd = read(".kiro/steering/data-dictionary.md") or ""
add("G2", "PASS" if "EXPECTED fields" not in dd else "FAIL", "Data dictionary verified by the kickoff", "",
    "Run the kickoff (prompts/00-kickoff.md) and merge its pull request.")
dr = read("docs/DECISIONS.md") or ""
add("G2", "PASS" if re.search(r"go/no-go|go-no-go", dr, re.I) else "WARN", "Go/no-go result recorded", "",
    "Record the kickoff's go/no-go result in docs/DECISIONS.md.")
add("G2", "PASS" if any((ROOT / "data/sample").glob("*.csv")) or any((ROOT / "data/sample").glob("*.parquet")) else "FAIL",
    "Committed data sample exists", "", "The kickoff creates data/sample/.")
add("G2", "PASS" if (ROOT / "Makefile").exists() else "FAIL", "Makefile exists", "", "The kickoff creates the Makefile.")

# ---------- G3: ready for the full run ----------
add("G3", "PASS" if (ROOT / "pipeline/tests/fixtures/expected_zombies.json").exists() else "FAIL",
    "Test-town answer key written (by a person)", "", "The data lead writes expected_zombies.json by hand before the build.")
agents = list((ROOT / ".kiro/agents").glob("*")) if (ROOT / ".kiro/agents").exists() else []
add("G3", "PASS" if len(agents) >= 5 else "FAIL", "Custom agents created", f"{len(agents)} found", "Run prompts/01-agents.md.")
hooks = list((ROOT / ".kiro/hooks").glob("*.json")) if (ROOT / ".kiro/hooks").exists() else []
add("G3", "PASS" if len(hooks) >= 5 else "FAIL", "Hooks created (current .json format)", f"{len(hooks)} found", "Run prompts/02-hooks.md.")
legacy = list(ROOT.rglob("*.kiro.hook"))
if legacy: add("G3", "FAIL", "No legacy-format hooks", ", ".join(map(str, legacy)), "Migrate old *.kiro.hook files; they don't run.")
specs = [d for d in (ROOT / ".kiro/specs").glob("*") if d.is_dir()] if (ROOT / ".kiro/specs").exists() else []
complete = [d.name for d in specs if all((d / f).exists() for f in ["requirements.md", "design.md", "tasks.md"])]
add("G3", "PASS" if len(complete) >= 3 else "FAIL", "Specs 1-3 have requirements, design, tasks", ", ".join(complete) or "none",
    "Run prompts/03-specs.md and review them as a team.")
wf = list((ROOT / ".kiro/workflows").glob("*.workflow.*")) if (ROOT / ".kiro/workflows").exists() else []
add("G3", "PASS" if any("build-undead-311" in w.name for w in wf) else "FAIL", "Build workflow recipe exists",
    ", ".join(w.name for w in wf) or "none", "Run prompts/04-workflow.md (smoke test first).")
add("G3", "PASS" if any("smoke" in w.name for w in wf) else "WARN", "Smoke-test recipe exists", "", "Create and run the smoke test first.")
add("G3", "PASS" if not (ROOT / ".kiro/STOP").exists() else "FAIL", "Kill-switch file absent", "", "Delete .kiro/STOP when ready.")

# Cloud copies must equal the repo copies on main (Kiro Web runs the cloud copies; see scripts/cloud_sync.py).
sys.path.insert(0, str(ROOT / "scripts"))
import cloud_sync  # noqa: E402
_cloud = cloud_sync.find_cloud_dir()
if _cloud is None:
    add("G3", "WARN", "Cloud copies match the repo on main", "no cloud-cache folder found, not compared",
        "Run on Kiro Web, or set CLOUD_CONFIG_DIR to the cloud-cache folder.")
else:
    _diffs = [p for ps in cloud_sync.compare(_cloud, cloud_sync.default_ref(ROOT)).values() for p in ps]
    add("G3", "FAIL" if _diffs else "PASS", "Cloud copies match the repo on main (workflows, agents, hooks, steering)",
        "; ".join(_diffs) or "identical",
        "RE-SYNC NEEDED: upload the repo copies in Kiro Web (Settings, Configuration Sync), then re-run `make cloud-sync-check`.")

# ---------- report ----------
order = {"FAIL": 0, "WARN": 1, "PASS": 2}
gate_reached = "G3"
for g in ["G1", "G2", "G3"]:
    if any(r["gate"] == g and r["status"] == "FAIL" for r in RESULTS):
        gate_reached = g; break
else:
    gate_reached = "READY"
for g in ["G1", "G2", "G3"]:
    print(f"\n== {g} ==")
    for r in sorted([r for r in RESULTS if r["gate"] == g], key=lambda r: order[r["status"]]):
        line = f"[{r['status']}] {r['check']}"
        if r["detail"]: line += f" — {r['detail']}"
        print(line)
        if r["status"] != "PASS" and r["fix"]: print(f"       fix: {r['fix']}")
labels = {"G1": "Setup is not complete: fix G1 before the kickoff.",
          "G2": "Setup done. Next: the kickoff (G2 items).",
          "G3": "Kickoff done. Next: agents, hooks, specs, smoke test (G3 items).",
          "READY": "All gates pass: ready for the full run."}
print(f"\nSTATUS: {labels[gate_reached]}")
if "--json" in sys.argv:
    out = Path(sys.argv[sys.argv.index("--json") + 1]); out.write_text(json.dumps({"status": gate_reached, "results": RESULTS}, indent=2))
sys.exit(0 if gate_reached == "READY" else 1)
