"""Fixed-cardinality multi-object tracking over cached detection candidates.

Two-stage design:
  A) `extract_candidates` (expensive, once): permissive per-frame detection -> CandidateSet.
  B) `track` (cheap, repeatable): exactly N identities per frame using
       - constant-velocity prediction (EMA velocity, signed dt -> works forward and backward),
       - Hungarian assignment with distance gating,
       - adaptive acceptance ladder: strict ring coverage first, then progressively relaxed
         thresholds only for still-unmatched tracks and with a tighter gate around the prediction,
       - user anchors (manual centres) that override the frame and re-seed the track,
       - post-hoc linear interpolation of gaps bounded by observations on both sides.
"""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field, replace
from enum import IntEnum
from typing import Callable, Optional

import cv2
import numpy as np
import pandas as pd
from scipy.optimize import linear_sum_assignment
from scipy.spatial import cKDTree

from core import arena as arena_mod
from core import orientation as ori
from core import detection as det
from core.analysis import FrameProcessor, scan_video
from core.models import Roi, TrimRange

CANDIDATE_MIN_COVERAGE = 0.45   # floor kept in the cache; relaxed levels cannot go below it
CANDIDATE_SEPARATION_FACTOR = 0.8
_BIG = 1e9


class Status(IntEnum):
    DETECTED = 0      # strict detection
    RELAXED = 1       # detection accepted with auto-relaxed thresholds
    MANUAL = 2        # user-defined centre
    INTERPOLATED = 3  # gap <= max_gap, bounded by observations on both sides
    PREDICTED = 4     # extrapolated or long gap -> needs review
    MISSING = 5       # no position available


STATUS_LABELS = {
    Status.DETECTED: "detectado",
    Status.RELAXED: "detectado (umbral relajado)",
    Status.MANUAL: "manual",
    Status.INTERPOLATED: "interpolado",
    Status.PREDICTED: "predicho (revisar)",
    Status.MISSING: "perdido",
}
OBSERVED = (Status.DETECTED, Status.RELAXED, Status.MANUAL)

# BGR overlay colours
STATUS_COLORS = {
    Status.DETECTED: (0, 200, 0),
    Status.RELAXED: (230, 200, 0),
    Status.MANUAL: (255, 0, 255),
    Status.INTERPOLATED: (0, 165, 255),
    Status.PREDICTED: (0, 0, 255),
    Status.MISSING: (0, 0, 255),
}


@dataclass(frozen=True)
class TrackerParams:
    n_objects: int = 22
    search_range: float = 30.0        # gate radius for a 1-frame gap [px]
    gap_growth: float = 3.0           # extra gate per additional missing frame [px]
    min_separation: float = 60.0      # births must be this far from existing tracks [px]
    strict_coverage: float = 0.82
    min_mass: float = 0.0
    relax_coverages: tuple[float, ...] = (0.70, 0.55)
    relax_gate_factor: float = 0.6    # relaxed levels only accept close to the prediction
    max_gap: int = 15                 # longer estimated runs are flagged as PREDICTED
    velocity_alpha: float = 0.5       # EMA weight of the newest velocity sample
    interpolate: bool = True
    persistence_window: int = 20      # frames used to confirm a new track is a real object
    persistence_min: float = 0.75     # min fraction of the window where the chain finds a candidate


# --------------------------------------------------------------------------- candidates
@dataclass
class CandidateSet:
    """Per-frame candidate arrays. Coordinates in full-frame pixels."""

    frames: np.ndarray                         # (F,) sorted frame indices actually read
    xy: list[np.ndarray] = field(default_factory=list)    # each (k, 2)
    mass: list[np.ndarray] = field(default_factory=list)  # each (k,)
    cov: list[np.ndarray] = field(default_factory=list)   # each (k,), NaN -> not validated
    sig: Optional[list[np.ndarray]] = None                 # each (k, bands, K) rotation signatures

    @staticmethod
    def from_dataframe(df: pd.DataFrame, frames: np.ndarray,
                       sigs: Optional[np.ndarray] = None) -> "CandidateSet":
        """`sigs`, if given, is aligned with the rows of `df`."""
        frames = np.asarray(sorted(set(int(f) for f in frames)), dtype=np.int64)
        cs = CandidateSet(frames, sig=[] if sigs is not None else None)
        df = df.reset_index(drop=True)
        pos = df.groupby("frame").indices if len(df) else {}
        x, y = df["x"].to_numpy(float), df["y"].to_numpy(float)
        m, c = df["mass"].to_numpy(float), df["ring_cov"].to_numpy(float)
        for f in frames:
            ix = pos.get(int(f))
            if ix is None:
                ix = np.zeros(0, np.int64)
            cs.xy.append(np.column_stack([x[ix], y[ix]]) if len(ix) else np.zeros((0, 2)))
            cs.mass.append(m[ix])
            cs.cov.append(c[ix])
            if sigs is not None:
                cs.sig.append(sigs[ix])
        return cs

    def signature_rows(self) -> Optional[np.ndarray]:
        """Signatures concatenated in to_dataframe() row order."""
        if self.sig is None:
            return None
        parts = [s for s, xy in zip(self.sig, self.xy) if len(xy)]
        return np.concatenate(parts) if parts else None

    def to_dataframe(self) -> pd.DataFrame:
        rows = [pd.DataFrame({"frame": f, "x": xy[:, 0], "y": xy[:, 1], "mass": m, "ring_cov": c})
                for f, xy, m, c in zip(self.frames, self.xy, self.mass, self.cov) if len(xy)]
        if not rows:
            return pd.DataFrame(columns=["frame", "x", "y", "mass", "ring_cov"])
        return pd.concat(rows, ignore_index=True)

    def __len__(self) -> int:
        return len(self.frames)


