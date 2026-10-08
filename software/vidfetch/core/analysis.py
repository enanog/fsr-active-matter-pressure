"""Glue between per-frame processing, detection and whole-range batch analysis."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable, Optional

import cv2
import numpy as np
import pandas as pd

from core import detection as det
from core import rotation
from core.models import Roi, TrimRange
from core.processing import Pipeline
from core.video_io import VideoReader


@dataclass
class FrameProcessor:
    """Value snapshot (thread-safe): ops pipeline followed by optional robot detection."""

    pipeline: Pipeline = field(default_factory=Pipeline)
    detection: det.DetectionParams = field(default_factory=det.DetectionParams)

    def run(self, frame: np.ndarray) -> tuple[np.ndarray, Optional[pd.DataFrame]]:
        out = self.pipeline(frame) if self.pipeline else frame
        if not self.detection.enabled:
            return out, None
        found = det.locate(out, self.detection)
        return det.draw(out, found, self.detection), found

    def __call__(self, frame: np.ndarray) -> np.ndarray:
        return self.run(frame)[0]

    def __bool__(self) -> bool:
        return bool(self.pipeline) or self.detection.enabled


def scan_video(
    src_path: str,
    trim: TrimRange,
    roi: Roi,
    processor: FrameProcessor,
    progress: Optional[Callable[[int], None]] = None,
    should_cancel: Optional[Callable[[], bool]] = None,
    with_signatures: bool = False,
    fps: Optional[float] = None,
) -> tuple[pd.DataFrame, np.ndarray, float, bool, Optional[np.ndarray]]:
    """Detect on every frame of [trim] inside [roi].

    Returns (detections in full-frame px, frame indices actually read, fps, cancelled,
    rotation signatures aligned with the detection rows or None).
    """
    if not processor.detection.enabled:
        raise ValueError("La detección no está activada.")
    chunks: list[pd.DataFrame] = []
    sig_chunks: list[np.ndarray] = []
    frames_read: list[int] = []
    p = processor.detection
    cancelled = False
    with VideoReader(src_path) as reader:
        info = reader.info
        trim = trim.clamped(info.frame_count)
        roi = roi.clamped(info.width, info.height)
        for i, idx in enumerate(range(trim.start, trim.end + 1)):
            if should_cancel is not None and should_cancel():
                cancelled = True
                break
            frame = reader.read(idx)
            if frame is None:
                break  # container overestimated frame count
            frames_read.append(idx)
            crop = roi.apply(frame)
            img = processor.pipeline(crop) if processor.pipeline else crop
            f = det.locate(img, p)
            if len(f):
                f = f.copy()
                f["frame"] = idx
                chunks.append(f)
                if with_signatures:
                    # Signatures at the analysis scale (robot ~24 px radius, area-averaged).
                    g = det._to_gray(img)
                    if p.scale != 1.0:
                        g = cv2.resize(g, None, fx=p.scale, fy=p.scale, interpolation=cv2.INTER_AREA)
                    sig_chunks.append(rotation.signatures(g, f["x"].to_numpy() * p.scale,
                                                          f["y"].to_numpy() * p.scale, p.r_out * p.scale))
            if progress is not None:
                progress(int(100 * (i + 1) / trim.length))

    if not chunks:
        df = det.empty_result()
        df["frame"] = pd.Series(dtype=int)
    else:
        df = pd.concat(chunks, ignore_index=True)
    df["x"] = df["x"] + roi.x
    df["y"] = df["y"] + roi.y
    time_fps = fps or info.fps   # frames per real second (time-lapse aware)
    df["t_s"] = df["frame"] / time_fps
    sigs = None
    if with_signatures:
        sigs = (np.concatenate(sig_chunks) if sig_chunks
                else np.zeros((0, len(rotation.BANDS), rotation.HARMONICS), np.complex64))
    return df, np.asarray(frames_read, dtype=np.int64), time_fps, cancelled, sigs


def detect_video(src_path, trim, roi, processor, progress=None, should_cancel=None, fps=None):
    df, _, _, cancelled, _ = scan_video(src_path, trim, roi, processor, progress, should_cancel, fps=fps)
    return df, cancelled


def save_tracks_csv(df: pd.DataFrame, path: str) -> None:
    order = ["frame", "t_s", "particle", "x", "y", "mass", "size", "ecc", "signal", "ring_cov"]
    cols = [c for c in order if c in df.columns]
    out = df[cols].rename(columns={"x": "x_px", "y": "y_px"})
    sort_cols = [c for c in ("frame", "particle") if c in out.columns]
    out.sort_values(sort_cols).to_csv(path, index=False, float_format="%.4f")
