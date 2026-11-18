"""Smoke test of the draft deploy (REQ-OPS-NIGHTLY.5): ops/undead-311-data/smoke_test.py.

The script is imported and run against a fake site (a dict of files) and against a real local HTTP server. Every check has a
passing case and a failing case, so a check that stopped checking would fail a test.
"""

from __future__ import annotations

import hashlib
import importlib.util
import io
import json
import re
import socket
import sys
import tarfile
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[3]
SCRIPT = REPO / "ops" / "undead-311-data" / "smoke_test.py"
_spec = importlib.util.spec_from_file_location("smoke_test", SCRIPT)
smoke = importlib.util.module_from_spec(_spec)
sys.modules["smoke_test"] = smoke
_spec.loader.exec_module(smoke)

VERSION = "2026-11-18+b68d616+89e078da"
CSP = "default-src 'self'"
SLUG = "back-bay"


def placebo(lo: float, hi: float) -> dict:
    return {"excess": (lo + hi) / 2, "lo": lo, "hi": hi, "calibration_warning": not (lo <= 0 <= hi)}


class Site:
    """A fake deployed site: path -> (status, headers, body). `build` writes the matching checkout folders into tmp_path."""

    def __init__(self, tmp_path: Path):
        self.public = tmp_path / "public"
        self.judging = tmp_path / "judging"
        self.files: dict[str, tuple[int, dict[str, str], bytes]] = {}
        self.shard_names = [f"{SLUG}-{y}.json" for y in (2015, 2016, 2017, 2018, 2019)]
        for name in self.shard_names:
            self.put_card(name, {"cards": [{"id": "101002841544", "closure": "Case Resolved pothole filled"}]})
        self.public.joinpath("cards").mkdir(parents=True, exist_ok=True)
        for name in self.shard_names:
            (self.public / "cards" / name).write_text("{}")
        for rel, body in {"points.json": b'{"id":[]}', "stats/judge_tour.json": b'{"zombie_ids":[]}', "cards/back-bay-2015.json": b'{"cards":[]}'}.items():
            f = self.judging / rel
            f.parent.mkdir(parents=True, exist_ok=True)
            f.write_bytes(body)
            self.files[f"/data/frozen/{rel}"] = (200, {}, body)
        self.files["/index.html"] = (200, {"content-security-policy": CSP}, b"<html></html>")
        for link in ("/methods", "/repeat", "/street", "/judge", f"/neighborhood/{SLUG}"):
            self.files[link] = (200, {}, b"<html></html>")
        self.put_json("/data/status.json", {"data_version": VERSION, "dataset": "full", "ok": True})
        self.put_json("/data/stats/scorecard.json", {"dataset": "full", "scorecards": [{"family": "citywide", "stayed_fixed_adj": None}]})
        self.put_json("/data/stats/excess.json", {"placebo": placebo(-3591.5, -3236.3)})

    def put_json(self, path: str, doc: dict) -> None:
        self.files[path] = (200, {}, json.dumps(doc).encode())

    def put_card(self, name: str, doc: dict | str) -> None:
        body = doc if isinstance(doc, str) else json.dumps(doc)
        self.files[f"/data/cards/{name}"] = (200, {}, body.encode())

    def fetch(self, path: str):
        return self.files.get(path, (404, {}, b"not found"))

    def run(self, **kw):
        kw.setdefault("seed", 1)
        return smoke.run_checks(self.fetch, manifest={"data_version": VERSION}, public=self.public, judging=self.judging, **kw)


@pytest.fixture
def site(tmp_path):
    return Site(tmp_path)


def failed(results) -> list[str]:
    return [name for name, ok, _ in results if not ok]


