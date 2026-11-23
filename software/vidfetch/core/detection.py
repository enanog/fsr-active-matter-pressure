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
METHOD_EDGE = "edge"      # battery edge: circle of strongest bright -> dark radial step (robust median)

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
    led_as_ring: bool = True       # saturated bright pixels (robot LEDs) count as dark ring in the coverage
    edge_min: float = 15.0         # METHOD_EDGE: min battery-edge contrast [gray levels]; ring_cov = score / (1.6 edge_min)

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


def led_mask(frame: np.ndarray) -> Optional[np.ndarray]:
    """Saturated, bright pixels that are not the teal enclosure wall: the robots' LEDs (red, blue, magenta)
    and the gold battery rims. They sit on a robot's PCB ring, so for the coverage test they are ring."""
    if frame.ndim != 3 or frame.shape[2] < 3:
        return None
    hsv = cv2.cvtColor(np.ascontiguousarray(frame[..., :3]), cv2.COLOR_BGR2HSV)
    h, s, v = hsv[..., 0], hsv[..., 1], hsv[..., 2]
    teal = (h >= 75) & (h <= 100)
    return (s > 110) & (v > 110) & ~teal


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
    if p.method == METHOD_EDGE:
        return locate_edge(gray, p)
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
        g_cov = gray
        led = led_mask(frame) if p.led_as_ring else None
        if led is not None and led.any():
            g_cov = gray.copy()
            g_cov[led] = 0
        f["ring_cov"] = [ring_coverage(g_cov, x, y, r0, r1, p.ring_pixel_dark)
                         for x, y in zip(f["x"], f["y"])]
        f = f[f["ring_cov"] >= p.min_coverage]
    else:
        f["ring_cov"] = np.nan
    for c in COLUMNS:
        if c not in f.columns:
            f[c] = np.nan
    return f[COLUMNS].reset_index(drop=True)


# --------------------------------------------------------------------------- battery-edge detector
# The battery (silver or gold coin cell) is a bright disc on the dark PCB. Its edge is a circle of radius
# ~0.66-0.84 r_out whose centre is the robot centre seen from above. Stage 1 finds candidates with a linear
# ring-difference filter (fast, mean contrast). Stage 2 refines each one on the full-resolution image by
# maximising a *quantile* (q = 0.4) of the inner-minus-outer contrast over angles: tabs, holes and LEDs that
# cross the edge cover < 60 % of the angles and do not move the centre. Gaps between robots have no battery
# inside: their score stays below ~11 gray levels, robots score 24-100 (measured on 20AL, Nov 2026).
EDGE_R_FRAC = (0.66, 0.84)   # battery radius / r_out
EDGE_DR_FRAC = 0.05          # half-width of the inner/outer sampling rings / r_out
EDGE_Q = 0.4


def _ring_kernel(r: float, dr: float, w: float) -> np.ndarray:
    R = int(np.ceil(r + dr + 3 * w))
    yy, xx = np.mgrid[-R:R + 1, -R:R + 1]
    d = np.hypot(xx, yy)
    inner = np.exp(-0.5 * ((d - (r - dr)) / w) ** 2)
    outer = np.exp(-0.5 * ((d - (r + dr)) / w) ** 2)
    return (inner / inner.sum() - outer / outer.sum()).astype(np.float32)


def _edge_scores(g: np.ndarray, cx: float, cy: float, offs: np.ndarray, radii: np.ndarray,
                 n_ang: int, dr: float, q: float = EDGE_Q) -> np.ndarray:
    """(len(offs), len(radii)) q-quantile over angles of I(r - dr) - I(r + dr)."""
    th = np.arange(n_ang) * (2 * np.pi / n_ang)
    ct, st = np.cos(th), np.sin(th)
    x0 = (cx + offs[:, 0])[:, None, None]
    y0 = (cy + offs[:, 1])[:, None, None]
    rr = radii[None, :, None]
    shape = (len(offs) * len(radii), n_ang)
    xi = (x0 + (rr - dr) * ct).astype(np.float32).reshape(shape)
    yi = (y0 + (rr - dr) * st).astype(np.float32).reshape(shape)
    xo = (x0 + (rr + dr) * ct).astype(np.float32).reshape(shape)
    yo = (y0 + (rr + dr) * st).astype(np.float32).reshape(shape)
    c = (cv2.remap(g, xi, yi, cv2.INTER_LINEAR, borderMode=cv2.BORDER_REPLICATE)
         - cv2.remap(g, xo, yo, cv2.INTER_LINEAR, borderMode=cv2.BORDER_REPLICATE))
    k = int(q * (n_ang - 1))
    return np.partition(c, k, axis=1)[:, k].reshape(len(offs), len(radii))


def _grid(half: float, step: float) -> np.ndarray:
    s = np.arange(-half, half + 1e-6, step, dtype=np.float32)
    return np.stack(np.meshgrid(s, s), axis=-1).reshape(-1, 2)


