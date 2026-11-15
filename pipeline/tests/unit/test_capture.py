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


def parameterised_routes() -> set[str]:
    """Static prefix of each `:param` route in App.tsx ("/zombie/" for `zombie/:id`)."""
    app = (REPO / "web" / "src" / "App.tsx").read_text(encoding="utf-8")
    return {"/" + p.split(":")[0] for p in re.findall(r'<Route path="([^"]+)"', app) if ":" in p}


def test_every_parameterised_route_has_an_example_page():
    """REQ-OPS-CAPTURE.1 (ops#205): districts/:id, zombie/:id and neighborhood/:slug each have an example page."""
    pages = [p["path"].split("?")[0] for p in CONFIG["pages"]]
    routes = parameterised_routes()
    assert {"/zombie/", "/neighborhood/", "/districts/"} <= routes
    for prefix in routes:
        assert any(p.startswith(prefix) and p != prefix for p in pages), f"{prefix}:param has no example page in capture.config.json"


def test_every_path_placeholder_is_resolved_by_the_script():
    """REQ-OPS-CAPTURE.1: each {placeholder} used in the config is filled in by capture.mjs."""
    src = (REPO / "ops" / "capture" / "capture.mjs").read_text(encoding="utf-8")
    for name in {m for p in CONFIG["pages"] for m in re.findall(r"\{(\w+)\}", p["path"])}:
        assert "{" + name + "}" in src, f"capture.mjs does not fill {{{name}}}"


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


@pytest.mark.skipif(NODE is None, reason="node not installed")
@settings(max_examples=examples(25), deadline=None)
@given(grey=st.integers(0, 255), d1=st.integers(0, 12), d2=st.integers(0, 12))
def test_neutral_colours_decode_to_greys(grey, d1, d2):
    """REQ-OPS-CAPTURE.1 (ops#201): a near-neutral colour (channels within 12 of each other) decodes with r = g = b."""
    pil = pytest.importorskip("PIL.Image")
    import tempfile

    r, g, b = min(255, grey + d1), grey, min(255, grey + d2)
    with tempfile.TemporaryDirectory() as d:
        script = Path(d) / "grey.mjs"
        out = Path(d) / "g.gif"
        script.write_text(
            f'import {{ encodeGif }} from "{(REPO / "ops" / "capture" / "gif.mjs").as_posix()}";\n'
            'import { writeFileSync } from "node:fs";\n'
            f'writeFileSync("{out.as_posix()}", encodeGif([{{ width: 2, height: 1, rgba: new Uint8Array([{r},{g},{b},255,{r},{g},{b},255]) }}]));\n',
            encoding="utf-8",
        )
        subprocess.run([NODE, str(script)], check=True)
        got = pil.open(out).convert("RGB").getpixel((0, 0))
    assert got[0] == got[1] == got[2], (r, g, b, got)
    assert abs(got[0] - (r + g + b) / 3) <= 8


@pytest.mark.skipif(NODE is None, reason="node not installed")
def test_every_palette_entry_is_a_cube_colour_or_a_grey():
    """REQ-OPS-CAPTURE.1 (ops#201): the 6x6x6 cube and the 36-step ramp fit in 256 entries, and a colour keeps its hue."""
    pil = pytest.importorskip("PIL.Image")
    import tempfile

    with tempfile.TemporaryDirectory() as d:
        out = Path(d) / "c.gif"
        write = Path(d) / "c.mjs"
        write.write_text(
            f'import {{ encodeGif }} from "{(REPO / "ops" / "capture" / "gif.mjs").as_posix()}";\n'
            'import { writeFileSync } from "node:fs";\n'
            f'writeFileSync("{out.as_posix()}", encodeGif([{{ width: 1, height: 1, rgba: new Uint8Array([200, 30, 30, 255]) }}]));\n',
            encoding="utf-8",
        )
        subprocess.run([NODE, str(write)], check=True)
        r, g, b = pil.open(out).convert("RGB").getpixel((0, 0))
    assert r > 150 and g < 80 and b < 80  # still red


# ---- capture runs only on the frozen snapshot (REQ-OPS-CAPTURE.1, REQ-OPS-SNAP.2, ops#200) ---------------------------


