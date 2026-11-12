"""Comparison of several trials on common settings (no GUI): the curves the Comparador overlays
(port of software/matlab/comparar_ensayos.m) and the summary row of each trial.

Every trial is analysed with the SAME parameters (smoothing, jam threshold, bins, mass), chosen
in the Comparador, so the curves are comparable; the sensor calibration, crop, exclusions and
video <-> sensor sync of each trial still come from its FSRScope configuration (read only).
The settings saved by Velocidades are used only for the window when `own_window` is on.
"""

from __future__ import annotations

import copy
import warnings
from dataclasses import dataclass, field
from typing import Optional

import numpy as np

from comun import paths
from comun.mobility import MobilityData, frame_mask, log_pdf, rolling_mean, samples
from comun.signal import analysis_mask
from comun.stats import survival
from comun.summary import summarize

SOURCES = {"colectiva": "V̄ por cuadro (media entre robots)",
           "individual": "|v| de cada robot y cuadro (observados)",
           "robot": "media de cada robot"}


@dataclass
class Options:
    smooth_s: float = 30.0          # moving average of the time plots and of V̄–G [s]
    source: str = "colectiva"       # distributions: see SOURCES
    dist_smoothed: bool = False     # distributions of the smoothed V̄ (changes width and tails)
    bins: int = 60
    normalize_ccdf: bool = True     # 1 - F of v / <v> (<v>: mean of each trial's samples)
    statistic: str = "media"        # jam criterion (same as Velocidades)
    threshold_mm_s: float = 0.35
    jam_smooth_s: float = 30.0
    jam_min_s: float = 20.0
    vg_bins: int = 25               # V̄ classes of the G-vs-V̄ plot
    vg_min_frames: int = 30         # a class needs this many frames (10 s at 3 frames/s)
    mass_g: float = 0.0             # 0: energy per unit mass
    k_inertia: float = 0.5
    own_window: bool = False        # use each trial's window saved by Velocidades

    def load_key(self) -> tuple:
        return ()                   # the raw load does not depend on the options


@dataclass
class TrialCurves:
    code: str
    label: str
    mode: str
    t_min: np.ndarray               # video time per row [min]
    used: np.ndarray                # bool per row: inside the window and with video
    v: np.ndarray                   # V̄ per row [mm/s]
    v_s: np.ndarray                 # smoothed V̄
    w_s: Optional[np.ndarray]       # smoothed <|ω|> [deg/s]
    e_tr_s: Optional[np.ndarray]    # smoothed kinetic energies (unit: energy_unit)
    e_rot_s: Optional[np.ndarray]
    energy_unit: str
    jam_spans: list                 # [(t0, t1)] minutes of video
    samples: np.ndarray             # distribution samples [mm/s]
    G_s: Optional[np.ndarray]       # smoothed G at each row [µS] (NaN outside the FSRScope mask)
    summary: dict = field(default_factory=dict)
    pressure_note: str = ""


def mode_of(code: str) -> str:
    m = paths.CODE_RE.match(code)
    if not m:
        return ""
    return "".join(c for c in m.group(1).split("_")[2] if c.isalpha()).upper()


def open_trial(trial: paths.Trial) -> MobilityData:
    """Slow part (reads the trajectories CSV and the sensor log): cache the result."""
    return MobilityData.open(trial)


def _configure(md: MobilityData, o: Options) -> MobilityData:
    md = copy.copy(md)
    s = copy.deepcopy(md.settings)
    if not o.own_window:
        s.t_start_min = s.t_end_min = None
    s.smooth_s, s.dist_smoothed = o.smooth_s, o.dist_smoothed
    s.mass_g, s.k_inertia = o.mass_g, o.k_inertia
    m = s.mobility
    m.statistic, m.v_threshold_mm_s, m.smooth_s, m.min_duration_s = (
        o.statistic, o.threshold_mm_s, o.jam_smooth_s, o.jam_min_s)
    m.hist_bins = o.bins
    md.settings = s
    md._jams = None
    return md


