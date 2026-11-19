"""Builds pipeline/undead311/ingest/first_names.txt: the top 2,000 US first names (REQ-ING-PII.7).

Source: US Social Security Administration, "Baby Names from Social Security Card Applications - National Data"
(https://www.ssa.gov/oact/babynames/limits.html, public domain US government data). www.ssa.gov refuses automated
downloads from the sandbox, so the script reads the verbatim yobYYYY.txt rows as merged by
https://github.com/hackerb9/ssa-baby-names (alldata.txt: name,sex,count,year; covers 1880-2020).
Ranking: births from 1950 through 2000 (the working-age adults who write closure notes in 2015-2026), both sexes
summed per name, top 2,000 by total count. Names shorter than 3 letters are skipped.

Usage: python pipeline/scripts/build_first_names.py alldata.txt
"""

from __future__ import annotations

import sys
from collections import Counter
from pathlib import Path

FIRST_YEAR, LAST_YEAR, TOP_N, MIN_LEN = 1950, 2000, 2000, 3
OUT = Path(__file__).resolve().parents[1] / "undead311" / "ingest" / "first_names.txt"
SOURCE_URL = "https://www.ssa.gov/oact/babynames/limits.html"


def build(rows: list[str]) -> list[str]:
    totals: Counter[str] = Counter()
    for line in rows:
        name, _sex, count, year = line.strip().split(",")
        if FIRST_YEAR <= int(year) <= LAST_YEAR and len(name) >= MIN_LEN:
            totals[name.lower()] += int(count)
    return [n for n, _ in sorted(totals.items(), key=lambda kv: (-kv[1], kv[0]))[:TOP_N]]


def main(path: str) -> None:
    names = build(Path(path).read_text(encoding="utf-8").splitlines())
    header = (
        f"# Top {TOP_N} US first names, births {FIRST_YEAR}-{LAST_YEAR}, both sexes, most common first.\n"
        f"# Source: US Social Security Administration, Baby Names from Social Security Card Applications, National Data\n"
        f"# ({SOURCE_URL}); public domain. Rows read from the hackerb9/ssa-baby-names mirror of yobYYYY.txt.\n"
        "# Built by pipeline/scripts/build_first_names.py (REQ-ING-PII.7). One lower-case name per line.\n"
    )
    OUT.write_text(header + "\n".join(names) + "\n", encoding="utf-8")
    print(f"wrote {len(names)} names to {OUT}")


if __name__ == "__main__":
    main(sys.argv[1])
