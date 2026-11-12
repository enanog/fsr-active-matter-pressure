"""Batch processing of every raw FSR log -> datos/presion/procesados/P_<code>.csv, with the
parameters saved from FSRScope (same as its "Procesar todos los registros").

    python software/herramientas/procesar_lote.py                 # every trial
    python software/herramientas/procesar_lote.py 20260925_1500   # only codes containing this text
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))   # software/: comun, vidfetch, ...
from comun import paths  # noqa: E402
from comun.lote import run_batch  # noqa: E402


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("filtro", nargs="*", help="procesar solo los códigos que contengan este texto")
    ap.add_argument("--crudos", type=Path, default=paths.RAW_DIR, help="carpeta de registros crudos")
    ap.add_argument("--salida", type=Path, default=paths.PROC_DIR, help="carpeta de salida")
    args = ap.parse_args(argv)

    trials = paths.discover_trials(args.crudos)
    if args.filtro:
        trials = [t for t in trials if any(f in t.code for f in args.filtro)]
    if not trials:
        print(f"No se encontraron registros con código válido en '{args.crudos}'.")
        return 1
    ok = run_batch(trials, args.salida, print)
    return 0 if ok == len(trials) else 2


if __name__ == "__main__":
    sys.exit(main())
