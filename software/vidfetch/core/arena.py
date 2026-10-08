"""Circular enclosure ("recinto"): automatic detection, manual fit and the centred reference frame.

Geometry is stored in full-frame video pixels (same coordinates as TrackingResult.x / .y).

Automatic detection (works on the analysed crop):
  1. Temporal median of a few frames spread over the trimmed range: moving robots vanish, the
     static wall stays.
  2. Ring mask: the wall is the dominant saturated hue of the image (teal on this setup). Pixels
     with S >= max(60, Otsu(S)) and hue within +/-HUE_TOL of the dominant hue are kept; red LEDs
     and yellow coin cells have other hues and fall out.
  3. Rays from a provisional centre (720 rays). On each ray the first run of ring pixels gives the
     inner edge and, if the run does not touch the image border or a mounting arm, the outer edge.
     Edges are refined to sub-pixel accuracy on the saturation profile (half-way crossing).
  4. Robust circle fit (algebraic Kasa fit + MAD rejection); centre updated and steps 3-4 repeated.
  If no saturated ring is found, a Hough circle on the gray median is used (flagged unreliable).

Time-resolved geometry (ArenaTrack): in the project's videos the enclosure slides on the plate
(~2-3 mm over the first 30 min) and the camera changes its magnification in steps (~0.5 %, refocus).
The circle is therefore measured every `step` frames, smoothed with a running median (keeps steps,
removes single bad fits) and interpolated to every frame: each robot position is expressed relative
to the centre and with the scale OF ITS OWN FRAME.

What the circles mean: the camera sees the top of the wall. The inner edge of the ring (top
rim) is the reference for the inner diameter D_in; the outer edge, for D_out. The ratio
r_out / r_in measured in pixels must match D_out / D_in: it is reported as a check.
Scale from the enclosure: s = (D_in / 2) / r_in [mm/px]. Perspective (the rim is closer to the
camera than the floor) biases it by ~ h_wall / H_camera (documented in the report).

Reference frame used for every export (real scene, mirror-corrected):
  origin = enclosure centre, x to the right, y upwards (counter-clockwise angles positive).
"""
from __future__ import annotations

import json
import math
from dataclasses import asdict, dataclass, replace
from typing import Callable, Optional, Sequence

import cv2
import numpy as np

from core.models import Roi, TrimRange
from core.video_io import VideoReader

D_IN_MM = 185.0           # inner diameter of the enclosure wall (user data)
D_OUT_MM = 195.0          # outer diameter
N_RAYS = 720
HUE_TOL = 12              # OpenCV hue units (0-179)
MIN_SAT = 60
RAY_STEP = 0.5            # px
MAX_RMS_RELIABLE = 3.0    # px
MIN_COVERAGE_RELIABLE = 0.5
MAX_RATIO_ERR = 0.03      # |r_out/r_in - D_out/D_in| tolerated


