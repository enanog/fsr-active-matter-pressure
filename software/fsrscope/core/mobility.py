"""Robot mobility (used by velocidades.py): collective speed V(t), jam detection by a speed
threshold, speed distributions, occupancy map and pressure split by state (jam / fluid).

Conventions
- Rows are video frames (contiguous; split recordings have NaN rows in the gap). Sensor time of a
  row: t = offset + frame / f_r, with offset and f_r taken from the FSRScope configuration of the
  trial (read only), so velocities and G share the time base FSRScope uses.
- Collective statistics per frame use every robot with a finite speed (interpolated points
  included, as in comparar_ensayos.py: N stays constant through short detection gaps).
  Individual and per-robot distributions use only observed points (detected / manual).
- Frames enter the statistics inside the window of this app (minutes of video). G enters inside
  that window AND inside the FSRScope analysis mask (its crop and excluded spans).
- Settings of this app live in datos/video/config/<code>.json, never in the FSRScope JSON.
"""

from __future__ import annotations

import copy
import json
import warnings
from dataclasses import asdict, dataclass, field, fields
from pathlib import Path
from typing import Optional

import numpy as np
import pandas as pd

from core import paths
from core.robots import Robots, load_robots
from core.settings import Analysis
from core.session import TrialData
from core.signal import analysis_mask
from core.stats import histogram, survival

VEL_CONFIG_DIR = paths.REPO_ROOT / "datos" / "video" / "config"
DEFAULT_FPS = 3.0


@dataclass
class Mobility:
    """Jam = the collective statistic (per-frame mean, median or p90 of |v| over the robots),
    rolling-median filtered over smooth_s, below v_threshold_mm_s for at least min_duration_s.
    The reports (comparar_ensayos.py) use p90 < 0.52 mm/s, 30 s, 20 s. With the mean, 0.35 mm/s
    classifies >= 98.5 % of the frames like that criterion in the 7 trials of 24/09-30/10
    (0.30 and 0.40 agree less)."""
    statistic: str = "media"         # "media" | "mediana" | "p90"
    v_threshold_mm_s: float = 0.35
    smooth_s: float = 30.0
    min_duration_s: float = 20.0
    hist_bins: int = 60
    heat_bin_mm: float = 5.0


@dataclass
class VelSettings:
    mobility: Mobility = field(default_factory=Mobility)
    t_start_min: Optional[float] = None    # window, minutes of video (None = start / end)
    t_end_min: Optional[float] = None
    smooth_s: float = 30.0                 # moving average of every time plot [s] (0 = none)
    dist_smoothed: bool = False            # distributions of the smoothed V̄ (changes width and tails)
    mass_g: float = 0.0                    # robot mass [g]; 0 = kinetic energy per unit mass
    k_inertia: float = 0.5                 # I = k m R² (0.5 = uniform disk: assumption)
    plots: dict = field(default_factory=dict)   # plot id -> {option: value}

    def to_json(self) -> str:
        return json.dumps(asdict(self), indent=2, ensure_ascii=False)

    @classmethod
    def from_dict(cls, d: dict) -> "VelSettings":
        names = {f.name for f in fields(Mobility)}
        mob = Mobility(**{k: v for k, v in (d.get("mobility") or {}).items() if k in names})
        scal = {f.name for f in fields(cls)} - {"mobility", "plots"}
        return cls(mobility=mob, plots=dict(d.get("plots") or {}),
                   **{k: v for k, v in d.items() if k in scal})


def vel_config_path(trial: paths.Trial) -> Path:
    return VEL_CONFIG_DIR / f"{trial.code}.json"


def load_vel_settings(trial: paths.Trial) -> VelSettings:
    p = vel_config_path(trial)
    try:
        if p.is_file():
            return VelSettings.from_dict(json.loads(p.read_text(encoding="utf-8")))
    except (OSError, ValueError, TypeError) as exc:
        print(f"Aviso: configuración ilegible '{p}': {exc}")
    return VelSettings()


def save_vel_settings(trial: paths.Trial, s: VelSettings) -> Path:
    p = vel_config_path(trial)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(s.to_json(), encoding="utf-8")
    return p

STAT_LABELS = {"media": "media", "mediana": "mediana", "p90": "percentil 90"}
SOURCE_LABELS = {"colectiva": "V̄(t): media entre robots por cuadro",
                 "robot": "media de cada robot (una por robot)",
                 "individual": "|v| de cada robot y cuadro (observados)"}
CONTACT_Q = 99.5        # percentile of r taken as the radius of robot centres touching the wall


