"""Robot trajectories exported by VidFetch (VP_<code>_robots.csv), for overlay and mobility plots."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd

# speed_mm_s: VidFetch >= 2026-10-08 (enclosure frame); speed_m_s: older exports.
REQUIRED = ["frame", "particle", "x_video_px", "y_video_px"]
SPEED_COLS = {"speed_mm_s": 1.0, "speed_m_s": 1e3}


@dataclass
class Robots:
    path: Path
    frames: np.ndarray       # sorted frame indices present (video frame numbers)
    x: np.ndarray            # (n_frames, n_robots) video pixel coords (as in the video file)
    y: np.ndarray
    speed_mm_s: np.ndarray   # (n_frames, n_robots)
    v_median: np.ndarray     # per frame [mm/s]
    v_p90: np.ndarray

    @property
    def n_robots(self) -> int:
        return self.x.shape[1]

    def row_of(self, frame: int) -> int:
        """Row of the given frame, or -1 if it has no data."""
        i = int(np.searchsorted(self.frames, frame))
        return i if i < len(self.frames) and self.frames[i] == frame else -1


def load_robots(path: Path) -> Robots:
    d = pd.read_csv(path, usecols=lambda c: c in REQUIRED or c in SPEED_COLS)
    missing = set(REQUIRED) - set(d.columns)
    speed_col = next((c for c in SPEED_COLS if c in d.columns), None)
    if missing or speed_col is None:
        raise ValueError(f"'{path.name}': faltan columnas {sorted(missing | ({'speed_mm_s'} if speed_col is None else set()))}")
    d = d.dropna(subset=["frame", "particle"])
    d["frame"] = d["frame"].astype(int)
    d["particle"] = d["particle"].astype(int)

    def wide(col: str) -> pd.DataFrame:
        return d.pivot_table(index="frame", columns="particle", values=col, aggfunc="first")

    x, y = wide("x_video_px"), wide("y_video_px")
    v = wide(speed_col).reindex(index=x.index, columns=x.columns) * SPEED_COLS[speed_col]
    y = y.reindex(index=x.index, columns=x.columns)
    vv = v.to_numpy(dtype=float)
    with np.errstate(all="ignore"):
        v_med = np.nanmedian(vv, axis=1)
        v_p90 = np.nanpercentile(vv, 90, axis=1)
    return Robots(path, x.index.to_numpy(), x.to_numpy(float), y.to_numpy(float), vv, v_med, v_p90)
