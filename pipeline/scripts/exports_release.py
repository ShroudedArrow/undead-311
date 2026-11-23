"""Pack, publish, fetch and unpack a run's exports as a release asset of `ShroudedArrow/undead-311-data` (REQ-OPS-PUBLISH).

  python pipeline/scripts/exports_release.py pack    --run-id full-2 [--exports DIR] [--out DIR]
  python pipeline/scripts/exports_release.py publish --run-id full-2 [--repo OWNER/REPO] [--dry-run]
  python pipeline/scripts/exports_release.py latest  [--repo OWNER/REPO]
  python pipeline/scripts/exports_release.py unpack  --archive FILE --sha256 FILE --dest web/public/data

A run's exports (`$DATA_DIR/exports/<run-id>`, the folder `run_full.py` writes) become one asset `exports-<run-id>.tar.gz` with
a SHA-256 file and a `MANIFEST.json` inside, attached to the release `exports-<run-id>` of the data repo. The nightly job there
(`ops/undead-311-data/.github/workflows/nightly.yml`) downloads the newest `exports-*` release, checks the hash and the
manifest, unpacks it into `web/public/data/`, builds the site and deploys it to Netlify.

* `pack` refuses an export whose `status.json` is missing, says `ok: false`, or carries a `DRY RUN ONLY` anomaly: a dry run is
  never published (full-1 was over its first-view budget on purpose and says so).
* `publish` needs a token in `DATA_RELEASE_TOKEN` (Contents: read and write on the data repo only). It talks to the GitHub REST
  API directly (no `gh`, so no GraphQL): look up or create the release, delete a same-named old asset, upload each asset to the
  uploads endpoint, then download it again with the token and compare its SHA-256 with the local file. A mismatch (or a missing
  or short asset) is an error and exit code 1; nothing is reported as published. The token is sent only to the API host; the
  signed redirect to the storage host gets no Authorization header. The script never reads `GH_TOKEN`. `--dry-run` packs and
  prints the calls without touching GitHub or needing the token. Nothing here prints the token or the environment. `latest`
  and `unpack` still use `gh` and need no token for a public repo (the nightly job passes its own).
* `unpack` checks the hash, rejects absolute paths, `..` and links, replaces only the files this pipeline owns
  (`owns_output`) and never touches `frozen/`. `status.json` goes in last.
"""

from __future__ import annotations

import argparse
import hashlib
import io
import json
import os
import re
import shutil
import subprocess
import sys
import tarfile
import tempfile
import urllib.error
import urllib.parse
import urllib.request
from datetime import UTC, datetime
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))

DATA_REPO = "ShroudedArrow/undead-311-data"
PREFIX = "exports-"
MANIFEST = "MANIFEST.json"