def runs(mask: np.ndarray, min_len: int) -> list[tuple[int, int]]:
    """[(first, last)] inclusive index ranges of True runs with at least min_len samples."""
    idx = np.flatnonzero(mask)
    if len(idx) == 0:
        return []
    groups = np.split(idx, np.flatnonzero(np.diff(idx) > 1) + 1)
    return [(int(g[0]), int(g[-1])) for g in groups if len(g) >= max(1, min_len)]


def rolling_median(x: np.ndarray, n: int) -> np.ndarray:
    """Centered rolling median over n samples, NaN-aware (NaN only where the window is empty)."""
    if n <= 1:
        return np.asarray(x, dtype=float)
    return pd.Series(x, dtype=float).rolling(int(n), center=True, min_periods=1).median().to_numpy()


def rolling_mean(x: np.ndarray, n: int) -> np.ndarray:
    if n <= 1:
        return np.asarray(x, dtype=float)
    return pd.Series(x, dtype=float).rolling(int(n), center=True, min_periods=1).mean().to_numpy()


# =============================================================================================
# jams
# =============================================================================================
@dataclass
class Jams:
    signal: np.ndarray                  # smoothed collective statistic per row [mm/s]
    mask: np.ndarray                    # bool per row: inside a jam
    runs: list                          # [(row0, row1)] inclusive
    valid: np.ndarray                   # bool per row: finite statistic (False in video gaps)
    key: tuple = ()


def detect_jams(r: Robots, mob: Mobility, fps: float) -> Jams:
    raw = r.collective(mob.statistic)
    sig = rolling_median(raw, int(round(mob.smooth_s * fps)))
    valid = np.isfinite(raw)
    sig = np.where(valid, sig, np.nan)               # never fill the gap of a split video
    below = np.isfinite(sig) & (sig < mob.v_threshold_mm_s)
    rr = merge_across_gaps(runs(below, 1), valid)
    min_len = int(round(mob.min_duration_s * fps))
    rr = [(a, b) for a, b in rr if valid[a:b + 1].sum() >= max(1, min_len)]
    mask = np.zeros(len(sig), dtype=bool)
    for a, b in rr:
        mask[a:b + 1] = True
    return Jams(sig, mask, rr, valid, jam_key(mob, fps))


def merge_across_gaps(rr: list, valid: np.ndarray) -> list:
    """Join consecutive runs separated only by rows without video (gap of a split recording):
    a jam on both sides of the cut is one episode. The gap rows stay out of every statistic."""
    out: list = []
    for a, b in rr:
        if out and not valid[out[-1][1] + 1:a].any():
            out[-1] = (out[-1][0], b)
        else:
            out.append((a, b))
    return out


def jam_key(mob: Mobility, fps: float) -> tuple:
    return (mob.statistic, mob.v_threshold_mm_s, mob.smooth_s, mob.min_duration_s, fps)


# =============================================================================================
# statistics
# =============================================================================================
@dataclass
class Dist:
    """Speed distribution of one source."""
    n: int = 0
    hist: tuple = (np.empty(0), np.empty(0))       # (edges, counts)
    pdf: tuple = (np.empty(0), np.empty(0))        # (centres, density) linear bins [1/(mm/s)]
    pdf_log: tuple = (np.empty(0), np.empty(0))    # (centres, density) logarithmic bins
    ccdf: tuple = (np.empty(0), np.empty(0))       # (v sorted, P(V >= v))


@dataclass
class KinStats:
    n_frames: int                       # frames used
    dist: dict = field(default_factory=dict)       # source -> Dist ("colectiva", "robot", "individual")
    heat: dict = field(default_factory=dict)       # subset -> (H [robots/cm²], xedges, yedges)
    heat_frames: dict = field(default_factory=dict)
    v_mean: float = np.nan              # time average of V̄(t) [mm/s]
    v_std: float = np.nan
    v_mean_jam: float = np.nan
    v_mean_fluid: float = np.nan
    jam_frac: float = np.nan            # fraction of the used frames inside a jam
    n_jams: int = 0                     # jam episodes overlapping the used frames
    jam_dur_s: np.ndarray = field(default_factory=lambda: np.empty(0))
    G_jam: float = np.nan               # mean conductance during jams / fluid [µS]
    G_fluid: float = np.nan
    G_med_jam: float = np.nan
    G_med_fluid: float = np.nan
    w_mean: float = np.nan              # time average of <|ω|> over the robots [deg/s]
    e_tr: float = np.nan                # time averages of the kinetic energy of the set
    e_rot: float = np.nan               # (unit: MobilityData.energy_unit)


