"""Velocidades: robot mobility from the VidFetch trajectories (V̄(t), speed distributions, jam
threshold, V̄ vs G, occupancy map) and the per-trial summary table. FSRScope (main.py) stays for
the pressure analysis with video; both share core/.

    python software/fsrscope/velocidades.py                   # interfaz
    python software/fsrscope/velocidades.py 20263010_1600     # abre directamente ese ensayo
    python software/fsrscope/velocidades.py --resumen [CSV]   # solo el resumen por ensayo
                                                              # (por defecto datos/resumen_ensayos.csv)
"""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("ensayo", nargs="?", help="código (o parte del código) del ensayo a abrir")
    ap.add_argument("--resumen", nargs="?", const="", default=None, metavar="CSV",
                    help="escribir el resumen por ensayo sin abrir la interfaz")
    args = ap.parse_args()

    if args.resumen is not None:
        from core.summary import write_summary
        write_summary(Path(args.resumen) if args.resumen else None)
        return 0

    from PySide6.QtCore import Qt
    from PySide6.QtWidgets import QApplication
    from gui.vel_window import VelWindow

    app = QApplication(sys.argv)
    app.setApplicationName("Velocidades")
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
