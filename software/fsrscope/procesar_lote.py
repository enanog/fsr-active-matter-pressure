"""Batch processing of every raw FSR log -> datos/presion/procesados/P_<code>.csv.

Uses, per trial, the parameters saved from the GUI (datos/presion/config/<code>.json); trials
never opened in the GUI get the defaults (automatic calibration from the firmware factor, no
crop). Replaces the former software/analisis_presion/procesar_presion_ventanas.py.

    python software/fsrscope/procesar_lote.py                 # every trial
    python software/fsrscope/procesar_lote.py 20262509_1500   # only codes containing this text
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from core import paths  # noqa: E402
from core.session import TrialData  # noqa: E402


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


def run_batch(trials, out_dir: Path = paths.PROC_DIR, log=print) -> int:
    """Process `trials` into out_dir; reports one line per trial through `log`. Returns #OK."""
    ok = 0
    for tr in trials:
        try:
            td = TrialData.open(tr, load_trajectories=True)
            out, df = td.export(Path(out_dir) / f"P_{tr.code}.csv")
            s = td.series
            cfg = "config guardada" if paths.config_path(tr).is_file() else "por defecto"
            log(f"OK   {tr.code}: {len(df)} filas, K = {s.k_us:.4f} µS/cuenta ({s.k_source}, "
                f"R_FB ≈ {s.r_feedback_eff:.0f} Ω), {cfg}"
                + (f" | aviso: {'; '.join(td.raw.warnings)}" if td.raw.warnings else ""))
            ok += 1
        except Exception as exc:  # keep processing the remaining trials
            log(f"FAIL {tr.code}: {exc}")
    log(f"{ok} OK, {len(trials) - ok} con error, de {len(trials)}.")
    return ok


if __name__ == "__main__":
    sys.exit(main())
