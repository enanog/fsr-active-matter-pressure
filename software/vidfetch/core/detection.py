"""Robot detection with trackpy.

Coin-cell robots appear as a bright disc (battery) inside a dark ring (PCB). The battery is not a
uniform blob (metal tab, specular glints), so feeding the raw frame to trackpy biases centroids and
picks up background clutter. The default 'ring' method first builds a matched-filter map
    R(x, y) = (mean_disc - mean_ring) * clip((G_max - mean_ring) / G_max, 0, 1)
which is high only where a bright disc is surrounded by an absolutely dark ring, then runs
trackpy.locate on R. Candidates are finally validated by the angular coverage of the dark ring:
gaps between robots are enclosed by neighbours' rings only partially (coverage ~0.6-0.8),
whereas a real robot ring is closed (coverage > 0.9).
"""
from __future__ import annotations

import warnings
from dataclasses import dataclass
from typing import Optional

import cv2
import numpy as np
import pandas as pd

try:
    import trackpy as tp
    tp.quiet()
    TRACKPY_ERROR: Optional[str] = None
except ImportError as _exc:  # keep the GUI usable without trackpy
    tp = None
    TRACKPY_ERROR = f"trackpy no está instalado ({_exc}). Ejecutar: pip install trackpy"

METHOD_RING = "ring"
METHOD_DIRECT = "direct"

COLUMNS = ["x", "y", "mass", "size", "ecc", "signal", "ring_cov"]


@dataclass(frozen=True)
class DetectionParams:
    enabled: bool = False
    method: str = METHOD_RING
    r_in: float = 36.0           # bright disc radius [px, input resolution]
    r_out: float = 48.0          # outer radius of the dark ring [px]
    scale: float = 0.5           # analysis downscale factor (speed)
    ring_gray_max: float = 110.0  # ring mean above this -> response suppressed
    separation: float = 72.0     # min distance between centres [px]
    minmass: float = 0.0         # trackpy minmass (on the analysed map)
    invert: bool = False         # direct method only: dark features on bright background
    validate_ring: bool = True
    ring_pixel_dark: float = 70.0  # pixel counts as 'dark ring' below this gray level
    min_coverage: float = 0.82     # min angular fraction of closed dark ring

    def trackpy_diameter(self) -> int:
        # Ring map peaks are ~0.7*disc wide; direct mode uses the full disc. Must be odd.
        d = (1.4 if self.method == METHOD_RING else 2.0) * self.r_in * self.scale
        return max(3, int(round(d)) | 1)


def _to_gray(frame: np.ndarray) -> np.ndarray:
    if frame.ndim == 2:
        g = frame
    elif frame.shape[2] == 4:
        g = cv2.cvtColor(frame, cv2.COLOR_BGRA2GRAY)
    else:
        g = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    return g if g.dtype == np.uint8 else np.clip(g, 0, 255).astype(np.uint8)


def _disc_ring_kernels(r_in: float, r_out: float) -> tuple[np.ndarray, np.ndarray]:
    R = int(np.ceil(r_out))
    yy, xx = np.mgrid[-R:R + 1, -R:R + 1]
    rr = np.hypot(xx, yy)
    disc = (rr <= r_in).astype(np.float32)
    ring = ((rr > r_in) & (rr <= r_out)).astype(np.float32)
    if disc.sum() == 0 or ring.sum() == 0:
        raise ValueError("Radios inválidos: se requiere r_ext > r_int ≥ 1 px (tras escalar).")
    return disc / disc.sum(), ring / ring.sum()


def robot_response(gray: np.ndarray, p: DetectionParams) -> np.ndarray:
    """Matched-filter map (uint8) at analysis scale."""
    ki, kr = _disc_ring_kernels(p.r_in * p.scale, p.r_out * p.scale)
    g = gray.astype(np.float32)
    m_disc = cv2.filter2D(g, -1, ki, borderType=cv2.BORDER_REFLECT)
    m_ring = cv2.filter2D(g, -1, kr, borderType=cv2.BORDER_REFLECT)
    gate = np.clip((p.ring_gray_max - m_ring) / max(p.ring_gray_max, 1e-6), 0.0, 1.0)
    return np.clip((m_disc - m_ring) * gate, 0, 255).astype(np.uint8)


def ring_coverage(gray: np.ndarray, x: float, y: float, r0: float, r1: float, dark: float) -> float:
    """Fraction of 360 rays whose darkest pixel in the band [r0, r1) is below `dark`."""
    r1i, r0i = int(np.ceil(r1)), int(max(0, np.floor(r0)))
    if r1i <= r0i:
        return 0.0
    pol = cv2.warpPolar(gray, (r1i + 1, 360), (float(x), float(y)), r1i + 1, cv2.WARP_POLAR_LINEAR)
    return float((pol[:, r0i:r1i].min(axis=1) < dark).mean())


