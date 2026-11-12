"""Frame access tuned for playback: sequential decode for small forward steps, seek otherwise."""

from __future__ import annotations

import math
from pathlib import Path
from typing import Optional

import cv2
import numpy as np

# Forward gaps up to this many frames are skipped with grab() (cheaper than a keyframe seek).
MAX_GRAB_GAP = 24


class VideoSource:
    def __init__(self, path: Path | str):
        self.path = Path(path)
        if not self.path.is_file():
            raise FileNotFoundError(f"No existe el video: {self.path}")
        self._cap = cv2.VideoCapture(str(self.path))
        if not self._cap.isOpened():
            raise IOError(f"OpenCV no pudo abrir el video: {self.path}")
        fps = self._cap.get(cv2.CAP_PROP_FPS)
        self.file_fps = float(fps) if fps and not math.isnan(fps) and fps > 0 else 30.0
        self.frame_count = int(self._cap.get(cv2.CAP_PROP_FRAME_COUNT))
        self.width = int(self._cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        self.height = int(self._cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        if self.frame_count <= 0 or self.width <= 0:
            self.close()
            raise IOError("El video no informa cuadros o tamaño válidos.")
        self._next = 0          # index of the frame the next cap.read() returns
        self._last_idx = -1
        self._last: Optional[np.ndarray] = None

    def read(self, index: int) -> Optional[np.ndarray]:
        """BGR frame `index` (clamped to the valid range); cached when unchanged."""
        if self._cap is None:
            return None
        index = int(min(max(index, 0), self.frame_count - 1))
        if index == self._last_idx:
            return self._last
        gap = index - self._next
        if 0 <= gap <= MAX_GRAB_GAP:
            for _ in range(gap):
                self._cap.grab()
        else:
            self._cap.set(cv2.CAP_PROP_POS_FRAMES, index)
        ok, frame = self._cap.read()
        if not ok or frame is None:
            self._next = -10 ** 9   # force a seek next time
            return self._last
        self._next = index + 1
        self._last_idx, self._last = index, frame
        return frame

    def close(self) -> None:
        if self._cap is not None:
            self._cap.release()
            self._cap = None


class PartedVideoSource:
    """Several files played as one video on a common frame axis (split recording, see
    comun.cortes). read() returns None for the frames inside a gap."""

    def __init__(self, paths_: list, starts: list[int]):
        if len(paths_) != len(starts) or not paths_:
            raise ValueError("una ruta por parte y un inicio por parte")
        self.parts = [VideoSource(p) for p in paths_]
        self.starts = [int(s) for s in starts]
        self.path = self.parts[0].path
        self.paths = [s.path for s in self.parts]
        self.file_fps = self.parts[0].file_fps
        self.width, self.height = self.parts[0].width, self.parts[0].height
        self.frame_count = self.starts[-1] + self.parts[-1].frame_count

    def locate(self, index: int) -> Optional[tuple[int, int]]:
        """(part number from 0, frame inside that part), or None inside a gap / out of range."""
        for k in range(len(self.parts) - 1, -1, -1):
            if index >= self.starts[k]:
                local = index - self.starts[k]
                return (k, local) if local < self.parts[k].frame_count else None
        return None

    def gap_at(self, index: int) -> Optional[tuple[int, float]]:
        """(part after the gap, frames to its start) if index falls in a gap."""
        for k in range(1, len(self.parts)):
            end_prev = self.starts[k - 1] + self.parts[k - 1].frame_count
            if end_prev <= index < self.starts[k]:
                return k, self.starts[k] - index
        return None

    def read(self, index: int) -> Optional[np.ndarray]:
        where = self.locate(int(index))
        if where is None:
            return None
        k, local = where
        return self.parts[k].read(local)

    def close(self) -> None:
        for s in self.parts:
            s.close()
