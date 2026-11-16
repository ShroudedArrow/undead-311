"""Download Boston 311 CSVs (2015-present) into $DATA_DIR/raw/ (REQ-ING-1, REQ-ING-DL).

Resolves DATA_DIR with the tech.md fallback and records hashes + download date in data/SNAPSHOT.md.
Every download (REQ-ING-DL.1-4):
  * retries up to 5 tries with exponential backoff (1, 2, 4, 8 s) on network errors, 5xx, 429 and short bodies;
  * resumes a `<file>.part` with an HTTP Range request (a server that ignores Range restarts the file);
  * checks the bytes received against Content-Length (and the Content-Range total) before the file is renamed;
  * compares the file with the previous row of data/SNAPSHOT.md. A file that is on disk is kept only when its hash,
    size and CKAN last_modified all match that row and the server reports the same size; otherwise it is fetched
    again. Files whose hash differs from the previous row are reported as CHANGED (also written to
    $DATA_DIR/logs/download-report.json), never silently kept.
"""

from __future__ import annotations

import datetime as dt
import hashlib
import http.client
import json
import os
import re
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import NamedTuple

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
TRIES = 5  # REQ-ING-DL.1: 5 tries, so 4 waits of BACKOFF_S * 2**n seconds
BACKOFF_S = 1.0
RETRYABLE_HTTP = {408, 425, 429, 500, 502, 503, 504}
CHUNK = 1 << 20


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


class DownloadError(RuntimeError):
    """A download that failed after every try."""


class SizeMismatch(OSError):
    """The body ended before (or after) the size the server announced; retryable."""


def is_retryable(exc: BaseException) -> bool:
    """Network trouble, a retryable HTTP status or a short body. Disk errors (ENOSPC, EACCES) are not retried."""
    if isinstance(exc, urllib.error.HTTPError):
        return exc.code in RETRYABLE_HTTP
    return isinstance(exc, (urllib.error.URLError, http.client.HTTPException, ConnectionError, TimeoutError, SizeMismatch))


def with_retries(fn, what: str, tries: int = TRIES, backoff: float | None = None, sleep=None, log=print):
    """Call `fn(attempt)` up to `tries` times, waiting backoff * 2**(attempt-1) seconds after a retryable failure."""
    backoff = BACKOFF_S if backoff is None else backoff
    sleep = sleep or time.sleep
    for attempt in range(1, tries + 1):
        try:
            return fn(attempt)
        except Exception as exc:  # re-raised unless retryable
            if not is_retryable(exc):
                raise
            if attempt == tries:
                raise DownloadError(f"{what}: failed after {tries} tries ({type(exc).__name__}: {exc})") from exc
            wait = backoff * 2 ** (attempt - 1)
            log(f"retry {what}: try {attempt} of {tries} failed ({type(exc).__name__}: {exc}); waiting {wait:g} s")
            sleep(wait)


def fetch_json(url: str, opener=None, **kw) -> dict:
    def once(_attempt: int) -> dict:
        with (opener or _OPENER).open(urllib.request.Request(url, headers={"User-Agent": UA}), timeout=60) as r:
            return json.load(r)

    return with_retries(once, f"GET {url}", **kw)


def _content_range(value: str | None) -> tuple[int | None, int | None]:
    """(start, total) from `bytes 100-199/1000` (`bytes */1000` gives (None, 1000)); (None, None) when absent."""
    m = re.match(r"\s*bytes\s+(?:(\d+)-\d+|\*)/(\d+|\*)", value or "")
    if not m:
        return None, None
    return (int(m.group(1)) if m.group(1) else None), (int(m.group(2)) if m.group(2).isdigit() else None)


def remote_size(url: str, opener=None, **kw) -> int | None:
    """Size the server reports (a one-byte Range request, which signed S3 links allow), or None when it cannot tell."""

    def once(_attempt: int) -> int | None:
        req = urllib.request.Request(url, headers={"User-Agent": UA, "Range": "bytes=0-0"})
        with (opener or _OPENER).open(req, timeout=60) as r:
            _start, total = _content_range(r.headers.get("Content-Range"))
            if total is not None:
                return total
            length = r.headers.get("Content-Length")
            return int(length) if r.status == 200 and length and length.isdigit() else None

    try:
        return with_retries(once, f"size of {url}", **kw)
    except (DownloadError, urllib.error.HTTPError):
        return None


