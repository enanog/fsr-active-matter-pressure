from __future__ import annotations

from dataclasses import dataclass

import numpy as np


@dataclass(frozen=True)
class Roi:
    """Rectangular region of interest in source-frame pixel coordinates."""

    x: int
    y: int
    w: int
    h: int

    @staticmethod
    def full(width: int, height: int) -> "Roi":
        return Roi(0, 0, width, height)

    def clamped(self, width: int, height: int) -> "Roi":
        x = min(max(0, int(self.x)), max(0, width - 1))
        y = min(max(0, int(self.y)), max(0, height - 1))
        w = min(max(1, int(self.w)), width - x)
        h = min(max(1, int(self.h)), height - y)
        return Roi(x, y, w, h)

    def apply(self, frame: np.ndarray) -> np.ndarray:
        return frame[self.y:self.y + self.h, self.x:self.x + self.w]


@dataclass(frozen=True)
class TrimRange:
    """Inclusive frame range [start, end]."""

    start: int
    end: int

    def clamped(self, frame_count: int) -> "TrimRange":
        last = max(0, frame_count - 1)
        s = min(max(0, int(self.start)), last)
        e = min(max(s, int(self.end)), last)
        return TrimRange(s, e)

    @property
    def length(self) -> int:
        return self.end - self.start + 1
