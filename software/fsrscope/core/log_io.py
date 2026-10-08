"""Robust loader for the FSR logger CSV files (every firmware/logger version seen so far).

Known formats (header examples):
  2026-08-24  timestamp(ms),t,n,dt_ms,adc_raw,R_ohm,G_uS,G0_mon,sigma_mon
  2026-08-27  timestamp(ms),ENV,ADC_RAW,G
  2026-09     timestamp(ms),[ADC_RAW,G,]R,R_LOG,ENV,ADC_STD,N,CLIP0,CLIPSAT,LED,[ADC_RAW,G,]SYNC
The "timestamp(ms)" column actually holds seconds in all of them (units are auto-detected).
Known defects handled: trailing comma (empty column), partially written rows, junk rows at EOF
with absurd timestamps, one SYNC marker row without data.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

import numpy as np
import pandas as pd

TIME_CANDIDATES = ("timestamp(ms)", "timestamp", "tiempo", "time", "t_s")
ADC_CANDIDATES = ("adc_raw", "adc")
G_CANDIDATES = ("g", "g_us")
R_CANDIDATES = ("r", "r_ohm")
GLITCH_TOL_S = 5.0     # a row whose time departs this much from its neighbours is junk
LED_MIN_ROWS = 3       # shortest LED run accepted as the sync pulse


@dataclass
class RawLog:
    path: Path
    data: pd.DataFrame          # numeric columns of the valid rows; column "t" = time [s] from t0
    adc_col: str
    t0_abs: float               # absolute timestamp of the first row (logger clock) [s]
    k_firmware: Optional[float]  # conductance factor logged by the firmware [uS/count]
    led_on: float = np.nan      # sync LED pulse start/end, relative to t0 [s]
    led_off: float = np.nan
    warnings: list = field(default_factory=list)

    @property
    def t(self) -> np.ndarray:
        return self.data["t"].to_numpy()

    @property
    def adc(self) -> np.ndarray:
        return self.data[self.adc_col].to_numpy()

    @property
    def duration_s(self) -> float:
        return float(self.data["t"].iloc[-1]) if len(self.data) else 0.0

    def numeric_columns(self) -> list[str]:
        return [c for c in self.data.columns if c != "t"]

    def full_saturation(self) -> Optional[np.ndarray]:
        """Rows where every oversampled ADC reading clipped (CLIPSAT == N), if logged."""
        cols = {c.lower(): c for c in self.data.columns}
        if "clipsat" in cols and "n" in cols:
            n = self.data[cols["n"]].to_numpy()
            return (self.data[cols["clipsat"]].to_numpy() >= n) & (n > 0)
        return None


def _find(columns, candidates) -> Optional[str]:
    low = {c.strip().lower(): c for c in columns}
    for cand in candidates:
        if cand in low:
            return low[cand]
    return None


def _first_led_run(led: np.ndarray, t: np.ndarray) -> tuple[float, float]:
    on = np.flatnonzero(led == 1)
    if len(on) < LED_MIN_ROWS:
        return np.nan, np.nan
    breaks = np.flatnonzero(np.diff(on) > 1)
    run = on[: breaks[0] + 1] if len(breaks) else on
    return float(t[run[0]]), float(t[run[-1]])


def load_log(path: Path | str) -> RawLog:
    path = Path(path)
    df = pd.read_csv(path, on_bad_lines="skip", low_memory=False)
    df.columns = [str(c).strip() for c in df.columns]
    df = df.loc[:, [c for c in df.columns if c and not c.startswith("Unnamed")]]
    df = df.apply(pd.to_numeric, errors="coerce")
    warnings: list[str] = []

    tcol = _find(df.columns, TIME_CANDIDATES) or df.columns[0]
    acol = _find(df.columns, ADC_CANDIDATES)
    if acol is None:
        raise ValueError(f"'{path.name}': no hay columna ADC (se buscó {ADC_CANDIDATES}); "
                         f"columnas: {list(df.columns)}")

    t = df[tcol].to_numpy(dtype=float, copy=True)
    # Units: the logger writes seconds under a "(ms)" header; real ms would give dt ~ 50.
    dts = np.diff(t[np.isfinite(t)])
    dts = dts[dts > 0]
    if len(dts) and np.median(dts) > 5.0:
        t = t / 1000.0

    # Junk rows: timestamp far from the running median of its neighbourhood.
    med = pd.Series(t).rolling(25, center=True, min_periods=1).median().to_numpy()
    glitch = np.isfinite(t) & (np.abs(t - med) > GLITCH_TOL_S)
    if glitch.any():
        warnings.append(f"{int(glitch.sum())} fila(s) con tiempo inválido descartada(s)")
    t[glitch] = np.nan
    finite = np.isfinite(t)
    if not finite.any():
        raise ValueError(f"'{path.name}': sin tiempos válidos.")
    t0 = float(t[finite][0])
    df = df.assign(t=t - t0)

    led_on = led_off = np.nan
    ledcol = _find(df.columns, ("led",))
    if ledcol is not None:
        led_on, led_off = _first_led_run(df[ledcol].to_numpy(), df["t"].to_numpy())

    synccol = _find(df.columns, ("sync",))
    if synccol is not None:
        df = df[df[synccol].isna()]
    df = df.dropna(subset=["t", acol])
    df = df.sort_values("t").drop_duplicates(subset="t")
    df = df.drop(columns=[c for c in (tcol, synccol) if c is not None and c != "t"])
    df = df.dropna(axis=1, how="all").reset_index(drop=True)
    if len(df) < 2:
        raise ValueError(f"'{path.name}': menos de 2 filas válidas.")

    # Conductance factor the firmware used: median of G/ADC where the ADC is clearly nonzero.
    k_fw = None
    adc = df[acol].to_numpy()
    gcol = _find(df.columns, G_CANDIDATES)
    rcol = _find(df.columns, R_CANDIDATES)
    ok = adc > 0.05
    if gcol is not None:
        g = df[gcol].to_numpy()
        ok &= np.isfinite(g) & (g > 0)
        if ok.sum() > 10:
            k_fw = float(np.median(g[ok] / adc[ok]))
    elif rcol is not None:
        r = df[rcol].to_numpy()
        ok &= np.isfinite(r) & (r > 0)
        if ok.sum() > 10:
            k_fw = float(np.median(1e6 / (r[ok] * adc[ok])))

    return RawLog(path, df, acol, t0, k_fw, led_on, led_off, warnings)
