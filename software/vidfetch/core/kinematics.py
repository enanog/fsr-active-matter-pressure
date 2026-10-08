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

Mirrored recordings (KinematicsParams.mirror): everything is computed in image coordinates (the
overlay is drawn on the image), and only the exported tables are converted to the real scene:
  horizontal (image flipped about its vertical axis): x -> W - x, vx -> -vx;
  vertical   (image flipped about its horizontal axis): y -> H - y, vy -> -vy;
  both cases reverse handedness: theta, omega -> -theta, -omega; the direction is recomputed.
x_video_px / y_video_px always stay in image (file) pixels.
"""
from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Optional

import numpy as np
import pandas as pd
from scipy.signal import savgol_filter

from core import rotation as rot
from core.tracking import OBSERVED, Status, TrackingResult

ROT_MEASURED = 0
ROT_INTERPOLATED = 1
ROT_UNAVAILABLE = 2
ARROW_NOTE = ("Flecha amarilla: velocidad (largo = desplazamiento en 7,5 cuadros). Aguja blanca: "
              "orientación actual; la marca a las 12 h es la referencia θ = 0 (el robot como estaba en "
              "el primer cuadro del tramo). Ángulos positivos = antihorario en pantalla.")
ROT_LABELS = {ROT_MEASURED: "medida", ROT_INTERPOLATED: "interpolada", ROT_UNAVAILABLE: "no disponible"}
MIRROR_NONE, MIRROR_H, MIRROR_V = "no", "horizontal", "vertical"
MIRROR_LABELS = {MIRROR_NONE: "No", MIRROR_H: "Horizontal (respecto del eje y)",
                 MIRROR_V: "Vertical (respecto del eje x)"}


@dataclass(frozen=True)
class KinematicsParams:
    window: int = 7            # Savitzky-Golay window [frames], odd
    polyorder: int = 2
    robot_diameter_mm: float = 35.0  # real robot diameter; 0 -> no SI conversion
    mirror: str = MIRROR_NONE        # the recording is a mirror image of the real scene


@dataclass
class Kinematics:
    frames: np.ndarray       # (F,)
    fps: float
    vx: np.ndarray           # (F, N) px/s, image axes
    vy: np.ndarray
    theta: np.ndarray        # (F, N) deg CCW, 0 at first frame of this range
    omega: np.ndarray        # (F, N) deg/s CCW
    rot_status: np.ndarray   # (F, N) int8
    mm_per_px: float = 0.0
    mirror: str = MIRROR_NONE

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
        return replace(self, frames=self.frames[a:b + 1], vx=self.vx[a:b + 1], vy=self.vy[a:b + 1],
                       theta=th, omega=self.omega[a:b + 1], rot_status=self.rot_status[a:b + 1])


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
        ang, _ = rot.solve_angles(sig)
        theta[:, k] = np.interp(rows_all, rows, ang)   # holds the end values outside the range
        st[:, k] = ROT_INTERPOLATED
        st[rows, k] = ROT_MEASURED
    return theta, st


def compute(result: TrackingResult, cand_sig: Optional[list], fps: float,
            p: KinematicsParams, r_out_px: float) -> Kinematics:
    pos_ok = result.status != Status.MISSING
    x = np.where(pos_ok, result.x, np.nan)
    y = np.where(pos_ok, result.y, np.nan)
    vx = _derivative(x, fps, p)
    vy = _derivative(y, fps, p)
    theta, rst = _rotation(result, cand_sig)
    theta = theta - theta[:1]
    omega = _derivative(theta, fps, p)
    mm_per_px = p.robot_diameter_mm / (2 * r_out_px) if p.robot_diameter_mm > 0 and r_out_px > 0 else 0.0
    mirror = p.mirror if p.mirror in MIRROR_LABELS else MIRROR_NONE
    return Kinematics(result.frames.copy(), fps, vx, vy, theta, omega, rst, mm_per_px, mirror)


# --------------------------------------------------------------------------- tables
def _sign(kin: Kinematics) -> tuple[float, float, float]:
    """(sx, sy, s_rot) multiplying vx, vy and theta/omega to go from image to real scene."""
    if kin.mirror == MIRROR_H:
        return -1.0, 1.0, -1.0
    if kin.mirror == MIRROR_V:
        return 1.0, -1.0, -1.0
    return 1.0, 1.0, 1.0


def table(result: TrackingResult, kin: Kinematics, origin: tuple[float, float],
          size: Optional[tuple[float, float]] = None) -> pd.DataFrame:
    """Long format: one row per (frame, robot). result and kin must cover the same rows.

    `size` = (width, height) of the analysed region in px, needed to un-mirror positions.
    """
    df = result.to_dataframe(kin.fps, origin)
    sx, sy, sr = _sign(kin)
    if sx < 0 or sy < 0:
        if size is None:
            raise ValueError("Para corregir el espejado hace falta el tamaño de la región analizada.")
        if sx < 0:
            df["x_px"] = size[0] - df["x_px"]
        if sy < 0:
            df["y_px"] = size[1] - df["y_px"]
    vx, vy = kin.vx * sx, kin.vy * sy
    df["vx_px_s"] = vx.ravel()
    df["vy_px_s"] = vy.ravel()
    df["speed_px_s"] = kin.speed.ravel()
    df["vel_dir_deg"] = np.degrees(np.arctan2(-vy, vx)).ravel()
    df["theta_deg"] = (kin.theta * sr).ravel()
    df["omega_deg_s"] = (kin.omega * sr).ravel()
    df["omega_rad_s"] = np.radians(kin.omega * sr).ravel()
    df["rot_status"] = pd.Series(kin.rot_status.ravel()).map(ROT_LABELS).to_numpy()
    if kin.mm_per_px > 0:
        s = kin.mm_per_px / 1000.0   # m/px
        df["x_m"] = df["x_px"] * s
        df["y_m"] = df["y_px"] * s
        df["vx_m_s"] = df["vx_px_s"] * s
        df["vy_m_s"] = df["vy_px_s"] * s
        df["speed_m_s"] = df["speed_px_s"] * s
    order = ["frame", "t_s", "particle", "x_px", "y_px", "status", "vx_px_s", "vy_px_s", "speed_px_s",
             "vel_dir_deg", "theta_deg", "omega_deg_s", "omega_rad_s", "rot_status",
             "x_m", "y_m", "vx_m_s", "vy_m_s", "speed_m_s",
             "mass", "ring_cov", "status_code", "x_video_px", "y_video_px"]
    df = df[[c for c in order if c in df.columns]]
    if kin.mirror != MIRROR_NONE:
        df["espejo"] = kin.mirror     # tells readers that x/y/v/theta are already un-mirrored
    return df


def summary(result: TrackingResult, kin: Kinematics) -> pd.DataFrame:
    """One row per robot."""
    rows = []
    obs_codes = [int(s) for s in OBSERVED]
    dt = 1.0 / kin.fps
    sr = _sign(kin)[2]
    for k in range(result.n_objects):
        x, y = result.x[:, k], result.y[:, k]
        ok = np.isfinite(x) & np.isfinite(y)
        steps = np.hypot(np.diff(x), np.diff(y))
        path = float(np.nansum(steps))
        disp = float(np.hypot(x[ok][-1] - x[ok][0], y[ok][-1] - y[ok][0])) if ok.sum() >= 2 else np.nan
        sp = kin.speed[:, k]
        om = kin.omega[:, k] * sr
        th = kin.theta[:, k] * sr
        row = {
            "particle": k,
            "frames": len(x),
            "duration_s": len(x) * dt,
            "pct_position_observed": 100.0 * np.isin(result.status[:, k], obs_codes).mean(),
            "pct_rotation_measured": 100.0 * (kin.rot_status[:, k] == ROT_MEASURED).mean(),
            "mean_speed_px_s": float(np.nanmean(sp)) if np.isfinite(sp).any() else np.nan,
            "max_speed_px_s": float(np.nanmax(sp)) if np.isfinite(sp).any() else np.nan,
            "path_length_px": path,
            "net_displacement_px": disp,
            "total_rotation_deg": float(th[np.isfinite(th)][-1]) if np.isfinite(th).any() else np.nan,
            "mean_omega_deg_s": float(np.nanmean(om)) if np.isfinite(om).any() else np.nan,
            "mean_abs_omega_deg_s": float(np.nanmean(np.abs(om))) if np.isfinite(om).any() else np.nan,
        }
        if kin.mm_per_px > 0:
            s = kin.mm_per_px / 1000.0
            row.update({"mean_speed_m_s": row["mean_speed_px_s"] * s, "max_speed_m_s": row["max_speed_px_s"] * s,
                        "path_length_m": path * s, "net_displacement_m": disp * s})
        rows.append(row)
    return pd.DataFrame(rows)


def wide_table(long_df: pd.DataFrame) -> pd.DataFrame:
    """One row per frame; every per-robot column becomes r{k}_{column} (grouped by robot)."""
    if long_df.empty:
        return long_df.copy()
    n = int(long_df["particle"].max()) + 1
    width = max(2, len(str(n - 1)))
    value_cols = [c for c in long_df.columns if c not in ("frame", "t_s", "particle", "espejo")]
    wide = long_df.pivot(index="frame", columns="particle", values=value_cols)
    wide = wide.reindex(columns=pd.MultiIndex.from_product([value_cols, range(n)]))
    ordered = [(c, k) for k in range(n) for c in value_cols]
    wide = wide[ordered]
    wide.columns = [f"r{k:0{width}d}_{c}" for c, k in ordered]
    t = long_df.groupby("frame")["t_s"].first()
    wide.insert(0, "t_s", t)
    if "espejo" in long_df.columns:
        wide["espejo"] = long_df["espejo"].iloc[0]
    return wide.reset_index()
