"""Background execution where only the latest request matters (stats while scrubbing/playing)."""

from __future__ import annotations

from concurrent.futures import Future, ThreadPoolExecutor
from typing import Any, Callable, Optional

from PySide6.QtCore import QObject, Signal, Slot


class LatestJobRunner(QObject):
    """Runs one job at a time; a request arriving while busy replaces any pending one."""

    finished = Signal(object, object)   # (tag, result)
    failed = Signal(object, str)        # (tag, message)
    _done = Signal(object, object)      # internal: (tag, future), crosses threads (queued)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._pool = ThreadPoolExecutor(max_workers=1)
        self._busy = False
        self._pending: Optional[tuple] = None
        self._done.connect(self._on_done)

    @property
    def busy(self) -> bool:
        return self._busy

    def submit(self, tag: Any, fn: Callable, *args) -> None:
        job = (tag, fn, args)
        if self._busy:
            self._pending = job
        else:
            self._start(job)

    def _start(self, job: tuple) -> None:
        tag, fn, args = job
        self._busy = True
        fut: Future = self._pool.submit(fn, *args)
        fut.add_done_callback(lambda f, tag=tag: self._done.emit(tag, f))

    @Slot(object, object)
    def _on_done(self, tag, fut: Future) -> None:
        self._busy = False
        exc = fut.exception()
        if exc is not None:
            self.failed.emit(tag, f"{type(exc).__name__}: {exc}")
        else:
            self.finished.emit(tag, fut.result())
        if self._pending is not None:
            job, self._pending = self._pending, None
            self._start(job)

    def shutdown(self) -> None:
        self._pending = None
        self._pool.shutdown(wait=False, cancel_futures=True)
