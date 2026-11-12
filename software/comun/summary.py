"""One row per trial with the mean values of speed, jams, pressure and occupancy
(datos/resumen_ensayos.csv). Every trial uses its own saved settings: the window and speed
threshold of velocidades.py (datos/video/config/) and the calibration, crop and excluded spans of
FSRScope (datos/presion/config/) for G.
"""

from __future__ import annotations

import re
import warnings
from pathlib import Path
from typing import Callable, Optional

import numpy as np
import pandas as pd

from comun import paths
from comun.mobility import MobilityData, frame_mask, vel_config_path, wall_layer
from comun.signal import analysis_mask
from comun.stats import compute_stats, moments

CODE_PARTS = re.compile(r"^(\d{8})_(\d{4})_(\d{2})([A-Z]{1,2})_(\d{2})$", re.IGNORECASE)


def date_key(code: str) -> tuple:
    """(year, month, day, hhmm) from a code AAAAMMDD_HHMM_..."""
    m = CODE_PARTS.match(code)
    if not m:
        return (9999, 99, 99, code)
    d = m.group(1)
    return (int(d[:4]), int(d[4:6]), int(d[6:8]), m.group(2))


def _f(v) -> float:
    try:
        v = float(v)
    except (TypeError, ValueError):
        return np.nan
    return v if np.isfinite(v) else np.nan


def summarize(md: MobilityData) -> dict:
    tr, r, mob = md.trial, md.robots, md.settings.mobility
    m = CODE_PARTS.match(tr.code)
    ks, jm = md.stats(), md.jams
    rows = frame_mask(md.frame_times, md.window()) & jm.valid
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", category=RuntimeWarning)
        vi = r.speed_mm_s[rows]
        if r.observed is not None:
            vi = vi[r.observed[rows]]
        vi = vi[np.isfinite(vi)]
        r_mean, wall = wall_layer(r, rows)
        row: dict = {
            "codigo": tr.code,
            "ensayo": tr.label,
            "n_robots": int(m.group(3)) if m else np.nan,
            "modo": m.group(4).upper() if m else "",
            "minutos_nominales": int(m.group(5)) if m else np.nan,
            "video_partido": int(len(r.parts) > 1),
            "ventana_desde_min": md.settings.t_start_min if md.settings.t_start_min is not None else 0.0,
            "ventana_hasta_min": md.settings.t_end_min if md.settings.t_end_min is not None else md.duration_min,
            "minutos_video_usados": rows.sum() / md.fps / 60,
            "cuadros_por_s": md.fps,
            # speed
            "v_media_mm_s": _f(ks.v_mean),
            "v_media_desvio_temporal_mm_s": _f(ks.v_std),
            "v_mediana_entre_robots_media_mm_s": _f(np.nanmean(r.v_median[rows])),
            "v_p90_entre_robots_media_mm_s": _f(np.nanmean(r.v_p90[rows])),
            "v_individual_media_mm_s": float(vi.mean()) if len(vi) else np.nan,
            "v_individual_mediana_mm_s": float(np.median(vi)) if len(vi) else np.nan,
            # jams
            "umbral_estadistico": mob.statistic,
            "umbral_mm_s": mob.v_threshold_mm_s,
            "umbral_suavizado_s": mob.smooth_s,
            "umbral_duracion_min_s": mob.min_duration_s,
            "frac_tiempo_atasco": _f(ks.jam_frac),
            "n_atascos": ks.n_jams,
            "atasco_dur_media_s": float(ks.jam_dur_s.mean()) if len(ks.jam_dur_s) else 0.0,
            "atasco_dur_max_s": float(ks.jam_dur_s.max()) if len(ks.jam_dur_s) else 0.0,
            "v_media_fluido_mm_s": _f(ks.v_mean_fluid),
            "v_media_atasco_mm_s": _f(ks.v_mean_jam),
            # rotation and kinetic energy of the set (I = k m R²)
            "omega_abs_media_deg_s": _f(ks.w_mean),
            "energia_unidad": md.energy_unit,
            "masa_g": md.settings.mass_g if md.settings.mass_g > 0 else np.nan,
            "k_inercia": md.settings.k_inertia,
            "E_traslacion_media": _f(ks.e_tr),
            "E_rotacion_media": _f(ks.e_rot),
            "E_total_media": _f(ks.e_tr + ks.e_rot),
            "E_rot_sobre_E_tras": _f(ks.e_rot / ks.e_tr) if ks.e_tr else np.nan,
            # occupancy
            "r_media_mm": _f(r_mean),
            "frac_capa_pared": _f(wall),
        }

    # --- pressure (FSRScope calibration, crop and exclusions, narrowed to the window) ----------
    pa = md.pressure_analysis()
    if md.td is not None and pa is not None:
        s = md.td.series
        st = compute_stats(s, pa, None, sweep=False)
        g = s.G[analysis_mask(s, pa)]
        dg = st.deltaG[np.isfinite(st.deltaG)]
        skew, kurt = moments(dg) if len(dg) > 3 else (np.nan, np.nan)
        row.update({
            "minutos_sensor_usados": st.n_used * s.step_s / 60,
            "G_media_uS": _f(st.G_mean), "G_desvio_uS": _f(st.G_std),
            "G_mediana_uS": float(np.median(g)) if len(g) else np.nan,
            "G_media_fluido_uS": _f(ks.G_fluid), "G_media_atasco_uS": _f(ks.G_jam),
            "G_mediana_fluido_uS": _f(ks.G_med_fluid), "G_mediana_atasco_uS": _f(ks.G_med_jam),
            "frac_saturado": _f(st.sat_frac),
            "deltaT_s": pa.deltaT_fixed_s, "asimetria_dG": _f(skew), "curtosis_dG": _f(kurt),
            "K_uS_por_cuenta": s.k_us, "R_FB_equivalente_ohm": s.r_feedback_eff,
        })
    row["config_velocidades"] = "guardada" if vel_config_path(tr).is_file() else "por defecto"
    row["config_presion"] = "guardada" if paths.config_path(tr).is_file() else "por defecto"
    if md.pressure_error:
        row["aviso"] = f"sin presión: {md.pressure_error}"
    return row


def trials_with_trajectories() -> list:
    return sorted((t for t in paths.discover_trials() if t.traj_path is not None), key=lambda t: date_key(t.code))


def build_summary(trials: Optional[list] = None, log: Callable[[str], None] = print,
                  current: Optional[MobilityData] = None) -> pd.DataFrame:
    """current: the trial open in the GUI, used as is (unsaved changes included)."""
    out = []
    for tr in trials if trials is not None else trials_with_trajectories():
        try:
            md = current if current is not None and current.trial == tr else MobilityData.open(tr)
            out.append(summarize(md))
            log(f"OK   {tr.code}: V̄ = {out[-1]['v_media_mm_s']:.3f} mm/s, "
                f"atasco {100 * out[-1]['frac_tiempo_atasco']:.1f} %")
        except Exception as exc:     # keep going with the remaining trials
            log(f"FAIL {tr.code}: {exc}")
    return pd.DataFrame(out)


def write_summary(path: Optional[Path] = None, log: Callable[[str], None] = print,
                  trials: Optional[list] = None, current: Optional[MobilityData] = None):
    path = Path(path or paths.SUMMARY_PATH)
    df = build_summary(trials, log, current)
    path.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(path, index=False, float_format="%.6g")
    log(f"Resumen: {len(df)} ensayos → {path}")
    return path, df
