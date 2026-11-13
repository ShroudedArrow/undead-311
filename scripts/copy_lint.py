"""make copy-lint: flag banned words/patterns (voice.md) and banned CSS defaults (design-system.md).

Scans copy (web/src/copy/**, docs/**, README.md, drafts/**) for voice.md's banned words and patterns, and
web/src/** styles/components for banned CSS defaults (gradients, uppercase + letter-spacing labels, an arrow
in button text). Counts TODO-COPY markers. Standard library only.

Exit 1 when any banned item is found. TODO-COPY markers are reported but allowed, unless --strict-todo
(used for the Dec 2 freeze) is passed. A line containing `copy-lint: ignore` is skipped; files that quote
the banned list on purpose are listed in QUOTING_FILES.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
COPY_GLOBS = ["web/src/copy/**/*.json", "docs/**/*.md", "README.md", "drafts/**/*.md", "drafts/**/*.txt"]
CODE_GLOBS = ["web/src/**/*.css", "web/src/**/*.scss", "web/src/**/*.tsx", "web/src/**/*.ts"]
# files that discuss the rules themselves (quoting a banned word is not using it)
QUOTING_FILES = {"docs/AUDIT.md", "docs/PROJECT.md", "docs/KIRO_SETUP.md", "docs/PREFLIGHT.md", "docs/KIRO_LOG.md",
                 "docs/DECISIONS.md", "docs/LEARNINGS.md"}

BANNED_WORDS = [
    "delve", "seamless", "seamlessly", "leverage", "unlock", "empower", "robust", "cutting-edge", "game-changer",
    "revolutionize", "harness", "elevate", "supercharge", "effortless", "effortlessly", "embark", "tapestry",
    "testament to", "in the realm of", "navigate the complexities", "in today's fast-paced world",
    "whether you're", "at the end of the day", "introducing",
]
WORD_RE = re.compile(r"\b(" + "|".join(re.escape(w) for w in BANNED_WORDS) + r")\b", re.IGNORECASE)
NOT_JUST_RE = re.compile(r"\bit'?s not just\b.{0,60}\bit'?s\b", re.IGNORECASE)
EMOJI_RE = re.compile("[\U0001F300-\U0001FAFF\u2600-\u27BF]")
SMALL = {"a", "an", "and", "as", "at", "but", "by", "for", "in", "of", "on", "or", "the", "to", "vs", "via", "with"}

CSS_RULES = [
    (re.compile(r"(linear|radial|conic)-gradient\(", re.IGNORECASE), "gradient (design-system.md: no gradients)"),
    (re.compile(r"backdrop-filter\s*:", re.IGNORECASE), "glassmorphism (backdrop-filter)"),
    (re.compile(r"\bbg-gradient-|\bfrom-\w+-\d{2,3}\b.*\bto-\w+-\d{2,3}\b"), "gradient utility classes"),
]
UPPER_RE = re.compile(r"text-transform\s*:\s*uppercase|\buppercase\b", re.IGNORECASE)
TRACKING_RE = re.compile(r"letter-spacing\s*:|\btracking-(wide|wider|widest)\b", re.IGNORECASE)
BUTTON_ARROW_RE = re.compile(r"<button[^>]*>[^<]*(→|->)[^<]*</button>|\"[^\"]*(button|cta)[^\"]*\"\s*:\s*\"[^\"]*→", re.IGNORECASE)


def files(globs: list[str]) -> list[Path]:
    out: set[Path] = set()
    for g in globs:
        out.update(p for p in ROOT.glob(g) if p.is_file() and "node_modules" not in p.parts)
    return sorted(out)


def title_case(heading: str) -> bool:
    words = [w for w in re.findall(r"[A-Za-z][A-Za-z'’-]*", heading)]
    if len(words) < 3:
        return False
    rest = [w for w in words[1:] if w.lower() not in SMALL and not w.isupper()]
    return len(rest) >= 2 and all(w[0].isupper() for w in rest)


def lint_copy(path: Path, findings: list[str]) -> int:
    rel = path.relative_to(ROOT).as_posix()
    text = path.read_text(errors="replace")
    todos = text.count("TODO-COPY")
    quoting = rel in QUOTING_FILES
    in_code = False
    para_dashes = 0
    for n, line in enumerate(text.splitlines(), 1):
        if line.strip().startswith("```"):
            in_code = not in_code
            continue
        if in_code or "copy-lint: ignore" in line:
            continue
        if not line.strip():
            para_dashes = 0
            continue
        if not quoting:
            for m in WORD_RE.finditer(line):
                findings.append(f"{rel}:{n}: banned word '{m.group(1)}'")
            if NOT_JUST_RE.search(line):
                findings.append(f"{rel}:{n}: banned pattern \"it's not just X, it's Y\"")
        if EMOJI_RE.search(line) and (line.lstrip().startswith(("-", "*", "#")) or rel.startswith("web/")):
            findings.append(f"{rel}:{n}: emoji bullet or header")
        if not quoting and re.search(r"[A-Za-z0-9)]!(\s|$|\")", line) and not re.search(r"!\[|!=|`[^`]*![^`]*`", line):
            findings.append(f"{rel}:{n}: exclamation mark")
        if line.startswith("#") and title_case(line.lstrip("# ")):
            findings.append(f"{rel}:{n}: Title Case heading")
        para_dashes += line.count("—")
        if para_dashes > 1 and not quoting:
            findings.append(f"{rel}:{n}: more than one em dash in a paragraph")
            para_dashes = -10**6  # report once per paragraph
    return todos


def lint_code(path: Path, findings: list[str]) -> int:
    rel = path.relative_to(ROOT).as_posix()
    text = path.read_text(errors="replace")
    for n, line in enumerate(text.splitlines(), 1):
        if "copy-lint: ignore" in line:
            continue
        for rx, why in CSS_RULES:
            if rx.search(line):
                findings.append(f"{rel}:{n}: {why}")
        if UPPER_RE.search(line) and TRACKING_RE.search(line):
            findings.append(f"{rel}:{n}: uppercase + letter-spacing label")
    for m in BUTTON_ARROW_RE.finditer(text):
        findings.append(f"{rel}: arrow in button text: {m.group(0)[:60]}")
    # same block: uppercase and letter-spacing within one CSS rule
    for block in re.findall(r"\{[^{}]*\}", text) if path.suffix in (".css", ".scss") else []:
        if UPPER_RE.search(block) and TRACKING_RE.search(block):
            findings.append(f"{rel}: uppercase + letter-spacing in one CSS rule")
    return text.count("TODO-COPY")


def main() -> int:
    strict = "--strict-todo" in sys.argv
    findings: list[str] = []
    todos = sum(lint_copy(p, findings) for p in files(COPY_GLOBS))
    todos += sum(lint_code(p, findings) for p in files(CODE_GLOBS))
    for f in findings:
        print(f)
    print(f"copy-lint: {len(findings)} banned item(s); {todos} TODO-COPY marker(s)")
    if findings or (strict and todos):
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