def fetch_file(url: str, dest: Path, opener=None, log=print, **kw) -> int:
    """Download `url` to `dest` through `dest.name + '.part'`, resuming it, and return the size in bytes.

    The `.part` file is renamed only when its size equals the size the server announced (Content-Length, or the total in
    Content-Range for a resumed request). A short body keeps the `.part` so the next try resumes it; an oversize or
    unusable one is removed."""
    dest = Path(dest)
    part = dest.with_name(dest.name + ".part")
    part.parent.mkdir(parents=True, exist_ok=True)

    def once(_attempt: int) -> int:
        offset = part.stat().st_size if part.exists() else 0
        headers = {"User-Agent": UA}
        if offset:
            headers["Range"] = f"bytes={offset}-"
        try:
            resp = (opener or _OPENER).open(urllib.request.Request(url, headers=headers), timeout=300)
        except urllib.error.HTTPError as e:
            if e.code == 416 and offset:  # nothing to send from that offset: the part is complete, or it is wrong
                _s, total = _content_range(e.headers.get("Content-Range"))
                if total == offset:
                    os.replace(part, dest)
                    return offset
                part.unlink(missing_ok=True)
                raise SizeMismatch(f"{part.name} ({offset} bytes) does not fit a file of {total} bytes; restarting") from e
            raise
        with resp:
            length = resp.headers.get("Content-Length")
            if resp.status == 206:
                start, total = _content_range(resp.headers.get("Content-Range"))
                if start != offset:
                    part.unlink(missing_ok=True)
                    raise SizeMismatch(f"server resumed at {start}, asked for {offset}; restarting")
                mode, expected = "ab", total if total is not None else (offset + int(length) if length else None)
            else:  # 200: the whole file, from the start (also when the server ignored our Range header)
                mode, expected = "wb", int(length) if length and length.isdigit() else None
            with part.open(mode) as out:
                while chunk := resp.read(CHUNK):
                    out.write(chunk)
        size = part.stat().st_size
        if expected is not None and size != expected:
            if size > expected:
                part.unlink(missing_ok=True)
            raise SizeMismatch(f"{dest.name}: got {size} bytes, server announced {expected}")
        if expected is None:
            log(f"note {dest.name}: the server sent no Content-Length, size not checked")
        os.replace(part, dest)
        return size

    return with_retries(once, f"download {dest.name}", log=log, **kw)


ROW_RE = re.compile(r"^\|\s*([^|\s]+\.(?:csv|geojson))\s*\|([^|]*)\|([^|]*)\|\s*(\d+)\s*\|\s*([0-9a-f]{64})\s*\|\s*$", re.MULTILINE)


def previous_rows(snapshot_text: str) -> dict[str, dict]:
    """File name -> {resource, last_modified, bytes, sha256} from the DOWNLOAD table of SNAPSHOT.md (the judging section,
    which lists other files, is ignored)."""
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from undead311.snapshot import BEGIN

    table = snapshot_text[: snapshot_text.find(BEGIN)] if BEGIN in snapshot_text else snapshot_text
    return {
        m.group(1): {"resource": m.group(2).strip(), "last_modified": m.group(3).strip(), "bytes": int(m.group(4)), "sha256": m.group(5)}
        for m in ROW_RE.finditer(table)
    }  # fmt: skip


class FileResult(NamedTuple):
    name: str
    status: str  # kept | unchanged | changed | new
    bytes: int
    sha256: str
    old_bytes: int | None = None
    old_sha256: str | None = None


def sync_file(dest: Path, url: str, prev: dict | None, last_modified: str | None, opener=None, log=print, **kw) -> FileResult:
    """Make `dest` the server's current file and say how it compares with the previous SNAPSHOT.md row (REQ-ING-DL.4).

    status `kept`: on disk, hash and size equal the previous row, CKAN last_modified is unchanged and the server reports
    the same size, so nothing was fetched. Anything else is fetched again: `unchanged` (same hash as the previous row),
    `changed` (a different hash) or `new` (no previous row)."""
    dest = Path(dest)
    local_ok = dest.is_file() and dest.stat().st_size > 0
    if local_ok and prev:
        size = dest.stat().st_size
        digest = sha256(dest)
        remote = remote_size(url, opener, **kw)
        same_stamp = not last_modified or not prev["last_modified"] or last_modified == prev["last_modified"]
        if digest == prev["sha256"] and size == prev["bytes"] and same_stamp and (remote is None or remote == size):
            log(f"keep {dest.name} (hash, size and last_modified match the previous snapshot row)")
            return FileResult(dest.name, "kept", size, digest, prev["bytes"], prev["sha256"])
        log(f"refetch {dest.name}: local file or server no longer matches the previous snapshot row")
    else:
        log(f"get  {dest.name}" + ("" if not local_ok else " (no previous snapshot row to check the local file against)"))
    size = fetch_file(url, dest, opener, log, **kw)
    digest = sha256(dest)
    if not prev:
        return FileResult(dest.name, "new", size, digest)
    status = "unchanged" if digest == prev["sha256"] else "changed"
    return FileResult(dest.name, status, size, digest, prev["bytes"], prev["sha256"])


