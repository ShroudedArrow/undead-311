"""guard hook (PreToolUse on EVERY tool call; no matcher). Standard library only.

The script classifies the call itself (hooklib.tool_kind): shell tools get the command checks, file-writing tools
get the protected-path checks, and every other or unknown tool is allowed.

Blocks (exit 2, reason on stderr) regardless of trust settings:
  * `rm -rf` (any recursive+force spelling) whose target is inside the repo or $DATA_DIR
    (build caches such as node_modules, dist, __pycache__ are allowed; see ARTIFACT_NAMES);
  * `git push --force` / `-f` / `--force-with-lease` / `+refspec`; `git reset --hard`; `git clean -f`;
  * any modification of a PROTECTED path, through a write tool or a shell command:
      .kiro/steering/**, .kiro/settings/**, .kiro/hooks/**, .kiro/agents/**  (humans only)
      .kiro/STOP                                                           (humans only)
      pipeline/tests/fixtures/expected_zombies.json                        (hand-written answer key)
Protected patterns match under ANY path prefix (relative, /projects/sandbox/undead-311/..., /projects/sandbox/.kiro/...).
Always ALLOWED: anything under .kiro/workflow-runs/** (workflow artifacts), and task checkbox updates in
.kiro/specs/**/tasks.md. While a workflow run is active (a `.kiro/workflow-runs/*/RUNNING` marker exists),
a tasks.md edit through str_replace must change checkbox state only.

Limits (documented in docs/DECISIONS.md): a program that writes a protected file itself (for example a Python
script) cannot be seen from the command line; reviewers, branch protection and the owner's PR review cover that.

Manual test: `echo '{"tool_name":"execute_bash","tool_input":{"command":"git push --force"}}' | python3 scripts/guard.py`
"""

from __future__ import annotations

import fnmatch
import os
import re
import shlex
import sys
from pathlib import Path, PurePosixPath

sys.path.insert(0, str(Path(__file__).resolve().parent))
import hooklib

BLOCK = 2
PROTECTED = [
    ".kiro/steering/**",
    ".kiro/settings/**",
    ".kiro/hooks/**",
    ".kiro/agents/**",
    ".kiro/STOP",
    "pipeline/tests/fixtures/expected_zombies.json",
]
PROTECTED_NAMES = [".kiro/steering", ".kiro/settings", ".kiro/hooks", ".kiro/agents", ".kiro/STOP", "expected_zombies.json"]
ALLOWED = [".kiro/workflow-runs/**"]
TASKS_GLOB = ".kiro/specs/**/tasks.md"
ARTIFACT_NAMES = {"node_modules", "dist", "build", "__pycache__", ".pytest_cache", ".ruff_cache", ".hypothesis",
                  "coverage", ".vite", "playwright-report", "test-results"}
WRITE_KEYS = ("path", "targetFile", "target_file", "file_path", "filePath", "file")
# shell verbs that modify the paths they name
MODIFY_VERBS = {"rm", "rmdir", "mv", "cp", "touch", "truncate", "tee", "ln", "install", "dd", "chmod", "chown",
                "unlink", "shred", "rsync"}
GIT_MODIFY = {"rm", "mv", "checkout", "restore", "apply", "am", "stash"}


def rel(path: str, root: Path) -> str | None:
    """Repo-relative POSIX path, or None when the path is outside the repo."""
    p = Path(os.path.expandvars(os.path.expanduser(path)))
    p = (p if p.is_absolute() else Path.cwd() / p).resolve()
    try:
        return PurePosixPath(p.relative_to(root)).as_posix()
    except ValueError:
        return None


def match(r: str, globs: list[str]) -> bool:
    return any(fnmatch.fnmatch(r, g) or r == g.rstrip("/*") or r.startswith(g.rstrip("*")) for g in globs)


def _forms(path: str) -> list[str]:
    """Absolute POSIX spellings of a path: lexically normalised, and symlink-resolved when that differs."""
    p = Path(os.path.expandvars(os.path.expanduser(path)))
    p = p if p.is_absolute() else Path.cwd() / p
    out = [PurePosixPath(os.path.normpath(p)).as_posix()]
    try:
        resolved = PurePosixPath(p.resolve()).as_posix()
    except (OSError, RuntimeError):
        resolved = out[0]
    if resolved not in out:
        out.append(resolved)
    return out


