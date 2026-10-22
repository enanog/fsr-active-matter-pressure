"""Per-robot kinematics from a TrackingResult: velocity vector, orientation and angular velocity.

Derivatives use a Savitzky-Golay filter (local polynomial least squares, deriv=1): position noise
is ~1-5 px/frame, which a finite difference would amplify by fps. Everything is computed on the
whole analysed range and only then sliced, so the edges of a later time trim keep full context.

Conventions (screen / image coordinates):
  x_px to the right, y_px downwards (same as the image).
  vx, vy = dx/dt, dy/dt in those axes.
  vel_dir_deg, theta_deg, omega: counter-clockwise as seen on screen (math convention, y up),
  vel_dir_deg = atan2(-vy, vx) in (-180, 180], 0 deg = to the right.
  theta_deg = accumulated rotation (multi-turn) relative to the robot's own orientation in the
  first frame of the (possibly trimmed) range.

Orientation of the scene (KinematicsParams.mirror, see core.orientation): no | rot180 | horizontal |
vertical. Everything is computed in image coordinates, and only the exported tables are converted to
the scene as the observer sees it (x right, y away from the observer): positions and velocities get
the axis signs (sx, sy); theta and omega are multiplied by -1 for a mirror and kept for rot180 (a
rotation keeps the sense of rotation). x_video_px / y_video_px always stay in file pixels.

Enclosure reference frame (exports): with an ArenaTrack (core.arena) every position is expressed
relative to the enclosure centre OF ITS OWN FRAME, x to the right, y UP, in the displayed scene, and
converted to mm with the scale of that frame:
    x_mm(f) = s(f) * sx * (x_video(f) - c_x(f)),   y_mm(f) = -s(f) * sy * (y_video(f) - c_y(f)),
with (sx, sy) = (-1, -1) for rot180, -1 on the mirrored axis for a mirror. The velocities of the
export are SG derivatives of x_mm, y_mm
(robot velocity relative to the enclosure). Scale s(f), by KinematicsParams.scale_source:
    "recinto"     s(f) = (D_in / 2) / r_in(f)                     (default; follows camera zoom)
    "perspectiva" s(f) = kappa * (D_in / 2) / r_in(f),  kappa = (D_in/2 - D/2) / (q99.5(r/r_in) * D_in/2)
                  (robots touching the wall end exactly at R_in: corrects the height of the robot tops)
    "robot"       s = D / (2 r_ext) from the robot calibration (constant; old behaviour)
Without enclosure the origin is the centre of the analysed crop and the scale comes from the robot.
"""
from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Optional

import numpy as np
import pandas as pd
from scipy.signal import savgol_filter

from core import orientation as ori
from core import rotation as rot
from core.tracking import OBSERVED, STATUS_LABELS, Status, TrackingResult

SCALE_ARENA = "recinto"
SCALE_PERSPECTIVE = "perspectiva"
SCALE_ROBOT = "robot"
SCALE_LABELS = {SCALE_ARENA: "Recinto (diámetro interior)",
                SCALE_PERSPECTIVE: "Recinto + corrección de perspectiva",
                SCALE_ROBOT: "Diámetro del robot"}
CONTACT_QUANTILE = 99.5      # percentile of r / r_in taken as "robot touching the wall"

ROT_MEASURED = 0
ROT_INTERPOLATED = 1
ROT_UNAVAILABLE = 2
ARROW_NOTE = ("Flecha amarilla: velocidad (largo = desplazamiento en 7,5 cuadros). Aguja blanca: "
              "orientación actual; la marca a las 12 h es la referencia θ = 0 (el robot como estaba en "
              "el primer cuadro del tramo). Ángulos positivos = antihorario en pantalla.")
ROT_LABELS = {ROT_MEASURED: "medida", ROT_INTERPOLATED: "interpolada", ROT_UNAVAILABLE: "no disponible"}
MIRROR_NONE, MIRROR_ROT180, MIRROR_H, MIRROR_V = ori.NONE, ori.ROT180, ori.MIRROR_H, ori.MIRROR_V
MIRROR_LABELS = ori.LABELS          # orientation of the scene (field name kept for saved sessions)