def report_changes(results: list[FileResult], log=print) -> list[FileResult]:
    """Print every file whose hash differs from the previous snapshot row and return them (REQ-ING-DL.4)."""
    changed = [r for r in results if r.status == "changed"]
    for r in changed:
        log(f"CHANGED {r.name}: {r.old_bytes} -> {r.bytes} bytes, sha256 {str(r.old_sha256)[:12]} -> {r.sha256[:12]}")
    log(f"download summary: {len(results)} files, " + ", ".join(f"{sum(r.status == k for r in results)} {k}" for k in ("kept", "unchanged", "changed", "new")))
    return changed


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
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from undead311.snapshot import BEGIN, extract_section, upsert_section

    judging = extract_section(snapshot_text)  # the judging section stays below the download table
    table = snapshot_text if judging is None else snapshot_text[: snapshot_text.find(BEGIN)]
    kept = GEO_ROW_RE.sub("", table).rstrip("\n")
    out = kept + "\n" + "".join(f"| {a} | {b} | {c} | {d} | {e} |\n" for a, b, c, d, e in rows)
    return out if judging is None else upsert_section(out, judging)


def download_geo(raw: Path, prev: dict[str, dict] | None = None, results: list[FileResult] | None = None) -> list[tuple]:
    """Fetch the street segments and neighborhood boundaries into `raw` (kept when they match the previous row)."""
    rows = []
    for name, (package, fmt) in GEO_FILES.items():
        res = geo_resource(fetch_json(PACKAGE_API + package)["result"], fmt)
        if res is None:
            raise RuntimeError(f"no {fmt} resource in CKAN package {package}")
        dest = raw / name
        result = sync_file(dest, res["url"], (prev or {}).get(name), res.get("last_modified"))
        if results is not None:
            results.append(result)
        rows.append((dest.name, res.get("name") or package, res.get("last_modified"), result.bytes, result.sha256))
    return rows


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def write_snapshot(snap: Path, text: str) -> None:
    """Write the download table, keeping the judging section that `make snapshot` wrote (REQ-OPS-SNAP.1)."""
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from undead311.snapshot import extract_section, upsert_section

    kept = extract_section(snap.read_text()) if snap.exists() else None
    snap.write_text(upsert_section(text, kept) if kept else text)


def write_report(data_dir: Path, results: list[FileResult], changed: list[FileResult]) -> Path:
    """$DATA_DIR/logs/download-report.json: every file's status and the ones that changed (REQ-ING-DL.4)."""
    out = data_dir / "logs" / "download-report.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    body = {"date": dt.date.today().isoformat(), "files": [r._asdict() for r in results], "changed": [r.name for r in changed]}
    out.write_text(json.dumps(body, indent=2, sort_keys=True) + "\n")
    return out


def main() -> None:
    data_dir = resolve_data_dir()
    raw = data_dir / "raw"
    raw.mkdir(parents=True, exist_ok=True)
    print(f"DATA_DIR resolved to {data_dir}")
    snap = Path(repo_root() / "data" / "SNAPSHOT.md")
    prev = previous_rows(snap.read_text()) if snap.exists() else {}
    results: list[FileResult] = []
    if "--geo-only" in sys.argv:  # fetch only the geography files and update their SNAPSHOT.md rows
        rows = download_geo(raw, prev, results)
        report_changes(results)
        snap.write_text(upsert_geo_rows(snap.read_text(), rows))
        print(f"updated {snap}")
        return
    pkg = fetch_json(PACKAGE_URL)["result"]
    rows = []
    for r in wanted_resources(pkg):
        dest = raw / f"311_{r['label']}.csv"
        result = sync_file(dest, r["url"], prev.get(dest.name), r["last_modified"])
        results.append(result)
        rows.append((dest.name, r["name"], r["last_modified"], result.bytes, result.sha256))
    rows += download_geo(raw, prev, results)
    changed = report_changes(results)
    print(f"wrote {write_report(data_dir, results, changed)}")
    lines = [
        "# Data snapshot",
        "",
        f"Downloaded: {dt.date.today().isoformat()} (source: Analyze Boston, dataset 311-service-requests)",
        "",
        "| file | resource | last_modified | bytes | sha256 |",
        "|---|---|---|---|---|",
    ]
    lines += [f"| {a} | {b} | {c} | {d} | {e} |" for a, b, c, d, e in rows]
    write_snapshot(snap, "\n".join(lines) + "\n")
    print(f"wrote {snap}")


if __name__ == "__main__":
    main()
