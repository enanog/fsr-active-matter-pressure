"""FSRScope: analysis of the FSR pressure logs with synchronised video playback.

    python software/fsrscope/app.py [código o ruta a un registro]
    FSRScope.exe [código o ruta a un registro]
"""

import sys
from pathlib import Path

if __package__ in (None, ""):          # run as a script: put software/ on the path
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def main(argv=None) -> int:
    argv = sys.argv if argv is None else argv
    from PySide6.QtWidgets import QApplication
    from comun.repo import ensure_repo

    app = QApplication(argv)
    app.setApplicationName("FSRScope")
    app.setOrganizationName("ITBA")
    if not ensure_repo("FSRScope"):
        return 1
    from comun import paths
    from fsrscope.gui.main_window import MainWindow

    win = MainWindow()
    win.show()
    if len(argv) > 1:
        arg = argv[1]
        p = Path(arg)
        trial = paths.trial_from_path(p) if p.is_file() else next(
            (t for t in paths.discover_trials() if arg in t.code), None)
        if trial is not None:
            win.open_trial(trial)
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