@dataclass(frozen=True)
class Arena:
    """Enclosure circle in full-frame video pixels."""

    cx: float
    cy: float
    r_in: float                       # px, inner edge of the wall (top rim)
    r_out: float = float("nan")       # px, outer edge (nan -> not measured)
    d_in_mm: float = D_IN_MM
    d_out_mm: float = D_OUT_MM
    method: str = "auto"              # auto | manual | manual (puntos) | hough
    rms_px: float = float("nan")      # residual of the inner-edge fit
    coverage: float = float("nan")    # fraction of rays where the inner edge was found
    n_frames: int = 0                 # frames used by the temporal median

    # ---- derived
    @property
    def mm_per_px(self) -> float:
        return self.d_in_mm / (2.0 * self.r_in) if self.r_in > 0 else float("nan")

    @property
    def r_in_mm(self) -> float:
        return self.d_in_mm / 2.0

    @property
    def ratio_expected(self) -> float:
        return self.d_out_mm / self.d_in_mm if self.d_in_mm > 0 else float("nan")

    @property
    def ratio_measured(self) -> float:
        return self.r_out / self.r_in if (self.r_in > 0 and np.isfinite(self.r_out)) else float("nan")

    @property
    def r_out_px(self) -> float:
        """Measured outer radius, or the one implied by the diameters."""
        return self.r_out if np.isfinite(self.r_out) else self.r_in * self.ratio_expected

    @property
    def reliable(self) -> bool:
        if self.method.startswith("manual"):
            return True
        ok = (np.isfinite(self.rms_px) and self.rms_px <= MAX_RMS_RELIABLE
              and np.isfinite(self.coverage) and self.coverage >= MIN_COVERAGE_RELIABLE)
        if np.isfinite(self.ratio_measured):
            ok = ok and abs(self.ratio_measured - self.ratio_expected) <= MAX_RATIO_ERR
        return bool(ok)

    def with_diameters(self, d_in_mm: float, d_out_mm: float) -> "Arena":
        return replace(self, d_in_mm=float(d_in_mm), d_out_mm=float(d_out_mm))

    def to_dict(self) -> dict:
        d = asdict(self)
        return {k: (None if isinstance(v, float) and not math.isfinite(v) else v) for k, v in d.items()}

    @staticmethod
    def from_dict(d: dict) -> "Arena":
        known = {f for f in Arena.__dataclass_fields__}
        kw = {k: (float("nan") if v is None and k in ("r_out", "rms_px", "coverage") else v)
              for k, v in d.items() if k in known}
        return Arena(**kw)

    # ---- reference frame
    def to_centered(self, x_video: np.ndarray, y_video: np.ndarray, mirror: str = "no"
                    ) -> tuple[np.ndarray, np.ndarray]:
        """Video px -> px relative to the centre, x right, y UP, in the real (un-mirrored) scene."""
        x = np.asarray(x_video, float) - self.cx
        y = -(np.asarray(y_video, float) - self.cy)
        if mirror == "horizontal":      # image flipped about its vertical axis
            x = -x
        elif mirror == "vertical":      # image flipped about its horizontal axis
            y = -y
        return x, y

    def describe(self) -> str:
        rat = (f" · r_ext/r_int {self.ratio_measured:.4f} (esperado {self.ratio_expected:.4f})"
               if np.isfinite(self.ratio_measured) else "")
        q = (f" · residuo {self.rms_px:.2f} px · cobertura {100 * self.coverage:.0f} %"
             if np.isfinite(self.rms_px) else "")
        warn = "" if self.reliable else " — revisar: detección poco confiable"
        return (f"Centro ({self.cx:.1f}, {self.cy:.1f}) px · r_int {self.r_in:.1f} px · "
                f"escala {self.mm_per_px:.4f} mm/px ({self.method}){rat}{q}{warn}")


# --------------------------------------------------------------------------- circle fitting
def fit_circle(x: np.ndarray, y: np.ndarray) -> tuple[float, float, float]:
    """Algebraic (Kasa) least-squares circle. Needs >= 3 non-collinear points."""
    x, y = np.asarray(x, float), np.asarray(y, float)
    if len(x) < 3:
        raise ValueError("Se necesitan al menos 3 puntos para ajustar un círculo.")
    A = np.column_stack([2 * x, 2 * y, np.ones_like(x)])
    b = x * x + y * y
    (a0, b0, c0), *_ = np.linalg.lstsq(A, b, rcond=None)
    r2 = c0 + a0 * a0 + b0 * b0
    if not np.isfinite(r2) or r2 <= 0:
        raise ValueError("Los puntos no definen un círculo (¿están alineados?).")
    return float(a0), float(b0), float(np.sqrt(r2))


def robust_fit(x: np.ndarray, y: np.ndarray, iters: int = 8, k: float = 2.5
               ) -> tuple[float, float, float, float, np.ndarray]:
    """Kasa fit with MAD outlier rejection. Returns (cx, cy, r, rms of inliers, inlier mask)."""
    x, y = np.asarray(x, float), np.asarray(y, float)
    m = np.ones(len(x), bool)
    cx = cy = r = float("nan")
    for _ in range(iters):
        if m.sum() < 3:
            break
        cx, cy, r = fit_circle(x[m], y[m])
        res = np.hypot(x - cx, y - cy) - r
        med = np.median(res[m])
        mad = 1.4826 * np.median(np.abs(res[m] - med))
        m_new = np.abs(res - med) <= max(k * mad, 0.75)
        if np.array_equal(m_new, m):
            break
        m = m_new
    res = np.hypot(x[m] - cx, y[m] - cy) - r
    return cx, cy, r, float(np.sqrt(np.mean(res ** 2))) if m.any() else float("nan"), m


def fit_points(points: Sequence[tuple[float, float]], d_in_mm: float = D_IN_MM,
               d_out_mm: float = D_OUT_MM) -> Arena:
    """Manual definition: >= 3 clicks on the inner edge of the wall (full-frame px)."""
    p = np.asarray(points, float).reshape(-1, 2)
    cx, cy, r = fit_circle(p[:, 0], p[:, 1])
    rms = float(np.sqrt(np.mean((np.hypot(p[:, 0] - cx, p[:, 1] - cy) - r) ** 2))) if len(p) > 3 else 0.0
    return Arena(cx, cy, r, float("nan"), d_in_mm, d_out_mm, "manual (puntos)", rms, float("nan"), 0)