@dataclass(frozen=True)
class KinematicsParams:
    window: int = 7            # Savitzky-Golay window [frames], odd
    polyorder: int = 2
    robot_diameter_mm: float = 33.0  # real robot diameter; 0 -> no SI conversion from the robot
    mirror: str = MIRROR_ROT180      # orientation of the scene (core.orientation); fixed camera of this
                                     # project: the observer stands at the top edge of the video
    scale_source: str = SCALE_ARENA  # recinto | perspectiva | robot (falls back to robot without enclosure)


@dataclass
class Kinematics:
    frames: np.ndarray       # (F,)
    fps: float
    vx: np.ndarray           # (F, N) px/s, image axes
    vy: np.ndarray
    theta: np.ndarray        # (F, N) deg CCW, 0 at first frame of this range
    omega: np.ndarray        # (F, N) deg/s CCW
    rot_status: np.ndarray   # (F, N) int8
    mm_per_px: float = 0.0   # representative scale (median of s(f)) [mm/px]
    mirror: str = MIRROR_NONE
    # --- enclosure frame (None without scale): real scene, origin at the centre, y up
    xa: Optional[np.ndarray] = None      # (F, N) mm
    ya: Optional[np.ndarray] = None
    vxa: Optional[np.ndarray] = None     # (F, N) mm/s, relative to the enclosure
    vya: Optional[np.ndarray] = None
    xpc: Optional[np.ndarray] = None     # (F, N) px, centred, y up, un-mirrored (no scale)
    ypc: Optional[np.ndarray] = None
    s_t: Optional[np.ndarray] = None     # (F,) mm/px of each frame
    centre: Optional[np.ndarray] = None  # (F, 2) enclosure centre in video px
    r_in_t: Optional[np.ndarray] = None  # (F,) enclosure inner radius in video px
    origin: str = "centro del recorte"   # or "recinto"
    scale_source: str = SCALE_ROBOT      # source actually used
    kappa: float = 1.0                   # perspective factor applied (1 = none)
    kappa_measured: float = float("nan") # perspective factor measured (always reported)
    r_contact_rel: float = float("nan")  # q99.5 of r / r_in (robot centres touching the wall)
    r_in_mm: float = float("nan")        # enclosure inner radius [mm]
    robot_diameter_mm: float = 0.0

    @property
    def speed(self) -> np.ndarray:
        return np.hypot(self.vx, self.vy)

    @property
    def direction(self) -> np.ndarray:
        return np.degrees(np.arctan2(-self.vy, self.vx))

    def slice(self, a: int, b: int) -> "Kinematics":
        """Rows [a, b]; theta re-referenced to each robot's orientation at row a."""
        th = self.theta[a:b + 1].copy()
        th -= th[:1]
        sl = slice(a, b + 1)
        cut = {k: (getattr(self, k)[sl] if getattr(self, k) is not None else None)
               for k in ("xa", "ya", "vxa", "vya", "xpc", "ypc", "s_t", "centre", "r_in_t")}
        return replace(self, frames=self.frames[sl], vx=self.vx[sl], vy=self.vy[sl],
                       theta=th, omega=self.omega[sl], rot_status=self.rot_status[sl], **cut)

    @property
    def has_frame(self) -> bool:
        """True when the enclosure-frame arrays (mm, centred) are available."""
        return self.xa is not None


def _odd_window(window: int, n: int, polyorder: int) -> Optional[int]:
    w = min(int(window), n if n % 2 else n - 1)
    w = w if w % 2 else w - 1
    return w if w > polyorder else None


def _derivative(v: np.ndarray, fps: float, p: KinematicsParams) -> np.ndarray:
    """d/dt along axis 0 for each column; NaNs are bridged by interpolation, then restored."""
    out = np.full_like(v, np.nan, dtype=float)
    n = len(v)
    for k in range(v.shape[1]):
        col = v[:, k]
        ok = np.isfinite(col)
        if ok.sum() < 2:
            continue
        idx = np.arange(n)
        filled = np.interp(idx, idx[ok], col[ok])
        w = _odd_window(p.window, n, p.polyorder)
        if w is None:
            d = np.gradient(filled) * fps
        else:
            d = savgol_filter(filled, w, p.polyorder, deriv=1, delta=1.0 / fps, mode="interp")
        d[~ok] = np.nan
        out[:, k] = d
    return out


