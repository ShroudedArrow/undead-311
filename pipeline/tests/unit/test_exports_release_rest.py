"""`exports_release.py publish` over the GitHub REST API, against a mock server (REQ-OPS-PUBLISH.1).

The mock plays three roles: the API (`/repos/...`), the uploads host (`/uploads/repos/...`) and, on a second port, the signed
storage host an asset download is redirected to. It records every request, so the tests can show that no `gh` (GraphQL) is
used, that the token reaches the API and uploads host only, and that a download that differs from the upload fails loudly.
"""

from __future__ import annotations

import importlib.util
import json
import re
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

import pytest

REPO = Path(__file__).resolve().parents[3]
_spec = importlib.util.spec_from_file_location("exports_release_rest", REPO / "pipeline" / "scripts" / "exports_release.py")
er = importlib.util.module_from_spec(_spec)
sys.modules["exports_release_rest"] = er
_spec.loader.exec_module(er)

SLUG = "ShroudedArrow/undead-311-data"
TOKEN = "ghp_test-token-must-never-be-printed"


class Mock:
    """State and behaviour switches of the mock GitHub."""

    def __init__(self) -> None:
        self.requests: list[dict] = []  # {host, method, path, auth}
        self.assets: dict[int, dict] = {}  # id -> {name, data, release}
        self.releases: dict[str, dict] = {}  # tag -> release json
        self.next_id = 100
        self.corrupt: str | None = None  # None | "flip" | "short"
        self.fail_upload_status: int | None = None
        self.api_port = 0
        self.storage_port = 0

    def paths(self, host: str | None = None) -> list[str]:
        return [f"{r['method']} {r['path']}" for r in self.requests if host in (None, r["host"])]


def make_handler(mock: Mock, role: str):
    class H(BaseHTTPRequestHandler):
        def log_message(self, *a):  # keep pytest output clean
            pass

        def _record(self) -> str:
            path = urlsplit(self.path).path
            mock.requests.append({"host": role, "method": self.command, "path": path, "auth": self.headers.get("Authorization")})
            return path

        def _json(self, code: int, body) -> None:
            data = json.dumps(body).encode()
            self.send_response(code)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def do_GET(self):
            path = self._record()
            if role == "storage":
                m = re.fullmatch(r"/blob/(\d+)", path)
                data = mock.assets[int(m.group(1))]["data"]
                if mock.corrupt == "flip":
                    data = bytes([data[0] ^ 1]) + data[1:]
                elif mock.corrupt == "short":
                    data = data[: len(data) // 2]
                self.send_response(200)
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)
                return
            m = re.fullmatch(r"/repos/[^/]+/[^/]+/releases/tags/(.+)", path)
            if m:
                rel = mock.releases.get(m.group(1))
                return self._json(200, rel) if rel else self._json(404, {"message": "Not Found"})
            m = re.fullmatch(r"/repos/[^/]+/[^/]+/releases/assets/(\d+)", path)
            if m and "octet-stream" in (self.headers.get("Accept") or ""):
                self.send_response(302)  # like GitHub: a signed URL on another host
                self.send_header("Location", f"http://localhost:{mock.storage_port}/blob/{m.group(1)}?sig=abc")
                self.send_header("Content-Length", "0")
                self.end_headers()
                return
            self._json(404, {"message": "no route"})

        def do_POST(self):
            path = self._record()
            body = self.rfile.read(int(self.headers.get("Content-Length") or 0))
            if path.endswith("/releases"):
                doc = json.loads(body)
                rel = {"id": mock.next_id, "tag_name": doc["tag_name"], "assets": []}
                mock.next_id += 1
                mock.releases[doc["tag_name"]] = rel
                return self._json(201, rel)
            m = re.fullmatch(r"/uploads/repos/[^/]+/[^/]+/releases/(\d+)/assets", path)
            if m:
                if mock.fail_upload_status:
                    return self._json(mock.fail_upload_status, {"message": "boom"})
                name = parse_qs(urlsplit(self.path).query)["name"][0]
                aid = mock.next_id
                mock.next_id += 1
                mock.assets[aid] = {"name": name, "data": body, "release": int(m.group(1))}
                return self._json(201, {"id": aid, "name": name, "size": len(body), "state": "uploaded"})
            self._json(404, {"message": "no route"})

        def do_DELETE(self):
            path = self._record()
            m = re.fullmatch(r"/repos/[^/]+/[^/]+/releases/assets/(\d+)", path)
            if m:
                mock.assets.pop(int(m.group(1)), None)
                self.send_response(204)
                self.send_header("Content-Length", "0")
                self.end_headers()
                return
            self._json(404, {"message": "no route"})

    return H