def candidate_params(p: det.DetectionParams) -> det.DetectionParams:
    """Permissive version of the user's detection params used to fill the cache."""
    return replace(p, enabled=True, minmass=0.0,
                   min_coverage=min(p.min_coverage, CANDIDATE_MIN_COVERAGE) if p.validate_ring else 0.0,
                   separation=p.separation * CANDIDATE_SEPARATION_FACTOR)


def extract_candidates(src_path: str, trim: TrimRange, roi: Roi, processor: FrameProcessor,
                       progress: Optional[Callable[[int], None]] = None,
                       should_cancel: Optional[Callable[[], bool]] = None,
                       arena_step: int = 0, d_in_mm: float = arena_mod.D_IN_MM,
                       d_out_mm: float = arena_mod.D_OUT_MM):
    """Returns (CandidateSet, fps, cancelled, ArenaTrack or None).

    With arena_step > 0 the enclosure is measured in the same pass (every `arena_step` frames).
    """
    proc = FrameProcessor(processor.pipeline, candidate_params(processor.detection))
    samples: list = []
    df, frames, fps, cancelled, sigs = scan_video(src_path, trim, roi, proc, progress, should_cancel,
                                                  with_signatures=True, arena_step=arena_step,
                                                  arena_samples=samples)
    if cancelled:
        return None, fps, True, None
    track = (arena_mod.ArenaTrack.from_samples(samples, (roi.x, roi.y), d_in_mm, d_out_mm, arena_step)
             if arena_step > 0 else None)
    return CandidateSet.from_dataframe(df, frames, sigs), fps, False, track


# --------------------------------------------------------------------------- result
@dataclass
class TrackingResult:
    frames: np.ndarray        # (F,)
    x: np.ndarray             # (F, N)
    y: np.ndarray
    status: np.ndarray        # (F, N) int8
    mass: np.ndarray
    cov: np.ndarray
    init_frame: int
    cand_idx: Optional[np.ndarray] = None   # (F, N) index of the assigned candidate, -1 if none

    @property
    def n_objects(self) -> int:
        return self.x.shape[1]

    def slice(self, a: int, b: int) -> "TrackingResult":
        """Rows [a, b] (inclusive) as an independent result."""
        sl = slice(a, b + 1)
        return TrackingResult(self.frames[sl].copy(), self.x[sl].copy(), self.y[sl].copy(),
                              self.status[sl].copy(), self.mass[sl].copy(), self.cov[sl].copy(),
                              self.init_frame,
                              None if self.cand_idx is None else self.cand_idx[sl].copy())

    def row_of(self, frame: int) -> Optional[int]:
        i = int(np.searchsorted(self.frames, frame))
        return i if i < len(self.frames) and self.frames[i] == frame else None

    def at(self, frame: int) -> Optional[tuple[np.ndarray, np.ndarray]]:
        i = self.row_of(frame)
        if i is None:
            return None
        return np.stack([self.x[i], self.y[i]], axis=1), self.status[i]

    def issues(self) -> pd.DataFrame:
        """One row per frame that has any estimated (non-observed) object."""
        s = self.status
        n_interp = (s == Status.INTERPOLATED).sum(1)
        n_pred = (s == Status.PREDICTED).sum(1)
        n_miss = (s == Status.MISSING).sum(1)
        bad = (n_interp + n_pred + n_miss) > 0
        rows = []
        for i in np.flatnonzero(bad):
            est = np.flatnonzero(s[i] >= Status.INTERPOLATED)
            sev = "error" if (n_pred[i] + n_miss[i]) > 0 else "advertencia"
            rows.append({"frame": int(self.frames[i]), "severity": sev,
                         "n_observed": int(self.n_objects - len(est)),
                         "n_interpolated": int(n_interp[i]), "n_predicted": int(n_pred[i]),
                         "n_missing": int(n_miss[i]),
                         "objects": " ".join(str(k) for k in est)})
        return pd.DataFrame(rows, columns=["frame", "severity", "n_observed", "n_interpolated",
                                           "n_predicted", "n_missing", "objects"])

    def summary(self) -> dict:
        s = self.status
        counts = {st: int((s == st).sum()) for st in Status}
        iss = self.issues()
        return {"frames": len(self.frames), "points": int(s.size), "counts": counts,
                "frames_warning": int((iss["severity"] == "advertencia").sum()),
                "frames_error": int((iss["severity"] == "error").sum())}

    def to_dataframe(self, fps: float, origin: tuple[float, float] = (0.0, 0.0)) -> pd.DataFrame:
        """x_px/y_px are relative to `origin` (the analysed crop); *_video_px are full-frame."""
        F, N = self.x.shape
        df = pd.DataFrame({
            "frame": np.repeat(self.frames, N),
            "particle": np.tile(np.arange(N), F),
            "x_px": self.x.ravel() - origin[0], "y_px": self.y.ravel() - origin[1],
            "status_code": self.status.ravel().astype(int),
            "mass": self.mass.ravel(), "ring_cov": self.cov.ravel(),
            "x_video_px": self.x.ravel(), "y_video_px": self.y.ravel(),
        })
        df.insert(1, "t_s", df["frame"] / fps)
        df.insert(6, "status", df["status_code"].map({int(k): v for k, v in STATUS_LABELS.items()}))
        return df


