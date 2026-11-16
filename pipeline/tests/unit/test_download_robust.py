"""Download robustness (REQ-ING-DL.1-4): retry with backoff, Range resume, size check, hash comparison.

A real HTTP server on 127.0.0.1 injects the faults: 503s, a body cut short, a server that ignores Range, a 416.
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
import re
import threading
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest

SPEC = importlib.util.spec_from_file_location("download_dl", Path(__file__).parents[2] / "scripts" / "download.py")
dl = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(dl)

OPENER = urllib.request.build_opener(urllib.request.ProxyHandler({}))  # never route localhost through a proxy
BODY = bytes(range(256)) * 400  # 102,400 bytes
sha = lambda b: hashlib.sha256(b).hexdigest()


class State:
    def __init__(self):
        self.files = {"/f.csv": BODY}
        self.fail = 0  # answer the next N requests with 503
        self.truncate = 0  # cut the body of the next N responses in half
        self.ignore_range = False
        self.requests: list[tuple[str, str | None]] = []


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, *args):
        pass

    def reply(self, code, headers, body=b""):
        self.send_response(code)
        for k, v in {**headers, "Content-Length": str(len(body))}.items():
            self.send_header(k, v)
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        st: State = self.server.state
        rng = self.headers.get("Range")
        st.requests.append((self.path, rng))
        if st.fail > 0:
            st.fail -= 1
            return self.reply(503, {})
        if self.path not in st.files:
            return self.reply(404, {})
        body, start, code, extra = st.files[self.path], 0, 200, {}
        if rng and not st.ignore_range:
            m = re.match(r"bytes=(\d+)-(\d*)", rng)
            start = int(m.group(1))
            if start >= len(body):
                return self.reply(416, {"Content-Range": f"bytes */{len(body)}"})
            end = int(m.group(2)) if m.group(2) else len(body) - 1
            body_part = body[start : end + 1]
            code, extra = 206, {"Content-Range": f"bytes {start}-{start + len(body_part) - 1}/{len(body)}"}
        else:
            body_part = body
        if st.truncate > 0 and len(body_part) > 1:
            st.truncate -= 1
            self.send_response(code)
            for k, v in {**extra, "Content-Length": str(len(body_part))}.items():
                self.send_header(k, v)
            self.end_headers()
            self.wfile.write(body_part[: len(body_part) // 2])
            self.wfile.flush()
            self.close_connection = True
            return
        self.reply(code, extra, body_part)


@pytest.fixture
def server():
    srv = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    srv.state = State()
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    srv.url = f"http://127.0.0.1:{srv.server_address[1]}"
    yield srv
    srv.shutdown()
    srv.server_close()


def fetch(srv, dest, **kw):
    sleeps: list[float] = []
    out = dl.fetch_file(srv.url + "/f.csv", dest, opener=OPENER, log=lambda *_: None, sleep=sleeps.append, **kw)
    return out, sleeps


def test_req_ing_dl_1_retries_with_exponential_backoff_then_succeeds(server, tmp_path):
    """REQ-ING-DL.1: two 503s, then the file; the waits double."""
    server.state.fail = 2
    size, sleeps = fetch(server, tmp_path / "f.csv")
    assert size == len(BODY) and (tmp_path / "f.csv").read_bytes() == BODY
    assert sleeps == [1.0, 2.0] and len(server.state.requests) == 3


def test_req_ing_dl_1_gives_up_after_five_tries_with_four_doubling_waits(server, tmp_path):
    """REQ-ING-DL.1: 5 tries, waits 1, 2, 4, 8 s, then a DownloadError naming the file."""
    server.state.fail = 99
    sleeps: list[float] = []
    with pytest.raises(dl.DownloadError, match="f.csv"):
        dl.fetch_file(server.url + "/f.csv", tmp_path / "f.csv", opener=OPENER, log=lambda *_: None, sleep=sleeps.append)
    assert sleeps == [1.0, 2.0, 4.0, 8.0] and len(server.state.requests) == 5
    assert not (tmp_path / "f.csv").exists()


def test_req_ing_dl_1_a_404_is_not_retried(server, tmp_path):
    """REQ-ING-DL.1: only network errors, 408/425/429 and 5xx are retried."""
    sleeps: list[float] = []
    with pytest.raises(urllib.error.HTTPError):
        dl.fetch_file(server.url + "/nope.csv", tmp_path / "n.csv", opener=OPENER, log=lambda *_: None, sleep=sleeps.append)
    assert sleeps == [] and len(server.state.requests) == 1


def test_req_ing_dl_1_a_refused_connection_is_retried(tmp_path):
    """REQ-ING-DL.1: nothing listens on the port, so every try fails and all 5 are used."""
    sleeps: list[float] = []
    with pytest.raises(dl.DownloadError):
        dl.fetch_file("http://127.0.0.1:9/x.csv", tmp_path / "x.csv", opener=OPENER, log=lambda *_: None, sleep=sleeps.append)
    assert len(sleeps) == 4


def test_req_ing_dl_2_resumes_a_part_file_with_a_range_request(server, tmp_path):
    """REQ-ING-DL.2: 1,000 bytes already on disk, so only the rest is requested and the result is byte-identical."""
    part = tmp_path / "f.csv.part"
    part.write_bytes(BODY[:1000])
    size, _ = fetch(server, tmp_path / "f.csv")
    assert size == len(BODY) and (tmp_path / "f.csv").read_bytes() == BODY and not part.exists()
    assert server.state.requests == [("/f.csv", "bytes=1000-")]


def test_req_ing_dl_2_a_body_cut_short_is_resumed_on_the_next_try(server, tmp_path):
    """REQ-ING-DL.2/3: the first response stops halfway; the part is kept and the retry asks for the rest."""
    server.state.truncate = 1
    size, sleeps = fetch(server, tmp_path / "f.csv")
    assert size == len(BODY) and (tmp_path / "f.csv").read_bytes() == BODY and sleeps == [1.0]
    assert server.state.requests[0][1] is None and server.state.requests[1][1] == f"bytes={len(BODY) // 2}-"


def test_req_ing_dl_2_a_server_that_ignores_range_restarts_the_file(server, tmp_path):
    """REQ-ING-DL.2: a 200 answer to a Range request replaces the part instead of appending to it."""
    server.state.ignore_range = True
    (tmp_path / "f.csv.part").write_bytes(b"stale bytes that must not stay")
    size, _ = fetch(server, tmp_path / "f.csv")
    assert size == len(BODY) and (tmp_path / "f.csv").read_bytes() == BODY


def test_req_ing_dl_2_a_complete_part_is_accepted_after_a_416(server, tmp_path):
    """REQ-ING-DL.2: the part already has every byte; the 416's total equals its size."""
    (tmp_path / "f.csv.part").write_bytes(BODY)
    size, _ = fetch(server, tmp_path / "f.csv")
    assert size == len(BODY) and (tmp_path / "f.csv").read_bytes() == BODY