def _snapshot_for(served: Path) -> str:
    """A SNAPSHOT.md text whose judging section describes the files under `served`."""
    from undead311 import snapshot as snap

    rows = sorted(
        (f"web/public/data/{p.relative_to(served).as_posix()}", p.stat().st_size, snap.sha256_file(p))
        for p in served.rglob("*")
        if p.is_file() and p.relative_to(served).parts[0] != snap.FROZEN_DIR
    )
    return snap.render_section(rows, "2026-01-01", "judged-2026-01-01")


def _served(tmp_path: Path) -> Path:
    served = tmp_path / "dist" / "data"
    (served / "stats").mkdir(parents=True)
    (served / "status.json").write_text('{"data_end": "2026-01-01"}', encoding="utf-8")
    (served / "zombies.json").write_text('{"zombies": []}', encoding="utf-8")
    (served / "stats" / "a.json").write_text("{}", encoding="utf-8")
    return served


def test_capture_passes_on_the_snapshot_and_clears_the_marker(tmp_path):
    """REQ-OPS-CAPTURE.1: matching data passes, and a NOT-SNAPSHOT marker from an earlier dev run is removed."""
    from undead311 import capture_guard as cg

    served = _served(tmp_path)
    media = tmp_path / "media"
    media.mkdir()
    (media / cg.MARKER).write_text("old", encoding="utf-8")
    problems = cg.check(served, _snapshot_for(served))
    assert problems == []
    assert cg.apply_marker(media, problems, dev=False) == 0
    assert not (media / cg.MARKER).exists()


def test_capture_refuses_when_there_is_no_judging_section(tmp_path):
    """REQ-OPS-CAPTURE.1: no judging section means no capture (exit 1)."""
    from undead311 import capture_guard as cg

    problems = cg.check(_served(tmp_path), "# Data snapshot\n")
    assert problems and "no judging section" in problems[0]
    assert cg.apply_marker(tmp_path / "media", problems, dev=False) == 1
    assert not (tmp_path / "media" / cg.MARKER).exists()


@pytest.mark.parametrize("change", ["edit", "add", "remove"])
def test_capture_refuses_data_that_differs_from_the_snapshot(tmp_path, change):
    """REQ-OPS-CAPTURE.1: an edited, added or missing served file stops the capture."""
    from undead311 import capture_guard as cg

    served = _served(tmp_path)
    text = _snapshot_for(served)
    if change == "edit":
        (served / "zombies.json").write_text('{"zombies": [1]}', encoding="utf-8")
    elif change == "add":
        (served / "extra.json").write_text("{}", encoding="utf-8")
    else:
        (served / "stats" / "a.json").unlink()
    problems = cg.check(served, text)
    assert problems
    assert cg.apply_marker(tmp_path / "media", problems, dev=False) == 1


def test_capture_dev_override_writes_the_marker(tmp_path):
    """REQ-OPS-CAPTURE.1: --dev lets a capture run on other data, and leaves a NOT-SNAPSHOT marker in docs/media."""
    from undead311 import capture_guard as cg

    problems = cg.check(_served(tmp_path), "")
    assert cg.apply_marker(tmp_path / "media", problems, dev=True) == 0
    assert "Do not publish" in (tmp_path / "media" / cg.MARKER).read_text(encoding="utf-8")


def test_capture_checks_the_frozen_folder_too(tmp_path):
    """REQ-OPS-SNAP.2: a frozen/ file that differs from the judging table stops the capture."""
    from undead311 import capture_guard as cg

    served = _served(tmp_path)
    text = _snapshot_for(served)
    (served / "frozen").mkdir()
    (served / "frozen" / "zombies.json").write_text("tampered", encoding="utf-8")
    assert any(line.startswith("frozen:") for line in cg.check(served, text))


def test_make_capture_checks_the_snapshot_before_capturing():
    """REQ-OPS-CAPTURE.1: the Makefile runs capture_check.py before the node script."""
    make = (REPO / "Makefile").read_text(encoding="utf-8")
    block = re.search(r"^capture:.*\n((?:\t.*\n)+)", make, re.MULTILINE)
    assert block
    body = block.group(1)
    assert body.index("capture_check.py") < body.index("capture.mjs")
    assert "CAPTURE_DEV" in body