def test_a_good_draft_passes_every_check(site):
    """REQ-OPS-NIGHTLY.5: all checks are run and a correct draft passes all of them."""
    results = site.run()
    assert failed(results) == []
    names = " | ".join(n for n, _, _ in results)
    for needle in ("index.html returns 200", "Content-Security-Policy", "data_version", "dataset is \"full\"", "adjusted stayed-fixed",
                   "excess is hidden", "/methods", "/repeat", "/street", "/judge", f"/neighborhood/{SLUG}", "frozen/points.json", "cards/"):
        assert needle in names, needle
    assert sum(1 for n, _, _ in results if n.startswith("cards/")) == 3


@pytest.mark.parametrize("status", [404, 500])
def test_index_must_return_200(site, status):
    site.files["/index.html"] = (status, {"content-security-policy": CSP}, b"")
    assert "index.html returns 200" in failed(site.run())


def test_the_csp_header_is_required(site):
    site.files["/index.html"] = (200, {}, b"<html></html>")
    assert failed(site.run()) == ["Content-Security-Policy header is present"]
    site.files["/index.html"] = (200, {"content-security-policy": "  "}, b"")
    assert "Content-Security-Policy header is present" in failed(site.run())


def test_data_version_must_match_the_downloaded_release(site):
    site.put_json("/data/status.json", {"data_version": "2026-11-12+old", "dataset": "full"})
    assert failed(site.run()) == ["status.json data_version matches the downloaded release"]
    site.put_json("/data/status.json", {"dataset": "full"})                               # no version at all
    assert "status.json data_version matches the downloaded release" in failed(site.run())


@pytest.mark.parametrize("where", ["status", "scorecard"])
def test_the_dataset_must_be_full_so_the_sample_notice_is_off(site, where):
    if where == "status":
        site.put_json("/data/status.json", {"data_version": VERSION, "dataset": "sample"})
    else:
        site.put_json("/data/stats/scorecard.json", {"dataset": "sample", "scorecards": []})
    assert len(failed(site.run())) == 1 and "dataset" in failed(site.run())[0]


def test_an_adjusted_stayed_fixed_rate_in_the_scorecard_fails(site):
    site.put_json("/data/stats/scorecard.json", {"dataset": "full", "scorecards": [{"family": "sign", "stayed_fixed_adj": {"rate": 0.4}}]})
    assert failed(site.run()) == ["scorecard has no adjusted stayed-fixed rate"]


def test_an_excess_the_site_would_show_fails_unless_allowed(site):
    """methods.md: the excess is shown only when the placebo interval covers 0; the owner rule is that it stays absent."""
    site.put_json("/data/stats/excess.json", {"placebo": placebo(-50, 40)})
    assert failed(site.run()) == ["excess is hidden (placebo interval does not cover 0)"]
    assert failed(site.run(allow_excess=True)) == []


@pytest.mark.parametrize("excess,shown", [
    ({"placebo": {"excess": 0, "lo": 0, "hi": 5}}, True),         # the interval's edge counts as covering 0, like the site
    ({"placebo": {"excess": 0, "lo": -5, "hi": 0}}, True),
    ({"placebo": {"excess": 3, "lo": 1, "hi": 5}}, False),
    ({"placebo": {"excess": -3, "lo": -5, "hi": -1}}, False),
    ({}, False),                                                  # no placebo, no excess (the site's rule)
    ({"placebo": {"excess": 0, "lo": True, "hi": 5}}, False),     # booleans are not numbers
    ({"placebo": "x"}, False),
])
def test_excess_shown_is_the_sites_rule(excess, shown):
    """REQ-OPS-NIGHTLY.5: mirrors web/src/lib/methods.ts excessShown."""
    assert smoke.excess_shown(excess) is shown


@pytest.mark.parametrize("link", ["/methods", "/repeat", "/street", "/judge", f"/neighborhood/{SLUG}"])
def test_each_deep_link_must_return_200(site, link):
    site.files.pop(link)
    assert failed(site.run()) == [f"{link} returns 200"]


def test_the_neighborhood_page_comes_from_the_shard_names(site):
    assert smoke.neighborhood_slug(site.public) == SLUG
    assert smoke.neighborhood_slug(site.public / "none") is None