# --------------------------------------------------------------------------- tracker
class _State:
    """Per-track kinematic state. Velocity is in forward time (px/frame)."""

    def __init__(self, n: int):
        self.has = np.zeros(n, bool)
        self.xy = np.full((n, 2), np.nan)
        self.f = np.zeros(n, np.int64)
        self.v = np.zeros((n, 2))
        self.has_v = np.zeros(n, bool)

    def predict(self, frame: int, max_gap: int) -> tuple[np.ndarray, np.ndarray]:
        dt = frame - self.f
        eff = np.sign(dt) * np.minimum(np.abs(dt), max_gap)  # damp long extrapolations
        return self.xy + self.v * eff[:, None], np.abs(dt)

    def observe(self, k: int, frame: int, xy: np.ndarray, alpha: float, reset_v: bool = False) -> None:
        if reset_v:
            self.v[k] = 0.0
            self.has_v[k] = False
        elif self.has[k] and frame != self.f[k]:
            v_new = (xy - self.xy[k]) / (frame - self.f[k])
            self.v[k] = v_new if not self.has_v[k] else alpha * v_new + (1 - alpha) * self.v[k]
            self.has_v[k] = True
        self.has[k] = True
        self.xy[k] = xy
        self.f[k] = frame


def _gated_assign(pred: np.ndarray, gates: np.ndarray, cand: np.ndarray) -> list[tuple[int, int]]:
    if len(pred) == 0 or len(cand) == 0:
        return []
    d = np.linalg.norm(pred[:, None, :] - cand[None, :, :], axis=2)
    cost = np.where(d <= gates[:, None], d, _BIG)
    r, c = linear_sum_assignment(cost)
    return [(i, j) for i, j in zip(r, c) if cost[i, j] < _BIG]


def _score(mass: np.ndarray, cov: np.ndarray) -> np.ndarray:
    return mass * np.nan_to_num(cov, nan=1.0)


class _Persistence:
    """Chained nearest-neighbour persistence of candidates (lazy KD-trees per frame)."""

    def __init__(self, cands: CandidateSet, p: TrackerParams):
        self.c, self.p = cands, p
        self._trees: dict[int, Optional[cKDTree]] = {}

    def _tree(self, i: int) -> Optional[cKDTree]:
        if i not in self._trees:
            xy = self.c.xy[i]
            self._trees[i] = cKDTree(xy) if len(xy) else None
        return self._trees[i]

    def __call__(self, i: int, js: np.ndarray, direction: int = 1) -> np.ndarray:
        """Fraction of the next W frames (in `direction`) where each chain finds a candidate."""
        if len(js) == 0:
            return np.zeros(0)
        W = max(1, self.p.persistence_window)
        F = len(self.c)
        if not (0 <= i + direction < F):  # at the boundary: look the other way
            direction = -direction
        pos = self.c.xy[i][js].copy()
        hits = np.zeros(len(js))
        steps = 0
        for d in range(1, W + 1):
            t = i + direction * d
            if not (0 <= t < F):
                break
            steps += 1
            tree = self._tree(t)
            if tree is None:
                continue
            dist, idx = tree.query(pos, distance_upper_bound=self.p.search_range)
            ok = np.isfinite(dist)
            hits += ok
            pos[ok] = self.c.xy[t][idx[ok]]
        return hits / steps if steps else np.ones(len(js))


def _strict_mask(cands: CandidateSet, i: int, p: TrackerParams) -> np.ndarray:
    cov = np.nan_to_num(cands.cov[i], nan=1.0)
    return (cov >= p.strict_coverage) & (cands.mass[i] >= p.min_mass)