def refine_edge(g: np.ndarray, x: float, y: float, r_out: float, search: float = 3.0,
                q: float = EDGE_Q) -> tuple:
    """Sub-pixel centre (x, y), battery radius and edge score near (x, y). g: smoothed float32 gray.

    A higher q (e.g. 0.6) still finds a battery whose edge is visible on only part of its rim (dull
    battery, shadow); use it only near a known robot position, it also lets some gaps through."""
    lo, hi = EDGE_R_FRAC[0] * r_out, EDGE_R_FRAC[1] * r_out
    dr = max(1.0, EDGE_DR_FRAC * r_out)
    st = max(0.5, r_out / 50.0)                       # 1 px at r_out = 50 px
    offs = _grid(search, st)
    radii = np.arange(lo, hi + 1e-6, st, dtype=np.float32)
    S = _edge_scores(g, x, y, offs, radii, 64, dr, q)
    i, j = np.unravel_index(int(S.argmax()), S.shape)
    cx, cy, r = x + float(offs[i, 0]), y + float(offs[i, 1]), float(radii[j])
    offs = _grid(1.2 * st, 0.2 * st)
    radii = np.arange(r - st, r + st + 1e-6, 0.25 * st, dtype=np.float32)
    S = _edge_scores(g, cx, cy, offs, radii, 96, dr, q)
    i, j = np.unravel_index(int(S.argmax()), S.shape)
    return cx + float(offs[i, 0]), cy + float(offs[i, 1]), float(radii[j]), float(S[i, j])


def locate_edge(gray: np.ndarray, p: DetectionParams) -> pd.DataFrame:
    g = cv2.GaussianBlur(gray.astype(np.float32), (0, 0), max(0.6, p.r_out / 50.0))
    sc = float(np.clip(p.scale, 0.2, 1.0))
    gs = g if sc == 1.0 else cv2.resize(g, None, fx=sc, fy=sc, interpolation=cv2.INTER_AREA)
    lo, hi = EDGE_R_FRAC[0] * p.r_out, EDGE_R_FRAC[1] * p.r_out
    dr = max(1.0, EDGE_DR_FRAC * p.r_out)
    resp = None
    for r in np.linspace(lo, hi, 4):
        k = _ring_kernel(r * sc, dr * sc, max(0.8, 0.02 * p.r_out * sc))
        m = cv2.filter2D(gs, -1, k, borderType=cv2.BORDER_REPLICATE)
        resp = m if resp is None else np.maximum(resp, m)
    sep = max(2.0, p.separation)
    # Stage-1 peaks closer than sep are kept (window 0.4 sep): on a battery with a bright tab or LED the
    # strongest linear peak can sit ~20 px off-centre and would hide the right one; the final NMS below,
    # after refinement, keeps one detection per robot.
    ks = int(round(0.4 * sep * sc)) | 1
    peaks = (resp >= cv2.dilate(resp, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (ks, ks)))) & (resp > 0.25 * p.edge_min)
    ys, xs = np.nonzero(peaks)
    order = np.argsort(-resp[ys, xs])[:200]
    # score a candidate must reach to be kept (ring_cov = score / (1.6 edge_min) >= min_coverage)
    th0 = (1.6 * p.edge_min * p.min_coverage) if p.validate_ring else -np.inf
    rows = []
    strong: list = []                                  # refined centres that already passed edge_min
    radii0 = np.linspace(lo, hi, 7).astype(np.float32)
    for yv, xv in zip(ys[order], xs[order]):
        x0, y0 = (xv + 0.5) / sc - 0.5, (yv + 0.5) / sc - 0.5
        if any((x0 - a) ** 2 + (y0 - b) ** 2 < (0.2 * sep) ** 2 for a, b in strong):
            continue                                   # same robot, already measured
        # cheap pre-check at the peak itself before the full search
        if _edge_scores(g, x0, y0, _grid(2.0 * max(0.5, p.r_out / 50.0), 2.0 * max(0.5, p.r_out / 50.0)),
                        radii0, 48, dr).max() < th0 * 0.5:
            continue
        x, y, r, s = refine_edge(g, x0, y0, p.r_out)
        rows.append((x, y, s, float(resp[yv, xv]), r))
        if s >= 1.6 * p.edge_min:                      # clearly a battery edge
            strong.append((x, y))
    if not rows:
        return empty_result()
    a = np.array(rows)
    keep = []
    for i in np.argsort(-a[:, 2]):                     # non-maximum suppression after refinement
        if all(np.hypot(a[i, 0] - a[j, 0], a[i, 1] - a[j, 1]) >= sep for j in keep):
            keep.append(i)
    a = a[keep]
    f = pd.DataFrame({"x": a[:, 0], "y": a[:, 1], "mass": a[:, 2], "signal": a[:, 3], "size": a[:, 4]})
    f["ring_cov"] = np.clip(f["mass"] / (1.6 * p.edge_min), 0.0, 1.0)
    if p.validate_ring:
        f = f[f["ring_cov"] >= p.min_coverage]
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
