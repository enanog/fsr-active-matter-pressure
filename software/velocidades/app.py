"""Velocidades: robot mobility from the VidFetch trajectories (V̄(t), speed distributions, jam
threshold, V̄ vs G, occupancy map) and the per-trial summary table.

    python software/velocidades/app.py                   # interfaz
    python software/velocidades/app.py 20261030_1600     # abre directamente ese ensayo
    python software/velocidades/app.py --resumen [CSV]   # solo el resumen por ensayo
                                                         # (por defecto datos/resumen_ensayos.csv)
    Velocidades.exe [ensayo]
"""

import argparse
import sys
from pathlib import Path

if __package__ in (None, ""):          # run as a script: put software/ on the path
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("ensayo", nargs="?", help="código (o parte del código) del ensayo a abrir")
    ap.add_argument("--resumen", nargs="?", const="", default=None, metavar="CSV",
                    help="escribir el resumen por ensayo sin abrir la interfaz")
    args = ap.parse_args(argv)

    if args.resumen is not None:
        from comun.summary import write_summary
        write_summary(Path(args.resumen) if args.resumen else None)
        return 0

    from PySide6.QtCore import Qt
    from PySide6.QtWidgets import QApplication
    from comun.qt.repo import ensure_repo

    app = QApplication(sys.argv[:1])
    app.setApplicationName("Velocidades")
    app.setOrganizationName("ITBA")
    if not ensure_repo("Velocidades"):
        return 1
    from velocidades.gui.vel_window import VelWindow

    win = VelWindow()
    win.show()
    if args.ensayo:
        for i in range(win.list.count()):
            it = win.list.item(i)
            if args.ensayo in it.data(Qt.ItemDataRole.UserRole).code:
                win.list.setCurrentRow(i)
                win._pick(it)
                break
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