def _rotation(result: TrackingResult, cand_sig: Optional[list]) -> tuple[np.ndarray, np.ndarray]:
    # Theta does not depend on fps or the SG window: cache it on the result so changing the time
    # scale or the window does not re-run the (global, slower) angle solver.
    cache = getattr(result, "_rotation_cache", None)
    if cache is not None and cache[0] is cand_sig:
        return cache[1].copy(), cache[2].copy()
    theta, st = _rotation_uncached(result, cand_sig)
    try:
        result._rotation_cache = (cand_sig, theta, st)
    except AttributeError:
        pass
    return theta.copy(), st.copy()


def _rotation_uncached(result: TrackingResult, cand_sig: Optional[list],
                       long_range: bool = True) -> tuple[np.ndarray, np.ndarray]:
    F, N = result.x.shape
    theta = np.full((F, N), np.nan)
    st = np.full((F, N), ROT_UNAVAILABLE, np.int8)
    if cand_sig is None or result.cand_idx is None:
        return theta, st
    obs_codes = [int(Status.DETECTED), int(Status.RELAXED)]  # manual points have no image signature
    rows_all = np.arange(F)
    for k in range(N):
        ci = result.cand_idx[:, k]
        rows = np.flatnonzero((ci >= 0) & np.isin(result.status[:, k], obs_codes))
        rows = np.array([r for r in rows if len(cand_sig[r]) > ci[r]], dtype=np.int64)
        if len(rows) == 0:
            continue
        sig = np.stack([cand_sig[r][ci[r]] for r in rows])
        ang, _ = rot.solve_angles(sig, long_range=long_range)
        theta[:, k] = np.interp(rows_all, rows, ang)   # holds the end values outside the range
        st[:, k] = ROT_INTERPOLATED
        st[rows, k] = ROT_MEASURED
    return theta, st


def compute(result: TrackingResult, cand_sig: Optional[list], fps: float,
            p: KinematicsParams, r_out_px: float, arena=None,
            crop: Optional[tuple[float, float, float, float]] = None) -> Kinematics:
    """`arena` = core.arena.ArenaTrack (or None); `crop` = (x, y, w, h) of the analysed ROI, used as
    fallback origin (its centre) when the enclosure is not defined."""
    pos_ok = result.status != Status.MISSING
    x = np.where(pos_ok, result.x, np.nan)
    y = np.where(pos_ok, result.y, np.nan)
    vx = _derivative(x, fps, p)
    vy = _derivative(y, fps, p)
    theta, rst = _rotation(result, cand_sig)
    theta = theta - theta[:1]
    omega = _derivative(theta, fps, p)
    mm_robot = p.robot_diameter_mm / (2 * r_out_px) if p.robot_diameter_mm > 0 and r_out_px > 0 else 0.0
    mirror = p.mirror if p.mirror in MIRROR_LABELS else MIRROR_NONE
    kin = Kinematics(result.frames.copy(), fps, vx, vy, theta, omega, rst, mm_robot, mirror,
                     robot_diameter_mm=p.robot_diameter_mm)
    _enclosure_frame(kin, x, y, result.status, fps, p, arena, crop, mm_robot)
    return kin