def _confirmed(cands: CandidateSet, i: int, p: TrackerParams, pers: _Persistence,
               direction: int = 1) -> tuple[np.ndarray, np.ndarray]:
    """Strict candidates at row i that persist; returned sorted by (persistence, score) desc."""
    js = np.flatnonzero(_strict_mask(cands, i, p))
    if len(js) == 0:
        return js, np.zeros(0)
    pr = pers(i, js, direction)
    keep = pr >= p.persistence_min
    js, pr = js[keep], pr[keep]
    sc = _score(cands.mass[i][js], cands.cov[i][js])
    order = np.lexsort((-sc, -pr))
    return js[order], pr[order]


def _choose_init_row(cands: CandidateSet, p: TrackerParams, pers: _Persistence) -> int:
    best_i, best_n = 0, -1
    for i in range(len(cands)):
        if _strict_mask(cands, i, p).sum() < min(p.n_objects, best_n + 1):
            continue  # cannot beat the current best; skip the persistence cost
        js, _ = _confirmed(cands, i, p, pers)
        n = len(_non_overlapping(cands.xy[i][js], p.min_separation, p.n_objects))
        if n >= p.n_objects:
            return i
        if n > best_n:
            best_i, best_n = i, n
    return best_i


def _non_overlapping(xy: np.ndarray, min_sep: float, limit: int,
                     occupied: Optional[np.ndarray] = None) -> list[int]:
    """Greedy selection (input order = priority) of points at least `min_sep` apart."""
    chosen: list[int] = []
    occ = [] if occupied is None else [q for q in occupied]
    for j, q in enumerate(xy):
        if len(chosen) >= limit:
            break
        if all(np.hypot(*(q - o)) >= min_sep for o in occ):
            chosen.append(j)
            occ.append(q)
    return chosen


def track(cands: CandidateSet, p: TrackerParams,
          anchors: Optional[dict[tuple[int, int], tuple[float, float]]] = None,
          progress: Optional[Callable[[int], None]] = None,
          should_cancel: Optional[Callable[[], bool]] = None) -> Optional[TrackingResult]:
    """Returns None if cancelled."""
    if p.n_objects < 1:
        raise ValueError("La cantidad de objetos debe ser ≥ 1.")
    if len(cands) == 0:
        raise ValueError("No hay cuadros analizados.")
    anchors = anchors or {}
    F, N = len(cands), p.n_objects
    X = np.full((F, N), np.nan)
    Y = np.full((F, N), np.nan)
    S = np.full((F, N), int(Status.MISSING), np.int8)
    M = np.full((F, N), np.nan)
    C = np.full((F, N), np.nan)
    CI = np.full((F, N), -1, np.int32)

    by_frame: dict[int, dict[int, tuple[float, float]]] = {}
    for (fr, k), xy in anchors.items():
        if 0 <= k < N:
            by_frame.setdefault(int(fr), {})[int(k)] = xy

    levels = [(p.strict_coverage, 1.0, Status.DETECTED)]
    levels += [(c, p.relax_gate_factor, Status.RELAXED)
               for c in sorted(p.relax_coverages, reverse=True) if c < p.strict_coverage]

    def step(i: int, st: _State, direction: int) -> None:
        fr = int(cands.frames[i])
        xy, mass = cands.xy[i], cands.mass[i]
        cov = np.nan_to_num(cands.cov[i], nan=1.0)
        used = np.zeros(len(xy), bool)
        done = np.zeros(N, bool)

        # 1) manual anchors: hard constraints; nearby candidates are consumed.
        for k, (ax, ay) in by_frame.get(fr, {}).items():
            a = np.array([ax, ay], float)
            st.observe(k, fr, a, p.velocity_alpha, reset_v=True)
            X[i, k], Y[i, k], S[i, k] = a[0], a[1], Status.MANUAL
            if len(xy):
                used |= np.linalg.norm(xy - a, axis=1) < p.search_range
            done[k] = True

        # 2) adaptive ladder over the remaining tracks
        pred, gap = st.predict(fr, p.max_gap)
        base_gate = np.minimum(p.search_range + p.gap_growth * np.maximum(gap - 1, 0), 2 * p.search_range)
        for cov_thr, gate_factor, status in levels:
            ks = np.flatnonzero(st.has & ~done)
            js = np.flatnonzero(~used & (cov >= cov_thr) & (mass >= (p.min_mass if status == Status.DETECTED else 0)))
            for a, b in _gated_assign(pred[ks], base_gate[ks] * gate_factor, xy[js]):
                k, j = ks[a], js[b]
                st.observe(k, fr, xy[j], p.velocity_alpha)
                X[i, k], Y[i, k], S[i, k] = xy[j, 0], xy[j, 1], status
                M[i, k], C[i, k], CI[i, k] = mass[j], cands.cov[i][j], j
                used[j] = True
                done[k] = True

        # 3) births for tracks never initialised: persistent strict leftovers far from everyone
        unborn = np.flatnonzero(~st.has & ~done)
        if len(unborn):
            js, _ = _confirmed(cands, i, p, pers, direction)
            js = js[~used[js]]
            occupied = np.vstack([st.xy[st.has], xy[used]])
            for k, b in zip(unborn, _non_overlapping(xy[js], p.min_separation, len(unborn), occupied)):
                j = js[b]
                st.observe(k, fr, xy[j], p.velocity_alpha)
                X[i, k], Y[i, k], S[i, k] = xy[j, 0], xy[j, 1], Status.DETECTED
                M[i, k], C[i, k], CI[i, k] = mass[j], cands.cov[i][j], j
                used[j] = True
                done[k] = True

        # 4) unmatched tracks keep their prediction (provisional; refined in post-processing)
        for k in np.flatnonzero(st.has & ~done):
            X[i, k], Y[i, k], S[i, k] = pred[k, 0], pred[k, 1], Status.PREDICTED

    pers = _Persistence(cands, p)
    i0 = _choose_init_row(cands, p, pers)
    done_rows = 0

    def tick() -> bool:
        nonlocal done_rows
        done_rows += 1
        if progress is not None and done_rows % 200 == 0:
            progress(int(100 * done_rows / F))
        return should_cancel is not None and done_rows % 200 == 0 and should_cancel()

    fwd = _State(N)
    for i in range(i0, F):
        step(i, fwd, +1)
        if tick():
            return None
    # Backward pass seeded with the init-frame observations (velocity sign handled by signed dt).
    bwd = _State(N)
    for k in range(N):
        if S[i0, k] in OBSERVED:
            bwd.observe(k, int(cands.frames[i0]), np.array([X[i0, k], Y[i0, k]]), p.velocity_alpha, reset_v=True)
    for i in range(i0 - 1, -1, -1):
        step(i, bwd, -1)
        if tick():
            return None

    _postprocess(cands.frames, X, Y, S, p)
    return TrackingResult(cands.frames.copy(), X, Y, S, M, C, int(cands.frames[i0]), CI)


