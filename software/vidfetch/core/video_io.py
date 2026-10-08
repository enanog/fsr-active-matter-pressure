from __future__ import annotations

import math
import os
from dataclasses import dataclass
from typing import Callable, Optional

import cv2
import numpy as np

from core.models import Roi, TrimRange

# OpenCV-supported codecs per output container (no audio: OpenCV only handles video streams).
CODECS = {".mp4": "mp4v", ".avi": "MJPG"}
DEFAULT_FPS = 30.0


@dataclass(frozen=True)
class VideoInfo:
    path: str
    width: int
    height: int
    fps: float
    frame_count: int

    @property
    def duration_s(self) -> float:
        return self.frame_count / self.fps if self.fps > 0 else 0.0


class VideoReader:
    """Thin wrapper over cv2.VideoCapture with cheap sequential reads and explicit seeks."""

    def __init__(self, path: str):
        if not path or not os.path.isfile(path):
            raise FileNotFoundError(f"No existe el archivo: {path}")
        self._cap = cv2.VideoCapture(path)
        if not self._cap.isOpened():
            raise IOError(f"OpenCV no pudo abrir el video: {path}")

        fps = self._cap.get(cv2.CAP_PROP_FPS)
        if fps is None or math.isnan(fps) or fps <= 0:
            fps = DEFAULT_FPS
        width = int(self._cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        height = int(self._cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        count = int(self._cap.get(cv2.CAP_PROP_FRAME_COUNT))
        if count <= 0:
            count = self._count_frames()
        if width <= 0 or height <= 0 or count <= 0:
            self._cap.release()
            raise IOError("El video no tiene cuadros legibles o metadatos válidos.")

        self.info = VideoInfo(path, width, height, float(fps), count)
        self._pos = 0

    def _count_frames(self) -> int:
        # Fallback for containers that do not report frame count.
        n = 0
        while self._cap.grab():
            n += 1
        self._cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
        return n

    def read(self, index: int) -> Optional[np.ndarray]:
        if index < 0 or index >= self.info.frame_count:
            return None
        if index != self._pos:
            self._cap.set(cv2.CAP_PROP_POS_FRAMES, index)
        ok, frame = self._cap.read()
        if not ok or frame is None:
            self._pos = -1  # force a seek on the next read
            return None
        self._pos = index + 1
        return frame

    def close(self) -> None:
        if self._cap is not None:
            self._cap.release()
            self._cap = None

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()


def ensure_bgr_u8(frame: np.ndarray) -> np.ndarray:
    if frame.dtype != np.uint8:
        frame = np.clip(frame, 0, 255).astype(np.uint8)
    if frame.ndim == 2:
        frame = cv2.cvtColor(frame, cv2.COLOR_GRAY2BGR)
    elif frame.shape[2] == 4:
        frame = cv2.cvtColor(frame, cv2.COLOR_BGRA2BGR)
    return frame


def _even_size(frame: np.ndarray) -> np.ndarray:
    # Several encoders reject odd dimensions; drop at most one row/column.
    h, w = frame.shape[:2]
    return frame[: h - (h % 2), : w - (w % 2)]


def export_video(
    src_path: str,
    dst_path: str,
    trim: TrimRange,
    roi: Roi,
    process: Optional[Callable[[np.ndarray], np.ndarray]] = None,
    progress: Optional[Callable[[int], None]] = None,
    should_cancel: Optional[Callable[[], bool]] = None,
    annotate: Optional[Callable[[np.ndarray, int], np.ndarray]] = None,
) -> tuple[int, bool]:
    """Write frames [trim] cropped to [roi], processed, then annotated with (image, frame_index).

    Returns (frames_written, cancelled)."""
    ext = os.path.splitext(dst_path)[1].lower()
    if ext not in CODECS:
        raise ValueError(f"Extensión no soportada '{ext}'. Usar: {', '.join(CODECS)}")
    if os.path.abspath(dst_path) == os.path.abspath(src_path):
        raise ValueError("El destino no puede ser el mismo archivo que el video original.")

    writer = None
    written = 0
    cancelled = False
    with VideoReader(src_path) as reader:
        info = reader.info
        trim = trim.clamped(info.frame_count)
        roi = roi.clamped(info.width, info.height)
        if roi.w < 2 or roi.h < 2:
            raise ValueError("La región seleccionada es demasiado chica (mínimo 2×2 px).")
        out_size = None
        try:
            for i, idx in enumerate(range(trim.start, trim.end + 1)):
                if should_cancel is not None and should_cancel():
                    cancelled = True
                    break
                frame = reader.read(idx)
                if frame is None:
                    break  # container overestimated frame count
                out = roi.apply(frame)
                if process is not None:
                    out = process(out)
                if annotate is not None:
                    out = annotate(out, idx)
                out = _even_size(ensure_bgr_u8(out))

                if writer is None:
                    out_size = (out.shape[1], out.shape[0])
                    fourcc = cv2.VideoWriter_fourcc(*CODECS[ext])
                    writer = cv2.VideoWriter(dst_path, fourcc, info.fps, out_size)
                    if not writer.isOpened():
                        raise IOError(f"No se pudo crear el archivo de salida: {dst_path}")
                elif (out.shape[1], out.shape[0]) != out_size:
                    out = cv2.resize(out, out_size)

                writer.write(np.ascontiguousarray(out))
                written += 1
                if progress is not None:
                    progress(int(100 * (i + 1) / trim.length))
        finally:
            if writer is not None:
                writer.release()

    if (cancelled or written == 0) and os.path.exists(dst_path):
        os.remove(dst_path)
    if written == 0 and not cancelled:
        raise IOError("No se escribió ningún cuadro.")
    return written, cancelled