def frame_mask(t_frames: np.ndarray, a: Analysis, t_now: Optional[float] = None) -> np.ndarray:
    m = np.ones(len(t_frames), dtype=bool)
    if a.t_start is not None:
        m &= t_frames >= a.t_start
    if a.t_end is not None:
        m &= t_frames <= a.t_end
    for seg in a.exclusions:
        t0, t1 = sorted(float(v) for v in seg)
        m &= ~((t_frames >= t0) & (t_frames <= t1))
    if t_now is not None:
        m &= t_frames <= t_now
    return m


def samples(r: Robots, rows: np.ndarray, source: str, colectiva: Optional[np.ndarray] = None) -> np.ndarray:
    """Speed samples [mm/s] for the distributions, over the selected rows. colectiva replaces V̄
    per frame (e.g. its moving average) for the "colectiva" source."""
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", category=RuntimeWarning)
        if source == "individual":
            v = r.speed_mm_s[rows]
            if r.observed is not None:
                v = v[r.observed[rows]]
            v = v.ravel()
        elif source == "robot":
            v = r.speed_mm_s[rows]
            if r.observed is not None:
                v = np.where(r.observed[rows], v, np.nan)
            v = np.nanmean(v, axis=0) if len(v) else np.empty(0)
        else:
            v = (r.v_mean if colectiva is None else colectiva)[rows]
    v = np.asarray(v, dtype=float)
    return v[np.isfinite(v)]


def log_pdf(x: np.ndarray, bins: int) -> tuple[np.ndarray, np.ndarray]:
    """Density with logarithmically spaced bins (normalised over all samples, so the area of the
    visible part is the fraction of samples > 0)."""
    pos = x[x > 0]
    if len(pos) < 2 or pos.max() <= pos.min():
        return np.empty(0), np.empty(0)
    lo = max(pos.min(), np.percentile(pos, 0.1))
    edges = np.logspace(np.log10(lo), np.log10(pos.max()), max(5, int(bins)) + 1)
    cnt, _ = np.histogram(pos, edges)
    dens = cnt / (len(x) * np.diff(edges))
    return np.sqrt(edges[1:] * edges[:-1]), dens


def occupancy(r: Robots, rows: np.ndarray, bin_mm: float) -> tuple:
    """Mean number of robot centres per cm² in each bin, over the given rows."""
    R = r.r_int_mm if np.isfinite(r.r_int_mm) else float(np.nanmax(np.hypot(r.x_mm, r.y_mm)))
    n_bins = max(4, int(np.ceil(2 * R / max(bin_mm, 0.5))))
    edges = np.linspace(-R, R, n_bins + 1)
    x, y = r.x_mm[rows].ravel(), r.y_mm[rows].ravel()
    ok = np.isfinite(x) & np.isfinite(y)
    H, xe, ye = np.histogram2d(x[ok], y[ok], bins=(edges, edges))
    area_cm2 = (xe[1] - xe[0]) * (ye[1] - ye[0]) / 100.0
    n = max(int(rows.sum()) if rows.dtype == bool else len(rows), 1)
    return H / n / area_cm2, xe, ye


def compute_kin_stats(r: Robots, jams: Jams, t_frames: np.ndarray, mob: Mobility, a: Analysis,
                      t_now: Optional[float] = None, series=None, p_mask=None,
                      frame_of_t=None, colectiva: Optional[np.ndarray] = None) -> KinStats:
    """series / p_mask / frame_of_t: pressure samples (core.signal.Series, analysis mask, function
    sensor time -> video frame) to split G by state; omitted -> no G statistics."""
    rows = frame_mask(t_frames, a, t_now) & jams.valid
    ks = KinStats(int(rows.sum()))
    if ks.n_frames < 2:
        return ks
    for source in SOURCE_LABELS:
        x = samples(r, rows, source, colectiva)
        d = Dist(len(x))
        if len(x) >= 2 and np.ptp(x) > 0:
            cnt, edges = np.histogram(x, bins=max(5, int(mob.hist_bins)), range=(0.0, float(x.max())))
            d.hist = (edges, cnt.astype(float))
            d.pdf = histogram(x, mob.hist_bins)
            d.pdf_log = log_pdf(x, mob.hist_bins)
            d.ccdf = survival(x)
        ks.dist[source] = d

    vm = r.v_mean[rows]
    jm = jams.mask[rows]
    ks.v_mean, ks.v_std = float(np.nanmean(vm)), float(np.nanstd(vm, ddof=1))
    ks.jam_frac = float(jm.mean())
    if jm.any():
        ks.v_mean_jam = float(np.nanmean(vm[jm]))
    if (~jm).any():
        ks.v_mean_fluid = float(np.nanmean(vm[~jm]))
    used = np.flatnonzero(rows)
    durs = []
    for a0, b0 in jams.runs:
        inside = np.flatnonzero(rows[a0:b0 + 1])
        if len(inside):     # span within the used frames (clipped by crop / live cursor)
            durs.append(inside[-1] - inside[0] + 1)
    fps = jams.key[-1] if jams.key else 1.0
    ks.n_jams = len(durs)
    ks.jam_dur_s = np.asarray(durs, dtype=float) / fps

    if r.has_positions:
        for name, sel in (("todo", rows), ("atasco", rows & jams.mask), ("fluido", rows & ~jams.mask)):
            ks.heat_frames[name] = int(sel.sum())
            if sel.any():
                ks.heat[name] = occupancy(r, sel, mob.heat_bin_mm)

    if series is not None and p_mask is not None and frame_of_t is not None and len(used):
        fr = np.asarray(frame_of_t(series.t)) - int(r.frames[0])
        inside = p_mask & (fr >= 0) & (fr < len(jams.mask))
        fr_c = np.clip(fr, 0, len(jams.mask) - 1)
        inside &= jams.valid[fr_c]
        state = jams.mask[fr_c]
        g = series.G
        for flag, attr in ((True, "jam"), (False, "fluid")):
            sel = inside & (state == flag)
            if sel.sum() > 1:
                setattr(ks, f"G_{attr}", float(np.mean(g[sel])))
                setattr(ks, f"G_med_{attr}", float(np.median(g[sel])))
    return ks