def test_req_ing_dl_2_a_part_longer_than_the_file_is_discarded_and_refetched(server, tmp_path):
    """REQ-ING-DL.2/3: a part from an older, bigger file cannot be resumed; it restarts from byte 0."""
    (tmp_path / "f.csv.part").write_bytes(BODY + b"extra")
    size, sleeps = fetch(server, tmp_path / "f.csv")
    assert size == len(BODY) and (tmp_path / "f.csv").read_bytes() == BODY and len(sleeps) == 1


def test_req_ing_dl_3_a_short_file_is_never_renamed_into_place(server, tmp_path):
    """REQ-ING-DL.3: every response is cut short, so the download fails and `f.csv` does not exist (the part stays)."""
    server.state.truncate = 99
    with pytest.raises(dl.DownloadError, match="announced"):
        fetch(server, tmp_path / "f.csv")
    assert not (tmp_path / "f.csv").exists() and (tmp_path / "f.csv.part").exists()
    assert 0 < (tmp_path / "f.csv.part").stat().st_size < len(BODY)


def prev_row(body: bytes, last_modified="2026-11-12T00:00:00"):
    return {"resource": "r", "last_modified": last_modified, "bytes": len(body), "sha256": sha(body)}


def sync(srv, dest, prev, last_modified="2026-11-12T00:00:00"):
    return dl.sync_file(dest, srv.url + "/f.csv", prev, last_modified, opener=OPENER, log=lambda *_: None, sleep=lambda s: None)


def test_req_ing_dl_4_a_matching_file_is_kept_without_downloading_it(server, tmp_path):
    """REQ-ING-DL.4: hash, size, last_modified and the server's size all match the previous row: only a 1-byte probe is sent."""
    (tmp_path / "f.csv").write_bytes(BODY)
    r = sync(server, tmp_path / "f.csv", prev_row(BODY))
    assert (r.status, r.bytes, r.sha256) == ("kept", len(BODY), sha(BODY))
    assert server.state.requests == [("/f.csv", "bytes=0-0")]


