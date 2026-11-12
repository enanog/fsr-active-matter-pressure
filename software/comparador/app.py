"""Comparador: overlay of several trials with common parameters (V̄(t), ⟨|ω|⟩(t), kinetic energy,
speed distributions, G vs V̄, summary table) and export of report-ready figures.

    python software/comparador/app.py
    Comparador.exe
"""

import sys
from pathlib import Path

if __package__ in (None, ""):          # run as a script: put software/ on the path
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def main(argv=None) -> int:
    argv = sys.argv if argv is None else argv
    from PySide6.QtWidgets import QApplication
    from comun.qt.repo import ensure_repo

    app = QApplication(argv)
    app.setApplicationName("Comparador")
    app.setOrganizationName("ITBA")
    if not ensure_repo("Comparador"):
        return 1
    from comparador.gui.window import ComparadorWindow

    win = ComparadorWindow()
    win.show()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
