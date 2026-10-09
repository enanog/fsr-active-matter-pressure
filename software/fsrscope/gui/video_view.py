"""Video panel synchronised to the sensor clock, with optional VidFetch robot overlay."""

from __future__ import annotations

from typing import Optional

import cv2
import numpy as np
from PySide6.QtCore import QRectF, Qt, Signal
from PySide6.QtGui import QColor, QImage, QPainter
from PySide6.QtWidgets import QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget

from core.session import TrialData
from core.video import VideoSource

SLOW_MM_S = 0.6     # robots below this speed are drawn red (jam threshold used in the reports)
FAST_MM_S = 3.5


class FrameView(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumSize(240, 240)
        self._img: Optional[QImage] = None
        self._msg = "Sin video"

    def set_frame(self, rgb: Optional[np.ndarray], msg: str = "") -> None:
        if rgb is None:
            self._img, self._msg = None, msg or "Sin video"
        else:
            rgb = np.ascontiguousarray(rgb)
            h, w = rgb.shape[:2]
            self._img = QImage(rgb.data, w, h, rgb.strides[0], QImage.Format.Format_RGB888).copy()
        self.update()

    def paintEvent(self, ev):
        p = QPainter(self)
        p.fillRect(self.rect(), QColor(20, 20, 20))
        if self._img is None:
            p.setPen(QColor(170, 170, 170))
            p.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter | Qt.TextFlag.TextWordWrap, self._msg)
            return
        iw, ih = self._img.width(), self._img.height()
        sc = min(self.width() / iw, self.height() / ih)
        w, h = iw * sc, ih * sc
        p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        p.drawImage(QRectF((self.width() - w) / 2, (self.height() - h) / 2, w, h), self._img)


def _speed_color(v: float) -> tuple[int, int, int]:
    """BGR from red (stopped) to green (fast)."""
    if not np.isfinite(v):
        return (160, 160, 160)
    a = float(np.clip((v - SLOW_MM_S) / (FAST_MM_S - SLOW_MM_S), 0, 1))
    return (40, int(60 + 170 * a), int(220 * (1 - a) + 30))


class VideoPanel(QWidget):
    openRequested = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.view = FrameView()
        self.info = QLabel("—")
        self.info.setStyleSheet("color:#444; padding:2px;")
        self.info.setWordWrap(True)
        self.btn_open = QPushButton("Abrir video…")
        self.btn_open.clicked.connect(self.openRequested)
        bar = QHBoxLayout()
        bar.addWidget(self.info, 1)
        bar.addWidget(self.btn_open)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(2, 2, 2, 2)
        lay.addWidget(self.view, 1)
        lay.addLayout(bar)
        self.src: Optional[VideoSource] = None
        self.td: Optional[TrialData] = None

    def set_source(self, td: Optional[TrialData], path) -> str:
        """Open `path` (or close if None). Returns an error message ('' if ok)."""
        self.close_source()
        self.td = td
        if path is None:
            self.view.set_frame(None, "Este ensayo no tiene video.\nUsá «Abrir video…» si existe en otra carpeta.")
            self.info.setText("—")
            return ""
        try:
            self.src = VideoSource(path)
        except (OSError, IOError) as exc:
            self.view.set_frame(None, str(exc))
            return str(exc)
        return ""

    def close_source(self) -> None:
        if self.src is not None:
            self.src.close()
            self.src = None

    def show_time(self, t_sensor: float) -> None:
        if self.src is None or self.td is None:
            return
        td, sy = self.td, self.td.settings.sync
        n = td.frame_at(t_sensor)
        t_video = t_sensor - td.offset_s
        if n < 0 or n >= self.src.frame_count:
            where = "antes del inicio" if n < 0 else "después del final"
            self.view.set_frame(None, f"t = {t_sensor:.1f} s: {where} del video\n"
                                      f"(video: {td.offset_s:.2f} s a "
                                      f"{td.offset_s + self.src.frame_count / sy.frames_per_s:.1f} s del sensor)")
            self.info.setText(f"{self.src.path.name} · fuera de rango")
            return
        frame = self.src.read(n)
        if frame is None:
            return
        img = frame.copy() if sy.show_robots and td.robots is not None else frame
        n_slow = None
        if sy.show_robots and td.robots is not None:
            n_slow = self._draw_robots(img, n)
        if sy.view == "rot180":
            img = cv2.rotate(img, cv2.ROTATE_180)
        self.view.set_frame(cv2.cvtColor(img, cv2.COLOR_BGR2RGB))
        extra = f" · robots lentos (< {SLOW_MM_S} mm/s): {n_slow}" if n_slow is not None else ""
        self.info.setText(f"{self.src.path.name} · cuadro {n}/{self.src.frame_count - 1} · "
                          f"t video = {t_video:.1f} s{extra}")

    def _draw_robots(self, img: np.ndarray, frame: int) -> Optional[int]:
        r = self.td.robots
        i = r.row_of(frame)
        if i < 0:
            return None
        rad = int(round(self.td.settings.sync.robot_radius_px))
        slow = 0
        for k in range(r.n_robots):
            x, y, v = r.x[i, k], r.y[i, k], r.speed_mm_s[i, k]
            if not (np.isfinite(x) and np.isfinite(y)):
                continue
            slow += int(np.isfinite(v) and v < SLOW_MM_S)
            cv2.circle(img, (int(round(x)), int(round(y))), rad, _speed_color(v), 2, cv2.LINE_AA)
        return slow
