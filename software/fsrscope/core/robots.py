"""Robot trajectories exported by VidFetch (VP_<code>_robots.csv): video overlay, mobility plots
and occupancy maps.

Split recordings (VP_<code>(1)_robots.csv, VP_<code>(2)_robots.csv, ...) are joined on one frame
axis using the gap measured in datos/video/cortes.json (medir_corte.py); the frames inside the gap
are NaN, so every array stays contiguous in frame number (row i <-> frame frames[0] + i).
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import numpy as np
import pandas as pd

# speed_mm_s: VidFetch >= 2026-10-08 (enclosure frame); speed_m_s: older exports.
REQUIRED = ["frame", "particle", "x_video_px", "y_video_px"]
SPEED_COLS = {"speed_mm_s": 1.0, "speed_m_s": 1e3}
OPTIONAL = ["x_mm", "y_mm", "r_mm", "status", "omega_rad_s", "omega_deg_s"]
OBSERVED = {"detectado", "detectado (umbral relajado)", "manual"}
PART_RE = re.compile(r"^(VP_.+)\((\d+)\)_robots$")
DEFAULT_FR_SPLIT = 30000 / 1001 / 10       # DJI time-lapse, used only if cortes.json has no f_r
DEFAULT_D_MM = 33.0


@dataclass
class Robots:
    path: Path
    frames: np.ndarray       # contiguous video frame numbers (gaps of split videos are NaN rows)
    x: np.ndarray            # (n_frames, n_robots) video pixel coords (as in the video file)
    y: np.ndarray
    speed_mm_s: np.ndarray   # (n_frames, n_robots)
    v_median: np.ndarray     # per frame [mm/s]
    v_p90: np.ndarray
    v_mean: np.ndarray       # per frame, mean over robots [mm/s]
    x_mm: Optional[np.ndarray] = None   # enclosure frame (origin at the centre, y up, observer view)
    y_mm: Optional[np.ndarray] = None
    observed: Optional[np.ndarray] = None   # bool (n_frames, n_robots): detected/manual, not interpolated
    omega_rad_s: Optional[np.ndarray] = None  # (n_frames, n_robots) spin about each robot's own axis
    r_int_mm: float = np.nan     # enclosure inner radius [mm] (from _info.json)
    diameter_mm: float = DEFAULT_D_MM
    parts: tuple = ()        # source files (one unless the recording was split)
    gap_frames: int = 0      # frames inside the gap(s) of a split recording

    @property
    def n_robots(self) -> int:
        return self.x.shape[1]

    @property
    def has_positions(self) -> bool:
        return self.x_mm is not None and self.y_mm is not None

    def row_of(self, frame: int) -> int:
        """Row of the given frame, or -1 if it has no data."""
        i = int(frame - self.frames[0]) if len(self.frames) else -1
        if 0 <= i < len(self.frames) and np.isfinite(self.x[i]).any():
            return i
        return -1

    def collective(self, stat: str) -> np.ndarray:
        """Per-frame statistic over the robots: 'media' | 'mediana' | 'p90'."""
        return {"media": self.v_mean, "mediana": self.v_median, "p90": self.v_p90}.get(stat, self.v_mean)


def part_paths(path: Path) -> list[Path]:
    """All parts of a split recording given any one of them (or [path] if not split)."""
    m = PART_RE.match(path.stem)
    if not m:
        return [path]
    found = [(int(mm.group(2)), p) for p in path.parent.glob(f"{m.group(1)}(*)_robots.csv")
             if (mm := PART_RE.match(p.stem)) and mm.group(1) == m.group(1)]
    return [p for _, p in sorted(found)] or [path]


def _read_one(path: Path) -> dict:
    d = pd.read_csv(path, usecols=lambda c: c in REQUIRED or c in SPEED_COLS or c in OPTIONAL)
    speed_col = next((c for c in SPEED_COLS if c in d.columns), None)
    missing = set(REQUIRED) - set(d.columns)
    if missing or speed_col is None:
        raise ValueError(f"'{path.name}': faltan columnas "
                         f"{sorted(missing | ({'speed_mm_s'} if speed_col is None else set()))}")
    d = d.dropna(subset=["frame", "particle"])
    d["frame"] = d["frame"].astype(int)
    d["particle"] = d["particle"].astype(int)
    d = d.drop_duplicates(["frame", "particle"])
    frames = np.arange(d["frame"].min(), d["frame"].max() + 1)
    robots = np.sort(d["particle"].unique())

    def wide(col: str, scale: float = 1.0) -> np.ndarray:
        w = d.pivot(index="frame", columns="particle", values=col).reindex(index=frames, columns=robots)
        return pd.DataFrame(w).apply(pd.to_numeric, errors="coerce").to_numpy(float) * scale

    out = {"frames": frames, "x": wide("x_video_px"), "y": wide("y_video_px"),
           "v": wide(speed_col, SPEED_COLS[speed_col])}
    if {"x_mm", "y_mm"} <= set(d.columns):
        out["x_mm"], out["y_mm"] = wide("x_mm"), wide("y_mm")
    if "omega_rad_s" in d.columns:
        out["w"] = wide("omega_rad_s")
    elif "omega_deg_s" in d.columns:
        out["w"] = wide("omega_deg_s", np.pi / 180.0)
    if "status" in d.columns:
        st = d.pivot(index="frame", columns="particle", values="status").reindex(index=frames, columns=robots)
        out["obs"] = st.isin(OBSERVED).to_numpy()
    return out


def _info(path: Path) -> dict:
    p = path.with_name(path.stem + "_info.json")
    try:
        return json.loads(p.read_text(encoding="utf-8")) if p.is_file() else {}
    except (OSError, ValueError):
        return {}


def _cuts(path: Path) -> dict:
    """datos/video/cortes.json next to the trajectories folder (trayectorias/../cortes.json)."""
    p = path.parent.parent / "cortes.json"
    try:
        return json.loads(p.read_text(encoding="utf-8")) if p.is_file() else {}
    except (OSError, ValueError):
        return {}


def _match_identities(a: np.ndarray, b: np.ndarray) -> np.ndarray:
    """Permutation of the columns of the next part that continues each robot of the previous one
    (minimum total displacement across the cut). Identity when positions are missing."""
    n = a.shape[0]
    if not (np.isfinite(a).all() and np.isfinite(b).all()) or b.shape[0] != n:
        return np.arange(b.shape[0])
    cost = np.linalg.norm(a[:, None, :] - b[None, :, :], axis=2)
    try:
        from scipy.optimize import linear_sum_assignment
        _, perm = linear_sum_assignment(cost)
        return perm
    except ImportError:   # greedy fallback (robots barely move across the cut)
        perm, free = np.full(n, -1), set(range(n))
        for i in np.argsort(cost.min(1)):
            j = min(free, key=lambda k: cost[i, k])
            perm[i] = j
            free.discard(j)
        return perm


def load_robots(path: Path) -> Robots:
    files = part_paths(path)
    parts = [_read_one(p) for p in files]
    gap_total = 0
    if len(parts) > 1:
        code = PART_RE.match(files[0].stem).group(1)[3:]          # strip 'VP_'
        cut = _cuts(files[0]).get(code, {})
        gaps = list(cut.get("hueco_s") or [])
        fr = float(cut.get("fr") or DEFAULT_FR_SPLIT)
        if len(gaps) < len(parts) - 1:
            raise ValueError(f"'{code}' está partido en {len(parts)} partes y no figura en cortes.json "
                             f"(correr software/analisis_video/medir_corte.py).")
        joined = parts[0]
        keys = [k for k in ("x", "y", "v", "x_mm", "y_mm", "obs", "w") if all(k in p for p in parts)]
        for q, gap in zip(parts[1:], gaps):
            ref = "x_mm" if "x_mm" in keys else "x"
            refy = "y_mm" if ref == "x_mm" else "y"
            last = np.column_stack([joined[ref][-1], joined[refy][-1]])
            first = np.column_stack([q[ref][0], q[refy][0]])
            perm = _match_identities(last, first)
            nmiss = max(int(round(gap * fr)) - 1, 0)
            gap_total += nmiss
            n_rob = joined["x"].shape[1]
            for k in keys:
                fill = np.zeros((nmiss, n_rob), bool) if k == "obs" else np.full((nmiss, n_rob), np.nan)
                joined[k] = np.vstack([joined[k], fill, q[k][:, perm]])
            joined["frames"] = np.arange(joined["frames"][0], joined["frames"][0] + len(joined["x"]))
        for k in [k for k in ("x_mm", "y_mm", "obs", "w") if k not in keys]:
            joined.pop(k, None)
        data = joined
    else:
        data = parts[0]

    vv = data["v"]
    with np.errstate(all="ignore"):
        import warnings
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", category=RuntimeWarning)
            v_med = np.nanmedian(vv, axis=1)
            v_p90 = np.nanpercentile(vv, 90, axis=1)
            v_mean = np.nanmean(vv, axis=1)
    info = _info(files[0])
    rec = info.get("recinto") or {}
    r_int = float(rec["d_int_mm"]) / 2 if rec.get("d_int_mm") else np.nan
    return Robots(files[0], data["frames"], data["x"], data["y"], vv, v_med, v_p90, v_mean,
                  data.get("x_mm"), data.get("y_mm"), data.get("obs"), data.get("w"), r_int,
                  float(info.get("diametro_robot_mm") or DEFAULT_D_MM), tuple(files), gap_total)
