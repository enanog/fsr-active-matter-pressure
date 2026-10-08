"""Statistics over the masked series: deltaG moments vs window size, survival, histograms."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

import numpy as np

from core.settings import Analysis
from core.signal import Series, analysis_mask, delta_g, lag_of


@dataclass
class Stats:
    n_used: int
    t_now: Optional[float]
    deltaG: np.ndarray                  # fixed-window deltaG(t), full length (NaN outside mask)
    deltaT: np.ndarray = field(default_factory=lambda: np.empty(0))
    skew: np.ndarray = field(default_factory=lambda: np.empty(0))
    kurt: np.ndarray = field(default_factory=lambda: np.empty(0))
    surv_G: np.ndarray = field(default_factory=lambda: np.empty(0))
    surv_P: np.ndarray = field(default_factory=lambda: np.empty(0))
    hist_G: tuple = (np.empty(0), np.empty(0))    # (bin centers, density)
    hist_dG: tuple = (np.empty(0), np.empty(0))
    G_mean: float = np.nan
    G_std: float = np.nan
    sat_frac: float = np.nan


def moments(x: np.ndarray) -> tuple[float, float]:
    """Bias-corrected sample skewness and excess kurtosis (same as pandas .skew()/.kurt() and
    Excel SKEW()/KURT())."""
    n = len(x)
    if n < 4:
        return np.nan, np.nan
    c = x - x.mean()
    c2 = c * c
    m2 = c2.mean()
    if m2 <= 0:
        return np.nan, np.nan
    m3 = (c2 * c).mean()
    m4 = (c2 * c2).mean()
    g1 = m3 / m2 ** 1.5
    g2 = m4 / m2 ** 2 - 3.0
    skew = np.sqrt(n * (n - 1)) / (n - 2) * g1
    kurt = ((n + 1) * g2 + 6.0) * (n - 1) / ((n - 2) * (n - 3))
    return float(skew), float(kurt)


def moments_vs_deltaT(g: np.ndarray, mask: np.ndarray, step_s: float, max_s: float):
    """For each window deltaT = k*step (k = 1..max/step): skewness and kurtosis of
    deltaG(t) = G(t) - G(t - deltaT) over all t where both ends are inside the mask."""
    n_lags = max(1, int(round(max_s / step_s)))
    lags = np.arange(1, n_lags + 1)
    skew = np.full(n_lags, np.nan)
    kurt = np.full(n_lags, np.nan)
    for i, L in enumerate(lags):
        if L >= len(g):
            break
        ok = mask[L:] & mask[:-L]
        d = (g[L:] - g[:-L])[ok]
        skew[i], kurt[i] = moments(d)
    return lags * step_s, skew, kurt


def survival(x: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Empirical P(X >= x_i), x sorted ascending (smallest -> 1, largest -> 1/n)."""
    x = np.sort(x[np.isfinite(x)])
    n = len(x)
    return x, (n - np.arange(n)) / n if n else np.empty(0)


def decimate_survival(x: np.ndarray, p: np.ndarray, n_max: int = 4000):
    """Subsample a survival curve for display, dense in the tail (log-spaced in rank)."""
    n = len(x)
    if n <= n_max:
        return x, p
    from_top = np.unique(np.round(np.logspace(0, np.log10(n), n_max)).astype(int))
    idx = np.unique(np.concatenate(([0], n - from_top)))
    return x[idx], p[idx]


def histogram(x: np.ndarray, bins: int) -> tuple[np.ndarray, np.ndarray]:
    x = x[np.isfinite(x)]
    if len(x) < 2 or np.ptp(x) == 0:
        return np.empty(0), np.empty(0)
    dens, edges = np.histogram(x, bins=max(5, int(bins)), density=True)
    return 0.5 * (edges[1:] + edges[:-1]), dens


def compute_stats(s: Series, a: Analysis, t_now: Optional[float] = None,
                  sweep: bool = True) -> Stats:
    mask = analysis_mask(s, a, t_now)
    g_used = s.G[mask]
    dG = delta_g(s.G, lag_of(a.deltaT_fixed_s, s.step_s), mask)
    st = Stats(int(mask.sum()), t_now, dG)
    if st.n_used < 4:
        return st
    st.G_mean, st.G_std = float(g_used.mean()), float(g_used.std(ddof=1))
    st.sat_frac = float(s.sat[mask].mean())
    if sweep:
        st.deltaT, st.skew, st.kurt = moments_vs_deltaT(s.G, mask, s.step_s, a.deltaT_max_s)
    st.surv_G, st.surv_P = survival(g_used)
    st.hist_G = histogram(g_used, a.hist_bins)
    st.hist_dG = histogram(dG, a.hist_bins)
    return st
