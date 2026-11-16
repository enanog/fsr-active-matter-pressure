"""Small widget factories shared by the GUI apps."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QDoubleSpinBox, QLabel


def dspin(lo: float, hi: float, dec: int, step: float, suffix: str = "", tip: str = "") -> QDoubleSpinBox:
    w = QDoubleSpinBox()
    w.setRange(lo, hi)
    w.setDecimals(dec)
    w.setSingleStep(step)
    w.setKeyboardTracking(False)        # emit on Enter / focus-out / arrows, not every keystroke
    if suffix:
        w.setSuffix(" " + suffix)
    if tip:
        w.setToolTip(tip)
    return w


def note(text: str = "") -> QLabel:
    lab = QLabel(text)
    lab.setWordWrap(True)
    lab.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
    lab.setStyleSheet("color:#444;")
    return lab