@pytest.fixture
def mock():
    m = Mock()
    api = ThreadingHTTPServer(("127.0.0.1", 0), make_handler(m, "api"))
    storage = ThreadingHTTPServer(("127.0.0.1", 0), make_handler(m, "storage"))
    m.api_port, m.storage_port = api.server_address[1], storage.server_address[1]
    threads = [threading.Thread(target=s.serve_forever, daemon=True) for s in (api, storage)]
    for t in threads:
        t.start()
    yield m
    for s in (api, storage):
        s.shutdown()
        s.server_close()


def urls(m: Mock) -> dict:
    return {"api_url": f"http://127.0.0.1:{m.api_port}", "uploads_url": f"http://127.0.0.1:{m.api_port}/uploads"}


def make_export(folder: Path) -> Path:
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "status.json").write_text(json.dumps({"ok": True, "dataset": "full", "data_version": "2026-11-12+abc", "data_end": "2026-11-11"}))
    (folder / "zombies.json").write_text(json.dumps({"rows": list(range(500))}))
    return folder


@pytest.fixture
def env(monkeypatch, tmp_path):
    monkeypatch.setenv("DATA_DIR", str(tmp_path / "data"))  # hermetic: data_dir() never falls back to git rev-parse
    monkeypatch.setenv("DATA_RELEASE_TOKEN", TOKEN)
    monkeypatch.delenv("GH_TOKEN", raising=False)

    def no_gh(*a, **k):
        raise AssertionError(f"publish must not run a subprocess (no gh, no GraphQL): {a}")

    monkeypatch.setattr(er.subprocess, "run", no_gh)


def test_req_ops_publish_1_uploads_through_rest_verifies_the_download_and_keeps_the_token_off_the_storage_host(tmp_path, mock, env):
    src = make_export(tmp_path / "e")
    er.publish("r1", src, SLUG, False, tmp_path / "rel", **urls(mock))
    archive = tmp_path / "rel" / "exports-r1.tar.gz"
    digest = tmp_path / "rel" / "exports-r1.sha256"
    stored = {a["name"]: a["data"] for a in mock.assets.values()}
    assert stored == {archive.name: archive.read_bytes(), digest.name: digest.read_bytes()}  # byte-identical upload
    api, storage = [r for r in mock.requests if r["host"] == "api"], [r for r in mock.requests if r["host"] == "storage"]
    assert all(r["auth"] == f"Bearer {TOKEN}" for r in api)
    assert len(storage) == 2 and all(r["auth"] is None for r in storage)  # the signed redirect never sees the token
    assert "POST /repos/ShroudedArrow/undead-311-data/releases" in mock.paths("api")  # no release yet: created
    assert sum(p.startswith("POST /uploads/") for p in mock.paths("api")) == 2
    assert not any("graphql" in p for p in mock.paths())


def test_req_ops_publish_1_an_existing_release_is_reused_and_a_same_named_asset_is_replaced(tmp_path, mock, env):
    src = make_export(tmp_path / "e")
    mock.releases["exports-r2"] = {"id": 7, "tag_name": "exports-r2", "assets": [{"id": 55, "name": "exports-r2.tar.gz"}]}
    mock.assets[55] = {"name": "exports-r2.tar.gz", "data": b"stale", "release": 7}
    er.publish("r2", src, SLUG, False, tmp_path / "rel", **urls(mock))
    assert f"DELETE /repos/{SLUG}/releases/assets/55" in mock.paths("api")
    assert f"POST /repos/{SLUG}/releases" not in mock.paths("api")
    assert 55 not in mock.assets and b"stale" not in [a["data"] for a in mock.assets.values()]