def empty_result() -> pd.DataFrame:
    return pd.DataFrame({c: pd.Series(dtype=float) for c in COLUMNS})


def locate(frame: np.ndarray, p: DetectionParams) -> pd.DataFrame:
    """Detect robots in one frame. Coordinates are in `frame` pixels."""
    if tp is None:
        raise RuntimeError(TRACKPY_ERROR)
    if not (0.05 <= p.scale <= 1.0):
        raise ValueError("La escala de análisis debe estar entre 0.05 y 1.")
    if p.r_out <= p.r_in:
        raise ValueError("El radio exterior debe ser mayor que el radio del disco.")

    gray = _to_gray(frame)
    small = gray if p.scale == 1.0 else cv2.resize(gray, None, fx=p.scale, fy=p.scale,
                                                   interpolation=cv2.INTER_AREA)
    if p.method == METHOD_RING:
        img, invert = robot_response(small, p), False
    else:
        img, invert = small, p.invert

    with warnings.catch_warnings():
        warnings.simplefilter("ignore")  # trackpy emits UserWarnings on empty/odd images
        f = tp.locate(img, p.trackpy_diameter(), minmass=p.minmass,
                      separation=max(1.0, p.separation * p.scale), invert=invert)
    if f is None or len(f) == 0:
        return empty_result()

    f = f.copy()
    f["x"] = f["x"] / p.scale
    f["y"] = f["y"] / p.scale
    if p.validate_ring:
        # Stay inside the ring, away from both edges (margin scales with ring width; 2 px at 4K).
        m = max(0.5, 0.17 * (p.r_out - p.r_in))
        r0, r1 = p.r_in + m, max(p.r_in + m + 1.0, p.r_out - m)
        f["ring_cov"] = [ring_coverage(gray, x, y, r0, r1, p.ring_pixel_dark)
                         for x, y in zip(f["x"], f["y"])]
        f = f[f["ring_cov"] >= p.min_coverage]
    else:
        f["ring_cov"] = np.nan
    for c in COLUMNS:
        if c not in f.columns:
            f[c] = np.nan
    return f[COLUMNS].reset_index(drop=True)


def draw(frame: np.ndarray, df: pd.DataFrame, p: DetectionParams) -> np.ndarray:
    """Return a BGR copy of `frame` with detections overlaid."""
    out = cv2.cvtColor(frame, cv2.COLOR_GRAY2BGR) if frame.ndim == 2 else frame.copy()
    h, w = out.shape[:2]
    th = max(2, int(round(min(h, w) / 400)))
    r = int(round(p.r_out))
    for x, y in zip(df["x"], df["y"]):
        if not (np.isfinite(x) and np.isfinite(y)):
            continue
        c = (int(round(x)), int(round(y)))
        cv2.circle(out, c, r, (0, 255, 0), th, cv2.LINE_AA)
        cv2.circle(out, c, th + 1, (0, 0, 255), -1, cv2.LINE_AA)
    label = f"N = {len(df)}"
    fs = max(0.6, min(h, w) / 700)
    cv2.putText(out, label, (10, int(30 * fs)), cv2.FONT_HERSHEY_SIMPLEX, fs, (0, 0, 0), th + 3, cv2.LINE_AA)
    cv2.putText(out, label, (10, int(30 * fs)), cv2.FONT_HERSHEY_SIMPLEX, fs, (0, 255, 255), th, cv2.LINE_AA)
    return out


def link_tracks(df: pd.DataFrame, search_range: float, memory: int, min_length: int = 0) -> pd.DataFrame:
    """Link per-frame detections into trajectories ('particle' column, renumbered 0..N-1).

    Tracks shorter than `min_length` frames are removed with trackpy.filter_stubs: transient
    false positives (gaps between robots) live a few frames; real robots persist.
    """
    if tp is None:
        raise RuntimeError(TRACKPY_ERROR)
    if df.empty:
        out = df.copy()
        out["particle"] = pd.Series(dtype=int)
        return out
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        linked = tp.link(df, search_range=search_range, memory=int(memory))
        if min_length > 1:
            linked = tp.filter_stubs(linked, int(min_length))
    linked = linked.reset_index(drop=True)
    order = linked.groupby("particle")["frame"].min().sort_values(kind="stable").index
    linked["particle"] = linked["particle"].map({old: new for new, old in enumerate(order)})
    return linked
