"""Ensemble (whole-group) averages per frame, computed from the long robots table.

One row per frame of `<video>_robots.csv` -> `<video>_conjunto.csv`, so that later analysis (MATLAB
`cargar_datos.m`, spreadsheets) can read the group series directly instead of re-averaging ~250k rows.

Conventions (same as the long table and as `cargar_datos.m` before this file existed):
  * Means are over ALL robots of the frame (detected, manual and interpolated), NaN left out; the
    columns `n_*` say how many robots entered.  `N` = rows of that frame in the long table.
  * Time base = the one of the export (`t_s = frame / cuadros_por_segundo_real` of the _info.json).
    Columns ending in _mm_s, _deg_s, _rad_s scale with 1/f and _mm2_s2, _rad2_s2, _uJ_kg with 1/f^2
    if the time base is corrected afterwards (cargar_datos.m does it for 3.0 -> 2.997 frames/s).
  * Energies per unit mass [mm^2/s^2 = uJ/kg]: E_tras = N <v^2>/2, E_rot = N k R^2 <w^2>/2 (Koenig;
    the orbital motion is already in v), R = robot diameter / 2, k = I / (m R^2).
Only numpy and pandas: usable without the GUI (software/herramientas/exportar_conjunto.py).
"""
from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Optional

import numpy as np
import pandas as pd

OBSERVED_LABELS = ("detectado", "detectado (umbral relajado)", "manual")
MOVING_MM_S = 1.0          # |v| above this enters the polar order (direction of a robot at rest is noise)
K_INERTIA = 0.5            # uniform disc

# column -> description (written to the _info.json of the ensemble file, in this order)
COLUMNS = {
    "frame": "cuadro del video analizado",
    "t_s": "tiempo [s] con la base de tiempo de la exportación (cuadro / cuadros_por_segundo_real)",
    "N": "robots en el cuadro (filas de la tabla larga)",
    "n_observados": "robots detectados o corregidos a mano (no interpolados ni predichos)",
    "n_v": "robots con velocidad (entran en las medias de v)",
    "V_media_mm_s": "media de |v| de los robots [mm/s]",
    "V_mediana_mm_s": "mediana de |v| [mm/s]",
    "V_p10_mm_s": "percentil 10 de |v| [mm/s]",
    "V_p90_mm_s": "percentil 90 de |v| [mm/s]",
    "V_desvio_mm_s": "desvío estándar de |v| entre robots (n-1) [mm/s]",
    "v2_media_mm2_s2": "media de v^2 [mm^2/s^2]",
    "vx_media_mm_s": "media de vx (velocidad del centro de masa) [mm/s]",
    "vy_media_mm_s": "media de vy [mm/s]",
    "orden_polar": "|media de v/|v|| de los robots con |v| > 1 mm/s (0 desordenado, 1 todos en la misma dirección)",
    "n_moviles": "robots con |v| > 1 mm/s (entran en orden_polar)",
    "omega_media_deg_s": "media de omega con signo [°/s] (> 0 antihorario)",
    "omega_abs_media_deg_s": "media de |omega| [°/s]",
    "w2_media_rad2_s2": "media de omega^2 [rad^2/s^2]",
    "n_omega": "robots con omega",
    "r_media_mm": "media de la distancia al centro del recinto [mm]",
    "v_tan_media_mm_s": "media de la velocidad tangencial (> 0 antihoraria alrededor del centro) [mm/s]",
    "v_rad_media_mm_s": "media de la velocidad radial (> 0 hacia afuera) [mm/s]",
    "Omega_grupo_rad_s": "rotación rígida del grupo sum(x vy - y vx) / sum(r^2) [rad/s] (> 0 antihoraria)",
    "n_pared": "robots en la capa de la pared (r >= r_contacto - D/2)",
    "E_tras_uJ_kg": "energía cinética de traslación por unidad de masa N <v^2>/2 [uJ/kg = mm^2/s^2]",
    "E_rot_uJ_kg": "energía cinética de rotación por unidad de masa N k R^2 <omega^2>/2 [uJ/kg]",
    "E_total_uJ_kg": "E_tras + E_rot [uJ/kg]",
}


def _col(df: pd.DataFrame, *names: str) -> Optional[np.ndarray]:
    for n in names:
        if n in df.columns:
            return pd.to_numeric(df[n], errors="coerce").to_numpy(float)
    return None