def _enclosure_frame(kin: Kinematics, x: np.ndarray, y: np.ndarray, status: np.ndarray, fps: float,
                     p: KinematicsParams, arena, crop, mm_robot: float) -> None:
    """Fill the centred / scaled arrays of `kin` (see the module docstring)."""
    F = len(kin.frames)
    sx, sy, _ = ori.signs(kin.mirror)
    defined = arena is not None and getattr(arena, "defined", False)
    if defined:
        cx, cy, r_in = arena.at(kin.frames)
        r_in_mm = arena.d_in_mm / 2.0
        kin.origin = "recinto"
        kin.r_in_mm = r_in_mm
    elif crop is not None:
        cx = np.full(F, crop[0] + crop[2] / 2.0)
        cy = np.full(F, crop[1] + crop[3] / 2.0)
        r_in = np.full(F, np.nan)
    else:
        return
    xpc = sx * (x - cx[:, None])
    ypc = -sy * (y - cy[:, None])
    kin.xpc, kin.ypc = xpc, ypc
    kin.centre = np.column_stack([cx, cy])
    kin.r_in_t = r_in
    if defined:
        rel = np.hypot(xpc, ypc) / r_in[:, None]
        obs = np.isin(status, [int(s) for s in OBSERVED]) & np.isfinite(rel)
        kin.r_contact_rel = float(np.nanpercentile(rel[obs], CONTACT_QUANTILE)) if obs.any() else float("nan")
        if p.robot_diameter_mm > 0 and np.isfinite(kin.r_contact_rel) and kin.r_contact_rel > 0:
            kin.kappa_measured = (r_in_mm - p.robot_diameter_mm / 2) / (kin.r_contact_rel * r_in_mm)
    src = p.scale_source if p.scale_source in SCALE_LABELS else SCALE_ARENA
    if defined and src in (SCALE_ARENA, SCALE_PERSPECTIVE):
        s_t = r_in_mm / r_in
        if src == SCALE_PERSPECTIVE and np.isfinite(kin.kappa_measured):
            kin.kappa = float(kin.kappa_measured)
            s_t = s_t * kin.kappa
        else:
            src = SCALE_ARENA
    elif mm_robot > 0:
        s_t, src = np.full(F, mm_robot), SCALE_ROBOT
    else:
        kin.scale_source = "sin escala"
        return
    kin.scale_source = src
    kin.s_t = s_t
    kin.mm_per_px = float(np.median(s_t))
    kin.xa = xpc * s_t[:, None]
    kin.ya = ypc * s_t[:, None]
    kin.vxa = _derivative(kin.xa, fps, p)
    kin.vya = _derivative(kin.ya, fps, p)



# --------------------------------------------------------------------------- tables
# Column order of the long CSV ("una fila por robot y cuadro"). Documented in the application report.
LONG_COLUMNS = [
    "frame", "t_s", "particle", "status",
    "x_mm", "y_mm", "r_mm", "phi_deg", "wall_dist_mm",
    "vx_mm_s", "vy_mm_s", "speed_mm_s", "vel_dir_deg", "v_rad_mm_s", "v_tan_mm_s",
    "theta_deg", "omega_deg_s", "omega_rad_s", "rot_status",
    "x_px", "y_px", "r_px", "vx_px_s", "vy_px_s", "speed_px_s",
    "mm_per_px", "xc_video_px", "yc_video_px", "x_video_px", "y_video_px",
    "mass", "ring_cov", "status_code",
]


def _sign(kin: Kinematics) -> tuple[float, float, float]:
    """(sx, sy, s_rot) multiplying vx, vy and theta/omega to go from image to the displayed scene."""
    return ori.signs(kin.mirror)


