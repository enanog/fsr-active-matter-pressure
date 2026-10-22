"""Side panels that never scroll horizontally: tabbed pages with vertical-only scrolling.

Every page takes the width of the panel; long combo items are elided, form rows put the field under
its label when both do not fit, and labels wrap. Buttons and check boxes must keep short texts
(details go in their tooltips), since their text sets their minimum width.
"""
from __future__ import annotations

from typing import Sequence

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QComboBox, QFormLayout, QFrame, QLabel, QScrollArea, QTabWidget,
                               QVBoxLayout, QWidget)


def compact(root: QWidget, combo_chars: int = 10) -> None:
    """Let `root` and its children shrink to the panel width."""
    for cb in root.findChildren(QComboBox):
        cb.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon)
        cb.setMinimumContentsLength(combo_chars)
    for form in root.findChildren(QFormLayout):
        form.setRowWrapPolicy(QFormLayout.RowWrapPolicy.WrapLongRows)
        form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.AllNonFixedFieldsGrow)
    for lbl in root.findChildren(QLabel):
        if not lbl.pixmap() or lbl.pixmap().isNull():
            lbl.setWordWrap(True)


class VScrollArea(QScrollArea):
    """Scroll area with a vertical bar only; the content always fills the viewport width."""

    def __init__(self, content: QWidget, parent=None):
        super().__init__(parent)
        compact(content)
        self.setWidgetResizable(True)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setFrameShape(QFrame.Shape.NoFrame)
        self.setWidget(content)


def page(widgets: Sequence[QWidget], stretch_index: int = -1) -> VScrollArea:
    """Vertical stack of widgets in a vertical-only scroll area. `stretch_index` gets the spare height
    (e.g. a list); otherwise the spare height goes below the last widget."""
    content = QWidget()
    lay = QVBoxLayout(content)
    lay.setContentsMargins(4, 6, 4, 6)
    for i, w in enumerate(widgets):
        lay.addWidget(w, 1 if i == stretch_index else 0)
    if stretch_index < 0:
        lay.addStretch(1)
    return VScrollArea(content)


def tabbed_panel(pages: Sequence[tuple[str, QWidget]], width: int) -> QTabWidget:
    tabs = QTabWidget()
    tabs.setDocumentMode(True)
    tabs.setUsesScrollButtons(False)
    tabs.tabBar().setExpanding(True)
    for title, w in pages:
        tabs.addTab(w, title)
    tabs.setFixedWidth(width)
    return tabs