def wall_threshold_from_info(info: dict, robot_diameter_mm: float) -> float:
    """r [mm] of the wall layer from an export _info.json (NaN if the enclosure is unknown)."""
    try:
        rec = info.get("recinto") or {}
        rel = float(info["r_contacto_sobre_r_int"])
        kappa = float(info.get("kappa_perspectiva_aplicado", 1.0))
        r_contact = rel * float(rec.get("d_int_mm", 185.0)) / 2.0 * kappa
        return r_contact - robot_diameter_mm / 2.0
    except (KeyError, TypeError, ValueError):
        return float("nan")


def ensemble_table(long_df: pd.DataFrame, robot_diameter_mm: float = 33.0, k_inertia: float = K_INERTIA,
                   r_wall_mm: float = float("nan")) -> pd.DataFrame:
    """One row per frame with the group averages (see COLUMNS). long_df = kinematics.table() or the CSV."""
    if long_df.empty:
        return pd.DataFrame(columns=list(COLUMNS))
    frame = pd.to_numeric(long_df["frame"], errors="coerce").to_numpy()
    if np.isnan(frame).any():
        raise ValueError("La tabla tiene filas sin número de cuadro.")
    frames, inv = np.unique(frame.astype(np.int64), return_inverse=True)
    F = len(frames)

    def count(mask: np.ndarray) -> np.ndarray:
        return np.bincount(inv, weights=mask.astype(float), minlength=F)

    def mean(v: Optional[np.ndarray]) -> np.ndarray:
        if v is None:
            return np.full(F, np.nan)
        ok = np.isfinite(v)
        n = count(ok)
        s = np.bincount(inv, weights=np.where(ok, v, 0.0), minlength=F)
        with np.errstate(invalid="ignore", divide="ignore"):
            return np.where(n > 0, s / n, np.nan)

    t = _col(long_df, "t_s")
    speed = _col(long_df, "speed_mm_s")
    vx, vy = _col(long_df, "vx_mm_s"), _col(long_df, "vy_mm_s")
    if speed is None and vx is not None and vy is not None:
        speed = np.hypot(vx, vy)
    if speed is None:
        raise ValueError("La tabla no tiene velocidades en mm/s (speed_mm_s): falta la escala del recinto.")
    om = _col(long_df, "omega_deg_s")
    if om is None:
        om_rad = _col(long_df, "omega_rad_s")
        om = np.degrees(om_rad) if om_rad is not None else None
    x, y = _col(long_df, "x_mm"), _col(long_df, "y_mm")
    r = _col(long_df, "r_mm")
    if r is None and x is not None and y is not None:
        r = np.hypot(x, y)

    out = pd.DataFrame({"frame": frames, "t_s": mean(t)})
    out["N"] = np.bincount(inv, minlength=F)
    if "status" in long_df.columns:
        out["n_observados"] = count(long_df["status"].astype(str).isin(OBSERVED_LABELS).to_numpy())
    else:
        out["n_observados"] = np.nan
    out["n_v"] = count(np.isfinite(speed))
    out["V_media_mm_s"] = mean(speed)
    # quantiles / std per frame (pandas groupby skips NaN)
    g = pd.Series(speed).groupby(inv)
    out["V_mediana_mm_s"] = g.median().reindex(range(F)).to_numpy()
    out["V_p10_mm_s"] = g.quantile(0.10).reindex(range(F)).to_numpy()
    out["V_p90_mm_s"] = g.quantile(0.90).reindex(range(F)).to_numpy()
    out["V_desvio_mm_s"] = g.std(ddof=1).reindex(range(F)).to_numpy()
    out["v2_media_mm2_s2"] = mean(speed ** 2)
    out["vx_media_mm_s"] = mean(vx)
    out["vy_media_mm_s"] = mean(vy)
    if vx is not None and vy is not None:
        moving = np.isfinite(speed) & (speed > MOVING_MM_S)
        with np.errstate(invalid="ignore", divide="ignore"):
            ux, uy = np.where(moving, vx / speed, np.nan), np.where(moving, vy / speed, np.nan)
        out["orden_polar"] = np.hypot(mean(ux), mean(uy))
        out["n_moviles"] = count(moving)
    else:
        out["orden_polar"], out["n_moviles"] = np.nan, 0.0
    out["omega_media_deg_s"] = mean(om)
    out["omega_abs_media_deg_s"] = mean(np.abs(om) if om is not None else None)
    out["w2_media_rad2_s2"] = mean(np.radians(om) ** 2 if om is not None else None)
    out["n_omega"] = count(np.isfinite(om)) if om is not None else 0.0
    out["r_media_mm"] = mean(r)
    out["v_tan_media_mm_s"] = mean(_col(long_df, "v_tan_mm_s"))
    out["v_rad_media_mm_s"] = mean(_col(long_df, "v_rad_mm_s"))
    if x is not None and y is not None and vx is not None and vy is not None:
        ok = np.isfinite(x) & np.isfinite(y) & np.isfinite(vx) & np.isfinite(vy)
        num = np.bincount(inv, weights=np.where(ok, x * vy - y * vx, 0.0), minlength=F)
        den = np.bincount(inv, weights=np.where(ok, x * x + y * y, 0.0), minlength=F)
        with np.errstate(invalid="ignore", divide="ignore"):
            out["Omega_grupo_rad_s"] = np.where(den > 0, num / den, np.nan)
    else:
        out["Omega_grupo_rad_s"] = np.nan
    out["n_pared"] = count(np.isfinite(r) & (r >= r_wall_mm)) if (r is not None and math.isfinite(r_wall_mm)) \
        else np.nan
    R = robot_diameter_mm / 2.0
    out["E_tras_uJ_kg"] = out["N"] * out["v2_media_mm2_s2"] / 2.0
    out["E_rot_uJ_kg"] = out["N"] * k_inertia * R ** 2 * out["w2_media_rad2_s2"] / 2.0
    out["E_total_uJ_kg"] = out["E_tras_uJ_kg"] + out["E_rot_uJ_kg"]
    for c in ("N", "n_observados", "n_v", "n_moviles", "n_omega", "n_pared"):
        if out[c].notna().all():
            out[c] = out[c].astype(np.int64)
    return out[list(COLUMNS)]


