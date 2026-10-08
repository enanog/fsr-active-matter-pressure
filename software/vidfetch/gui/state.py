from __future__ import annotations

from typing import Optional

from PySide6.QtCore import QObject, Signal

from core.models import Roi, TrimRange
from core.video_io import VideoInfo

# Time-lapse videos: real capture rate (frames per real second). The project's DJI videos are
# recorded at ~3 frames/s and played back at 29.97 fps (x10 acceleration).
DEFAULT_REAL_FPS = 3.0


class ProjectState(QObject):
    """Single source of truth for the loaded video, trim range and ROI shared by all tabs."""

    loaded = Signal(object)        # VideoInfo
    trimChanged = Signal(object)   # TrimRange
    roiChanged = Signal(object)    # Roi
    timeScaleChanged = Signal(float)  # frames per real second now in effect

    def __init__(self, parent=None):
        super().__init__(parent)
        self.info: Optional[VideoInfo] = None
        self.trim = TrimRange(0, 0)
        self.roi = Roi(0, 0, 1, 1)
        self.real_fps: Optional[float] = DEFAULT_REAL_FPS  # None -> the file's own fps is real time

    @property
    def time_fps(self) -> float:
        """Frames per REAL second used for every time, velocity and angular-velocity value."""
        if self.real_fps:
            return self.real_fps
        return self.info.fps if self.info is not None else 30.0

    @property
    def acceleration(self) -> float:
        """Playback speed-up of the file relative to real time (1 = real time)."""
        return (self.info.fps / self.time_fps) if self.info is not None else 1.0

    def set_real_fps(self, value: Optional[float]) -> None:
        if value is not None and not (value > 0):
            raise ValueError("La escala de tiempo debe ser positiva.")
        if value != self.real_fps:
            self.real_fps = value
            self.timeScaleChanged.emit(self.time_fps)

    def load(self, info: VideoInfo) -> None:
        self.info = info
        self.trim = TrimRange(0, info.frame_count - 1)
        self.roi = Roi.full(info.width, info.height)
        self.loaded.emit(info)
        self.trimChanged.emit(self.trim)
        self.roiChanged.emit(self.roi)

    def set_trim(self, trim: TrimRange) -> None:
        if self.info is None:
            return
        trim = trim.clamped(self.info.frame_count)
        if trim != self.trim:
            self.trim = trim
            self.trimChanged.emit(trim)

    def set_roi(self, roi: Roi) -> None:
        if self.info is None:
            return
        roi = roi.clamped(self.info.width, self.info.height)
        if roi != self.roi:
            self.roi = roi
            self.roiChanged.emit(roi)
