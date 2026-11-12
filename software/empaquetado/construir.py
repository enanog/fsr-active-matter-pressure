"""Build one Windows executable per app with PyInstaller.

    pip install -r software/requirements.txt -r software/empaquetado/requirements-build.txt
    python software/empaquetado/construir.py                      # las cuatro apps
    python software/empaquetado/construir.py fsrscope velocidades # solo esas
    python software/empaquetado/construir.py comparador --onefile # un único .exe (arranca más lento)

Output: software/empaquetado/dist/<App>/<App>.exe (one folder per app: copy the whole folder).
Leaving the folder inside the repository lets the app find datos/ on its own; anywhere else it asks
for the project folder once (or set the PRESION_REPO environment variable).

Why one folder per app (default) and not --onefile: PySide6 + OpenCV + SciPy weigh 300-500 MB;
a one-file exe unpacks all of it to a temp folder on every start (10-30 s), a folder starts at once.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
SOFTWARE = HERE.parent

COMMON_EXCLUDES = ["tkinter", "IPython", "jupyter_client", "ipykernel", "notebook", "pytest",
                   "PyQt5", "PyQt6", "PySide2", "sphinx", "numba", "llvmlite", "gi"]
QT_UNUSED = ["PySide6.QtWebEngineCore", "PySide6.QtWebEngineWidgets", "PySide6.QtWebEngineQuick",
             "PySide6.Qt3DCore", "PySide6.Qt3DRender", "PySide6.QtQuick3D", "PySide6.QtCharts",
             "PySide6.QtDataVisualization", "PySide6.QtGraphs", "PySide6.QtPdf", "PySide6.QtLocation",
             "PySide6.QtBluetooth", "PySide6.QtNfc", "PySide6.QtSensors", "PySide6.QtSerialPort",
             "PySide6.QtMultimedia", "PySide6.QtQuick", "PySide6.QtQml", "PySide6.QtDesigner"]

APPS = {
    # name: (exe name, extra excludes, extra PyInstaller args)
    "vidfetch": ("VidFetch", ["pyqtgraph"], ["--collect-submodules", "trackpy"]),
    "fsrscope": ("FSRScope", ["trackpy", "matplotlib"], []),
    "velocidades": ("Velocidades", ["trackpy", "matplotlib"], []),
    "comparador": ("Comparador", ["trackpy"], []),
}


def build(app: str, onefile: bool, clean: bool) -> Path:
    import PyInstaller.__main__
    exe, excludes, extra = APPS[app]
    args = [str(HERE / "lanzadores" / f"lanzar_{app}.py"),
            "--name", exe, "--windowed", "--noconfirm",
            "--paths", str(SOFTWARE),
            "--distpath", str(HERE / "dist"),
            "--workpath", str(HERE / "build"),
            "--specpath", str(HERE / "build"),
            "--onefile" if onefile else "--onedir"]
    icon = HERE / "iconos" / f"{app}.ico"
    if icon.is_file():
        args += ["--icon", str(icon)]
    if clean:
        args.append("--clean")
    for m in COMMON_EXCLUDES + QT_UNUSED + excludes:
        args += ["--exclude-module", m]
    args += extra
    PyInstaller.__main__.run(args)
    return HERE / "dist" / (exe if not onefile else "")


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("apps", nargs="*", choices=[[], *APPS], default=[], metavar="app",
                    help=f"apps a construir ({', '.join(APPS)}); vacío = todas")
    ap.add_argument("--onefile", action="store_true", help="un único .exe por app")
    ap.add_argument("--limpiar", action="store_true", help="borrar la caché de PyInstaller antes")
    a = ap.parse_args(argv)
    try:
        import PyInstaller  # noqa: F401
    except ImportError:
        print("Falta PyInstaller: pip install -r software/empaquetado/requirements-build.txt")
        return 1
    done = []
    for app in a.apps or list(APPS):
        print(f"\n=== {app} ===")
        done.append(build(app, a.onefile, a.limpiar))
    print("\nListo:", *done, sep="\n  ")
    return 0


if __name__ == "__main__":
    sys.exit(main())