def _runs(mask: np.ndarray) -> list[tuple[int, int]]:
    """Inclusive [start, end] index runs where mask is True."""
    if not mask.any():
        return []
    d = np.diff(np.concatenate([[0], mask.astype(np.int8), [0]]))
    return list(zip(np.flatnonzero(d == 1), np.flatnonzero(d == -1) - 1))


def _postprocess(frames: np.ndarray, X, Y, S, p: TrackerParams) -> None:
    obs_codes = [int(s) for s in OBSERVED]
    for k in range(X.shape[1]):
        observed = np.isin(S[:, k], obs_codes)
        for a, b in _runs(~observed):
            bounded = a > 0 and b < len(frames) - 1
            length = int(frames[b] - frames[a] + 1)
            if bounded and p.interpolate:
                f0, f1 = frames[a - 1], frames[b + 1]
                w = (frames[a:b + 1] - f0) / (f1 - f0)
                X[a:b + 1, k] = X[a - 1, k] + w * (X[b + 1, k] - X[a - 1, k])
                Y[a:b + 1, k] = Y[a - 1, k] + w * (Y[b + 1, k] - Y[a - 1, k])
                S[a:b + 1, k] = Status.INTERPOLATED if length <= p.max_gap else Status.PREDICTED
            else:
                seg = S[a:b + 1, k]
                seg[seg != Status.MISSING] = Status.PREDICTED


# --------------------------------------------------------------------------- drawing
ARROW_FRAMES = 7.5     # velocity arrow = displacement over this many frames (time-scale independent)


def _outlined_line(img, p0, p1, col, th, arrow=False):
    f = cv2.arrowedLine if arrow else cv2.line
    kw = {"tipLength": 0.3} if arrow else {}
    f(img, p0, p1, (0, 0, 0), th + 2, cv2.LINE_AA, **kw)
    f(img, p0, p1, col, th, cv2.LINE_AA, **kw)


def draw_oriented(img: np.ndarray, key: str, xy: np.ndarray, status: np.ndarray, radius: float,
                  selected: Optional[int] = None, velocity: Optional[np.ndarray] = None,
                  theta_deg: Optional[np.ndarray] = None, fps: float = 30.0) -> np.ndarray:
    """draw_tracks on the oriented image (core.orientation); inputs in raw `img` pixel coordinates."""
    h, w = img.shape[:2]
    out = ori.image(img, key)
    qx, qy = ori.points(xy[:, 0], xy[:, 1], w, h, key)
    vel = None
    if velocity is not None:
        vx, vy = ori.vectors(velocity[:, 0], velocity[:, 1], key)
        vel = np.column_stack([vx, vy])
    ang = None if theta_deg is None else ori.signs(key)[2] * np.asarray(theta_deg, float)
    return draw_tracks(out, np.column_stack([qx, qy]), status, radius, selected, vel, ang, fps=fps)


