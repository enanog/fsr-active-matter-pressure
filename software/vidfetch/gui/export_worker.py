from __future__ import annotations

from typing import Any, Callable

from PySide6.QtCore import QThread, Signal


class TaskWorker(QThread):
    """Runs `func(progress=..., should_cancel=..., **kwargs) -> (result, cancelled)` off the GUI thread.

    kwargs must be value snapshots (no live widgets).
    """

    progress = Signal(int)
    succeeded = Signal(object)
    cancelled = Signal()
    failed = Signal(str)

    def __init__(self, func: Callable[..., tuple[Any, bool]], parent=None, **kwargs):
        super().__init__(parent)
        self._func = func
        self._kwargs = kwargs

    def run(self) -> None:
        try:
            result, was_cancelled = self._func(progress=self.progress.emit,
                                               should_cancel=self.isInterruptionRequested,
                                               **self._kwargs)
        except Exception as exc:
            self.failed.emit(f"{type(exc).__name__}: {exc}")
            return
        if was_cancelled:
            self.cancelled.emit()
        else:
            self.succeeded.emit(result)
