"""Assembles PNG frames into one looping GIF with a single adaptive palette (colours stay close to the design palette).

Usage: python assemble_gif.py OUT.gif WIDTH FRAME_MS LAST_MS FRAME1.png FRAME2.png ...
Needs Pillow (`pip install pillow`); used only by ops/capture/live.mjs, not by the pipeline or the web build.
"""
import sys

from PIL import Image


def main(argv: list[str]) -> None:
    out, width, frame_ms, last_ms, *paths = argv
    width, frame_ms, last_ms = int(width), int(frame_ms), int(last_ms)
    frames = []
    for p in paths:
        im = Image.open(p).convert("RGB")
        h = round(im.height * width / im.width)
        frames.append(im.resize((width, h), Image.LANCZOS))
    # one palette for the whole clip, from a sample of its frames, so colours do not flicker between frames
    step = max(1, len(frames) // 8)
    sample = frames[::step]
    sheet = Image.new("RGB", (width, frames[0].height * len(sample)))
    for i, f in enumerate(sample):
        sheet.paste(f, (0, i * f.height))
    pal = sheet.quantize(256, method=Image.Quantize.MEDIANCUT, dither=Image.Dither.NONE)
    q = [f.quantize(palette=pal, dither=Image.Dither.NONE) for f in frames]
    durations = [frame_ms] * (len(q) - 1) + [last_ms]
    q[0].save(out, save_all=True, append_images=q[1:], duration=durations, loop=0, optimize=False, disposal=1)


if __name__ == "__main__":
    main(sys.argv[1:])