def draw_tracks(img: np.ndarray, xy: np.ndarray, status: np.ndarray, radius: float,
                selected: Optional[int] = None, velocity: Optional[np.ndarray] = None,
                theta_deg: Optional[np.ndarray] = None, fps: float = 30.0) -> np.ndarray:
    """xy in `img` pixel coordinates; velocity (N, 2) px/s (real time); theta_deg (N,) CCW from first frame.

    `fps` = frames per real second: the arrow shows the displacement over ARROW_FRAMES frames,
    so its on-screen length does not depend on the time scale.

    Orientation: a tick at 12 o'clock marks the reference (theta = 0, robot as in the first frame);
    the white needle shows the current orientation rotated by theta.
    """
    out = cv2.cvtColor(img, cv2.COLOR_GRAY2BGR) if img.ndim == 2 else img.copy()
    h, w = out.shape[:2]
    th = max(2, int(round(min(h, w) / 400)))
    fs = max(0.45, radius / 60)
    r = int(round(radius))
    for k, ((x, y), s) in enumerate(zip(xy, status)):
        if not (np.isfinite(x) and np.isfinite(y)):
            continue
        c = (int(round(x)), int(round(y)))
        col = STATUS_COLORS[Status(int(s))]
        if s >= Status.INTERPOLATED:  # dashed look for estimated positions
            for a0 in range(0, 360, 30):
                cv2.ellipse(out, c, (r, r), 0, a0, a0 + 18, col, th, cv2.LINE_AA)
        else:
            cv2.circle(out, c, r, col, th, cv2.LINE_AA)
        if selected == k:
            cv2.circle(out, c, r + 3 * th, (255, 255, 255), th, cv2.LINE_AA)
        if theta_deg is not None and np.isfinite(theta_deg[k]):
            t = np.radians(theta_deg[k])
            _outlined_line(out, (c[0], c[1] - r - max(3, r // 6)), (c[0], c[1] - r + max(4, r // 4)),
                           (200, 200, 200), th)   # theta = 0 reference
            tip = (int(round(x - 0.85 * r * np.sin(t))), int(round(y - 0.85 * r * np.cos(t))))
            _outlined_line(out, c, tip, (255, 255, 255), th)
        if velocity is not None and np.all(np.isfinite(velocity[k])):
            v = velocity[k] * (ARROW_FRAMES / fps)
            n = float(np.hypot(*v))
            if n > 1.0:
                v = v * min(1.0, 2.5 * r / n)
                tip = (int(round(x + v[0])), int(round(y + v[1])))
                _outlined_line(out, c, tip, (0, 230, 255), th, arrow=True)
        cv2.circle(out, c, th + 1, col, -1, cv2.LINE_AA)
        txt = str(k)
        (tw, _), _ = cv2.getTextSize(txt, cv2.FONT_HERSHEY_SIMPLEX, fs, th)
        org = (c[0] - tw // 2, c[1] + int(r * 0.6))
        cv2.putText(out, txt, org, cv2.FONT_HERSHEY_SIMPLEX, fs, (0, 0, 0), th + 3, cv2.LINE_AA)
        cv2.putText(out, txt, org, cv2.FONT_HERSHEY_SIMPLEX, fs, (255, 255, 255), th, cv2.LINE_AA)
    n_obs = int(np.isin(status, [int(s) for s in OBSERVED]).sum())
    label = f"{n_obs}/{len(status)} observados"
    fs2 = max(0.6, min(h, w) / 700)
    col = (0, 255, 255) if n_obs == len(status) else (0, 0, 255)
    cv2.putText(out, label, (10, int(30 * fs2)), cv2.FONT_HERSHEY_SIMPLEX, fs2, (0, 0, 0), th + 3, cv2.LINE_AA)
    cv2.putText(out, label, (10, int(30 * fs2)), cv2.FONT_HERSHEY_SIMPLEX, fs2, col, th, cv2.LINE_AA)
    return out


# --------------------------------------------------------------------------- session
@dataclass
class SessionView:
    """Time-trimmed view of a full analysis (no re-analysis needed)."""

    result: TrackingResult
    kin: Optional[object]      # core.kinematics.Kinematics
    rows: tuple[int, int]      # row range in the full result
    message: str               # empty if the view equals the full analysis


@dataclass
class TrackingSession:
    """Everything needed to re-run tracking/kinematics without re-reading the video."""

    src_path: str
    roi: Roi
    trim: TrimRange
    fps: float
    detection: det.DetectionParams
    candidates: CandidateSet
    params: TrackerParams = field(default_factory=TrackerParams)
    anchors: dict[tuple[int, int], tuple[float, float]] = field(default_factory=dict)
    result: Optional[TrackingResult] = None
    kin_params: Optional[object] = None   # core.kinematics.KinematicsParams
    kin: Optional[object] = None          # core.kinematics.Kinematics (full range)
    arena: Optional[arena_mod.ArenaTrack] = None   # enclosure (origin and scale of the exports)

    def run(self, progress=None, should_cancel=None) -> Optional[TrackingResult]:
        res = track(self.candidates, self.params, self.anchors, progress, should_cancel)
        if res is not None:
            self.result = res
            self.kin = self.compute_kinematics(res)
        return res

    def compute_kinematics(self, result: Optional[TrackingResult] = None):
        from core import kinematics as km
        result = result or self.result
        if result is None:
            return None
        p = self.kin_params or km.KinematicsParams()
        return km.compute(result, self.candidates.sig, self.fps, p, self.detection.r_out, self.arena,
                          (self.roi.x, self.roi.y, self.roi.w, self.roi.h))

    @property
    def has_rotation(self) -> bool:
        return self.candidates.sig is not None

    def view(self, trim: Optional[TrimRange] = None) -> Optional[SessionView]:
        """Full result restricted to `trim` (intersection). Kinematics are sliced, never recomputed,
        so derivatives at the cut keep their full-range context; theta is re-zeroed at the cut."""
        res = self.result
        if res is None:
            return None
        f = res.frames
        a, b = 0, len(f) - 1
        msg = ""
        if trim is not None:
            lo, hi = max(trim.start, int(f[0])), min(trim.end, int(f[-1]))
            if lo > hi:
                msg = (f"El tramo {trim.start}–{trim.end} no se superpone con lo analizado "
                       f"({f[0]}–{f[-1]}); se muestra el análisis completo.")
            else:
                a = int(np.searchsorted(f, lo))
                b = int(np.searchsorted(f, hi, side="right")) - 1
                if trim.start < f[0] or trim.end > f[-1]:
                    msg = (f"El tramo pedido ({trim.start}–{trim.end}) excede lo analizado ({f[0]}–{f[-1]}): "
                           f"se muestra la intersección {f[a]}–{f[b]}. Volvé a analizar para cubrirlo.")
                elif (a, b) != (0, len(f) - 1):
                    msg = (f"Mostrando cuadros {f[a]}–{f[b]}, recortados del análisis completo "
                           f"({f[0]}–{f[-1]}). θ = 0 en el cuadro {f[a]}.")
        if (a, b) == (0, len(f) - 1):
            return SessionView(res, self.kin, (a, b), msg)
        kin = self.kin.slice(a, b) if self.kin is not None else None
        return SessionView(res.slice(a, b), kin, (a, b), msg)

    def to_dataframe(self, view: Optional[SessionView] = None) -> pd.DataFrame:
        from core import kinematics as km
        v = view or self.view()
        if v is None:
            raise RuntimeError("No hay resultados de seguimiento.")
        if v.kin is None:
            return v.result.to_dataframe(self.fps, (self.roi.x, self.roi.y))
        return km.table(v.result, v.kin, (self.roi.x, self.roi.y), (self.roi.w, self.roi.h))

    def robot_dataframe(self, k: int, view: Optional[SessionView] = None) -> pd.DataFrame:
        """Every column of the long table for robot k only (one row per frame)."""
        from core import kinematics as km
        return km.robot_table(self.to_dataframe(view), k)

    def export_info(self, view: Optional[SessionView] = None) -> dict:
        """Metadata written next to every CSV export (JSON side-car)."""
        v = view or self.view()
        kin = v.kin if v is not None else None
        info = {"video": self.src_path, "roi": asdict(self.roi),
                "cuadros": [int(v.result.frames[0]), int(v.result.frames[-1])] if v is not None else None,
                "cuadros_por_segundo_real": self.fps,
                "convencion": ("origen en el centro del recinto en cada cuadro; x a la derecha, y hacia arriba; "
                               "escena vista por el observador (ver 'orientacion'); ángulos positivos "
                               "antihorarios; "
                               "theta = 0 en el primer cuadro del tramo"),
                "recinto": self.arena.stats() if self.arena is not None else None}
        if kin is not None:
            info.update({"origen": kin.origin, "fuente_escala": kin.scale_source,
                         "mm_por_px_mediana": kin.mm_per_px, "kappa_perspectiva_aplicado": kin.kappa,
                         "kappa_perspectiva_medido": kin.kappa_measured,
                         "r_contacto_sobre_r_int": kin.r_contact_rel,
                         "diametro_robot_mm": kin.robot_diameter_mm, "orientacion": kin.mirror,
                         "orientacion_descripcion": ori.DESCRIPTION[ori.valid(kin.mirror)]})
        return info

    def summary_dataframe(self, view: Optional[SessionView] = None) -> pd.DataFrame:
        from core import kinematics as km
        v = view or self.view()
        return km.summary(v.result, v.kin)

    def set_anchor(self, frame: int, k: int, x: float, y: float) -> None:
        self.anchors[(int(frame), int(k))] = (float(x), float(y))

    def remove_anchors(self, frame: int, k: Optional[int] = None) -> int:
        keys = [key for key in self.anchors if key[0] == frame and (k is None or key[1] == k)]
        for key in keys:
            del self.anchors[key]
        return len(keys)

    def annotator(self, view: Optional[SessionView] = None, show_velocity: bool = True,
                  show_orientation: bool = True, show_arena: bool = True) -> Callable[[np.ndarray, int], np.ndarray]:
        """Thread-safe overlay callable (frame crop, frame index) -> annotated crop, ORIENTED as the
        scene is shown (core.orientation: e.g. rotated 180 deg), with labels drawn upright."""
        v = view or self.view()
        if v is None:
            raise RuntimeError("No hay resultados de seguimiento.")
        res, kin, roi, r = v.result, v.kin, self.roi, self.detection.r_out
        off = np.array([roi.x, roi.y])
        key = ori.valid(getattr(self.kin_params, "mirror", ori.NONE) if self.kin_params is not None else ori.NONE)

        def annotate(img: np.ndarray, idx: int) -> np.ndarray:
            i = res.row_of(idx)
            if i is None:
                return ori.image(img, key)
            vel = np.stack([kin.vx[i], kin.vy[i]], 1) if (kin is not None and show_velocity) else None
            ang = kin.theta[i] if (kin is not None and show_orientation and self.has_rotation) else None
            xy = np.stack([res.x[i], res.y[i]], 1) - off
            out = draw_oriented(img, key, xy, res.status[i], r, velocity=vel, theta_deg=ang, fps=self.fps)
            if show_arena and self.arena is not None and self.arena.defined:
                a, _ = arena_mod.oriented(self.arena.arena_at(idx), (roi.x, roi.y), img.shape[1::-1], key)
                out = arena_mod.draw(out, a, (roi.x, roi.y), ori.NONE)
            return out
        return annotate

    # --- persistence (.npz: arrays + JSON metadata, no pickle) ---
    def save(self, path: str) -> None:
        cdf = self.candidates.to_dataframe()
        a = np.array([[f, k, x, y] for (f, k), (x, y) in self.anchors.items()], float).reshape(-1, 4)
        kp = asdict(self.kin_params) if self.kin_params is not None else None
        meta = {"version": 3, "src_path": self.src_path, "roi": asdict(self.roi), "trim": asdict(self.trim),
                "fps": self.fps, "detection": asdict(self.detection), "kinematics": kp,
                "params": {**asdict(self.params), "relax_coverages": list(self.params.relax_coverages)},
                "arena": self.arena.meta() if self.arena is not None else None}
        arrays = {"meta": np.array(json.dumps(meta)), "frames": self.candidates.frames,
                  "cand": cdf[["frame", "x", "y", "mass", "ring_cov"]].to_numpy(float), "anchors": a}
        if self.arena is not None:
            arrays.update(self.arena.to_arrays())
        sig = self.candidates.signature_rows()
        if sig is not None:
            arrays["sig"] = sig.astype(np.complex64)
        np.savez_compressed(path, **arrays)

    @staticmethod
    def load(path: str) -> "TrackingSession":
        from core import kinematics as km
        with np.load(path, allow_pickle=False) as z:
            meta = json.loads(str(z["meta"]))
            frames = z["frames"].astype(np.int64)
            cand = z["cand"]
            anchors_arr = z["anchors"]
            sig = z["sig"] if "sig" in z.files else None
            arena_arr = z["arena"] if "arena" in z.files else None
        if meta.get("version") not in (1, 2, 3):
            raise ValueError("Versión de archivo de análisis no soportada.")
        cdf = pd.DataFrame(cand, columns=["frame", "x", "y", "mass", "ring_cov"])
        cdf["frame"] = cdf["frame"].astype(np.int64)
        if sig is not None and len(sig) != len(cdf):
            sig = None  # inconsistent file: drop rotation rather than misalign it
        params = meta["params"]
        params["relax_coverages"] = tuple(params["relax_coverages"])
        kp = meta.get("kinematics")
        if kp:
            known = set(km.KinematicsParams.__dataclass_fields__)
            kp = {k: v for k, v in kp.items() if k in known}
        return TrackingSession(
            src_path=meta["src_path"], roi=Roi(**meta["roi"]), trim=TrimRange(**meta["trim"]),
            fps=float(meta["fps"]), detection=det.DetectionParams(**meta["detection"]),
            candidates=CandidateSet.from_dataframe(cdf, frames, sig), params=TrackerParams(**params),
            anchors={(int(f), int(k)): (float(x), float(y)) for f, k, x, y in anchors_arr},
            kin_params=km.KinematicsParams(**kp) if kp else None,
            arena=arena_mod.ArenaTrack.from_saved(arena_arr, meta.get("arena")))