def test_judge_mode_files_must_match_data_judging_byte_for_byte(site):
    site.files["/data/frozen/points.json"] = (200, {}, b'{"id":["x"]}')
    assert failed(site.run()) == ["frozen/points.json matches data/judging/"]
    site.files.pop("/data/frozen/points.json")
    assert failed(site.run()) == ["frozen/points.json matches data/judging/"]


def test_an_empty_judging_folder_fails_rather_than_passing_vacuously(site):
    for f in sorted(site.judging.rglob("*"), reverse=True):
        f.unlink() if f.is_file() else f.rmdir()
    assert failed(site.run()) == ["judge-mode files exist in data/judging/"]


@pytest.mark.parametrize("text,what", [
    ("call me at (617) 635-4500 please", "a phone number"),
    ("617-635-4500", "a phone number"),
    ("617.635.4500", "a phone number"),
    ("+1 617 635 4500", "a phone number"),
    ("mail jane.doe+311@example.org now", "an e-mail address"),
])
def test_a_card_with_an_email_or_phone_number_fails(site, text, what):
    for name in site.shard_names:
        site.put_card(name, {"closure": text})
    bad = failed(site.run())
    assert len(bad) == 3 and all(n.startswith("cards/") for n in bad)
    assert what in " ".join(d for _, ok, d in site.run() if not ok)


@pytest.mark.parametrize("text", [
    "101002841544 and BCS-00121517",                      # case ids
    '"lat":42.3475,"lon":-71.0686,"open":"2026-11-18 13:58:07.36"',   # coordinates and timestamps
    "Closed date : 2025-09-30 13:58:07.36 Case Resolved",
    "span 12.345.6789",
])
def test_ids_coordinates_and_dates_are_not_phone_numbers(text):
    assert smoke.sensitive_text(text) == []


def test_a_bare_at_sign_used_as_at_passes_but_strict_at_fails_it(site):
    """The rehearsal-2 cards hold "pulled @ Farrington Ave" in 13 of 215 shards: not an address, so not a failure by default."""
    for name in site.shard_names:
        site.put_card(name, {"closure": "Overhead span was pulled @ Farrington Ave"})
    results = site.run()
    assert failed(results) == []
    assert any("bare @" in d for _, _, d in results)
    assert len(failed(site.run(strict_at=True))) == 3


def test_a_card_shard_that_is_missing_or_not_json_fails(site):
    for name in site.shard_names:
        site.put_card(name, "<html>app shell</html>")
    assert len(failed(site.run())) == 3
    for name in site.shard_names:
        site.files.pop(f"/data/cards/{name}")
    assert len(failed(site.run())) == 3


def test_three_distinct_shards_are_sampled_with_a_seed_and_differently_without(site):
    a = [n for n, _, _ in site.run(seed=7) if n.startswith("cards/")]
    assert a == [n for n, _, _ in site.run(seed=7) if n.startswith("cards/")] and len(set(a)) == 3
    seen = {tuple(n for n, _, _ in site.run(seed=s) if n.startswith("cards/")) for s in range(20)}
    assert len(seen) > 1


def test_fewer_than_three_shards_is_a_failure(site):
    for name in site.shard_names[2:]:
        (site.public / "cards" / name).unlink()
    assert any("card shards to sample" in n for n in failed(site.run()))


def test_an_unreachable_draft_reports_failures_instead_of_raising(site):
    def down(path):
        raise smoke.SmokeError(f"{path}: no answer")
    results = smoke.run_checks(down, manifest={"data_version": VERSION}, public=site.public, judging=site.judging, seed=1)
    assert failed(results) and all(not ok for _, ok, _ in results if "returns 200" in _)


def test_the_manifest_comes_from_the_archive(tmp_path):
    archive = tmp_path / "exports-x.tar.gz"
    blob = json.dumps({"data_version": VERSION, "files": {}}).encode()
    with tarfile.open(archive, "w:gz") as tar:
        info = tarfile.TarInfo("MANIFEST.json")
        info.size = len(blob)
        tar.addfile(info, io.BytesIO(blob))
    assert smoke.manifest_of(archive)["data_version"] == VERSION