# --------------------------------------------------------------------------- detection
def median_background(frames: Sequence[np.ndarray]) -> np.ndarray:
    if not frames:
        raise ValueError("No hay cuadros para detectar el recinto.")
    stack = np.stack([f if f.ndim == 3 else cv2.cvtColor(f, cv2.COLOR_GRAY2BGR) for f in frames])
    return np.median(stack, axis=0).astype(np.uint8)


def ring_mask(bgr: np.ndarray) -> tuple[Optional[np.ndarray], np.ndarray, Optional[int]]:
    """(mask of the coloured wall or None, saturation channel, dominant hue)."""
    hsv = cv2.cvtColor(bgr, cv2.COLOR_BGR2HSV)
    h, s, v = cv2.split(hsv)
    otsu, _ = cv2.threshold(s, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    sat = (s >= max(MIN_SAT, float(otsu))) & (v >= 30)
    if sat.mean() < 0.005:
        return None, s, None
    hist = np.bincount(h[sat].ravel(), minlength=180).astype(float)
    hist = np.convolve(np.r_[hist[-HUE_TOL:], hist, hist[:HUE_TOL]], np.ones(2 * HUE_TOL + 1), "valid")
    hue = int(np.argmax(hist))
    dh = np.abs(h.astype(int) - hue)
    dh = np.minimum(dh, 180 - dh)
    mask = sat & (dh <= HUE_TOL)
    mask = cv2.morphologyEx(mask.astype(np.uint8), cv2.MORPH_OPEN, np.ones((3, 3), np.uint8)) > 0
    if mask.mean() < 0.003:
        return None, s, hue
    return mask, s, hue


def _subpixel(prof: np.ndarray, i: int, rising: bool) -> float:
    """Half-way crossing of `prof` around index i (edge between i-1/i if rising, i/i+1 otherwise)."""
    a, b = (i - 1, i) if rising else (i, i + 1)
    if a < 0 or b >= len(prof):
        return float(i)
    lo = float(np.min(prof[max(0, a - 6):a + 1])) if rising else float(np.min(prof[b:b + 7]))
    hi = float(np.max(prof[b:b + 7])) if rising else float(np.max(prof[max(0, a - 6):a + 1]))
    mid = 0.5 * (lo + hi)
    pa, pb = float(prof[a]), float(prof[b])
    if pb == pa:
        return float(i)
    t = float(np.clip((mid - pa) / (pb - pa), 0.0, 1.0))
    return a + t


def _cast(mask: np.ndarray, sat: np.ndarray, cx: float, cy: float, r0: float
          ) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Per-ray inner / outer edge radii (nan where not found)."""
    H, W = mask.shape
    ang = np.linspace(0, 2 * np.pi, N_RAYS, endpoint=False)
    rr = np.arange(0.35 * r0, 1.6 * r0, RAY_STEP)
    px = cx + np.outer(np.cos(ang), rr)
    py = cy + np.outer(np.sin(ang), rr)
    inside = (px >= 0) & (px <= W - 1) & (py >= 0) & (py <= H - 1)
    xi = np.clip(np.round(px).astype(int), 0, W - 1)
    yi = np.clip(np.round(py).astype(int), 0, H - 1)
    m = mask[yi, xi] & inside
    sp = cv2.remap(sat.astype(np.float32), px.astype(np.float32), py.astype(np.float32),
                   cv2.INTER_LINEAR, borderMode=cv2.BORDER_REPLICATE)
    r_in = np.full(N_RAYS, np.nan)
    r_out = np.full(N_RAYS, np.nan)
    max_run = 0.15 * r0 / RAY_STEP           # longer runs = mounting arm or clutter
    for k in range(N_RAYS):
        idx = np.flatnonzero(m[k])
        if len(idx) == 0:
            continue
        i0 = idx[0]
        j = i0
        while j + 1 < len(rr) and m[k, j + 1]:
            j += 1
        if (j - i0) > 4 * max_run:
            continue                          # not a wall crossing
        r_in[k] = rr[0] + _subpixel(sp[k], i0, rising=True) * RAY_STEP
        if j + 1 < len(rr) and inside[k, j + 1] and (j - i0) <= max_run:
            r_out[k] = rr[0] + _subpixel(sp[k], j, rising=False) * RAY_STEP
    return ang, r_in, r_out


def _initial_guess(bgr: np.ndarray, mask: Optional[np.ndarray]) -> tuple[float, float, float]:
    H, W = bgr.shape[:2]
    src = (mask.astype(np.uint8) * 255) if mask is not None else cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY)
    src = cv2.GaussianBlur(src, (9, 9), 2)
    lo, hi = int(0.15 * min(H, W)), int(0.62 * max(H, W))
    circles = cv2.HoughCircles(src, cv2.HOUGH_GRADIENT, dp=2, minDist=max(H, W),
                               param1=100, param2=30, minRadius=lo, maxRadius=hi)
    if circles is not None and len(circles[0]):
        x, y, r = circles[0][0]
        return float(x), float(y), float(r)
    return W / 2.0, H / 2.0, 0.45 * min(H, W)


def detect(frames: Sequence[np.ndarray], offset: tuple[float, float] = (0.0, 0.0),
           d_in_mm: float = D_IN_MM, d_out_mm: float = D_OUT_MM) -> Arena:
    """Detect the enclosure on `frames` (crops of the analysed ROI). `offset` = ROI origin."""
    bg = median_background(frames)
    mask, sat, _ = ring_mask(bg)
    cx, cy, r0 = _initial_guess(bg, mask)
    if mask is None:
        return Arena(cx + offset[0], cy + offset[1], r0, float("nan"), d_in_mm, d_out_mm, "hough",
                     float("nan"), float("nan"), len(frames))
    # The crop is usually centred on the enclosure: start from the image centre if Hough is far off.
    H, W = mask.shape
    if np.hypot(cx - W / 2, cy - H / 2) > 0.25 * min(H, W):
        cx, cy, r0 = W / 2.0, H / 2.0, 0.45 * min(H, W)
    rms = cov = float("nan")
    r_out = float("nan")
    for _ in range(4):
        ang, ri, ro = _cast(mask, sat, cx, cy, r0)
        ok = np.isfinite(ri)
        if ok.sum() < 12:
            break
        x, y = cx + ri[ok] * np.cos(ang[ok]), cy + ri[ok] * np.sin(ang[ok])
        ncx, ncy, nr, rms, inl = robust_fit(x, y)
        cov = float(inl.sum() / N_RAYS)
        okc = np.isfinite(ro)
        if okc.sum() >= 12:
            xo, yo = cx + ro[okc] * np.cos(ang[okc]), cy + ro[okc] * np.sin(ang[okc])
            # Concentric outer edge: only the radius is free (centre from the precise inner edge).
            d = np.hypot(xo - ncx, yo - ncy)
            med = np.median(d)
            mad = 1.4826 * np.median(np.abs(d - med))
            r_out = float(np.median(d[np.abs(d - med) <= max(2.5 * mad, 0.75)]))
        else:
            r_out = float("nan")
        moved = np.hypot(ncx - cx, ncy - cy)
        cx, cy, r0 = ncx, ncy, nr
        if moved < 0.05:
            break
    if not np.isfinite(rms):
        return Arena(cx + offset[0], cy + offset[1], r0, float("nan"), d_in_mm, d_out_mm, "hough",
                     float("nan"), float("nan"), len(frames))
    return Arena(cx + offset[0], cy + offset[1], r0, r_out, d_in_mm, d_out_mm, "auto", rms, cov, len(frames))


def sample_frames(src_path: str, trim: TrimRange, roi: Roi, n: int = 9) -> list[np.ndarray]:
    """Evenly spaced raw crops (no pipeline: colour is needed) from the trimmed range."""
    out: list[np.ndarray] = []
    with VideoReader(src_path) as reader:
        info = reader.info
        trim = trim.clamped(info.frame_count)
        roi = roi.clamped(info.width, info.height)
        for idx in np.unique(np.linspace(trim.start, trim.end, max(1, n)).round().astype(int)):
            frame = reader.read(int(idx))
            if frame is not None:
                out.append(roi.apply(frame).copy())
    if not out:
        raise IOError("No se pudieron leer cuadros para detectar el recinto.")
    return out


def detect_video(src_path: str, trim: TrimRange, roi: Roi, d_in_mm: float = D_IN_MM,
                 d_out_mm: float = D_OUT_MM, n_frames: int = 9,
                 progress: Optional[Callable[[int], None]] = None,
                 should_cancel: Optional[Callable[[], bool]] = None):
    """Worker-friendly wrapper: returns (Arena, cancelled)."""
    frames = sample_frames(src_path, trim, roi, n_frames)
    if progress:
        progress(60)
    if should_cancel and should_cancel():
        return None, True
    a = detect(frames, (roi.x, roi.y), d_in_mm, d_out_mm)
    if progress:
        progress(100)
    return a, False


# --------------------------------------------------------------------------- drawing
def draw(img: np.ndarray, arena: Arena, offset: tuple[float, float] = (0.0, 0.0),
         mirror: str = "no", points: Sequence[tuple[float, float]] = ()) -> np.ndarray:
    """Overlay: inner (solid) and outer (dashed) circles, centre and the exported x/y axes.

    `offset` = ROI origin (img is the crop); `points` = manual clicks in full-frame px.
    The axes are drawn as they map onto the image: with a mirrored recording the real +x points left.
    """
    out = img if img.ndim == 3 else cv2.cvtColor(img, cv2.COLOR_GRAY2BGR)
    out = out.copy()
    th = max(1, int(round(min(out.shape[:2]) / 400)))
    c = (arena.cx - offset[0], arena.cy - offset[1])
    ci = (int(round(c[0])), int(round(c[1])))
    col_in, col_out, col_ax = (0, 255, 255), (255, 160, 0), (255, 255, 255)
    cv2.circle(out, ci, int(round(arena.r_in)), (0, 0, 0), th + 2, cv2.LINE_AA)
    cv2.circle(out, ci, int(round(arena.r_in)), col_in, th, cv2.LINE_AA)
    ro = arena.r_out_px
    for a0 in range(0, 360, 10):
        cv2.ellipse(out, ci, (int(round(ro)), int(round(ro))), 0, a0, a0 + 5, col_out, th, cv2.LINE_AA)
    L = 0.25 * arena.r_in
    sx = -1.0 if mirror == "horizontal" else 1.0
    sy = 1.0 if mirror == "vertical" else -1.0     # image y grows downwards
    for (dx, dy), name in (((sx * L, 0.0), "x"), ((0.0, sy * L), "y")):
        tip = (int(round(c[0] + dx)), int(round(c[1] + dy)))
        cv2.arrowedLine(out, ci, tip, (0, 0, 0), th + 2, cv2.LINE_AA, tipLength=0.15)
        cv2.arrowedLine(out, ci, tip, col_ax, th, cv2.LINE_AA, tipLength=0.15)
        cv2.putText(out, name, (tip[0] + 4, tip[1] - 4), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 0, 0), th + 2,
                    cv2.LINE_AA)
        cv2.putText(out, name, (tip[0] + 4, tip[1] - 4), cv2.FONT_HERSHEY_SIMPLEX, 0.6, col_ax, th, cv2.LINE_AA)
    cv2.drawMarker(out, ci, (0, 0, 255), cv2.MARKER_CROSS, 14, th + 1, cv2.LINE_AA)
    for (px, py) in points:
        p = (int(round(px - offset[0])), int(round(py - offset[1])))
        cv2.circle(out, p, 4, (255, 0, 255), -1, cv2.LINE_AA)
    return out


def save_json(path: str, arena: Optional[Arena], extra: Optional[dict] = None) -> None:
    data = {"recinto": arena.to_dict() if arena is not None else None}
    if arena is not None:
        data["recinto"]["mm_per_px"] = arena.mm_per_px
    data.update(extra or {})
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


# --------------------------------------------------------------------------- time-resolved geometry
DEFAULT_STEP = 15          # frames between enclosure samples (5 s real at 3 frames/s)
SMOOTH_SAMPLES = 5         # running-median window over samples


def fit_concentric(xi: np.ndarray, yi: np.ndarray, xo: np.ndarray, yo: np.ndarray, iters: int = 8,
                   k: float = 2.5) -> tuple[float, float, float, float, float, np.ndarray, np.ndarray]:
    """Two concentric circles (shared centre) fitted to inner and outer edge points, with MAD rejection.

    Returns (cx, cy, r_in, r_out, rms_in, inlier_in, inlier_out). r_out is nan with < 12 outer points.
    """
    use_out = len(xo) >= 12
    mi, mo = np.ones(len(xi), bool), np.ones(len(xo), bool)
    cx = cy = ri = ro = float("nan")
    for _ in range(iters):
        if mi.sum() < 3:
            break
        rows = [np.column_stack([2 * xi[mi], 2 * yi[mi], np.ones(mi.sum()), np.zeros(mi.sum())])]
        rhs = [xi[mi] ** 2 + yi[mi] ** 2]
        if use_out and mo.sum() >= 12:
            rows.append(np.column_stack([2 * xo[mo], 2 * yo[mo], np.zeros(mo.sum()), np.ones(mo.sum())]))
            rhs.append(xo[mo] ** 2 + yo[mo] ** 2)
            A, b = np.vstack(rows), np.concatenate(rhs)
            (cx, cy, ci, co), *_ = np.linalg.lstsq(A, b, rcond=None)
            ro = float(np.sqrt(max(co + cx * cx + cy * cy, 0.0)))
        else:
            (cx, cy, ci), *_ = np.linalg.lstsq(rows[0][:, :3], rhs[0], rcond=None)
            ro = float("nan")
        ri = float(np.sqrt(max(ci + cx * cx + cy * cy, 0.0)))
        changed = False
        for x, y, r, m in ((xi, yi, ri, mi), (xo, yo, ro, mo)):
            if len(x) == 0 or not np.isfinite(r):
                continue
            res = np.hypot(x - cx, y - cy) - r
            med = np.median(res[m]) if m.any() else 0.0
            mad = 1.4826 * np.median(np.abs(res[m] - med)) if m.any() else 0.0
            new = np.abs(res - med) <= max(k * mad, 0.75)
            changed |= not np.array_equal(new, m)
            m[:] = new
        if not changed:
            break
    res_in = np.hypot(xi[mi] - cx, yi[mi] - cy) - ri
    rms = float(np.sqrt(np.mean(res_in ** 2))) if mi.any() else float("nan")
    return float(cx), float(cy), ri, ro, rms, mi, mo


def detect_one(img: np.ndarray, guess: Optional[tuple[float, float, float]] = None
               ) -> Optional[tuple[float, float, float, float, float, float]]:
    """Single frame (crop coordinates): (cx, cy, r_in, r_out, rms_in, coverage) or None.

    `guess` = (cx, cy, r_in) from the previous sample: skips the Hough initialisation.
    """
    mask, sat, _ = ring_mask(img)
    if mask is None:
        return None
    if guess is None:
        a = detect([img])
        if a.method != "auto":
            return None
        cx, cy, r0 = a.cx, a.cy, a.r_in
    else:
        cx, cy, r0 = guess
    out = None
    for _ in range(3):
        ang, ri, ro = _cast(mask, sat, cx, cy, r0)
        oi, oo = np.isfinite(ri), np.isfinite(ro)
        if oi.sum() < 12:
            return None
        xi, yi = cx + ri[oi] * np.cos(ang[oi]), cy + ri[oi] * np.sin(ang[oi])
        xo, yo = cx + ro[oo] * np.cos(ang[oo]), cy + ro[oo] * np.sin(ang[oo])
        ncx, ncy, nri, nro, rms, mi, _ = fit_concentric(xi, yi, xo, yo)
        out = (ncx, ncy, nri, nro, rms, float(mi.sum() / N_RAYS))
        moved = np.hypot(ncx - cx, ncy - cy) + abs(nri - r0)
        cx, cy, r0 = ncx, ncy, nri
        if moved < 0.05:
            break
    return out


def _running_median(v: np.ndarray, w: int) -> np.ndarray:
    if len(v) < 3 or w < 3:
        return v.copy()
    h = w // 2
    pad = np.concatenate([np.full(h, v[0]), v, np.full(h, v[-1])])
    win = np.lib.stride_tricks.sliding_window_view(pad, w)
    return np.median(win, axis=1)


@dataclass
class ArenaTrack:
    """Enclosure circle as a function of the frame number (full-frame video px).

    Automatic samples (`frames`, `cx`, `cy`, `r_in`, `r_out`, `rms`, `cov`) come from detect_one().
    A manual circle (`manual`, defined on `manual_frame`) overrides them; with `follow_motion` and
    automatic samples available, it is moved and rescaled with the detected motion:
        c(f) = c_manual + c_auto(f) - c_auto(f0),   r(f) = r_manual * r_auto(f) / r_auto(f0).
    """

    frames: np.ndarray
    cx: np.ndarray
    cy: np.ndarray
    r_in: np.ndarray
    r_out: np.ndarray
    rms: np.ndarray
    cov: np.ndarray
    d_in_mm: float = D_IN_MM
    d_out_mm: float = D_OUT_MM
    step: int = DEFAULT_STEP
    manual: Optional[Arena] = None
    manual_frame: Optional[int] = None
    follow_motion: bool = True
    manual_points: tuple = ()

    # ---- construction
    @staticmethod
    def empty(d_in_mm: float = D_IN_MM, d_out_mm: float = D_OUT_MM) -> "ArenaTrack":
        z = np.zeros(0)
        return ArenaTrack(np.zeros(0, np.int64), z, z, z, z, z, z, d_in_mm, d_out_mm)

    @staticmethod
    def from_samples(samples: list[tuple[int, Optional[tuple]]], offset: tuple[float, float],
                     d_in_mm: float = D_IN_MM, d_out_mm: float = D_OUT_MM,
                     step: int = DEFAULT_STEP) -> "ArenaTrack":
        """`samples` = [(frame, detect_one result in crop px or None), ...]."""
        good = [(f, r) for f, r in samples if r is not None]
        if not good:
            return ArenaTrack.empty(d_in_mm, d_out_mm)
        f = np.array([g[0] for g in good], np.int64)
        v = np.array([g[1] for g in good], float)
        order = np.argsort(f)
        f, v = f[order], v[order]
        return ArenaTrack(f, v[:, 0] + offset[0], v[:, 1] + offset[1], v[:, 2], v[:, 3], v[:, 4], v[:, 5],
                          d_in_mm, d_out_mm, step)

    # ---- quality
    @property
    def has_auto(self) -> bool:
        return len(self.frames) > 0

    def ok(self) -> np.ndarray:
        """Samples usable for the geometry (good fit, enough of the rim visible, sane radius)."""
        if not self.has_auto:
            return np.zeros(0, bool)
        med = np.median(self.r_in)
        return ((self.rms <= MAX_RMS_RELIABLE) & (self.cov >= MIN_COVERAGE_RELIABLE)
                & (np.abs(self.r_in / med - 1) < 0.03))

    @property
    def defined(self) -> bool:
        return self.manual is not None or (self.has_auto and self.ok().sum() >= 1)

    @property
    def method(self) -> str:
        if self.manual is not None:
            return "manual + movimiento detectado" if (self.follow_motion and self.has_auto) else "manual"
        return "automático" if self.has_auto else "sin definir"

    def smoothed(self) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
        """(frames, cx, cy, r_in) of the good automatic samples after the running median."""
        ok = self.ok()
        f = self.frames[ok]
        w = SMOOTH_SAMPLES if len(f) >= SMOOTH_SAMPLES else 1
        return (f, _running_median(self.cx[ok], w), _running_median(self.cy[ok], w),
                _running_median(self.r_in[ok], w))

    # ---- evaluation
    def at(self, frames: np.ndarray) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
        """(cx, cy, r_in) in video px for every requested frame (held constant beyond the ends)."""
        frames = np.asarray(frames, float)
        if self.has_auto and self.ok().any():
            f, cx, cy, r = self.smoothed()
            acx, acy, ar_ = (np.interp(frames, f, cx), np.interp(frames, f, cy), np.interp(frames, f, r))
        else:
            acx = acy = ar_ = None
        if self.manual is not None:
            m = self.manual
            if self.follow_motion and acx is not None and self.manual_frame is not None:
                f, cx, cy, r = self.smoothed()
                f0 = float(self.manual_frame)
                return (m.cx + acx - np.interp(f0, f, cx), m.cy + acy - np.interp(f0, f, cy),
                        m.r_in * ar_ / np.interp(f0, f, r))
            n = len(frames)
            return np.full(n, m.cx), np.full(n, m.cy), np.full(n, m.r_in)
        if acx is None:
            raise ValueError("El recinto no está definido.")
        return acx, acy, ar_

    def arena_at(self, frame: int) -> Optional[Arena]:
        if not self.defined:
            return None
        cx, cy, r = (float(v[0]) for v in self.at(np.array([frame])))
        ratio = self.ratio_measured()
        r_out = r * ratio if np.isfinite(ratio) else float("nan")
        return Arena(cx, cy, r, r_out, self.d_in_mm, self.d_out_mm, self.method)

    # ---- summaries
    def ratio_measured(self) -> float:
        ok = self.ok() & np.isfinite(self.r_out) if self.has_auto else np.zeros(0, bool)
        return float(np.median(self.r_out[ok] / self.r_in[ok])) if ok.any() else float("nan")

    def static(self) -> Optional[Arena]:
        """Representative single circle (medians): for reports and as a fallback."""
        if self.manual is not None and not (self.follow_motion and self.has_auto):
            return self.manual
        if not self.defined:
            return None
        f, cx, cy, r = self.smoothed() if self.has_auto else (None,) * 4
        if self.manual is not None:
            frames = self.frames[self.ok()]
            cxs, cys, rs = self.at(frames)
            cx, cy, r = cxs, cys, rs
        ok = self.ok()
        return Arena(float(np.median(cx)), float(np.median(cy)), float(np.median(r)),
                     float(np.median(r)) * self.ratio_measured(), self.d_in_mm, self.d_out_mm, self.method,
                     float(np.median(self.rms[ok])) if ok.any() else float("nan"),
                     float(np.median(self.cov[ok])) if ok.any() else float("nan"), int(ok.sum()))

    def stats(self) -> dict:
        """Numbers for the UI, the JSON side-car and the report."""
        a = self.static()
        d = {"metodo": self.method, "d_int_mm": self.d_in_mm, "d_ext_mm": self.d_out_mm,
             "muestras": int(len(self.frames)), "muestras_validas": int(self.ok().sum()) if self.has_auto else 0,
             "paso_cuadros": int(self.step)}
        if a is None:
            return d
        d.update({"cx_px": a.cx, "cy_px": a.cy, "r_int_px": a.r_in, "mm_por_px": a.mm_per_px,
                  "r_ext_sobre_r_int": self.ratio_measured(), "esperado": a.ratio_expected})
        if self.has_auto and self.ok().any():
            ok = self.ok()
            f = self.frames[ok]
            cx, cy, r = self.at(f)
            s = a.mm_per_px
            d.update({"residuo_px": float(np.median(self.rms[ok])), "cobertura": float(np.median(self.cov[ok])),
                      "desplazamiento_x_mm": float((cx.max() - cx.min()) * s),
                      "desplazamiento_y_mm": float((cy.max() - cy.min()) * s),
                      "variacion_escala_pct": float(100 * (r.max() / r.min() - 1))})
        return d

    def describe(self) -> str:
        st = self.stats()
        if "mm_por_px" not in st:
            return "Recinto sin definir: detectalo o marcá al menos 3 puntos del borde interior."
        txt = (f"{st['metodo']} · centro ({st['cx_px']:.1f}, {st['cy_px']:.1f}) px · r_int {st['r_int_px']:.1f} px · "
               f"escala {st['mm_por_px']:.4f} mm/px")
        if np.isfinite(st.get("r_ext_sobre_r_int", np.nan)):
            txt += f" · r_ext/r_int {st['r_ext_sobre_r_int']:.4f} (esperado {st['esperado']:.4f})"
        if "desplazamiento_x_mm" in st:
            txt += (f"<br>{st['muestras_validas']}/{st['muestras']} muestras · residuo {st['residuo_px']:.2f} px · "
                    f"movimiento del recinto {st['desplazamiento_x_mm']:.1f} × {st['desplazamiento_y_mm']:.1f} mm · "
                    f"variación de escala {st['variacion_escala_pct']:.2f} %")
        return txt

    # ---- persistence (numeric arrays + JSON-able metadata)
    def to_arrays(self) -> dict:
        return {"arena": np.column_stack([self.frames, self.cx, self.cy, self.r_in, self.r_out,
                                          self.rms, self.cov]).astype(float).reshape(-1, 7)}

    def meta(self) -> dict:
        return {"d_in_mm": self.d_in_mm, "d_out_mm": self.d_out_mm, "step": int(self.step),
                "manual": self.manual.to_dict() if self.manual is not None else None,
                "manual_frame": self.manual_frame, "follow_motion": self.follow_motion,
                "manual_points": [list(map(float, p)) for p in self.manual_points]}

    @staticmethod
    def from_saved(arr: Optional[np.ndarray], meta: Optional[dict]) -> Optional["ArenaTrack"]:
        if arr is None and not meta:
            return None
        meta = meta or {}
        a = np.zeros((0, 7)) if arr is None else np.asarray(arr, float).reshape(-1, 7)
        t = ArenaTrack(a[:, 0].astype(np.int64), a[:, 1], a[:, 2], a[:, 3], a[:, 4], a[:, 5], a[:, 6],
                       float(meta.get("d_in_mm", D_IN_MM)), float(meta.get("d_out_mm", D_OUT_MM)),
                       int(meta.get("step", DEFAULT_STEP)))
        if meta.get("manual"):
            t.manual = Arena.from_dict(meta["manual"])
            t.manual_frame = meta.get("manual_frame")
            t.follow_motion = bool(meta.get("follow_motion", True))
            t.manual_points = tuple(tuple(p) for p in meta.get("manual_points", []))
        return t

    def with_diameters(self, d_in_mm: float, d_out_mm: float) -> "ArenaTrack":
        t = replace(self, d_in_mm=float(d_in_mm), d_out_mm=float(d_out_mm))
        if t.manual is not None:
            t.manual = t.manual.with_diameters(d_in_mm, d_out_mm)
        return t


def track_video(src_path: str, trim: TrimRange, roi: Roi, step: int = DEFAULT_STEP,
                d_in_mm: float = D_IN_MM, d_out_mm: float = D_OUT_MM,
                progress: Optional[Callable[[int], None]] = None,
                should_cancel: Optional[Callable[[], bool]] = None):
    """Enclosure every `step` frames of [trim] (sequential grab, decode only the sampled frames).

    Worker-friendly: returns (ArenaTrack, cancelled).
    """
    cap = cv2.VideoCapture(src_path)
    if not cap.isOpened():
        raise IOError(f"OpenCV no pudo abrir el video: {src_path}")
    try:
        n = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        W, H = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH)), int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        trim = trim.clamped(n)
        roi = roi.clamped(W, H)
        cap.set(cv2.CAP_PROP_POS_FRAMES, trim.start)
        samples: list[tuple[int, Optional[tuple]]] = []
        guess = None
        total = trim.length
        for i, idx in enumerate(range(trim.start, trim.end + 1)):
            if not cap.grab():
                break
            if (idx - trim.start) % step and idx != trim.end:
                continue
            ok, frame = cap.retrieve()
            if not ok:
                continue
            res = detect_one(roi.apply(frame), guess)
            samples.append((idx, res))
            if res is not None:
                guess = (res[0], res[1], res[2])
            if should_cancel is not None and should_cancel():
                return None, True
            if progress is not None:
                progress(int(100 * (i + 1) / total))
    finally:
        cap.release()
    return ArenaTrack.from_samples(samples, (roi.x, roi.y), d_in_mm, d_out_mm, step), False
