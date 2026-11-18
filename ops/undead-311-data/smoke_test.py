"""Smoke test of a draft deploy before it goes to production (REQ-OPS-NIGHTLY.5).

  uv run --locked python ops/undead-311-data/smoke_test.py --base-url https://<draft>--site.netlify.app \\
      --archive "$RUNNER_TEMP/exports/exports-<run>.tar.gz" --public web/public/data --judging data/judging

The nightly job deploys the built site as a draft (no --prod), runs this against the draft's URL, and promotes the same files to
production only when it exits 0. Standard library only. Checks, each printed as PASS or FAIL (all are run, so one report shows
every problem):

  1. index.html answers 200.
  2. data/status.json carries the data_version of the downloaded release (the MANIFEST.json inside the archive).
  3. The dataset is "full" in status.json and stats/scorecard.json, so the sample notice stays off.
  4. The scorecard shows no excess and no adjusted stayed-fixed rate. The site shows the excess only when the headline placebo
     interval covers 0 (web/src/lib/methods.ts, methods.md) and never shows the adjusted rate; this checks the served data
     against that rule and fails if an excess would be shown (--allow-excess lifts that once the owner has approved it).
  5. Deep links /methods, /repeat, /street, /judge and one neighborhood page answer 200.
  6. The Content-Security-Policy header is present.
  7. Every judge-mode file served under data/frozen/ is byte for byte the file in data/judging/ of the checkout.
  8. Three randomly chosen card shards load, parse, and contain no e-mail address and no phone number. A bare "@" used as "at"
     in closure text ("pole down @ Farrington Ave") is not an address: 13 of the 215 shards of the rehearsal-2 run hold one. It is
     counted in the report and only fails the check with --strict-at, which fails on any "@".

  9. The files the nightly job leaves out of the deploy (LEFT_OUT_*; nothing in the app fetches them) answer 404 on the draft.

It does not render the pages in a browser: rule 4 is checked on the files the pages render from.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import random
import re
import sys
import tarfile
import time
import urllib.error
import urllib.request
from collections.abc import Callable
from pathlib import Path

# (status, lower-cased headers, body)
Response = tuple[int, dict[str, str], bytes]
Fetch = Callable[[str], Response]

DEEP_LINKS = ("/methods", "/repeat", "/street", "/judge")
# Files the nightly job deletes from web/dist before the draft deploy, because no page of the app fetches them (checked by
# test_nightly_template.py and by loading every route in a browser). Paths are under web/dist. The workflow's trim step and the
# smoke test read the same lists.
LEFT_OUT_DIRS = ("data/incidents",)
LEFT_OUT_FILES = ("data/separate_deaths.json", "data/stats/trends.json", "data/stats/stats_status.json")
SHARDS_TO_CHECK = 3
# A phone number needs separators between its groups, so a 12-digit case id or a coordinate never matches.
PHONE = re.compile(r"(?<![\d.])(?:\+?1[\s.-]?)?(?:\(\d{3}\)\s?|\d{3}[\s.-])\d{3}[\s.-]\d{4}(?![\d.])")
# An e-mail address: something before the "@", a domain with a dot after it. "pulled @ Farrington Ave" does not match.
EMAIL = re.compile(r"[\w.+%-]+@[\w-]+(?:\.[\w-]+)+")
SHARD_FILE = re.compile(r"^(?P<slug>.+)-(?P<year>\d{4})\.json$")


def http_fetch(base_url: str, timeout: float = 30.0, retries: int = 3, wait: float = 5.0) -> Fetch:
    """A fetch that follows redirects and retries a connection error or a 5xx (a fresh draft can take a moment to answer).
    A 4xx is returned as it is, so a missing file is a failed check and not an exception."""
    base = base_url.rstrip("/")

    def fetch(path: str) -> Response:
        last: Exception | None = None
        for attempt in range(retries):
            try:
                req = urllib.request.Request(base + path, headers={"User-Agent": "undead311-smoke-test"})
                with urllib.request.urlopen(req, timeout=timeout) as r:
                    return r.status, {k.lower(): v for k, v in r.headers.items()}, r.read()
            except urllib.error.HTTPError as e:
                if e.code < 500:
                    return e.code, {k.lower(): v for k, v in e.headers.items()}, e.read()
                last = e
            except (urllib.error.URLError, TimeoutError, ConnectionError) as e:
                last = e
            if attempt + 1 < retries:
                time.sleep(wait)
        raise SmokeError(f"{path}: no answer after {retries} tries ({last})")

    return fetch


class SmokeError(Exception):
    """The draft could not be reached at all."""


def manifest_of(archive: Path) -> dict:
    """The MANIFEST.json inside an exports archive."""
    with tarfile.open(archive, "r:gz") as tar:
        member = tar.extractfile("MANIFEST.json")
        if member is None:
            raise SmokeError(f"{archive} has no MANIFEST.json")
        return json.loads(member.read())


def excess_shown(excess: dict) -> bool:
    """The site's own rule (web/src/lib/methods.ts `excessShown`): an excess is shown only when the headline placebo interval covers 0."""
    p = excess.get("placebo")
    if not isinstance(p, dict):
        return False
    nums = [p.get(k) for k in ("excess", "lo", "hi")]
    if not all(isinstance(n, (int, float)) and not isinstance(n, bool) for n in nums):
        return False
    return p["lo"] <= 0 <= p["hi"]