@pytest.mark.parametrize("mode", ["flip", "short"])
def test_req_ops_publish_1_a_downloaded_hash_that_differs_fails_loudly(tmp_path, mock, env, mode, capsys):
    """A byte changed in storage, or a body cut short: the uploaded asset is not what was sent. Exit code 1, a message that
    names the file and both hashes, and never a success line."""
    mock.corrupt = mode
    src = make_export(tmp_path / "e")
    with pytest.raises(er.ExportsError, match=r"UPLOAD VERIFICATION FAILED for exports-r3\.tar\.gz"):
        er.publish("r3", src, SLUG, False, tmp_path / "rel", **urls(mock))
    assert "published and verified" not in capsys.readouterr().out
    code = er.main(["publish", "--run-id", "r3", "--exports", str(src), "--out", str(tmp_path / "rel2"), "--repo", SLUG,
                    "--api-url", urls(mock)["api_url"], "--uploads-url", urls(mock)["uploads_url"]])
    err = capsys.readouterr()
    assert code == 1 and "UPLOAD VERIFICATION FAILED" in err.err and "published and verified" not in err.out
    assert TOKEN not in err.err + err.out


def test_req_ops_publish_1_an_upload_error_stops_with_the_status_and_never_prints_the_token(tmp_path, mock, env, capsys):
    mock.fail_upload_status = 500
    src = make_export(tmp_path / "e")
    with pytest.raises(er.ExportsError, match="500") as exc:
        er.publish("r4", src, SLUG, False, tmp_path / "rel", **urls(mock))
    assert TOKEN not in str(exc.value)
    assert not mock.assets and not [r for r in mock.requests if r["host"] == "storage"]


def test_req_ops_publish_1_the_token_comes_from_data_release_token_never_gh_token(tmp_path, mock, env, monkeypatch):
    src = make_export(tmp_path / "e")
    monkeypatch.delenv("DATA_RELEASE_TOKEN")
    monkeypatch.setenv("GH_TOKEN", "other-tool-token")
    with pytest.raises(er.ExportsError, match="DATA_RELEASE_TOKEN is not set"):
        er.publish("r5", src, SLUG, False, tmp_path / "rel", **urls(mock))
    assert not mock.requests
    monkeypatch.setenv("DATA_RELEASE_TOKEN", TOKEN)
    er.publish("r5", src, SLUG, False, tmp_path / "rel2", **urls(mock))
    assert all(r["auth"] == f"Bearer {TOKEN}" for r in mock.requests if r["host"] == "api")
    assert "other-tool-token" not in json.dumps(mock.requests)


def test_req_ops_publish_1_the_token_is_never_sent_over_plain_http_to_a_remote_host(tmp_path, env):
    src = make_export(tmp_path / "e")
    with pytest.raises(er.ExportsError, match="must be https"):
        er.publish("r6", src, SLUG, False, tmp_path / "rel", api_url="http://example.com", uploads_url="https://uploads.github.com")


def test_req_ops_publish_1_a_dry_run_lists_the_rest_calls_and_sends_nothing(tmp_path, mock, monkeypatch, capsys):
    monkeypatch.delenv("DATA_RELEASE_TOKEN", raising=False)
    src = make_export(tmp_path / "e")
    calls = er.publish("r7", src, SLUG, True, tmp_path / "rel", **urls(mock))
    out = capsys.readouterr().out
    assert not mock.requests and len(calls) == 5
    assert "uploads?" not in out and "/assets?name=exports-r7.tar.gz" in out and "verify the SHA-256" in out
    assert "gh release" not in out