def _suffix_verdict(form: str) -> bool:
    """True when the path is protected, whatever folder prefixes it. Hooks load from the sandbox's cloud
    configuration (/projects/sandbox/.kiro) and run elsewhere, so `.kiro/hooks/x` may arrive as a relative path,
    /projects/sandbox/undead-311/.kiro/hooks/x or /projects/sandbox/.kiro/hooks/x. Every trailing run of path
    components is tested against the patterns; the leftmost hit decides, so `.kiro/workflow-runs/**` stays allowed."""
    parts = [x for x in form.split("/") if x]
    for i in range(len(parts)):
        suffix = "/".join(parts[i:])
        if match(suffix, ALLOWED):
            return False
        if match(suffix, PROTECTED):
            return True
    return False


def is_protected(path: str | None) -> bool:
    """Protected-path check on a raw path string (relative to the cwd, or absolute with any prefix)."""
    return bool(path) and any(_suffix_verdict(f) for f in _forms(path))


def run_active(root: Path) -> bool:
    return any((root / ".kiro" / "workflow-runs").glob("*/RUNNING"))


def checkbox_only(old: str, new: str) -> bool:
    norm = lambda s: re.sub(r"\[[ xX~-]\]", "[]", s)
    return old != new and norm(old) == norm(new)


def check_write(ti: dict, name: str, root: Path) -> str | None:
    target = hooklib.first(ti, *WRITE_KEYS)
    if not target:
        return None
    if is_protected(str(target)):
        return f"{name} on protected path {target} (humans only)"
    r = rel(str(target), root)
    if r is None:
        return None
    if fnmatch.fnmatch(r, TASKS_GLOB) and run_active(root):
        old = hooklib.first(ti, "oldStr", "old_str", "old_string")
        new = hooklib.first(ti, "newStr", "new_str", "new_string")
        if old is not None and new is not None and not checkbox_only(str(old), str(new)):
            return f"{r}: only task checkbox updates are allowed during a workflow run"
        if old is None and name not in ("str_replace",):
            return f"{r}: rewriting tasks.md is not allowed during a workflow run (update checkboxes with str_replace)"
    return None


def split_commands(cmd: str) -> list[list[str]]:
    """Split a shell line into simple commands on ; && || | and newlines; tokens via shlex (best effort)."""
    parts = re.split(r"\|\||&&|;|\||\n", cmd)
    out = []
    for p in parts:
        try:
            toks = shlex.split(p, comments=True)
        except ValueError:
            toks = p.split()
        # drop env assignments and common wrappers
        while toks and (re.match(r"^[A-Za-z_][A-Za-z0-9_]*=", toks[0]) or toks[0] in ("sudo", "command", "env", "nohup", "time")):
            toks = toks[1:]
        if toks:
            out.append(toks)
    return out


def rm_rf_problem(toks: list[str], root: Path, data_dir: Path | None) -> str | None:
    flags = "".join(t.lstrip("-") for t in toks[1:] if t.startswith("-") and not t.startswith("--"))
    longs = {t for t in toks[1:] if t.startswith("--")}
    recursive = "r" in flags or "R" in flags or "--recursive" in longs
    force = "f" in flags or "--force" in longs
    if not (recursive and force):
        return None
    targets = [t for t in toks[1:] if not t.startswith("-")]
    if not targets:
        return "rm -rf without a target"
    for t in targets:
        if any(ch in t for ch in "*?$`") or t in ("/", ".", "..", "~"):
            return f"rm -rf with a wildcard or variable target ({t})"
        p = Path(os.path.expanduser(t))
        p = (p if p.is_absolute() else Path.cwd() / p).resolve()
        inside_repo = p == root or root in p.parents
        inside_data = data_dir is not None and (p == data_dir or data_dir in p.parents)
        if (inside_repo or inside_data) and p.name not in ARTIFACT_NAMES and not match(rel(str(p), root) or "", ALLOWED):
            return f"rm -rf inside the repo or $DATA_DIR ({t})"
    return None