def neighborhood_slug(public: Path) -> str | None:
    """A neighborhood the site has pages for, from the card shard names (`<slug>-<year>.json`)."""
    for f in sorted((public / "cards").glob("*.json")):
        m = SHARD_FILE.match(f.name)
        if m:
            return m["slug"]
    return None


def sensitive_text(text: str, strict_at: bool = False) -> list[str]:
    """What must never appear in a published card: an e-mail address or a phone number (with `strict_at`, any "@")."""
    found = []
    if EMAIL.search(text):
        found.append("an e-mail address")
    elif strict_at and "@" in text:
        found.append('"@"')
    if PHONE.search(text):
        found.append("a phone number")
    return found


def run_checks(fetch: Fetch, *, manifest: dict, public: Path, judging: Path, seed: int | None = None, allow_excess: bool = False,
               neighborhood: str | None = None, strict_at: bool = False) -> list[tuple[str, bool, str]]:
    """(name, passed, detail) for every check. Nothing raises for a failed check."""
    results: list[tuple[str, bool, str]] = []

    def record(name: str, ok: bool, detail: str = "") -> None:
        results.append((name, ok, detail))

    def get(path: str) -> Response | None:
        try:
            return fetch(path)
        except SmokeError as e:
            record(f"fetch {path}", False, str(e))
            return None

    def get_json(path: str) -> dict | None:
        r = get(path)
        if r is None or r[0] != 200:
            if r is not None:
                record(f"fetch {path}", False, f"status {r[0]}")
            return None
        try:
            doc = json.loads(r[2])
        except ValueError:
            record(f"fetch {path}", False, "not JSON (a missing file answered with the app shell?)")
            return None
        return doc if isinstance(doc, dict) else None

    # 1 + 6: index.html and its security header
    index = get("/index.html")
    record("index.html returns 200", index is not None and index[0] == 200, "" if index is None else f"status {index[0]}")
    csp = index[1].get("content-security-policy", "") if index else ""
    record("Content-Security-Policy header is present", bool(csp.strip()), "missing on /index.html" if not csp.strip() else "")

    # 2 + 3: status.json
    status = get_json("/data/status.json")
    if status is not None:
        want, got = manifest.get("data_version"), status.get("data_version")
        record("status.json data_version matches the downloaded release", bool(want) and want == got, f"release {want!r}, draft {got!r}")
        record('status.json dataset is "full" (sample notice off)', status.get("dataset") == "full", f"dataset {status.get('dataset')!r}")
    scorecard = get_json("/data/stats/scorecard.json")
    if scorecard is not None:
        record('scorecard.json dataset is "full"', scorecard.get("dataset") == "full", f"dataset {scorecard.get('dataset')!r}")

    # 4: no excess and no adjusted stayed-fixed rate
    if scorecard is not None:
        adjusted = [s.get("family") for s in scorecard.get("scorecards", []) if s.get("stayed_fixed_adj") is not None]
        record("scorecard has no adjusted stayed-fixed rate", not adjusted, f"adjusted rate present for {adjusted[:5]}" if adjusted else "")
    excess = get_json("/data/stats/excess.json")
    if excess is not None:
        shown = excess_shown(excess)
        record("excess is hidden (placebo interval does not cover 0)" if not allow_excess else "excess shown only with --allow-excess",
               allow_excess or not shown, "the placebo interval covers 0, so the site would show an excess" if shown and not allow_excess else "")

    # 5: deep links
    slug = neighborhood or neighborhood_slug(public)
    links = list(DEEP_LINKS) + ([f"/neighborhood/{slug}"] if slug else [])
    if not slug:
        record("a neighborhood page was found to test", False, f"no card shard names in {public / 'cards'}")
    for link in links:
        r = get(link)
        record(f"{link} returns 200", r is not None and r[0] == 200, "" if r is None else f"status {r[0]}")

    # 7: judge-mode files
    files = sorted(p for p in judging.rglob("*") if p.is_file()) if judging.is_dir() else []
    if not files:
        record("judge-mode files exist in data/judging/", False, f"nothing under {judging}")
    for p in files:
        rel = p.relative_to(judging).as_posix()
        r = get(f"/data/frozen/{rel}")
        same = r is not None and r[0] == 200 and hashlib.sha256(r[2]).digest() == hashlib.sha256(p.read_bytes()).digest()
        detail = "" if r is None or same else (f"status {r[0]}" if r[0] != 200 else "content differs")
        record(f"frozen/{rel} matches data/judging/", same, detail)

    # 8: three random card shards
    shards = sorted(f.name for f in (public / "cards").glob("*.json"))
    picked = random.Random(seed).sample(shards, min(SHARDS_TO_CHECK, len(shards)))
    if len(shards) < SHARDS_TO_CHECK:
        record(f"at least {SHARDS_TO_CHECK} card shards to sample", False, f"{len(shards)} in {public / 'cards'}")
    for name in picked:
        r = get(f"/data/cards/{name}")
        if r is None or r[0] != 200:
            record(f"cards/{name} loads", False, "" if r is None else f"status {r[0]}")
            continue
        try:
            json.loads(r[2])
        except ValueError:
            record(f"cards/{name} loads", False, "not JSON")
            continue
        body = r[2].decode("utf-8", errors="replace")
        bad = sensitive_text(body, strict_at)
        at = body.count("@")
        record(f"cards/{name} loads and holds no e-mail address or phone number", not bad,
               f"found {', '.join(bad)}" if bad else f"{at} bare @ used as 'at'" if at else "")

    # 9: the files left out of the deploy are not served (a 404, not an app shell and not a file)
    for path in LEFT_OUT_FILES:
        r = get(f"/{path}")
        record(f"{path} is left out of the deploy", r is not None and r[0] == 404, "" if r is None else f"status {r[0]}")
    for d in LEFT_OUT_DIRS:
        local = public / Path(d).relative_to("data")
        names = sorted(f.name for f in local.glob("*.json"))
        if not names:
            record(f"{d} has files to check", False, f"nothing under {local}")
        for name in random.Random(seed).sample(names, min(SHARDS_TO_CHECK, len(names))):
            r = get(f"/{d}/{name}")
            record(f"{d}/{name} is left out of the deploy", r is not None and r[0] == 404, "" if r is None else f"status {r[0]}")
    return results


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--base-url", required=True, help="the draft deploy's URL")
    p.add_argument("--archive", type=Path, required=True, help="the downloaded exports-<run>.tar.gz (its MANIFEST.json names the data_version)")
    p.add_argument("--public", type=Path, default=Path("web/public/data"), help="the unpacked data folder (names the card shards)")
    p.add_argument("--judging", type=Path, default=Path("data/judging"))
    p.add_argument("--neighborhood", default=None, help="neighborhood slug for the page check (default: from the card shard names)")
    p.add_argument("--seed", type=int, default=None, help="seed for the shard sample (default: random)")
    p.add_argument("--retries", type=int, default=3, help="tries per request (a fresh draft can take a moment to answer)")
    p.add_argument("--retry-wait", type=float, default=5.0, help="seconds between tries")
    p.add_argument("--strict-at", action="store_true", help='fail on any "@" in a card, not only on an e-mail address')
    p.add_argument("--allow-excess", action="store_true", help="do not fail when the site would show the excess")
    args = p.parse_args(argv)
    try:
        manifest = manifest_of(args.archive)
        results = run_checks(http_fetch(args.base_url, retries=args.retries, wait=args.retry_wait), manifest=manifest, public=args.public, judging=args.judging, seed=args.seed,
                             allow_excess=args.allow_excess, neighborhood=args.neighborhood, strict_at=args.strict_at)
    except (SmokeError, OSError, tarfile.TarError, KeyError) as e:
        print(f"smoke test: could not run: {e}", file=sys.stderr)
        return 2
    failed = [r for r in results if not r[1]]
    for name, ok, detail in results:
        print(f"{'PASS' if ok else 'FAIL'}  {name}" + (f"  ({detail})" if detail else ""))
    print(f"smoke test: {len(results) - len(failed)} of {len(results)} checks passed against {args.base_url}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
