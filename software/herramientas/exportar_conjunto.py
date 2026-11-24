"""Group averages per frame from already exported trajectories: VP_<code>_robots.csv -> VP_<code>_conjunto.csv.

Usage (from the repository root):
    python software/herramientas/exportar_conjunto.py                 # every VP_*_robots.csv of datos/video/trayectorias
    python software/herramientas/exportar_conjunto.py 20261117        # only the files whose name contains a text
    python software/herramientas/exportar_conjunto.py ruta/a/X_robots.csv --forzar

Writes next to every robots CSV:
    VP_<code>_conjunto.csv          one row per frame (columns in vidfetch/core/conjunto.py, COLUMNS)
    VP_<code>_conjunto_info.json    time base, robot diameter, wall-layer radius, column descriptions
Skips files whose _conjunto.csv is newer than the robots CSV (unless --forzar). VidFetch writes the same files
when it exports the CSV with every robot, and reexportar.py too.
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))   # software/: comun, vidfetch, ...
import pandas as pd  # noqa: E402

from comun.paths import REPO_ROOT as ROOT  # noqa: E402
from vidfetch.core import conjunto as cj  # noqa: E402

CARPETA = Path(ROOT) / "datos" / "video" / "trayectorias"


def archivos(filtros: list[str]) -> list[Path]:
    rutas = [Path(f) for f in filtros if f.lower().endswith(".csv")]
    textos = [f for f in filtros if not f.lower().endswith(".csv")]
    if rutas:
        return rutas
    todos = sorted(CARPETA.glob("VP_*_robots.csv"))
    return [p for p in todos if not textos or any(t in p.name for t in textos)]


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("filtros", nargs="*", help="textos del nombre (código) o rutas a *_robots.csv")
    ap.add_argument("--forzar", action="store_true", help="regenerar aunque el _conjunto.csv esté al día")
    ap.add_argument("--diametro-robot", type=float, help="diámetro del robot [mm] (def. el del _info.json o 33)")
    ap.add_argument("--k-inercia", type=float, default=cj.K_INERTIA, help="I = k m R^2 (def. 0,5: disco)")
    a = ap.parse_args()

    lista = archivos(a.filtros)
    if not lista:
        sys.exit(f"Ningún *_robots.csv coincide en {CARPETA}.")
    for p in lista:
        dst = cj.ensemble_path(p)
        if not a.forzar and dst.is_file() and dst.stat().st_mtime >= p.stat().st_mtime:
            print(f"{dst.name}: al día (usá --forzar para regenerarlo)")
            continue
        t0 = time.perf_counter()
        info_p = p.with_name(p.stem + "_info.json")
        info = json.loads(info_p.read_text(encoding="utf-8")) if info_p.is_file() else {}
        if not info:
            print(f"  aviso: {info_p.name} no existe (sin base de tiempo ni capa de pared en el _info)")
        df = pd.read_csv(p, low_memory=False)
        out = cj.write_ensemble(df, p, info, a.diametro_robot, k_inertia=a.k_inercia)
        n = sum(1 for _ in open(out, encoding="utf-8")) - 1
        print(f"{out.name}: {n} cuadros ({time.perf_counter() - t0:.1f} s)")


if __name__ == "__main__":
    main()