def git_problem(toks: list[str], root: Path) -> str | None:
    args = toks[1:]
    while args and args[0] in ("-C", "-c"):
        args = args[2:]
    if not args:
        return None
    sub, rest = args[0], args[1:]
    if sub == "push":
        if any(a in ("-f", "--force", "--force-with-lease", "--force-if-includes") or a.startswith("--force")
               or (a.startswith("-") and not a.startswith("--") and "f" in a) for a in rest):
            return "git push --force is forbidden"
        if any(a.startswith("+") for a in rest):
            return "git push with a +refspec (force) is forbidden"
        if any(a.startswith(":") or a == "--delete" or a == "-d" for a in rest):
            return "deleting a remote branch is forbidden"
    if sub == "reset" and "--hard" in rest:
        return "git reset --hard is forbidden"
    if sub == "clean" and any(a.startswith("-") and "f" in a for a in rest):
        return "git clean -f is forbidden"
    if sub in GIT_MODIFY and any(is_protected(a) for a in rest if not a.startswith("-")):
        return f"git {sub} on a protected path"
    if sub == "checkout" and "--" in rest and any(is_protected(a) for a in rest[rest.index("--") + 1:]):
        return "git checkout on a protected path"
    return None


def check_shell(cmd: str, root: Path) -> str | None:
    dd = os.environ.get("DATA_DIR")
    data_dir = Path(dd).resolve() if dd else None
    # redirections into protected paths: > path, >> path, tee path
    for m in re.finditer(r"(?:>>?|>\|)\s*([^\s;&|]+)", cmd):
        if is_protected(m.group(1).strip("'\"")):
            return f"redirect into protected path {m.group(1)}"
    # in-place editors and writers naming a protected path
    for toks in split_commands(cmd):
        exe = os.path.basename(toks[0])
        if exe == "rm":
            why = rm_rf_problem(toks, root, data_dir)
            if why:
                return why
        if exe == "git":
            why = git_problem(toks, root)
            if why:
                return why
        targets = [t for t in toks[1:] if not t.startswith("-")]
        prot = [t for t in targets if is_protected(t)]
        if not prot:
            continue
        if exe in MODIFY_VERBS:
            return f"{exe} on protected path {prot[0]}"
        if exe in ("sed", "perl", "ruby") and any(t.startswith("-i") or t == "-pi" for t in toks[1:]):
            return f"in-place edit of protected path {prot[0]}"
        if exe in ("python", "python3", "node") and any(t in ("-c", "-e") for t in toks[1:]):
            return f"inline script naming protected path {prot[0]}"
    # a literal protected filename with an inline script that opens files for writing
    if any(n in cmd for n in PROTECTED_NAMES) and re.search(r"open\([^)]*['\"][wa]", cmd):
        return "inline script writing a protected path"
    return None


def decide(payload: dict, root: Path) -> str | None:
    """The hook has no matcher, so it sees every tool call and decides from the tool name and arguments.

    shell tools (shell, execute_bash, ...) -> forbidden commands; file-writing tools -> protected paths;
    every other tool, including tools it has never seen -> allowed.
    """
    name = hooklib.tool_name(payload)
    ti = hooklib.tool_input(payload)
    kind = hooklib.tool_kind(name)
    if kind == "shell":
        cmd = hooklib.first(ti, "command", "cmd", "script")
        return check_shell(cmd, root) if isinstance(cmd, str) else None
    if kind == "write":
        return check_write(ti, name, root)
    return None


def main() -> int:
    payload = hooklib.read_payload()
    root = hooklib.repo_root()
    try:
        why = decide(payload, root)
    except Exception as e:  # a guard bug must not wedge every tool call; report it loudly  # noqa: BLE001
        hooklib.log_stderr(f"guard: internal error {type(e).__name__}: {e}; allowing")
        return 0
    if why:
        hooklib.log_stderr(f"GUARD BLOCKED: {why}. See .kiro/hooks/guard.json and structure.md.")
        return BLOCK
    return 0


if __name__ == "__main__":
    sys.exit(main())
