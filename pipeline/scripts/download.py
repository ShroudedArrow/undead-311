"""Download Boston 311 CSVs (2015-present) into $DATA_DIR/raw/ (REQ-ING-1).

Resolves DATA_DIR with the tech.md fallback, skips files already present,
and records hashes + download date in data/SNAPSHOT.md.
"""

from __future__ import annotations

import datetime as dt
import hashlib
import json
import os
import re
import subprocess
import sys
import urllib.request
from pathlib import Path

PACKAGE_URL = "https://data.boston.gov/api/3/action/package_show?id=311-service-requests"
MIN_YEAR = 2015
UA = "undead-311-pipeline/0.1 (+https://github.com/ShroudedArrow/undead-311)"


class _Redirect(urllib.request.HTTPRedirectHandler):
    """Strip the explicit ':443' S3 adds to signed redirects (it breaks the signature in urllib)."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return super().redirect_request(req, fp, code, msg, headers, newurl.replace(":443/", "/", 1))


_OPENER = urllib.request.build_opener(_Redirect)


def repo_root() -> Path:
    out = subprocess.run(["git", "rev-parse", "--show-toplevel"], capture_output=True, text=True, check=True)
    return Path(out.stdout.strip()).resolve()


def resolve_data_dir() -> Path:
    """DATA_DIR if set and writable, else <repo root>/.local-data/data."""
    env = os.environ.get("DATA_DIR")
    if env:
        try:
            p = Path(env)
            p.mkdir(parents=True, exist_ok=True)
            probe = p / ".write-test"
            probe.touch()
            probe.unlink()
            return p.resolve()
        except OSError:
            print(f"DATA_DIR={env} not writable; using fallback", file=sys.stderr)
    p = repo_root() / ".local-data" / "data"
    p.mkdir(parents=True, exist_ok=True)
    return p


def fetch_json(url: str) -> dict:
    with _OPENER.open(urllib.request.Request(url, headers={"User-Agent": UA}), timeout=60) as r:
        return json.load(r)


def wanted_resources(pkg: dict) -> list[dict]:
    out = []
    for r in pkg["resources"]:
        if (r.get("format") or "").upper() != "CSV":
            continue
        name = r.get("name") or ""
        m = re.search(r"(20\d\d)", name)
        if "NEW SYSTEM" in name.upper():
            label = "new_system"
        elif m and int(m.group(1)) >= MIN_YEAR:
            label = m.group(1)
        else:
            continue
        out.append({"label": label, "name": name, "url": r["url"], "last_modified": r.get("last_modified")})
    return sorted(out, key=lambda x: x["label"])


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def main() -> None:
    data_dir = resolve_data_dir()
    raw = data_dir / "raw"
    raw.mkdir(parents=True, exist_ok=True)
    print(f"DATA_DIR resolved to {data_dir}")
    pkg = fetch_json(PACKAGE_URL)["result"]
    rows = []
    for r in wanted_resources(pkg):
        dest = raw / f"311_{r['label']}.csv"
        if dest.exists() and dest.stat().st_size > 0:
            print(f"skip {dest.name}")
        else:
            print(f"get  {dest.name}")
            tmp = dest.with_suffix(".part")
            req = urllib.request.Request(r["url"], headers={"User-Agent": UA})
            with _OPENER.open(req, timeout=300) as resp, tmp.open("wb") as out:
                while chunk := resp.read(1 << 20):
                    out.write(chunk)
            tmp.rename(dest)
        rows.append((dest.name, r["name"], r["last_modified"], dest.stat().st_size, sha256(dest)))
    snap = Path(repo_root() / "data" / "SNAPSHOT.md")
    lines = [
        "# Data snapshot",
        "",
        f"Downloaded: {dt.date.today().isoformat()} (source: Analyze Boston, dataset 311-service-requests)",
        "",
        "| file | resource | last_modified | bytes | sha256 |",
        "|---|---|---|---|---|",
    ]
    lines += [f"| {a} | {b} | {c} | {d} | {e} |" for a, b, c, d, e in rows]
    snap.write_text("\n".join(lines) + "\n")
    print(f"wrote {snap}")


if __name__ == "__main__":
    main()
