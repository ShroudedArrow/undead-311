"""`make capture` (REQ-OPS-CAPTURE.1, REQ-OPS-CAPTURE.2): the capture config covers every page, both sizes, the judge-tour
video and the time-lapse GIF, hides third-party logos but keeps the OpenStreetMap attribution, and the GIF writer produces
valid GIFs. No browser is started here; the capture itself is run by hand and by the owner."""

from __future__ import annotations

import json
import re
import shutil
import subprocess
from pathlib import Path

import pytest
from helpers import examples
from hypothesis import given, settings
from hypothesis import strategies as st

REPO = Path(__file__).resolve().parents[3]
CONFIG = json.loads((REPO / "ops" / "capture" / "capture.config.json").read_text(encoding="utf-8"))
NODE = shutil.which("node")


def static_routes() -> set[str]:
    """Paths of the static routes in web/src/App.tsx ("/" for the index, no parameters, no catch-all)."""
    app = (REPO / "web" / "src" / "App.tsx").read_text(encoding="utf-8")
    paths = {"/"} if "<Route index" in app else set()
    for p in re.findall(r'<Route path="([^"]+)"', app):
        if ":" not in p and p != "*":
            paths.add("/" + p)
    return paths


def test_every_route_has_a_screenshot_page():
    """REQ-OPS-CAPTURE.1: every page of the site is screenshotted (dynamic routes by an example)."""
    pages = {p["path"].split("?")[0] for p in CONFIG["pages"]}
    for route in static_routes():
        assert route in pages, f"{route} is a route in App.tsx but not in capture.config.json"
    assert any(p.startswith("/zombie/") for p in pages)
    assert any(p.startswith("/neighborhood/") for p in pages)


def test_desktop_and_phone_sizes():
    """REQ-OPS-CAPTURE.1: each page is captured at a desktop and a phone size."""
    sizes = {v["name"]: (v["width"], v["height"]) for v in CONFIG["viewports"]}
    assert sizes["desktop"][0] >= 1024
    assert sizes["phone"][0] <= 480


def test_outputs_go_to_docs_media():
    """REQ-OPS-CAPTURE.1: video, GIF and screenshots land in docs/media/."""
    assert CONFIG["out_dir"] == "docs/media"
    assert CONFIG["video"]["file"].endswith(".webm")
    assert CONFIG["gif"]["file"].endswith(".gif")
    assert len({p["name"] for p in CONFIG["pages"]}) == len(CONFIG["pages"])


def test_logos_are_hidden_and_the_osm_attribution_is_kept():
    """REQ-OPS-CAPTURE.2 (language.md): third-party logos are hidden; OpenStreetMap attribution stays (tech.md)."""
    hide = CONFIG["hide_selectors"]
    assert ".maplibregl-ctrl-logo" in hide
    assert any("logo" in s for s in hide if s != ".maplibregl-ctrl-logo")
    assert ".maplibregl-ctrl-attrib" in CONFIG["keep_selectors"]
    assert not set(hide) & set(CONFIG["keep_selectors"])
    assert not any("attrib" in s for s in hide)


def test_script_hides_logos_before_every_capture():
    """REQ-OPS-CAPTURE.2: hideLogos runs for each screenshot page, the video and the GIF."""
    src = (REPO / "ops" / "capture" / "capture.mjs").read_text(encoding="utf-8")
    assert "hide_selectors" in src
    assert src.count("await hideLogos(page)") >= 4  # screenshots, two video pages, the GIF


def test_make_capture_runs_the_script():
    """REQ-OPS-CAPTURE.1: the Makefile target is wired to the script, not a stub."""
    make = (REPO / "Makefile").read_text(encoding="utf-8")
    block = re.search(r"^capture:.*\n((?:\t.*\n)+)", make, re.MULTILINE)
    assert block and "ops/capture/capture.mjs" in block.group(1)


def write_gif(tmp_path: Path, w: int, h: int, n: int, delay: int) -> Path:
    out = tmp_path / "t.gif"
    subprocess.run([NODE, str(REPO / "ops" / "capture" / "gif.mjs"), str(out), str(w), str(h), str(n), str(delay)], check=True)
    return out


@pytest.mark.skipif(NODE is None, reason="node not installed")
def test_gif_writer_makes_a_valid_gif(tmp_path):
    """REQ-OPS-CAPTURE.1: header, size, trailer and frame count are right."""
    data = write_gif(tmp_path, 40, 20, 5, 200).read_bytes()
    assert data[:6] == b"GIF89a"
    assert int.from_bytes(data[6:8], "little") == 40
    assert int.from_bytes(data[8:10], "little") == 20
    assert data[-1] == 0x3B
    assert data.count(b"\x21\xf9\x04\x04") == 5  # one graphic control block per frame


@pytest.mark.skipif(NODE is None, reason="node not installed")
@settings(max_examples=examples(8), deadline=None)
@given(w=st.integers(1, 90), h=st.integers(1, 60), n=st.integers(1, 4))
def test_gif_round_trips_through_a_decoder(w, h, n):
    """REQ-OPS-CAPTURE.1: any size decodes (LZW code-size growth and reset), with the right frame count and colours."""
    pil = pytest.importorskip("PIL.Image")
    import tempfile

    with tempfile.TemporaryDirectory() as d:
        im = pil.open(write_gif(Path(d), w, h, n, 100))
        assert im.size == (w, h)
        assert im.n_frames == n
        im.seek(n - 1)
        rgb = im.convert("RGB")
        hot = min(w - 1, n - 1)  # the generator paints this column red and the rest cream
        near = lambda got, want: all(abs(a - b) <= 51 for a, b in zip(got, want))
        assert near(rgb.getpixel((hot, h - 1)), (220, 40, 40))
        other = 0 if hot != 0 else w - 1
        if other != hot:
            assert near(rgb.getpixel((other, h - 1)), (255, 255, 170))


@pytest.mark.skipif(NODE is None, reason="node not installed")
def test_gif_with_noisy_pixels_exercises_table_reset(tmp_path):
    """REQ-OPS-CAPTURE.1: more than 4096 codes forces a table reset; the picture must still decode."""
    pil = pytest.importorskip("PIL.Image")
    script = tmp_path / "noise.mjs"
    script.write_text(
        f'import {{ encodeGif }} from "{(REPO / "ops" / "capture" / "gif.mjs").as_posix()}";\n'
        'import { writeFileSync } from "node:fs";\n'
        "const w = 120, h = 90, rgba = new Uint8Array(w * h * 4);\n"
        "let s = 12345;\n"
        "for (let i = 0; i < w * h; i++) { s = (Math.imul(s, 1103515245) + 12345) & 0x7fffffff; rgba.set([(s >> 3) & 255, (s >> 11) & 255, (s >> 19) & 255, 255], i * 4); }\n"
        f'writeFileSync("{(tmp_path / "n.gif").as_posix()}", encodeGif([{{ width: w, height: h, rgba }}]));\n',
        encoding="utf-8",
    )
    subprocess.run([NODE, str(script)], check=True)
    im = pil.open(tmp_path / "n.gif").convert("RGB")
    assert im.size == (120, 90)
    # every decoded pixel is within one palette step of the noise the script generated
    s = 12345
    for i in range(120 * 90):
        s = (s * 1103515245 + 12345) & 0x7FFFFFFF
        want = ((s >> 3) & 255, (s >> 11) & 255, (s >> 19) & 255)
        got = im.getpixel((i % 120, i // 120))
        assert all(abs(a - b) <= 26 for a, b in zip(got, want)), (i, got, want)
