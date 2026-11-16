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
* `publish` needs the GitHub CLI and a token in `GH_TOKEN` with Contents: read and write on the data repo only. `--dry-run`
  packs and prints the commands without touching GitHub. Nothing here prints the token or the environment.
* `unpack` checks the hash, rejects absolute paths, `..` and links, replaces only the files this pipeline owns
  (`owns_output`) and never touches `frozen/`. `status.json` goes in last.
"""

from __future__ import annotations

import argparse
import hashlib
import io
import json
import os
import shutil
import subprocess
import sys
import tarfile
import tempfile
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


def gh(*args: str, check: bool = True) -> subprocess.CompletedProcess:
    return subprocess.run(["gh", *args], capture_output=True, text=True, check=check, timeout=600)


def latest_tag(repo: str) -> str:
    """The newest `exports-*` release of `repo` by creation date (REQ-OPS-PUBLISH.3)."""
    out = gh("release", "list", "--repo", repo, "--limit", "100", "--json", "tagName,createdAt").stdout
    tags = [r for r in json.loads(out) if r["tagName"].startswith(PREFIX)]
    if not tags:
        raise ExportsError(f"no {PREFIX}* release in {repo}")
    return max(tags, key=lambda r: r["createdAt"])["tagName"]


def publish(run_id: str, exports: Path, repo: str, dry_run: bool, out: Path) -> list[list[str]]:
    archive, digest = pack(run_id, exports, out)
    tag = f"{PREFIX}{run_id}"
    cmds = [
        ["gh", "release", "view", tag, "--repo", repo],
        ["gh", "release", "create", tag, "--repo", repo, "--title", f"Exports {run_id}",
         "--notes", f"Pipeline exports of run {run_id} (one tar.gz and its SHA-256). The nightly job downloads the newest one."],
        ["gh", "release", "upload", tag, str(archive), str(digest), "--repo", repo, "--clobber"],
    ]  # fmt: skip
    if dry_run:
        for c in cmds:
            print("would run:", " ".join(c))
        return cmds
    if gh(*cmds[0][1:], check=False).returncode != 0:
        gh(*cmds[1][1:])
    gh(*cmds[2][1:])
    return cmds


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
        from undead311.paths import data_dir

        base = data_dir()
        exports = a.exports or base / "exports" / a.run_id
        out = a.out or base / "releases" / a.run_id
        if a.cmd == "pack":
            archive, digest = pack(a.run_id, exports, out)
            print(f"wrote {archive} and {digest}")
            return 0
        publish(a.run_id, exports, a.repo, a.dry_run, out)
        return 0
    except ExportsError as exc:
        print(f"exports_release: {exc}", file=sys.stderr)
        return 1
    except (subprocess.CalledProcessError, OSError) as exc:  # gh output may hold URLs, never the token
        print(f"exports_release: {type(exc).__name__}: {str(exc)[:300]}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