def _g_on_frames(md: MobilityData, smooth_s: float) -> tuple[Optional[np.ndarray], str]:
    if md.td is None:
        return None, f"sin presión: {md.pressure_error}" if md.pressure_error else "sin registro del sensor"
    s = md.td.series
    pa = md.pressure_analysis()
    mask = analysis_mask(s, pa)
    g = np.where(mask, s.G, np.nan)
    k = max(1, int(round(smooth_s / s.step_s)))
    g_s = np.where(mask, rolling_mean(g, k), np.nan)
    tf = md.frame_times
    idx = np.clip(np.searchsorted(s.t, tf), 0, len(s.t) - 1)
    inside = (tf >= s.t[0]) & (tf <= s.t[-1])
    return np.where(inside, g_s[idx], np.nan), ""


def curves(md0: MobilityData, o: Options) -> TrialCurves:
    """Everything the Comparador plots for one trial, with the common options."""
    md = _configure(md0, o)
    r = md.robots
    jams = md.jams
    used = frame_mask(md.frame_times, md.window()) & jams.valid
    v = np.where(used, r.v_mean, np.nan)
    v_s = np.where(used, md.smooth(r.v_mean), np.nan)
    w = md.w_abs_mean
    w_s = None if w is None else np.where(used, md.smooth(w), np.nan)
    e = md.energy()
    e_tr_s = e_rot_s = None
    if e is not None:
        e_tr_s, e_rot_s = (np.where(used, md.smooth(x), np.nan) for x in e)
    col = md.smooth(r.v_mean) if o.dist_smoothed else None
    x = samples(r, used, o.source, col)
    g_s, note = _g_on_frames(md, o.smooth_s)
    if g_s is not None:
        g_s = np.where(used, g_s, np.nan)
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", category=RuntimeWarning)
        try:
            summ = summarize(md)
        except Exception as exc:      # summary is a convenience: never block the curves
            summ = {"codigo": md.trial.code, "aviso": f"resumen: {exc}"}
    t0, t1 = md.settings.t_start_min, md.settings.t_end_min
    spans = [(a, b) for a, b in md.jam_spans_min()
             if (t1 is None or a <= t1) and (t0 is None or b >= t0)]
    return TrialCurves(md.trial.code, md.trial.label, mode_of(md.trial.code), md.frame_minutes, used,
                       v, v_s, w_s, e_tr_s, e_rot_s, md.energy_unit, spans, x, g_s, summ, note)


# =============================================================================================
# distributions and V̄–G classes (computed over the selected trials)
# =============================================================================================
def common_edges(sample_sets: list[np.ndarray], bins: int, normalize: bool = False) -> np.ndarray:
    """Bin edges shared by every trial so histograms and P(v) are comparable."""
    hi = 0.0
    for x in sample_sets:
        if len(x):
            hi = max(hi, float(np.percentile(x / (x.mean() if normalize and x.mean() > 0 else 1.0), 99.9)))
    return np.linspace(0.0, hi if hi > 0 else 1.0, max(5, int(bins)) + 1)