def table(result: TrackingResult, kin: Kinematics, origin: tuple[float, float] = (0.0, 0.0),
          size: Optional[tuple[float, float]] = None) -> pd.DataFrame:
    """Long format: one row per (frame, robot). result and kin must cover the same rows.

    Positions and velocities are in the enclosure frame (origin at the centre, x right, y up, real
    scene); see the module docstring. `origin` / `size` are only used when kin has no centred arrays
    (old callers): then x_px, y_px are relative to `origin` with y up.
    """
    F, N = result.x.shape
    sx, sy, sr = _sign(kin)
    df = pd.DataFrame({"frame": np.repeat(result.frames, N), "particle": np.tile(np.arange(N), F)})
    df.insert(1, "t_s", df["frame"] / kin.fps)
    df["status_code"] = result.status.ravel().astype(int)
    df["status"] = df["status_code"].map({int(k): v for k, v in STATUS_LABELS.items()})
    if kin.xpc is not None:
        xpc, ypc = kin.xpc, kin.ypc
    else:  # no centring information: crop corner + mirror (legacy)
        xpc = sx * (result.x - origin[0] - (size[0] if (sx < 0 and size) else 0.0))
        ypc = -sy * (result.y - origin[1] - (size[1] if (sy < 0 and size) else 0.0))
    df["x_px"], df["y_px"] = xpc.ravel(), ypc.ravel()
    df["r_px"] = np.hypot(xpc, ypc).ravel()
    vxp, vyp = sx * kin.vx, -sy * kin.vy                  # image derivatives -> y up, real scene
    df["vx_px_s"], df["vy_px_s"] = vxp.ravel(), vyp.ravel()
    df["speed_px_s"] = np.hypot(vxp, vyp).ravel()
    if kin.has_frame:
        xa, ya, vxa, vya = kin.xa, kin.ya, kin.vxa, kin.vya
        r = np.hypot(xa, ya)
        df["x_mm"], df["y_mm"], df["r_mm"] = xa.ravel(), ya.ravel(), r.ravel()
        df["phi_deg"] = np.degrees(np.arctan2(ya, xa)).ravel()
        if np.isfinite(kin.r_in_mm):
            df["wall_dist_mm"] = (kin.r_in_mm - r).ravel()    # centre-to-wall; contact ~ D/2
        df["vx_mm_s"], df["vy_mm_s"] = vxa.ravel(), vya.ravel()
        df["speed_mm_s"] = np.hypot(vxa, vya).ravel()
        df["vel_dir_deg"] = np.degrees(np.arctan2(vya, vxa)).ravel()
        with np.errstate(invalid="ignore", divide="ignore"):
            df["v_rad_mm_s"] = ((xa * vxa + ya * vya) / r).ravel()
            df["v_tan_mm_s"] = ((xa * vya - ya * vxa) / r).ravel()   # > 0: counter-clockwise about the centre
        df["mm_per_px"] = np.repeat(kin.s_t, N)
    else:
        df["vel_dir_deg"] = np.degrees(np.arctan2(vyp, vxp)).ravel()
    df["theta_deg"] = (kin.theta * sr).ravel()
    df["omega_deg_s"] = (kin.omega * sr).ravel()
    df["omega_rad_s"] = np.radians(kin.omega * sr).ravel()
    df["rot_status"] = pd.Series(kin.rot_status.ravel()).map(ROT_LABELS).to_numpy()
    if kin.centre is not None:
        df["xc_video_px"] = np.repeat(kin.centre[:, 0], N)
        df["yc_video_px"] = np.repeat(kin.centre[:, 1], N)
    df["x_video_px"], df["y_video_px"] = result.x.ravel(), result.y.ravel()
    df["mass"], df["ring_cov"] = result.mass.ravel(), result.cov.ravel()
    df = df[[c for c in LONG_COLUMNS if c in df.columns]]
    df["orientacion"] = kin.mirror    # x/y/v/theta are already in the displayed scene
    return df


def robot_table(long_df: pd.DataFrame, k: int) -> pd.DataFrame:
    """All rows of one robot (one per frame), same columns as the long table."""
    out = long_df[long_df["particle"] == int(k)].reset_index(drop=True)
    if out.empty:
        raise ValueError(f"No hay datos del robot {k}.")
    return out


def wall_layer_threshold(kin: Kinematics) -> float:
    """r [mm] above which a robot is in the wall layer: less than half a diameter from the contact radius."""
    if not (kin.has_frame and np.isfinite(kin.r_contact_rel) and np.isfinite(kin.r_in_mm)):
        return float("nan")
    r_contact = kin.r_contact_rel * kin.r_in_mm * kin.kappa
    return r_contact - 0.5 * kin.robot_diameter_mm if kin.robot_diameter_mm > 0 else float("nan")


