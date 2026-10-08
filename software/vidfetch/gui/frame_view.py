from __future__ import annotations

from typing import Optional

import cv2
import numpy as np
from PySide6.QtCore import QPointF, QRectF, Qt, Signal
from PySide6.QtGui import QColor, QImage, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import QWidget

from core.models import Roi


def ndarray_to_qimage(frame: np.ndarray) -> QImage:
    frame = np.ascontiguousarray(frame)
    h, w = frame.shape[:2]
    if frame.ndim == 2:
        img = QImage(frame.data, w, h, frame.strides[0], QImage.Format.Format_Grayscale8)
    else:
        rgb = np.ascontiguousarray(cv2.cvtColor(frame, cv2.COLOR_BGR2RGB))
        img = QImage(rgb.data, w, h, rgb.strides[0], QImage.Format.Format_RGB888)
    return img.copy()  # detach from the numpy buffer


class FrameView(QWidget):
    """Aspect-preserving frame display."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumSize(320, 240)
        self._image: Optional[QImage] = None

    def set_frame(self, frame: Optional[np.ndarray]) -> None:
        self._image = ndarray_to_qimage(frame) if frame is not None else None
        self.update()

    def _target_rect(self) -> QRectF:
        if self._image is None or self._image.width() == 0:
            return QRectF()
        iw, ih = self._image.width(), self._image.height()
        scale = min(self.width() / iw, self.height() / ih)
        w, h = iw * scale, ih * scale
        return QRectF((self.width() - w) / 2, (self.height() - h) / 2, w, h)

    def _scale(self) -> float:
        t = self._target_rect()
        return t.width() / self._image.width() if self._image is not None and t.width() > 0 else 1.0

    def widget_to_image(self, pos: QPointF) -> tuple[int, int]:
        t = self._target_rect()
        if self._image is None or t.isEmpty():
            return 0, 0
        s = self._scale()
        x = int(round((pos.x() - t.x()) / s))
        y = int(round((pos.y() - t.y()) / s))
        return min(max(0, x), self._image.width()), min(max(0, y), self._image.height())

    def paintEvent(self, event):
        p = QPainter(self)
        p.fillRect(self.rect(), QColor(24, 24, 24))
        if self._image is None:
            p.setPen(QColor(150, 150, 150))
            p.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, "Sin video")
            return
        target = self._target_rect()
        p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        p.drawImage(target, self._image)
        self._paint_overlay(p, target)

    def _paint_overlay(self, p: QPainter, target: QRectF) -> None:
        pass


class RoiFrameView(FrameView):
    """FrameView with mouse-drawn rectangular ROI selection."""

    roiChanged = Signal(object)  # Roi

    MIN_SIZE_PX = 4

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setCursor(Qt.CursorShape.CrossCursor)
        self._roi: Optional[Roi] = None
        self._drag_start: Optional[tuple[int, int]] = None
        self._drag_roi: Optional[Roi] = None

    def set_roi(self, roi: Optional[Roi]) -> None:
        self._roi = roi
        self.update()

    @staticmethod
    def _roi_from_points(a: tuple[int, int], b: tuple[int, int]) -> Roi:
        x0, x1 = sorted((a[0], b[0]))
        y0, y1 = sorted((a[1], b[1]))
        return Roi(x0, y0, x1 - x0, y1 - y0)

    def mousePressEvent(self, e):
        if e.button() == Qt.MouseButton.LeftButton and self._image is not None:
            self._drag_start = self.widget_to_image(e.position())
            self._drag_roi = None

    def mouseMoveEvent(self, e):
        if self._drag_start is not None:
            self._drag_roi = self._roi_from_points(self._drag_start, self.widget_to_image(e.position()))
            self.update()

    def mouseReleaseEvent(self, e):
        if e.button() != Qt.MouseButton.LeftButton or self._drag_start is None:
            return
        roi = self._drag_roi
        self._drag_start = self._drag_roi = None
        if roi is not None and roi.w >= self.MIN_SIZE_PX and roi.h >= self.MIN_SIZE_PX:
            self._roi = roi
            self.roiChanged.emit(roi)
        self.update()

    def _paint_overlay(self, p: QPainter, target: QRectF) -> None:
        roi = self._drag_roi or self._roi
        if roi is None:
            return
        s = self._scale()
        r = QRectF(target.x() + roi.x * s, target.y() + roi.y * s, roi.w * s, roi.h * s)
        shade = QPainterPath()
        shade.setFillRule(Qt.FillRule.OddEvenFill)
        shade.addRect(target)
        shade.addRect(r)
        p.fillPath(shade, QColor(0, 0, 0, 140))
        pen = QPen(QColor(255, 200, 0), 2, Qt.PenStyle.DashLine if self._drag_roi else Qt.PenStyle.SolidLine)
        p.setPen(pen)
        p.drawRect(r)


class ClickFrameView(FrameView):
    """FrameView that reports left clicks in (sub-pixel) image coordinates."""

    clicked = Signal(float, float)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setCursor(Qt.CursorShape.CrossCursor)

    def mousePressEvent(self, e):
        if e.button() != Qt.MouseButton.LeftButton or self._image is None:
            return
        t = self._target_rect()
        if not t.contains(e.position()):
            return
        s = self._scale()
        self.clicked.emit((e.position().x() - t.x()) / s, (e.position().y() - t.y()) / s)