def hist_fraction(x: np.ndarray, edges: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """(centres, fraction of the samples per bin)."""
    cnt, _ = np.histogram(x, edges)
    return 0.5 * (edges[1:] + edges[:-1]), cnt / max(len(x), 1)


def pdf(x: np.ndarray, edges: np.ndarray, log_bins: bool = False) -> tuple[np.ndarray, np.ndarray]:
    """Probability density [1/(mm/s)] normalised over all samples."""
    if log_bins:
        return log_pdf(x, len(edges) - 1)
    cnt, _ = np.histogram(x, edges)
    return 0.5 * (edges[1:] + edges[:-1]), cnt / (max(len(x), 1) * np.diff(edges))


def ccdf(x: np.ndarray, normalize: bool) -> tuple[np.ndarray, np.ndarray]:
    """1 - F = P(V >= v), of v or of v / <v>."""
    if not len(x):
        return np.empty(0), np.empty(0)
    xs, p = survival(x / x.mean() if normalize and x.mean() > 0 else x)
    if len(xs) > 6000:                       # plenty for a line, keeps the plot responsive
        keep = np.unique(np.r_[np.linspace(0, len(xs) - 1, 5000).astype(int), np.arange(len(xs) - 500, len(xs))])
        xs, p = xs[keep], p[keep]
    return xs, p


def vg_edges(curves_list: list[TrialCurves], n: int) -> np.ndarray:
    hi = 0.0
    for c in curves_list:
        ok = np.isfinite(c.v_s) & (np.isfinite(c.G_s) if c.G_s is not None else False)
        if ok.any():
            hi = max(hi, float(np.percentile(c.v_s[ok], 99.5)))
    return np.linspace(0.0, hi if hi > 0 else 1.0, max(3, int(n)) + 1)


def g_by_v(c: TrialCurves, edges: np.ndarray, min_frames: int):
    """Median and interquartile range of G per class of smoothed V̄. Every class is returned;
    classes with fewer than min_frames frames are NaN, so lines break there instead of joining
    distant classes. Returns (centres, median, q25, q75, n)."""
    nb = len(edges) - 1
    x = 0.5 * (edges[1:] + edges[:-1])
    med, q25, q75 = (np.full(nb, np.nan) for _ in range(3))
    n = np.zeros(nb)
    if c.G_s is None:
        return np.empty(0), np.empty(0), np.empty(0), np.empty(0), np.empty(0)
    ok = np.isfinite(c.v_s) & np.isfinite(c.G_s)
    v, g = c.v_s[ok], c.G_s[ok]
    k = np.digitize(v, edges) - 1
    for i in range(nb):
        gi = g[k == i]
        n[i] = len(gi)
        if len(gi) >= max(1, min_frames):
            q25[i], med[i], q75[i] = np.percentile(gi, [25, 50, 75])
    if not np.isfinite(med).any():
        return np.empty(0), np.empty(0), np.empty(0), np.empty(0), np.empty(0)
    last = int(np.flatnonzero(np.isfinite(med))[-1]) + 1      # trim empty classes at the end
    return x[:last], med[:last], q25[:last], q75[:last], n[:last]


def correlation_vg(c: TrialCurves) -> float:
    """Spearman correlation between smoothed V̄ and smoothed G over the frames with both."""
    if c.G_s is None:
        return np.nan
    ok = np.isfinite(c.v_s) & np.isfinite(c.G_s)
    if ok.sum() < 10:
        return np.nan
    ra = np.argsort(np.argsort(c.v_s[ok]))
    rb = np.argsort(np.argsort(c.G_s[ok]))
    return float(np.corrcoef(ra, rb)[0, 1])


SUMMARY_COLUMNS = [
    ("ensayo", "Ensayo", None), ("modo", "Modo", None), ("minutos_video_usados", "Min. usados", "{:.1f}"),
    ("v_media_mm_s", "V̄ media [mm/s]", "{:.3f}"), ("v_individual_mediana_mm_s", "|v| mediana [mm/s]", "{:.3f}"),
    ("omega_abs_media_deg_s", "⟨|ω|⟩ [°/s]", "{:.2f}"), ("frac_tiempo_atasco", "Atasco [%]", "pct"),
    ("n_atascos", "N atascos", "{:.0f}"), ("atasco_dur_max_s", "Atasco máx [s]", "{:.0f}"),
    ("E_total_media", "E total [unidad]", "{:.3g}"), ("E_rot_sobre_E_tras", "E_rot/E_tras", "{:.2f}"),
    ("frac_capa_pared", "Capa pared [%]", "pct"), ("G_mediana_uS", "G mediana [µS]", "{:.3g}"),
    ("G_mediana_fluido_uS", "G med. fluido [µS]", "{:.3g}"), ("G_mediana_atasco_uS", "G med. atasco [µS]", "{:.3g}"),
    ("frac_saturado", "Saturado [%]", "pct"), ("rho_vg", "ρ(V̄, G)", "{:.2f}"),
]


def fmt(value, spec) -> str:
    try:
        v = float(value)
    except (TypeError, ValueError):
        return "" if value is None else str(value)
    if not np.isfinite(v):
        return "—"
    if spec == "pct":
        return f"{100 * v:.1f}"
    return spec.format(v) if spec else f"{v:g}"