def summary(result: TrackingResult, kin: Kinematics) -> pd.DataFrame:
    """One row per robot (mm when the scale is known, px otherwise)."""
    rows = []
    obs_codes = [int(s) for s in OBSERVED]
    dt = 1.0 / kin.fps
    sr = _sign(kin)[2]
    mm = kin.has_frame
    X = kin.xa if mm else kin.xpc if kin.xpc is not None else result.x
    Y = kin.ya if mm else kin.ypc if kin.ypc is not None else result.y
    VX = kin.vxa if mm else kin.vx
    VY = kin.vya if mm else kin.vy
    u = "mm" if mm else "px"
    r_wall = wall_layer_threshold(kin)
    for k in range(result.n_objects):
        x, y = X[:, k], Y[:, k]
        ok = np.isfinite(x) & np.isfinite(y)
        path = float(np.nansum(np.hypot(np.diff(x), np.diff(y))))
        disp = float(np.hypot(x[ok][-1] - x[ok][0], y[ok][-1] - y[ok][0])) if ok.sum() >= 2 else np.nan
        sp = np.hypot(VX[:, k], VY[:, k])
        om = kin.omega[:, k] * sr
        th = kin.theta[:, k] * sr
        r = np.hypot(x, y)
        row = {
            "particle": k,
            "frames": len(x),
            "duration_s": len(x) * dt,
            "pct_position_observed": 100.0 * np.isin(result.status[:, k], obs_codes).mean(),
            "pct_rotation_measured": 100.0 * (kin.rot_status[:, k] == ROT_MEASURED).mean(),
            f"mean_speed_{u}_s": float(np.nanmean(sp)) if np.isfinite(sp).any() else np.nan,
            f"median_speed_{u}_s": float(np.nanmedian(sp)) if np.isfinite(sp).any() else np.nan,
            f"max_speed_{u}_s": float(np.nanmax(sp)) if np.isfinite(sp).any() else np.nan,
            f"path_length_{u}": path,
            f"net_displacement_{u}": disp,
            f"mean_r_{u}": float(np.nanmean(r)) if ok.any() else np.nan,
            "total_rotation_deg": float(th[np.isfinite(th)][-1]) if np.isfinite(th).any() else np.nan,
            "turns": float(th[np.isfinite(th)][-1] / 360.0) if np.isfinite(th).any() else np.nan,
            "mean_omega_deg_s": float(np.nanmean(om)) if np.isfinite(om).any() else np.nan,
            "mean_abs_omega_deg_s": float(np.nanmean(np.abs(om))) if np.isfinite(om).any() else np.nan,
            "pct_omega_cw": 100.0 * float(np.nanmean(om[np.isfinite(om)] < 0)) if np.isfinite(om).any() else np.nan,
        }
        if mm:
            with np.errstate(invalid="ignore", divide="ignore"):
                vt = (x * VY[:, k] - y * VX[:, k]) / r
            row["mean_v_tan_mm_s"] = float(np.nanmean(vt))
            if np.isfinite(r_wall):
                row["pct_wall_layer"] = 100.0 * float(np.nanmean(r[ok] >= r_wall))
        rows.append(row)
    return pd.DataFrame(rows)


def wide_table(long_df: pd.DataFrame) -> pd.DataFrame:
    """One row per frame; every per-robot column becomes r{k}_{column} (grouped by robot)."""
    if long_df.empty:
        return long_df.copy()
    n = int(long_df["particle"].max()) + 1
    width = max(2, len(str(n - 1)))
    per_frame = [c for c in ("mm_per_px", "xc_video_px", "yc_video_px") if c in long_df.columns]
    value_cols = [c for c in long_df.columns if c not in ("frame", "t_s", "particle", "espejo", "orientacion", *per_frame)]
    wide = long_df.pivot(index="frame", columns="particle", values=value_cols)
    wide = wide.reindex(columns=pd.MultiIndex.from_product([value_cols, range(n)]))
    ordered = [(c, k) for k in range(n) for c in value_cols]
    wide = wide[ordered]
    wide.columns = [f"r{k:0{width}d}_{c}" for c, k in ordered]
    first = long_df.groupby("frame")[["t_s", *per_frame]].first()
    for i, c in enumerate(["t_s", *per_frame]):
        wide.insert(i, c, first[c])
    for c in ("orientacion", "espejo"):
        if c in long_df.columns:
            wide[c] = long_df[c].iloc[0]
    return wide.reset_index()
