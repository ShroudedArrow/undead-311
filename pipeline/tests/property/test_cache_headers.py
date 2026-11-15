"""Check O3 (nightly-and-deploy design): the generated cache headers never mark an unhashed file immutable.

REQ-OPS-CACHE.1: hashed build assets get `Cache-Control: public, max-age=31536000, immutable`; `index.html`,
`status.json` and the data files get `no-cache`. The generator is ops/cache-headers/cache-headers.mjs (plain Node, so the
Netlify build needs no Python). Hypothesis builds file lists, one Node call per example.
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess
from pathlib import Path

import pytest
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

REPO = Path(__file__).resolve().parents[3]
SCRIPT = REPO / "ops" / "cache-headers" / "cache-headers.mjs"
IMMUTABLE = "public, max-age=31536000, immutable"

pytestmark = pytest.mark.skipif(shutil.which("node") is None, reason="node is needed to run the generator")


def generate(lists: list[list[str]]) -> list[str]:
    out = subprocess.run(
        ["node", str(SCRIPT), "--stdin-json"], input=json.dumps(lists), capture_output=True, text=True, check=True, timeout=60
    )
    return json.loads(out.stdout)


def rules(block: str) -> dict[str, str]:
    """path -> Cache-Control value from a generated block."""
    found: dict[str, str] = {}
    path = None
    for line in block.splitlines():
        if line.startswith("#") or not line.strip():
            continue
        if line.startswith("  Cache-Control:"):
            assert path is not None
            found[path] = line.split(":", 1)[1].strip()
        else:
            path = line.strip()
    return found


B64 = st.text(alphabet="ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789_-", min_size=8, max_size=8)
EXT = st.sampled_from(["js", "css", "woff2", "png", "svg", "json", "pmtiles", "html", "txt"])
STEM = st.text(alphabet="abcdefghijklmnopqrstuvwxyz-_", min_size=1, max_size=12)
# Names a person or a build tool could produce: hashed assets, look-alikes, public/ files, generated data, odd characters.
FILE = st.one_of(
    st.builds(lambda s, h, e: f"assets/{s}-{h}.{e}", STEM, B64, EXT),
    st.builds(lambda s, e: f"assets/{s}.{e}", STEM, EXT),
    st.builds(lambda s, h, e: f"{s}-{h}.{e}", STEM, B64, EXT),                 # hash-like name outside assets/
    st.builds(lambda s, h, e: f"data/{s}-{h}.{e}", STEM, B64, EXT),            # hash-like name under data/
    st.builds(lambda s, h, e: f"assets/sub/{s}-{h}.{e}", STEM, B64, EXT),      # nested under assets/
    st.builds(lambda s, e: f"{s}.{e}", STEM, EXT),
    st.builds(lambda s, e: f"data/cards/{s}.{e}", STEM, EXT),
    st.builds(lambda s, h, e: f"assets/{s}-{h}.{e}.gz", STEM, B64, EXT),
    st.sampled_from(["index.html", "status.json", "data/status.json", "tiles/boston.pmtiles", "_headers", "favicon.svg"]),
    st.text(min_size=1, max_size=30),
)
LISTS = st.lists(FILE, max_size=25)
HASHED_NAME = re.compile(r"^assets/[^/]+-[A-Za-z0-9_-]{8}\.[A-Za-z0-9]+(\.map)?$")
ALL_LOWERCASE_HASH = re.compile(r"-[a-z]{8}\.[a-z0-9]+(\.map)?$")


@settings(max_examples=40, suppress_health_check=[HealthCheck.too_slow], deadline=None)
@given(LISTS)
def test_only_hashed_assets_are_ever_immutable(files):
    """REQ-OPS-CACHE.1 (check O3): every immutable rule names a hashed asset in the file list; no wildcard is immutable."""
    (block,) = generate([files])
    for path, value in rules(block).items():
        if value == IMMUTABLE:
            assert "*" not in path
            name = path.lstrip("/")
            assert name in files, f"immutable rule for a file that is not in the build: {path}"
            assert HASHED_NAME.match(name), f"immutable on an unhashed file: {path}"
            assert not ALL_LOWERCASE_HASH.search(name), f"all-lowercase word taken for a hash: {path}"


@settings(max_examples=40, suppress_health_check=[HealthCheck.too_slow], deadline=None)
@given(LISTS)
def test_the_entry_points_and_data_are_always_no_cache_and_never_immutable(files):
    """REQ-OPS-CACHE.1: whatever the file list, `/`, index.html, status.json and data/* revalidate."""
    (block,) = generate([files])
    r = rules(block)
    for path in ("/", "/index.html", "/status.json", "/data/*"):
        assert r[path] == "no-cache"
    assert all(v != IMMUTABLE for p, v in r.items() if p in {"/", "/index.html", "/status.json"} or p.startswith("/data/"))


@settings(max_examples=40, suppress_health_check=[HealthCheck.too_slow], deadline=None)
@given(LISTS, st.randoms(use_true_random=False))
def test_generated_headers_do_not_depend_on_file_order_or_duplicates(files, rnd):
    """REQ-OPS-CACHE.1: the block is deterministic (sorted, deduplicated)."""
    shuffled = files + files[:3]
    rnd.shuffle(shuffled)
    a, b = generate([files, shuffled])
    assert a == b


def test_a_vite_style_build_gets_immutable_assets_and_revalidated_pages():
    """REQ-OPS-CACHE.1: a realistic file list."""
    files = [
        "index.html", "status.json", "_headers", "data/zombies.json", "data/cards/a.json", "tiles/boston.pmtiles",
        "assets/index-DfX2k3_a.js", "assets/index-B3kd9Qxv.css", "assets/courier-prime-latin-400-normal-Cz1aB2c3.woff2",
        "assets/index-DfX2k3_a.js.map",
    ]
    (block,) = generate([files])
    r = rules(block)
    assert {p for p, v in r.items() if v == IMMUTABLE} == {
        "/assets/index-DfX2k3_a.js", "/assets/index-B3kd9Qxv.css",
        "/assets/courier-prime-latin-400-normal-Cz1aB2c3.woff2", "/assets/index-DfX2k3_a.js.map",
    }
    assert "/tiles/boston.pmtiles" not in r and "/data/zombies.json" not in r   # covered by /data/* or the host default


@pytest.mark.parametrize("name", [
    "assets/index-gallery.js", "assets/thumbnail-abcdefgh.png", "index-DfX2k3_a.js", "data/x-DfX2k3_a.json",
    "assets/sub/x-DfX2k3_a.js", "assets/x-DfX2k3_a.js.gz", "assets/x-short.js", "assets/x-DfX2k3_a1.js", "assets/DfX2k3_a.js",
    "assets/a b-DfX2k3_a.js", "assets/a*-DfX2k3_a.js", "assets/a:b-DfX2k3_a.js",
])
def test_look_alike_names_are_not_immutable(name):
    """REQ-OPS-CACHE.1 (O3): look-alikes, other folders, compressed copies and unsafe names stay at the host default."""
    (block,) = generate([[name]])
    assert IMMUTABLE not in rules(block).values()


def test_the_cli_adds_the_block_to_headers_once_and_keeps_the_security_headers(tmp_path):
    """REQ-OPS-CACHE.1, REQ-OPS-HOST.3: the existing CSP rule survives; a second run replaces the block, not repeats it."""
    dist = tmp_path / "dist"
    (dist / "assets").mkdir(parents=True)
    (dist / "assets" / "index-DfX2k3_a.js").write_text("x")
    (dist / "index.html").write_text("<html></html>")
    (dist / "_headers").write_text("/*\n  Content-Security-Policy: default-src 'self'\n")
    for _ in range(2):
        subprocess.run(["node", str(SCRIPT), str(dist)], check=True, capture_output=True, timeout=60)
    text = (dist / "_headers").read_text()
    assert text.startswith("/*\n  Content-Security-Policy: default-src 'self'\n")
    assert text.count("# BEGIN cache-headers") == 1 and text.count("/assets/index-DfX2k3_a.js\n") == 1
    assert text.endswith("# END cache-headers\n")


def test_the_cli_fails_on_a_missing_folder(tmp_path):
    """REQ-OPS-CACHE.1: a build without web/dist stops loudly."""
    r = subprocess.run(["node", str(SCRIPT), str(tmp_path / "nope")], check=False, capture_output=True, text=True, timeout=60)
    assert r.returncode == 1 and "not found" in r.stderr