class ExportsError(RuntimeError):
    """The export folder or archive cannot be published or used (a message for a person, not a traceback)."""


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with Path(path).open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def read_status(folder: Path) -> dict:
    try:
        return json.loads((Path(folder) / "status.json").read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise ExportsError(f"{folder}/status.json is missing or damaged ({type(exc).__name__}); run the pipeline first") from exc


def check_publishable(status: dict) -> None:
    """Refuse a failed or dry-run export (REQ-OPS-PUBLISH.1)."""
    if status.get("ok") is not True:
        raise ExportsError("status.json does not say ok: true; not publishing")
    dry = [a for a in status.get("anomalies", []) if str(a).startswith("DRY RUN ONLY")]
    if dry:
        raise ExportsError("status.json carries a DRY RUN ONLY anomaly; a dry run is never published: " + dry[0][:160])
    if status.get("dataset") not in {"full", "sample"}:
        raise ExportsError("status.json has no dataset field")


def pack(run_id: str, exports: Path, out: Path) -> tuple[Path, Path]:
    """`exports-<run_id>.tar.gz` and `exports-<run_id>.sha256` in `out` (REQ-OPS-PUBLISH.1). Deterministic bytes for the same
    files: sorted names, zero timestamps and owners."""
    exports = Path(exports)
    status = read_status(exports)
    check_publishable(status)
    files = sorted(p for p in exports.rglob("*") if p.is_file() and p.suffix != ".tmp" and ".staging-" not in str(p))
    rels = [p.relative_to(exports).as_posix() for p in files]
    if "status.json" not in rels:
        raise ExportsError("no status.json in the export folder")
    manifest = {
        "run_id": run_id, "data_version": status["data_version"], "dataset": status.get("dataset"),
        "data_end": status.get("data_end"), "created_utc": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "files": {r: p.stat().st_size for r, p in zip(rels, files, strict=True)},
    }  # fmt: skip
    out = Path(out)
    out.mkdir(parents=True, exist_ok=True)
    archive = out / f"{PREFIX}{run_id}.tar.gz"
    tmp = archive.with_name(archive.name + ".tmp")
    with tmp.open("wb") as raw:
        import gzip

        with gzip.GzipFile(fileobj=raw, mode="wb", compresslevel=9, mtime=0) as gz, tarfile.open(fileobj=gz, mode="w") as tar:
            blob = (json.dumps(manifest, indent=2, sort_keys=True) + "\n").encode()
            info = tarfile.TarInfo(MANIFEST)
            info.size, info.mtime = len(blob), 0
            tar.addfile(info, io.BytesIO(blob))
            for rel, p in zip(rels, files, strict=True):
                if rel == "status.json":
                    continue
                add(tar, rel, p)
            add(tar, "status.json", exports / "status.json")  # last, like the swap
    os.replace(tmp, archive)
    digest = out / f"{PREFIX}{run_id}.sha256"
    digest.write_text(f"{sha256_file(archive)}  {archive.name}\n", encoding="utf-8")
    return archive, digest


def add(tar: tarfile.TarFile, rel: str, path: Path) -> None:
    info = tarfile.TarInfo(rel)
    info.size, info.mtime, info.uid, info.gid, info.uname, info.gname = path.stat().st_size, 0, 0, 0, "", ""
    info.mode = 0o644
    with path.open("rb") as f:
        tar.addfile(info, f)


def safe_members(tar: tarfile.TarFile) -> list[tarfile.TarInfo]:
    members = tar.getmembers()
    for m in members:
        parts = Path(m.name).parts
        if not m.isreg() or m.name.startswith("/") or ".." in parts or not parts:
            raise ExportsError(f"unsafe or non-file member in the archive: {m.name!r}")
    return members


def unpack(archive: Path, sha_file: Path, dest: Path) -> dict:
    """Verify, then replace the owned files in `dest` with the archive's (REQ-OPS-PUBLISH.2). Returns the manifest."""
    from undead311.pipeline import owns_output

    archive, dest = Path(archive), Path(dest)
    want = Path(sha_file).read_text(encoding="utf-8").split()[0]
    got = sha256_file(archive)
    if want != got:
        raise ExportsError(f"SHA-256 mismatch for {archive.name}: expected {want[:12]}, got {got[:12]}")
    with tempfile.TemporaryDirectory(dir=dest.parent if dest.parent.is_dir() else None) as tmpdir:
        tmp = Path(tmpdir)
        with tarfile.open(archive, "r:gz") as tar:
            members = safe_members(tar)
            for m in members:
                target = tmp / m.name
                target.parent.mkdir(parents=True, exist_ok=True)
                with tar.extractfile(m) as src, target.open("wb") as dst:  # type: ignore[union-attr]
                    shutil.copyfileobj(src, dst)
        manifest = json.loads((tmp / MANIFEST).read_text(encoding="utf-8"))
        (tmp / MANIFEST).unlink()
        staged = sorted(p.relative_to(tmp).as_posix() for p in tmp.rglob("*") if p.is_file())
        if set(staged) != set(manifest["files"]):
            raise ExportsError("the archive's files differ from its manifest")
        for rel in staged:
            if not owns_output(rel):
                raise ExportsError(f"the archive holds a file this pipeline does not own: {rel}")
        check_publishable(json.loads((tmp / "status.json").read_text(encoding="utf-8")))
        dest.mkdir(parents=True, exist_ok=True)
        for f in sorted(p for p in dest.rglob("*") if p.is_file()):
            rel = f.relative_to(dest).as_posix()
            if not rel.startswith("frozen/") and owns_output(rel):
                f.unlink()
        for rel in [r for r in staged if r != "status.json"] + ["status.json"]:
            target = dest / rel
            target.parent.mkdir(parents=True, exist_ok=True)
            os.replace(tmp / rel, target)
    return manifest


TOKEN_VAR = "DATA_RELEASE_TOKEN"


def gh(*args: str, check: bool = True) -> subprocess.CompletedProcess:
    """Run `gh` (used by `latest` only). The caller's environment is used as it is (the nightly job's own `github.token`)."""
    return subprocess.run(["gh", *args], capture_output=True, text=True, check=check, timeout=600)


def latest_tag(repo: str) -> str:
    """The newest `exports-*` release of `repo` by creation date (REQ-OPS-PUBLISH.3)."""
    out = gh("release", "list", "--repo", repo, "--limit", "100", "--json", "tagName,createdAt").stdout
    tags = [r for r in json.loads(out) if r["tagName"].startswith(PREFIX)]
    if not tags:
        raise ExportsError(f"no {PREFIX}* release in {repo}")
    return max(tags, key=lambda r: r["createdAt"])["tagName"]


API_URL = "https://api.github.com"
UPLOADS_URL = "https://uploads.github.com"
API_VERSION = "2022-11-28"
LOCAL_HOSTS = {"127.0.0.1", "localhost", "::1"}


def check_endpoint(url: str) -> str:
    """The token only goes to https, or to a loopback address (the mock server of the tests)."""
    u = urllib.parse.urlsplit(url)
    if u.scheme != "https" and not (u.scheme == "http" and u.hostname in LOCAL_HOSTS):
        raise ExportsError(f"refusing to send the token to {url!r}: the endpoint must be https")
    return url.rstrip("/")


class _SameHostRedirect(urllib.request.HTTPRedirectHandler):
    """Follow a redirect, but drop the Authorization header when it leaves the original host: the signed storage URL GitHub
    redirects an asset download to rejects a request that also carries a bearer token, and the token must not travel there."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        new = super().redirect_request(req, fp, code, msg, headers, newurl)
        if new is not None and urllib.parse.urlsplit(newurl).netloc != urllib.parse.urlsplit(req.full_url).netloc:
            new.headers.pop("Authorization", None)
            new.unredirected_hdrs.pop("Authorization", None)
        return new


class GitHubRest:
    """The few REST calls `publish` needs. Every failure becomes an `ExportsError` without the token in its text."""

    def __init__(self, token: str, repo: str, api_url: str = API_URL, uploads_url: str = UPLOADS_URL, timeout: float = 600):
        self.token, self.repo, self.timeout = token, repo, timeout
        self.api, self.uploads = check_endpoint(api_url), check_endpoint(uploads_url)
        self.opener = urllib.request.build_opener(_SameHostRedirect)

    def _request(self, method: str, url: str, *, body: bytes | None = None, content_type: str | None = None,
                 accept: str = "application/vnd.github+json") -> urllib.request.Request:
        headers = {"Authorization": f"Bearer {self.token}", "Accept": accept, "X-GitHub-Api-Version": API_VERSION,
                   "User-Agent": "undead-311-exports-release"}  # fmt: skip
        if content_type:
            headers["Content-Type"] = content_type
        return urllib.request.Request(url, data=body, method=method, headers=headers)

    def call(self, method: str, url: str, payload: dict | None = None, *, raw: bytes | None = None,
             content_type: str | None = None, ok_missing: bool = False) -> dict | list | None:
        """One JSON call. A 404 returns None when `ok_missing`; any other failure raises."""
        body = json.dumps(payload).encode() if payload is not None else raw
        req = self._request(method, url, body=body, content_type=content_type or ("application/json" if payload is not None else None))
        try:
            with self.opener.open(req, timeout=self.timeout) as r:
                data = r.read()
        except urllib.error.HTTPError as exc:
            if exc.code == 404 and ok_missing:
                return None
            detail = exc.read(300).decode("utf-8", "replace") if exc.fp else ""
            raise ExportsError(f"GitHub answered {exc.code} to {method} {urllib.parse.urlsplit(url).path}: {detail[:200]}") from None
        except (urllib.error.URLError, OSError) as exc:
            raise ExportsError(f"{method} {urllib.parse.urlsplit(url).path} failed: {type(exc).__name__}") from None
        return json.loads(data) if data else None

    def release(self, tag: str) -> dict:
        """The release for `tag`; created (from the default branch) when it does not exist yet."""
        rel = self.call("GET", f"{self.api}/repos/{self.repo}/releases/tags/{urllib.parse.quote(tag)}", ok_missing=True)
        if rel is None:
            rel = self.call("POST", f"{self.api}/repos/{self.repo}/releases", {
                "tag_name": tag, "name": f"Exports {tag.removeprefix(PREFIX)}",
                "body": f"Pipeline exports of run {tag.removeprefix(PREFIX)} (one tar.gz and its SHA-256). "
                        "The nightly job downloads the newest one.",
            })  # fmt: skip
        if not isinstance(rel, dict) or "id" not in rel:
            raise ExportsError("GitHub's release answer has no id")
        return rel

    def upload(self, release: dict, path: Path) -> dict:
        """Upload `path` as an asset of `release`, replacing a same-named asset. Returns the new asset's JSON."""
        for old in release.get("assets", []):
            if old.get("name") == path.name:
                self.call("DELETE", f"{self.api}/repos/{self.repo}/releases/assets/{old['id']}")
        ctype = "application/gzip" if path.suffix == ".gz" else "text/plain"
        url = f"{self.uploads}/repos/{self.repo}/releases/{release['id']}/assets?name={urllib.parse.quote(path.name)}"
        asset = self.call("POST", url, raw=path.read_bytes(), content_type=ctype)
        if not isinstance(asset, dict) or "id" not in asset:
            raise ExportsError(f"the upload of {path.name} returned no asset id")
        return asset

    def download_sha256(self, asset_id: int) -> tuple[str, int]:
        """SHA-256 and size of the asset as GitHub serves it back, fetched with the token (the repo may be private)."""
        req = self._request("GET", f"{self.api}/repos/{self.repo}/releases/assets/{asset_id}", accept="application/octet-stream")
        h, size = hashlib.sha256(), 0
        try:
            with self.opener.open(req, timeout=self.timeout) as r:
                for chunk in iter(lambda: r.read(1 << 20), b""):
                    h.update(chunk)
                    size += len(chunk)
        except urllib.error.HTTPError as exc:
            raise ExportsError(f"GitHub answered {exc.code} to the verification download of asset {asset_id}") from None
        except (urllib.error.URLError, OSError) as exc:
            raise ExportsError(f"the verification download of asset {asset_id} failed: {type(exc).__name__}") from None
        return h.hexdigest(), size


    def release_by_tag(self, tag: str) -> dict | None:
        """The release for `tag` with its assets, or None when there is none."""
        rel = self.call("GET", f"{self.api}/repos/{self.repo}/releases/tags/{urllib.parse.quote(tag)}", ok_missing=True)
        return rel if isinstance(rel, dict) else None

    def download_to(self, asset_id: int, path: Path) -> tuple[str, int]:
        """Stream the asset to `path`; returns its SHA-256 and size. The token goes to the API host only (see `_SameHostRedirect`)."""
        req = self._request("GET", f"{self.api}/repos/{self.repo}/releases/assets/{asset_id}", accept="application/octet-stream")
        h, size = hashlib.sha256(), 0
        try:
            with self.opener.open(req, timeout=self.timeout) as r, Path(path).open("wb") as out:
                for chunk in iter(lambda: r.read(1 << 20), b""):
                    h.update(chunk)
                    size += len(chunk)
                    out.write(chunk)
        except urllib.error.HTTPError as exc:
            raise ExportsError(f"GitHub answered {exc.code} to the download of asset {asset_id}") from None
        except (urllib.error.URLError, OSError) as exc:
            raise ExportsError(f"the download of asset {asset_id} failed: {type(exc).__name__}") from None
        return h.hexdigest(), size


class GhApi:
    """The same two reads over `gh api` (REST endpoints only, never GraphQL). For a sandbox whose `gh` carries its own
    credentials, so no `DATA_RELEASE_TOKEN` is read or sent. `fetch_release(transport="gh")`."""

    def __init__(self, repo: str, timeout: float = 600):
        self.repo, self.timeout = repo, timeout

    def release_by_tag(self, tag: str) -> dict | None:
        r = subprocess.run(["gh", "api", f"repos/{self.repo}/releases/tags/{urllib.parse.quote(tag)}"], check=False, capture_output=True, timeout=self.timeout)
        if r.returncode != 0:
            if b"404" in r.stderr:
                return None
            raise ExportsError(f"gh api failed for release {tag}: {r.stderr.decode('utf-8', 'replace')[:200]}")
        rel = json.loads(r.stdout)
        return rel if isinstance(rel, dict) else None

    def download_to(self, asset_id: int, path: Path) -> tuple[str, int]:
        with Path(path).open("wb") as out:
            r = subprocess.run(["gh", "api", "-H", "Accept: application/octet-stream", f"repos/{self.repo}/releases/assets/{asset_id}"],
                               check=False, stdout=out, stderr=subprocess.PIPE, timeout=self.timeout)
        if r.returncode != 0:
            raise ExportsError(f"gh api failed for asset {asset_id}: {r.stderr.decode('utf-8', 'replace')[:200]}")
        return sha256_file(path), Path(path).stat().st_size


def fetch_release(run_id: str, dest: Path, expected_sha256: str, repo: str = DATA_REPO, token: str | None = None,
                  api_url: str = API_URL, transport: str = "rest") -> dict:
    """Download the release `exports-<run_id>` through the REST API, check the archive's SHA-256 against `expected_sha256`
    (the value recorded at the snapshot) and against the release's own `.sha256` file, and unpack it into `dest`
    (REQ-OPS-SNAP.5). Nothing is unpacked unless both hashes agree. Returns the manifest."""
    if transport not in {"rest", "gh"}:
        raise ExportsError(f"unknown transport {transport!r}; use rest or gh")
    token = token if token is not None else os.environ.get(TOKEN_VAR, "").strip()
    if transport == "rest" and not token:
        raise ExportsError(f"{TOKEN_VAR} is not set; the data repo is private, so downloading its release needs a read token (or transport gh)")
    if not re.fullmatch(r"[0-9a-f]{64}", expected_sha256 or ""):
        raise ExportsError("the expected SHA-256 must be 64 lowercase hex digits")
    api = GhApi(repo) if transport == "gh" else GitHubRest(token, repo, api_url, UPLOADS_URL)
    rel = api.release_by_tag(PREFIX + run_id)
    if rel is None:
        raise ExportsError(f"no release {PREFIX}{run_id} in {repo}")
    assets = {a.get("name"): a for a in rel.get("assets", []) if isinstance(a, dict) and "id" in a}
    name = f"{PREFIX}{run_id}.tar.gz"
    for need in (name, name.removesuffix(".tar.gz") + ".sha256"):
        if need not in assets:
            raise ExportsError(f"release {PREFIX}{run_id} has no asset {need}")
    dest = Path(dest)
    dest.mkdir(parents=True, exist_ok=True)
    archive, sha_file = dest / name, dest / (name.removesuffix(".tar.gz") + ".sha256")
    got, _ = api.download_to(assets[name]["id"], archive)
    if got != expected_sha256:
        archive.unlink(missing_ok=True)
        raise ExportsError(f"SHA-256 mismatch for {name}: the snapshot recorded {expected_sha256[:12]}, the release serves {got[:12]}")
    api.download_to(assets[sha_file.name]["id"], sha_file)
    published = sha_file.read_text(encoding="utf-8").split()[:1]
    if published != [expected_sha256]:
        raise ExportsError(f"the release's {sha_file.name} does not say {expected_sha256[:12]}; refusing to unpack")
    out = dest / "exports"
    return unpack(archive, sha_file, out)


def verify_asset(gh_rest: GitHubRest, asset: dict, path: Path) -> None:
    """Download the uploaded asset again and compare it with the local file (REQ-OPS-PUBLISH.1). Raises on any difference."""
    want, want_size = sha256_file(path), path.stat().st_size
    got, got_size = gh_rest.download_sha256(asset["id"])
    if got != want or got_size != want_size:
        raise ExportsError(
            f"UPLOAD VERIFICATION FAILED for {path.name} (asset {asset['id']}): local sha256 {want[:12]} ({want_size} bytes), "
            f"downloaded sha256 {got[:12]} ({got_size} bytes). The release is NOT usable; run publish again."
        )


def publish(run_id: str, exports: Path, repo: str, dry_run: bool, out: Path,
            api_url: str = API_URL, uploads_url: str = UPLOADS_URL) -> list[str]:
    archive, digest = pack(run_id, exports, out)
    tag = f"{PREFIX}{run_id}"
    calls = [
        f"GET {api_url}/repos/{repo}/releases/tags/{tag}  (POST {api_url}/repos/{repo}/releases when it does not exist)",
        *[f"POST {uploads_url}/repos/{repo}/releases/<id>/assets?name={p.name}  (a same-named asset is deleted first)" for p in (archive, digest)],
        *[f"GET {api_url}/repos/{repo}/releases/assets/<id>  (verify the SHA-256 of {p.name})" for p in (archive, digest)],
    ]  # fmt: skip
    if dry_run:
        for c in calls:
            print("would call:", c)
        return calls
    token = os.environ.get(TOKEN_VAR, "").strip()
    if not token:
        raise ExportsError(f"{TOKEN_VAR} is not set; publishing needs a token with Contents: read and write on {repo} (docs/DEPLOY.md)")
    gh_rest = GitHubRest(token, repo, api_url, uploads_url)
    release = gh_rest.release(tag)
    uploaded = [(gh_rest.upload(release, p), p) for p in (archive, digest)]
    for asset, p in uploaded:
        verify_asset(gh_rest, asset, p)
        print(f"published and verified {p.name} ({sha256_file(p)[:12]}) in release {tag}")
    return calls


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    for name in ("pack", "publish"):
        p = sub.add_parser(name)
        p.add_argument("--run-id", required=True)
        p.add_argument("--exports", type=Path, default=None, help="export folder (default $DATA_DIR/exports/<run-id>)")
        p.add_argument("--out", type=Path, default=None, help="where the archive goes (default $DATA_DIR/releases/<run-id>)")
        if name == "publish":
            p.add_argument("--repo", default=DATA_REPO)
            p.add_argument("--dry-run", action="store_true")
            p.add_argument("--api-url", default=API_URL, help=argparse.SUPPRESS)
            p.add_argument("--uploads-url", default=UPLOADS_URL, help=argparse.SUPPRESS)
    p = sub.add_parser("latest")
    p.add_argument("--repo", default=DATA_REPO)
    p = sub.add_parser("unpack")
    p.add_argument("--archive", type=Path, required=True)
    p.add_argument("--sha256", type=Path, required=True)
    p.add_argument("--dest", type=Path, required=True)
    a = ap.parse_args(argv)
    try:
        if a.cmd == "latest":
            print(latest_tag(a.repo))
            return 0
        if a.cmd == "unpack":
            m = unpack(a.archive, a.sha256, a.dest)
            print(f"unpacked {len(m['files'])} files of run {m['run_id']} ({m['data_version']}) into {a.dest}")
            return 0
        base: Path | None = None
        if a.exports is None or a.out is None:  # data_dir() may run git; skip it when both paths are given
            from undead311.paths import data_dir

            base = data_dir()
        exports = a.exports if a.exports is not None else base / "exports" / a.run_id
        out = a.out if a.out is not None else base / "releases" / a.run_id
        if a.cmd == "pack":
            archive, digest = pack(a.run_id, exports, out)
            print(f"wrote {archive} and {digest}")
            return 0
        publish(a.run_id, exports, a.repo, a.dry_run, out, a.api_url, a.uploads_url)
        return 0
    except ExportsError as exc:
        print(f"exports_release: {exc}", file=sys.stderr)
        return 1
    except (subprocess.CalledProcessError, OSError) as exc:  # gh output may hold URLs, never the token
        print(f"exports_release: {type(exc).__name__}: {str(exc)[:300]}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
