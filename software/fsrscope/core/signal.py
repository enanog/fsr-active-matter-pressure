"""Raw log -> calibrated, uniformly sampled series, and the analysis mask (crop/exclusions).

No smoothing or baseline subtraction is applied on purpose: the firmware already filters, and
jamming events are slow, sustained changes that an adaptive baseline would erase.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

import numpy as np

from core.log_io import RawLog
from core.settings import Analysis, Calibration


@dataclass
class Series:
    t: np.ndarray        # uniform grid, sensor time from the first log row [s]
    adc: np.ndarray      # ADC counts (oversampled mean, so fractional)
    G: np.ndarray        # FSR conductance [uS]
    sat: np.ndarray      # bool, ADC at full scale (G is a lower bound there)
    k_us: float          # conductance factor used [uS/count]
    k_source: str        # "firmware" | "parámetros"
    r_feedback_eff: float  # R_FEEDBACK equivalent to k_us with the current V_REF/V_EXC [ohm]
    adc_fs: float
    step_s: float

    @property
    def R(self) -> np.ndarray:
        """FSR resistance [ohm] (inf where G = 0)."""
        with np.errstate(divide="ignore"):
            return np.where(self.G > 0, 1e6 / self.G, np.inf)

    @property
    def g_max(self) -> float:
        """Largest measurable conductance (ADC at full scale) [uS]."""
        return self.k_us * self.adc_fs

    @property
    def r_floor(self) -> float:
        """Smallest measurable FSR resistance before the ADC saturates [ohm]."""
        return 1e6 / self.g_max

    def index_at(self, t: float) -> int:
        return int(np.clip(np.searchsorted(self.t, t, side="right") - 1, 0, len(self.t) - 1))


def conductance_factor(raw: RawLog, cal: Calibration) -> tuple[float, str]:
    if cal.mode == "auto" and raw.k_firmware is not None:
        return raw.k_firmware, "firmware"
    return cal.k_params(), "parámetros"


def build_series(raw: RawLog, cal: Calibration, step_s: float) -> Series:
    if step_s <= 0:
        raise ValueError("El paso de remuestreo debe ser > 0.")
    t_raw, adc_raw = raw.t, raw.adc
    n = int(np.floor((t_raw[-1] - t_raw[0]) / step_s)) + 1
    t = t_raw[0] + np.arange(n) * step_s
    adc = np.interp(t, t_raw, adc_raw)
    k, src = conductance_factor(raw, cal)

    # Saturation: firmware clip counters when logged, else ADC at full scale (nearest row).
    idx = np.clip(np.searchsorted(t_raw, t), 0, len(t_raw) - 1)
    sat = adc_raw[idx] >= cal.adc_fs - 0.5
    full = raw.full_saturation()
    if full is not None:
        sat |= full[idx]

    return Series(t, adc, adc * k, sat, k, src, cal.r_feedback_from_k(k), cal.adc_fs, step_s)


def analysis_mask(s: Series, a: Analysis, t_now: Optional[float] = None) -> np.ndarray:
    """Samples that enter the statistics: inside the crop, outside exclusions, (unsaturated),
    and not after t_now (live mode)."""
    m = np.ones(len(s.t), dtype=bool)
    if a.t_start is not None:
        m &= s.t >= a.t_start
    if a.t_end is not None:
        m &= s.t <= a.t_end
    for seg in a.exclusions or []:
        try:
            t0, t1 = sorted((float(seg[0]), float(seg[1])))
        except (TypeError, ValueError, IndexError):
            continue
        m &= ~((s.t >= t0) & (s.t <= t1))
    if a.exclude_saturated:
        m &= ~s.sat
    if t_now is not None:
        m &= s.t <= t_now
    return m


def delta_g(g: np.ndarray, lag: int, mask: Optional[np.ndarray] = None) -> np.ndarray:
    """deltaG(t) = G(t) - G(t - lag*step), NaN where the window is incomplete or touches a
    masked-out sample (so excluded sections never leak into the differences)."""
    out = np.full(len(g), np.nan)
    if 0 < lag < len(g):
        out[lag:] = g[lag:] - g[:-lag]
        if mask is not None:
            ok = np.zeros(len(g), dtype=bool)
            ok[lag:] = mask[lag:] & mask[:-lag]
            out[~ok] = np.nan
    return out


def lag_of(deltaT_s: float, step_s: float) -> int:
    return max(1, int(round(deltaT_s / step_s)))


def true_runs(b: np.ndarray, t: np.ndarray) -> list[tuple[float, float]]:
    """[(t_start, t_end)] of the contiguous True runs of b (for shading saturated spans)."""
    if not b.any():
        return []
    d = np.diff(np.concatenate(([0], b.astype(np.int8), [0])))
    starts, ends = np.flatnonzero(d == 1), np.flatnonzero(d == -1) - 1
    return [(float(t[a]), float(t[e])) for a, e in zip(starts, ends)]