def test_req_ing_dl_4_a_changed_server_file_is_replaced_and_reported_as_changed(server, tmp_path):
    """REQ-ING-DL.4: the file on disk equals the old row but the server has a new version: it is refetched and reported."""
    (tmp_path / "f.csv").write_bytes(BODY)
    new = BODY + b"new rows\n"
    server.state.files["/f.csv"] = new
    r = sync(server, tmp_path / "f.csv", prev_row(BODY))
    assert r.status == "changed" and r.old_sha256 == sha(BODY) and r.sha256 == sha(new) and r.old_bytes == len(BODY)
    assert (tmp_path / "f.csv").read_bytes() == new
    lines: list[str] = []
    assert dl.report_changes([r], log=lines.append) == [r]
    assert any(x.startswith("CHANGED f.csv") for x in lines)


def test_req_ing_dl_4_a_stale_local_file_is_refetched_not_kept(server, tmp_path):
    """REQ-ING-DL.4: the local file differs from the previous row (stale or damaged); the server has the recorded version."""
    (tmp_path / "f.csv").write_bytes(b"old and wrong")
    r = sync(server, tmp_path / "f.csv", prev_row(BODY))
    assert r.status == "unchanged" and (tmp_path / "f.csv").read_bytes() == BODY


def test_req_ing_dl_4_a_new_last_modified_forces_a_refetch_even_with_equal_bytes(server, tmp_path):
    """REQ-ING-DL.4."""
    (tmp_path / "f.csv").write_bytes(BODY)
    r = sync(server, tmp_path / "f.csv", prev_row(BODY, "2026-09-18T00:00:00"), "2026-11-16T00:00:00")
    assert r.status == "unchanged" and len(server.state.requests) == 2


def test_req_ing_dl_4_a_file_with_no_previous_row_is_new_and_a_local_copy_is_not_trusted(server, tmp_path):
    """REQ-ING-DL.4."""
    (tmp_path / "f.csv").write_bytes(b"unverifiable local copy")
    r = sync(server, tmp_path / "f.csv", None)
    assert r.status == "new" and (tmp_path / "f.csv").read_bytes() == BODY


def test_req_ing_dl_4_previous_rows_read_the_download_table_only():
    """REQ-ING-DL.4: the judging section lists `raw/...` rows too; they are not the previous download rows."""
    text = (
        "# Data snapshot\n\n| file | resource | last_modified | bytes | sha256 |\n|---|---|---|---|---|\n"
        f"| 311_2024.csv | R | 2026-09-18 | 12 | {'a' * 64} |\n| street_segments_sam.geojson | G | t | 5 | {'b' * 64} |\n\n"
        f"<!-- BEGIN judging snapshot (written by make snapshot; do not edit) -->\n| raw/311_2025.csv | 9 | {'c' * 64} |\n"
        "<!-- END judging snapshot -->\n"
    )
    rows = dl.previous_rows(text)
    assert set(rows) == {"311_2024.csv", "street_segments_sam.geojson"} and rows["311_2024.csv"]["bytes"] == 12


def test_req_ing_dl_4_the_real_snapshot_table_parses_to_every_listed_file():
    """REQ-ING-DL.4: the committed data/SNAPSHOT.md download table is readable by the parser."""
    text = (Path(__file__).resolve().parents[3] / "data" / "SNAPSHOT.md").read_text()
    rows = dl.previous_rows(text)
    assert "311_new_system.csv" in rows and "street_segments_sam.geojson" in rows
    assert all(len(r["sha256"]) == 64 for r in rows.values())


def test_req_ing_dl_4_the_report_file_lists_changed_files(tmp_path):
    """REQ-ING-DL.4."""
    a = dl.FileResult("a.csv", "changed", 2, "x" * 64, 1, "y" * 64)
    b = dl.FileResult("b.csv", "kept", 3, "z" * 64, 3, "z" * 64)
    out = dl.write_report(tmp_path, [a, b], [a])
    body = json.loads(out.read_text())
    assert out == tmp_path / "logs" / "download-report.json"
    assert body["changed"] == ["a.csv"] and [f["status"] for f in body["files"]] == ["changed", "kept"]
