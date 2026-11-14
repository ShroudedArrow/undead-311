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
PACKAGE_API = "https://data.boston.gov/api/3/action/package_show?id="
# Geography files (REQ-ING-SNAP.1): raw file name -> (CKAN package id, resource format). Recorded in data/SNAPSHOT.md.
GEO_FILES = {
    "street_segments_sam.geojson": ("boston-street-segments-sam-system", "GEOJSON"),
    "neighborhood_boundaries.geojson": ("bpda-neighborhood-boundaries", "GEOJSON"),
}
_GEO_NAMES = "|".join(re.escape(n) for n in GEO_FILES)
GEO_ROW_RE = re.compile(rf"^\|\s*(?:{_GEO_NAMES})\s*\|.*\n?", re.MULTILINE)
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


def geo_resource(pkg: dict, fmt: str) -> dict | None:
    """The package's resource in `fmt` (GEOJSON, case-insensitive), or None."""
    for r in pkg.get("resources", []):
        if (r.get("format") or "").upper() == fmt.upper():
            return r
    return None


def upsert_geo_rows(snapshot_text: str, rows: list[tuple]) -> str:
    """`snapshot_text` with the geography rows replaced by `rows` (name, resource, last_modified, bytes, sha256), appended
    after the table's last row. The 311 rows are left as they are (REQ-ING-SNAP.1)."""
    kept = GEO_ROW_RE.sub("", snapshot_text).rstrip("\n")
    return kept + "\n" + "".join(f"| {a} | {b} | {c} | {d} | {e} |\n" for a, b, c, d, e in rows)


def download_geo(raw: Path) -> list[tuple]:
    """Fetch the street segments and neighborhood boundaries into `raw` (skips files already present)."""
    rows = []
    for name, (package, fmt) in GEO_FILES.items():
        res = geo_resource(fetch_json(PACKAGE_API + package)["result"], fmt)
        if res is None:
            raise RuntimeError(f"no {fmt} resource in CKAN package {package}")
        dest = raw / name
        if dest.exists() and dest.stat().st_size > 0:
            print(f"skip {dest.name}")
        else:
            print(f"get  {dest.name}")
            tmp = dest.with_suffix(".part")
            with _OPENER.open(urllib.request.Request(res["url"], headers={"User-Agent": UA}), timeout=300) as resp, tmp.open("wb") as out:
                while chunk := resp.read(1 << 20):
                    out.write(chunk)
            tmp.rename(dest)
        rows.append((dest.name, res.get("name") or package, res.get("last_modified"), dest.stat().st_size, sha256(dest)))
    return rows


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
    snap = Path(repo_root() / "data" / "SNAPSHOT.md")
    if "--geo-only" in sys.argv:  # fetch only the geography files and update their SNAPSHOT.md rows
        snap.write_text(upsert_geo_rows(snap.read_text(), download_geo(raw)))
        print(f"updated {snap}")
        return
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
    rows += download_geo(raw)
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
