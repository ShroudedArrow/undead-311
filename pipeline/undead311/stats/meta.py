"""Header fields every stats file carries beside `data_version`: `params` and `seed` (design "Data models").

`seed` is null when nothing in the file is resampled (REQ-STAT-EXP.1, REQ-STAT-EXP.2).
"""

from __future__ import annotations

from undead311.detect.params import Params


def params_json(params: Params) -> dict:
    """The detector parameters a stats file depends on."""
    return {"WINDOW_DAYS": params.WINDOW_DAYS, "RADIUS_M": params.RADIUS_M, "matching": params.matching}
