"""Automatic, resolution-independent calibration of the robot detector.

Every geometric parameter of the detector/tracker scales with the apparent robot size, so we
measure that size first and derive the rest from it:

1. Radius: the disc/ring matched filter (same model used for detection) is evaluated on a
   geometric radius grid. The mean of the K strongest local maxima peaks when the template matches
   the real robot (smaller -> ring falls on the bright battery; larger -> disc swallows the dark
   ring). Coarse grid on a ~256 px image, then a fine grid on an image rescaled so the robot is
   ~24 px, with parabolic refinement in log(r).
2. Intensities: disc and ring gray levels are sampled at the strongest peaks; dark thresholds are
   placed at fixed fractions of that contrast (reproduces the hand-tuned 4K values 70/110).
3. Count: full detection with the derived params on the sample frames -> median N.

Reference geometry (measured on DJI_0196, 4K): r_out = 48 px, r_in = 36 px (ratio 0.75),
max speed ~13 px/frame (0.28 r_out).
"""
from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Callable, Optional

import cv2
import numpy as np

from core import detection as det
from core.models import Roi, TrimRange
from core.processing import Pipeline
from core.video_io import VideoReader

RING_RATIO = 0.75            # r_in / r_out
TARGET_R_ANALYSIS = 24.0     # r_out after downscaling for detection (px)
SEPARATION_PER_R = 1.5       # separation / r_out
SEARCH_PER_R = 0.625         # tracker search range / r_out
GAP_GROWTH_PER_R = 0.0625    # tracker gate growth per missing frame / r_out
PIXEL_DARK_FRAC = 0.14       # ring pixel threshold = ring + frac * (disc - ring)
RING_MAX_FRAC = 0.50         # ring mean gate     = ring + frac * (disc - ring)
MIN_R_OUT = 4.0              # px, below this a ring cannot be resolved


@dataclass(frozen=True)
class Calibration:
    r_out: float              # px at the input (ROI) resolution
    r_in: float
    ring_gray: float          # typical dark-ring gray level
    disc_gray: float          # typical bright-disc gray level
    n_estimate: Optional[int]
    n_per_frame: tuple[int, ...]
    radius_spread: float      # relative spread (max-min)/median of per-frame radius estimates
    frame_size: tuple[int, int]  # (w, h) analysed

    @property
    def diameter(self) -> float:
        return 2 * self.r_out

    @property
    def reliable(self) -> bool:
        return (self.radius_spread < 0.10 and self.disc_gray - self.ring_gray > 30
                and self.n_estimate is not None and self.n_estimate > 0)


def _kernels(r_in: float, r_out: float) -> tuple[np.ndarray, np.ndarray]:
    R = int(np.ceil(r_out))
    yy, xx = np.mgrid[-R:R + 1, -R:R + 1]
    rr = np.hypot(xx, yy)
    d = (rr <= r_in).astype(np.float32)
    g = ((rr > r_in) & (rr <= r_out)).astype(np.float32)
    return d / max(d.sum(), 1), g / max(g.sum(), 1)


def _response(g: np.ndarray, r: float, gate_max: float) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    kd, kr = _kernels(RING_RATIO * r, r)
    md = cv2.filter2D(g, -1, kd, borderType=cv2.BORDER_REFLECT)
    mr = cv2.filter2D(g, -1, kr, borderType=cv2.BORDER_REFLECT)
    return (md - mr) * np.clip((gate_max - mr) / gate_max, 0, 1), md, mr


def _peaks(R: np.ndarray, r: float, k: int) -> tuple[np.ndarray, np.ndarray]:
    w = 2 * max(1, int(round(r))) + 1
    mx = cv2.dilate(R, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (w, w)))
    ys, xs = np.nonzero((R == mx) & (R > 0))
    order = np.argsort(-R[ys, xs])[:k]
    return ys[order], xs[order]


def _score(g: np.ndarray, r: float, gate_max: float, k: int) -> float:
    R = _response(g, r, gate_max)[0]
    ys, xs = _peaks(R, r, k)
    return float(R[ys, xs].mean()) if len(ys) else 0.0


def _best_on_grid(g: np.ndarray, rs: np.ndarray, gate_max: float, k: int, step: float) -> float:
    sc = np.array([_score(g, r, gate_max, k) for r in rs])
    i = int(np.argmax(sc))
    if 0 < i < len(sc) - 1:
        y0, y1, y2 = sc[i - 1:i + 2]
        den = y0 - 2 * y1 + y2
        off = float(np.clip(0.5 * (y0 - y2) / den, -1, 1)) if den != 0 else 0.0
        return float(rs[i] * step ** off)
    return float(rs[i])


def _resize(gray: np.ndarray, f: float) -> np.ndarray:
    if abs(f - 1.0) < 1e-3:
        return gray.astype(np.float32)
    interp = cv2.INTER_AREA if f < 1 else cv2.INTER_CUBIC
    return cv2.resize(gray, None, fx=f, fy=f, interpolation=interp).astype(np.float32)


