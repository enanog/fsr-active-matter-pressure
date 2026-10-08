from __future__ import annotations

from typing import Callable, Optional

import numpy as np
from PySide6.QtCore import QTimer, Qt, Signal
from PySide6.QtWidgets import (QHBoxLayout, QLabel, QSlider, QStyle, QToolButton,
                               QVBoxLayout, QWidget)

from core.video_io import VideoReader
from gui.frame_view import FrameView


class PlayerWidget(QWidget):
    """Frame view + transport controls. Playback is QTimer-driven (non-blocking)."""

    frameChanged = Signal(int)

    def __init__(self, view: FrameView, parent=None):
        super().__init__(parent)
        self.view = view
        self._reader: Optional[VideoReader] = None
        self._transform: Optional[Callable[[np.ndarray], np.ndarray]] = None
        self._start = self._end = self._current = 0
        self._time_fps: Optional[float] = None   # frames per real second (None -> file fps)
        self._last_raw: Optional[np.ndarray] = None

        self._timer = QTimer(self)
        self._timer.timeout.connect(self._tick)

        st = self.style()
        self.btn_play = QToolButton(icon=st.standardIcon(QStyle.StandardPixmap.SP_MediaPlay))
        self.btn_prev = QToolButton(icon=st.standardIcon(QStyle.StandardPixmap.SP_MediaSeekBackward))
        self.btn_next = QToolButton(icon=st.standardIcon(QStyle.StandardPixmap.SP_MediaSeekForward))
        self.btn_play.setToolTip("Reproducir / pausar (Espacio)")
        self.btn_prev.setToolTip("Cuadro anterior")
        self.btn_next.setToolTip("Cuadro siguiente")
        self.slider = QSlider(Qt.Orientation.Horizontal)
        self.lbl = QLabel("—")
        self.lbl.setMinimumWidth(190)
        self.lbl.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)

        self.btn_play.clicked.connect(self.toggle_play)
        self.btn_prev.clicked.connect(lambda: self.step(-1))
        self.btn_next.clicked.connect(lambda: self.step(1))
        self.slider.valueChanged.connect(self._on_slider)

        bar = QHBoxLayout()
        for w in (self.btn_prev, self.btn_play, self.btn_next):
            bar.addWidget(w)
        bar.addWidget(self.slider, 1)
        bar.addWidget(self.lbl)

        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.addWidget(view, 1)
        lay.addLayout(bar)
        self._set_enabled(False)

    # --- public API ---
    def load(self, path: str) -> None:
        self.close_source()
        self._reader = VideoReader(path)
        self._set_enabled(True)
        self.set_range(0, self._reader.info.frame_count - 1)

    def close_source(self) -> None:
        self.stop()
        if self._reader is not None:
            self._reader.close()
            self._reader = None
        self._last_raw = None
        self.view.set_frame(None)
        self._set_enabled(False)

    def set_range(self, start: int, end: int) -> None:
        if self._reader is None:
            return
        self.stop()
        self._start, self._end = start, max(start, end)
        self.slider.blockSignals(True)
        self.slider.setRange(self._start, self._end)
        self.slider.blockSignals(False)
        self.seek(min(max(self._current, self._start), self._end))

    def set_time_fps(self, fps: Optional[float]) -> None:
        """Real-time scale for the time label only (playback keeps the file's rate)."""
        self._time_fps = fps
        if self._reader is not None:
            self._update_label()

    def set_transform(self, fn: Optional[Callable[[np.ndarray], np.ndarray]]) -> None:
        self._transform = fn

    def refresh(self) -> None:
        self._render(self._last_raw)

    @property
    def current_index(self) -> int:
        return self._current

    def seek(self, index: int) -> bool:
        return self._show(min(max(index, self._start), self._end))

    def step(self, delta: int) -> None:
        self.stop()
        self.seek(self._current + delta)

    def toggle_play(self) -> None:
        if self._timer.isActive():
            self.stop()
            return
        if self._reader is None:
            return
        if self._current >= self._end:
            self.seek(self._start)
        self._timer.start(max(1, int(round(1000.0 / self._reader.info.fps))))
        self.btn_play.setIcon(self.style().standardIcon(QStyle.StandardPixmap.SP_MediaPause))

    def stop(self) -> None:
        self._timer.stop()
        self.btn_play.setIcon(self.style().standardIcon(QStyle.StandardPixmap.SP_MediaPlay))

    # --- internals ---
    def _set_enabled(self, on: bool) -> None:
        for w in (self.btn_play, self.btn_prev, self.btn_next, self.slider):
            w.setEnabled(on)

    def _tick(self) -> None:
        if self._current + 1 > self._end or not self._show(self._current + 1):
            self.stop()

    def _on_slider(self, value: int) -> None:
        if value != self._current:
            self._show(value)

    def _show(self, index: int) -> bool:
        if self._reader is None:
            return False
        frame = self._reader.read(index)
        if frame is None:
            return False
        self._current = index
        self._last_raw = frame
        self._render(frame)
        self.slider.blockSignals(True)
        self.slider.setValue(index)
        self.slider.blockSignals(False)
        self._update_label()
        self.frameChanged.emit(index)
        return True

    def _update_label(self) -> None:
        fps = self._time_fps or self._reader.info.fps
        t = self._current / fps
        t_txt = f"{t:.2f} s" if t < 120 else f"{int(t // 60)} min {t % 60:04.1f} s"
        self.lbl.setText(f"cuadro {self._current} / {self._reader.info.frame_count - 1}   ·   t = {t_txt}")

    def _render(self, raw: Optional[np.ndarray]) -> None:
        if raw is None:
            return
        out = raw
        if self._transform is not None:
            try:
                out = self._transform(raw)
            except Exception as exc:  # keep UI alive on a bad op/param combo
                self.lbl.setText(f"Error de procesamiento: {exc}")
                out = raw
        self.view.set_frame(out)
