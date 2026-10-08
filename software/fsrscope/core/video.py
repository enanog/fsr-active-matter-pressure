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