def wall_layer(r: Robots, rows: np.ndarray) -> tuple[float, float]:
    """(mean distance to the centre [mm], fraction of robot-frames in the wall layer). Wall layer:
    centre closer than half a diameter to the contact radius Rc = q99.5(r) (comparar_ensayos.py)."""
    if not r.has_positions or not rows.any():
        return np.nan, np.nan
    rr = np.hypot(r.x_mm[rows], r.y_mm[rows])
    obs = r.observed[rows] if r.observed is not None else np.isfinite(rr)
    ok = obs & np.isfinite(rr)
    if ok.sum() < 10:
        return np.nan, np.nan
    rc = np.percentile(rr[ok], CONTACT_Q)
    return float(rr[ok].mean()), float((rr[ok] >= rc - r.diameter_mm / 2).mean())


# =============================================================================================
# one trial, as loaded by velocidades.py
# =============================================================================================
class MobilityData:
    """Trajectories of one trial plus, when the sensor log loads, its conductance series and the
    video <-> sensor synchronisation from the FSRScope configuration (read only)."""

    def __init__(self, trial: paths.Trial, robots: Robots, settings: VelSettings,
                 td: Optional[TrialData] = None, pressure_error: str = ""):
        self.trial, self.robots, self.settings = trial, robots, settings
        self.td, self.pressure_error = td, pressure_error
        self._jams: Optional[Jams] = None

    @classmethod
    def open(cls, trial: paths.Trial) -> "MobilityData":
        if trial.traj_path is None:
            raise ValueError(f"{trial.code}: no hay trayectorias VP_{trial.code}_robots.csv")
        robots = load_robots(trial.traj_path)
        td, err = None, ""
        try:
            td = TrialData.open(trial, load_trajectories=False)
        except Exception as exc:          # velocities are still usable without the sensor log
            err = str(exc)
        return cls(trial, robots, load_vel_settings(trial), td, err)

    # --- time base -----------------------------------------------------------------------------
    @property
    def fps(self) -> float:
        return self.td.settings.sync.frames_per_s if self.td is not None else DEFAULT_FPS

    @property
    def offset_s(self) -> float:
        """Sensor time of video frame 0 (0 without a sensor log)."""
        return self.td.offset_s if self.td is not None else 0.0

    @property
    def frame_times(self) -> np.ndarray:
        """Sensor time of every row [s]."""
        return self.offset_s + self.robots.frames / self.fps

    @property
    def frame_minutes(self) -> np.ndarray:
        """Video time of every row [min]."""
        return self.robots.frames / self.fps / 60.0

    def frames_at(self, t_sensor: np.ndarray) -> np.ndarray:
        t = np.asarray(t_sensor, dtype=float)
        return np.floor((t - self.offset_s) * self.fps + 1e-9).astype(np.int64)

    def sensor_to_minutes(self, t_sensor: np.ndarray) -> np.ndarray:
        return (np.asarray(t_sensor, dtype=float) - self.offset_s) / 60.0

    @property
    def duration_min(self) -> float:
        return float(self.frame_minutes[-1]) if len(self.robots.frames) else 0.0

    # --- window ----------------------------------------------------------------------------------
    def window(self) -> Analysis:
        """Window of this app as an Analysis in sensor time (no exclusions)."""
        s = self.settings
        a = Analysis()
        a.t_start = None if s.t_start_min is None else self.offset_s + 60.0 * s.t_start_min
        a.t_end = None if s.t_end_min is None else self.offset_s + 60.0 * s.t_end_min
        return a

    def pressure_analysis(self) -> Optional[Analysis]:
        """FSRScope analysis (crop, exclusions) narrowed to the window of this app."""
        if self.td is None:
            return None
        a = copy.deepcopy(self.td.settings.analysis)
        w = self.window()
        if w.t_start is not None:
            a.t_start = w.t_start if a.t_start is None else max(a.t_start, w.t_start)
        if w.t_end is not None:
            a.t_end = w.t_end if a.t_end is None else min(a.t_end, w.t_end)
        return a

    # --- jams --------------------------------------------------------------------------------------
    @property
    def jams(self) -> Jams:
        key = jam_key(self.settings.mobility, self.fps)
        if self._jams is None or self._jams.key != key:
            self._jams = detect_jams(self.robots, self.settings.mobility, self.fps)
        return self._jams

    def jam_spans_min(self) -> list[tuple[float, float]]:
        """Jam episodes in minutes of video [(t0, t1)]."""
        tm, dt = self.frame_minutes, 1.0 / self.fps / 60.0
        return [(float(tm[a]), float(tm[b]) + dt) for a, b in self.jams.runs]

    # --- smoothing, rotation, kinetic energy ---------------------------------------------------
    def smooth(self, x: np.ndarray, seconds: Optional[float] = None) -> np.ndarray:
        """Centered moving average over `seconds` (default: the window of the settings); rows
        without data (gap of a split video) stay empty."""
        w = self.settings.smooth_s if seconds is None else seconds
        k = max(1, int(round(float(w or 0.0) * self.fps)))
        x = np.asarray(x, dtype=float)
        return np.where(np.isfinite(x), rolling_mean(x, k), np.nan)

    @property
    def w_abs_mean(self) -> Optional[np.ndarray]:
        """<|ω|> over the robots per frame [deg/s] (None if the trajectories have no ω)."""
        w = self.robots.omega_rad_s
        if w is None:
            return None
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", category=RuntimeWarning)
            return np.degrees(np.nanmean(np.abs(w), axis=1))

    @property
    def energy_unit(self) -> str:
        return "nJ" if self.settings.mass_g > 0 else "µJ/kg"

    def energy(self) -> Optional[tuple[np.ndarray, np.ndarray]]:
        """Kinetic energy of the whole set per frame: (translation Σ½mv², rotation Σ½Iω²), with
        I = k m R² about each robot's own axis (König: the orbit is already in v). Per unit mass
        [mm²/s² = µJ/kg] when mass_g = 0, else [nJ] (1 g · 1 µJ/kg = 1 nJ). Sum = N · mean over the
        robots with data, so a robot missing in one frame does not drop the total."""
        r = self.robots
        if r.omega_rad_s is None:
            return None
        R = r.diameter_mm / 2
        scale = self.settings.mass_g if self.settings.mass_g > 0 else 1.0
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", category=RuntimeWarning)
            e_tr = r.n_robots * np.nanmean(0.5 * r.speed_mm_s ** 2, axis=1)
            e_rot = r.n_robots * np.nanmean(0.5 * self.settings.k_inertia * R * R * r.omega_rad_s ** 2, axis=1)
        return scale * e_tr, scale * e_rot

    # --- statistics ----------------------------------------------------------------------------
    def stats(self) -> KinStats:
        pa = self.pressure_analysis()
        series = self.td.series if self.td is not None else None
        pmask = analysis_mask(series, pa) if series is not None else None
        col = self.smooth(self.robots.v_mean) if self.settings.dist_smoothed else None
        ks = compute_kin_stats(self.robots, self.jams, self.frame_times, self.settings.mobility,
                               self.window(), None, series, pmask, self.frames_at, col)
        rows = frame_mask(self.frame_times, self.window()) & self.jams.valid
        if rows.sum() > 1:
            with warnings.catch_warnings():
                warnings.simplefilter("ignore", category=RuntimeWarning)
                w = self.w_abs_mean
                if w is not None:
                    ks.w_mean = float(np.nanmean(w[rows]))
                e = self.energy()
                if e is not None:
                    ks.e_tr, ks.e_rot = float(np.nanmean(e[0][rows])), float(np.nanmean(e[1][rows]))
        return ks