def estimate_radius(gray: np.ndarray, k: int = 10) -> tuple[float, float]:
    """Returns (r_out in input px, Otsu threshold) for one grayscale frame."""
    h, w = gray.shape
    otsu, _ = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    gate = max(float(otsu) * 1.1, 1.0)
    # Coarse
    f0 = min(1.0, 256.0 / max(h, w))
    g0 = _resize(gray, f0)
    rs = MIN_R_OUT * 1.15 ** np.arange(60)
    rs = rs[rs <= min(g0.shape) / 4]
    if len(rs) < 3:
        raise ValueError("La imagen es demasiado chica para estimar el tamaño de los robots.")
    r0 = _best_on_grid(g0, rs, gate, k, 1.15) / f0
    # Fine: rescale so the robot is ~TARGET_R_ANALYSIS px
    f1 = min(1.0, TARGET_R_ANALYSIS / r0) if r0 > TARGET_R_ANALYSIS else 1.0
    g1 = _resize(gray, f1)
    centre = r0 * f1
    rs = centre * 1.02 ** np.arange(-8, 9)
    rs = rs[(rs >= MIN_R_OUT) & (rs <= min(g1.shape) / 4)]
    r1 = _best_on_grid(g1, rs, gate, k, 1.02) / f1 if len(rs) >= 3 else r0
    return r1, float(otsu)


def _gray_levels(gray: np.ndarray, r_out: float, gate: float, k: int) -> tuple[float, float]:
    f = min(1.0, TARGET_R_ANALYSIS / r_out)
    g = _resize(gray, f)
    r = r_out * f
    R, md, mr = _response(g, r, gate)
    ys, xs = _peaks(R, r, k)
    if len(ys) == 0:
        return float(np.percentile(gray, 10)), float(np.percentile(gray, 90))
    return float(np.median(mr[ys, xs])), float(np.median(md[ys, xs]))


def _to_gray(img: np.ndarray) -> np.ndarray:
    return img if img.ndim == 2 else cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)


def calibrate_frames(frames: list[np.ndarray], base: det.DetectionParams,
                     n_hint: Optional[int] = None) -> tuple[Calibration, det.DetectionParams]:
    if not frames:
        raise ValueError("No hay cuadros para calibrar.")
    k = n_hint if n_hint else 10
    grays = [_to_gray(f) for f in frames]
    radii, otsus = zip(*(estimate_radius(g, k) for g in grays))
    r_out = float(np.median(radii))
    spread = float((max(radii) - min(radii)) / r_out) if r_out > 0 else 1.0
    gate = max(float(np.median(otsus)) * 1.1, 1.0)
    levels = [_gray_levels(g, r_out, gate, k) for g in grays]
    ring = float(np.median([l[0] for l in levels]))
    disc = float(np.median([l[1] for l in levels]))
    params = derive_detection_params(r_out, ring, disc, base)
    counts = tuple(len(det.locate(f, params)) for f in frames) if det.tp is not None else ()
    n_est = int(np.median(counts)) if counts else None
    h, w = grays[0].shape
    cal = Calibration(r_out, RING_RATIO * r_out, ring, disc, n_est, counts, spread, (w, h))
    return cal, params


def derive_detection_params(r_out: float, ring_gray: float, disc_gray: float,
                            base: det.DetectionParams) -> det.DetectionParams:
    contrast = max(disc_gray - ring_gray, 1.0)
    return replace(
        base,
        r_out=round(r_out, 1),
        r_in=round(RING_RATIO * r_out, 1),
        scale=round(float(np.clip(TARGET_R_ANALYSIS / r_out, 0.05, 1.0)), 3),
        separation=round(SEPARATION_PER_R * r_out, 1),
        ring_pixel_dark=round(float(np.clip(ring_gray + PIXEL_DARK_FRAC * contrast, 1, 254)), 0),
        ring_gray_max=round(float(np.clip(ring_gray + RING_MAX_FRAC * contrast, 1, 254)), 0),
    )


def derive_tracker_values(r_out: float) -> dict:
    """Size-dependent tracker settings (search range, gate growth)."""
    return {"search_range": round(SEARCH_PER_R * r_out, 1),
            "gap_growth": round(GAP_GROWTH_PER_R * r_out, 2)}


def sample_frames(src_path: str, trim: TrimRange, roi: Roi, pipeline: Optional[Pipeline],
                  n_samples: int = 5) -> list[np.ndarray]:
    """Evenly spaced crops (pipeline applied) from the trimmed range."""
    out: list[np.ndarray] = []
    with VideoReader(src_path) as reader:
        info = reader.info
        trim = trim.clamped(info.frame_count)
        roi = roi.clamped(info.width, info.height)
        idxs = np.unique(np.linspace(trim.start, trim.end, max(1, n_samples)).round().astype(int))
        for idx in idxs:
            frame = reader.read(int(idx))
            if frame is None:
                continue
            crop = roi.apply(frame)
            out.append(pipeline(crop) if pipeline else crop)
    if not out:
        raise IOError("No se pudieron leer cuadros para calibrar.")
    return out


def calibrate_video(src_path: str, trim: TrimRange, roi: Roi, pipeline: Optional[Pipeline],
                    base: det.DetectionParams, n_hint: Optional[int] = None, n_samples: int = 5,
                    progress: Optional[Callable[[int], None]] = None,
                    should_cancel: Optional[Callable[[], bool]] = None):
    frames = sample_frames(src_path, trim, roi, pipeline, n_samples)
    if progress:
        progress(30)
    if should_cancel and should_cancel():
        return None, True
    result = calibrate_frames(frames, base, n_hint)
    if progress:
        progress(100)
    return result, False


def describe(cal: Calibration) -> str:
    n = f"N ≈ {cal.n_estimate} (por cuadro: {', '.join(map(str, cal.n_per_frame))})" \
        if cal.n_estimate is not None else "N no estimado"
    warn = "" if cal.reliable else " — revisar: calibración poco confiable"
    return (f"Imagen {cal.frame_size[0]}×{cal.frame_size[1]} px · diámetro robot ≈ {cal.diameter:.1f} px "
            f"(dispersión {100 * cal.radius_spread:.1f} %) · gris anillo {cal.ring_gray:.0f} / "
            f"disco {cal.disc_gray:.0f} · {n}{warn}")
