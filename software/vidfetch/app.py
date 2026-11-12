"""VidFetch: crop arena videos and track the robots (position, velocity, θ, ω).

    python software/vidfetch/app.py [video]
    VidFetch.exe [video]
"""

import sys
from pathlib import Path

if __package__ in (None, ""):          # run as a script: put software/ on the path
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def main(argv=None) -> int:
    import multiprocessing
    multiprocessing.freeze_support()   # no-op unless frozen (PyInstaller) and spawning
    argv = sys.argv if argv is None else argv
    from PySide6.QtWidgets import QApplication
    from vidfetch.gui.main_window import MainWindow

    app = QApplication(argv)
    app.setApplicationName("VidFetch")
    app.setOrganizationName("ITBA")
    win = MainWindow()
    win.show()
    if len(argv) > 1:
        win.open_video(argv[1])
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