def ensemble_path(robots_csv: str | Path) -> Path:
    """<x>_robots.csv -> <x>_conjunto.csv (any other name: <stem>_conjunto.csv)."""
    p = Path(robots_csv)
    stem = p.stem[:-len("_robots")] if p.stem.endswith("_robots") else p.stem
    return p.with_name(stem + "_conjunto.csv")


def ensemble_info(info: dict, robot_diameter_mm: float, k_inertia: float, r_wall_mm: float,
                  source: str) -> dict:
    return {"fuente": source,
            "cuadros_por_segundo_real": info.get("cuadros_por_segundo_real"),
            "video": info.get("video"),
            "diametro_robot_mm": robot_diameter_mm,
            "k_inercia": k_inertia,
            "r_capa_pared_mm": None if not math.isfinite(r_wall_mm) else r_wall_mm,
            "umbral_movil_mm_s": MOVING_MM_S,
            "convencion": "una fila por cuadro; medias sobre todos los robots del cuadro (detectados, manuales e "
                          "interpolados) sin NaN; misma base de tiempo y orientación que la tabla por robot",
            "columnas": COLUMNS}


def write_ensemble(long_df: pd.DataFrame, robots_csv: str | Path, info: Optional[dict] = None,
                   robot_diameter_mm: Optional[float] = None, r_wall_mm: Optional[float] = None,
                   k_inertia: float = K_INERTIA) -> Path:
    """Writes <x>_conjunto.csv and <x>_conjunto_info.json next to the robots CSV; returns the CSV path."""
    info = info or {}
    D = float(robot_diameter_mm if robot_diameter_mm is not None else info.get("diametro_robot_mm", 33.0) or 33.0)
    rw = float(r_wall_mm) if r_wall_mm is not None else wall_threshold_from_info(info, D)
    out = ensemble_table(long_df, D, k_inertia, rw)
    path = ensemble_path(robots_csv)
    out.to_csv(path, index=False, float_format="%.6g")
    path.with_name(path.stem + "_info.json").write_text(
        json.dumps(ensemble_info(info, D, k_inertia, rw, Path(robots_csv).name), ensure_ascii=False, indent=2,
                   default=float), encoding="utf-8")
    return path
