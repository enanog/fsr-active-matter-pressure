"""Processed-file writer (P_<code>.csv). Column set and order are user-selectable; the default
reproduces the legacy layout of procesar_presion_ventanas.py so existing plots keep working."""

from __future__ import annotations

from collections import OrderedDict
from pathlib import Path
from typing import Callable, Optional

import numpy as np
import pandas as pd

from core.settings import TrialSettings
from core.signal import Series, analysis_mask
from core.stats import Stats

# key -> description shown in the GUI
COLUMNS: "OrderedDict[str, str]" = OrderedDict([
    ("tiempo", "tiempo del sensor [s] (desde la primera fila del registro)"),
    ("ADC_RAW", "ADC remuestreado [cuentas]"),
    ("G", "conductancia [µS]"),
    ("deltaG", "ΔG(t) = G(t) − G(t − ΔT) con la ventana fija [µS]"),
    ("deltaT", "barrido de ventana ΔT [s]"),
    ("skewness", "asimetría de ΔG vs ΔT"),
    ("G_surv", "G ordenada para la supervivencia [µS]"),
    ("P_G_geq", "P(G ≥ g)"),
    ("kurtosis", "curtosis en exceso de ΔG vs ΔT"),
    ("R", "resistencia del FSR [Ω]"),
    ("tiempo_video", "tiempo del video [s] (t − desfase)"),
    ("saturado", "1 si el ADC está a fondo de escala"),
    ("en_analisis", "1 si la muestra entra en la estadística"),
    ("hist_G_centro", "histograma de G: centro de clase [µS]"),
    ("hist_G_densidad", "histograma de G: densidad [1/µS]"),
    ("hist_dG_centro", "histograma de ΔG: centro de clase [µS]"),
    ("hist_dG_densidad", "histograma de ΔG: densidad [1/µS]"),
    ("v_robots_mediana", "robots: mediana de |v| [mm/s] (si hay trayectorias)"),
    ("v_robots_p90", "robots: percentil 90 de |v| [mm/s]"),
])
LEGACY = ["tiempo", "ADC_RAW", "G", "deltaG", "deltaT", "skewness", "G_surv", "P_G_geq"]


def default_columns() -> list[list]:
    return [[k, k in LEGACY] for k in COLUMNS]


def normalized_columns(saved: list) -> list[list]:
    """Saved [[key, checked], ...] completed with any new keys and stripped of unknown ones."""
    out = [[k, bool(c)] for k, c in saved if k in COLUMNS]
    seen = {k for k, _ in out}
    out += [[k, False] for k in COLUMNS if k not in seen]
    return out


def header(key: str, s: TrialSettings) -> str:
    return f"deltaG_{s.analysis.deltaT_fixed_s:g}s" if key == "deltaG" else key


def build_table(series: Series, stats: Stats, s: TrialSettings, offset_s: float,
                robot_speed: Optional[Callable[[np.ndarray], tuple]] = None) -> pd.DataFrame:
    """robot_speed(t_sensor) -> (median, p90) arrays on the given times, or None."""
    a = s.analysis
    keep = np.ones(len(series.t), dtype=bool)
    if a.t_start is not None:
        keep &= series.t >= a.t_start
    if a.t_end is not None:
        keep &= series.t <= a.t_end
    t = series.t[keep]
    mask = analysis_mask(series, a)[keep]

    cols: dict[str, np.ndarray] = {
        "tiempo": t,
        "tiempo_video": t - offset_s,
        "ADC_RAW": series.adc[keep],
        "G": series.G[keep],
        "R": series.R[keep],
        "saturado": series.sat[keep].astype(int),
        "en_analisis": mask.astype(int),
        "deltaG": stats.deltaG[keep],
        "deltaT": stats.deltaT,
        "skewness": stats.skew,
        "kurtosis": stats.kurt,
        "G_surv": stats.surv_G,
        "P_G_geq": stats.surv_P,
        "hist_G_centro": stats.hist_G[0],
        "hist_G_densidad": stats.hist_G[1],
        "hist_dG_centro": stats.hist_dG[0],
        "hist_dG_densidad": stats.hist_dG[1],
    }
    if robot_speed is not None:
        cols["v_robots_mediana"], cols["v_robots_p90"] = robot_speed(t)

    chosen = [k for k, on in normalized_columns(s.export_columns or default_columns()) if on]
    chosen = [k for k in chosen if k in cols]
    if not chosen:
        raise ValueError("No hay columnas seleccionadas para exportar.")
    n = max(len(cols[k]) for k in chosen)
    data = {}
    for k in chosen:
        v = np.asarray(cols[k], dtype=float)
        pad = np.full(n, np.nan)
        pad[: len(v)] = v[:n]
        data[header(k, s)] = pad
    return pd.DataFrame(data)


def write_table(df: pd.DataFrame, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(path, index=False)
