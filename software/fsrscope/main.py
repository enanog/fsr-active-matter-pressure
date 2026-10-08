"""FSRScope: analysis of the FSR pressure logs with synchronised video playback.

    python software/fsrscope/main.py [código o ruta a un registro]
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from PySide6.QtWidgets import QApplication  # noqa: E402

from core import paths  # noqa: E402
from gui.main_window import MainWindow  # noqa: E402


def main() -> int:
    app = QApplication(sys.argv)
    app.setApplicationName("FSRScope")
    win = MainWindow()
    win.show()
    if len(sys.argv) > 1:
        arg = sys.argv[1]
        p = Path(arg)
        trial = paths.trial_from_path(p) if p.is_file() else next(
            (t for t in paths.discover_trials() if arg in t.code), None)
        if trial is not None:
            win.open_trial(trial)
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
