"""Batch processing of raw FSR logs -> datos/presion/procesados/P_<code>.csv (used by FSRScope's
"Procesar todos los registros" and by herramientas/procesar_lote.py).

Uses, per trial, the parameters saved from FSRScope (datos/presion/config/<code>.json); trials
never opened there get the defaults (automatic calibration from the firmware factor, no crop).
"""

from __future__ import annotations

from pathlib import Path
from typing import Callable, Optional

from comun import paths
from comun.session import TrialData


def run_batch(trials, out_dir: Optional[Path] = None, log: Callable[[str], None] = print) -> int:
    """Process `trials` into out_dir (default datos/presion/procesados); one line per trial
    through `log`. Returns the number processed without error."""
    out_dir = Path(out_dir) if out_dir is not None else paths.PROC_DIR
    ok = 0
    for tr in trials:
        try:
            td = TrialData.open(tr, load_trajectories=True)
            out, df = td.export(out_dir / f"P_{tr.code}.csv")
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