# ---- the real HTTP client and the command line ---------------------------------------------------------------------------

class Handler(BaseHTTPRequestHandler):
    site: Site

    def do_GET(self):
        status, headers, body = self.site.fetch(self.path)
        self.send_response(status)
        for k, v in headers.items():
            self.send_header(k, v)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *args):
        pass


@pytest.fixture
def served(site):
    handler = type("H", (Handler,), {"site": site})
    server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield site, f"http://127.0.0.1:{server.server_address[1]}"
    server.shutdown()
    server.server_close()


def write_archive(path: Path, version: str = VERSION) -> Path:
    blob = json.dumps({"data_version": version, "files": {}}).encode()
    with tarfile.open(path, "w:gz") as tar:
        info = tarfile.TarInfo("MANIFEST.json")
        info.size = len(blob)
        tar.addfile(info, io.BytesIO(blob))
    return path


def cli(served, tmp_path, *extra, version=VERSION):
    site, url = served
    archive = write_archive(tmp_path / "a.tar.gz", version)
    return smoke.main(["--base-url", url, "--archive", str(archive), "--public", str(site.public), "--judging", str(site.judging),
                       "--seed", "1", "--retries", "1", *extra])


def test_http_client_returns_a_404_as_a_status_and_follows_the_real_headers(served):
    _, url = served
    fetch = smoke.http_fetch(url, retries=1)
    status, headers, _ = fetch("/index.html")
    assert status == 200 and headers["content-security-policy"] == CSP
    assert fetch("/nope")[0] == 404


def test_the_command_exits_0_for_a_good_draft_and_1_for_a_bad_one(served, tmp_path, capsys):
    site, _ = served
    assert cli(served, tmp_path) == 0
    out = capsys.readouterr().out
    assert "smoke test:" in out and "FAIL" not in out
    site.put_json("/data/status.json", {"data_version": "other", "dataset": "full"})
    assert cli(served, tmp_path) == 1
    assert "FAIL  status.json data_version" in capsys.readouterr().out
    assert cli(served, tmp_path, version="other") == 0            # the draft now matches that release


def test_an_unreachable_draft_fails_every_check_and_a_missing_archive_exits_2(site, tmp_path, capsys):
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]                                   # closed again: nothing listens
    archive = write_archive(tmp_path / "a.tar.gz")
    code = smoke.main(["--base-url", f"http://127.0.0.1:{port}", "--archive", str(archive), "--public", str(site.public),
                       "--judging", str(site.judging), "--retries", "1", "--retry-wait", "0"])
    out = capsys.readouterr()
    assert code == 1 and "FAIL" in out.out                          # every fetch failed, so every check failed (not a crash)
    assert smoke.main(["--base-url", "http://127.0.0.1:1", "--archive", str(tmp_path / "missing.tar.gz"), "--retries", "1"]) == 2
    assert "could not run" in capsys.readouterr().err


def test_the_script_uses_only_the_standard_library():
    """REQ-OPS-NIGHTLY.5: it runs under `uv run --locked` in the judged checkout but must not need anything beyond Python."""
    imports = set(re.findall(r"^(?:from|import) (\w+)", SCRIPT.read_text(), re.MULTILINE))
    assert imports <= set(sys.stdlib_module_names) | {"__future__"}, imports - set(sys.stdlib_module_names)


def test_no_check_hashes_a_different_file_than_the_one_it_compares(site):
    """The comparison is by content: a same-length different file fails."""
    original = (site.judging / "points.json").read_bytes()
    different = bytes(reversed(original))
    assert len(different) == len(original) and hashlib.sha256(different).digest() != hashlib.sha256(original).digest()
    site.files["/data/frozen/points.json"] = (200, {}, different)
    assert "frozen/points.json matches data/judging/" in failed(site.run())
