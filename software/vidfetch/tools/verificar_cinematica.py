"""Visual and numeric check of positions, axes, displacements and velocities exported by VidFetch.

Works only from the exported CSV (+ its _info.json) and the analysed video, i.e. it checks the data
as the reports use them. Needs only OpenCV, NumPy and pandas (no SciPy / matplotlib).

Usage (from the repository root):
  python software/vidfetch/tools/verificar_cinematica.py datos/video/trayectorias/VP_<code>_robots.csv ^
      --video datos/video/recortados/VC_<code>.MP4 [--cuadro 6000] [--robots 3,7,12] [--delta 5]
Output (datos/video/verificacion/, or next to --salida):
  cinematica_<code>.png           panels A + B side by side
  cinematica_<code>_ejes.png      panel A at double resolution, with the mm grid
  cinematica_<code>_centros.png   panel C (robot centres, 1 mm grid)
  cinematica_<code>.txt           numeric checks

Panel A (axes and origin): the frame is flipped back to the REAL scene (if the video is mirrored) and
every robot is redrawn from x_mm, y_mm only: u = xc' + x/s, v = yc - y/s. The enclosure, its centre and
the +x (right) / +y (up) axes are drawn too. If origin, mirror, axis signs or scale were wrong, the
circles would not sit on the robots.
Panel B (displacement and velocity): for a few moving robots, the CSV velocity is integrated over
[t, t + delta] (trapezoid): the yellow arrow on frame t ends where the robot should be at t + delta.
On frame t + delta the yellow circle is that prediction and the green one the exported position: the
real robot must be inside both.
Grid: lines of constant x and y of the enclosure frame (real scene, mm): every 10 mm, labelled every
50 mm on the full frame; every 1 mm, labelled every 5 mm on the close-ups. Positions can be read on it.
Panel C (centres): close-ups of several robots (--centros, or spread over the layers) with the exported
centre (red cross, coordinates printed) and an INDEPENDENT centre: a circle fitted to the robot body
directly on the image (Hough transform, cyan). Both must coincide; the .txt gives the statistics of
their distance over many robots and frames.
Numeric checks (printed and saved in the .txt):
  1. x_mm, y_mm rebuilt from x_video_px, xc_video_px, mm_per_px and the mirror (transform consistency);
  2. integral of v over 10 s vs the exported displacement (all robots, every 30 s);
  3. exported v vs a raw central difference of x_video_px (independent of the Savitzky-Golay filter);
  4. contact radius q99.5(r) vs R_int - D/2 (scale/perspective) and sign of the mean omega.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import cv2
import numpy as np
import pandas as pd

COLS = ["frame", "t_s", "particle", "status", "x_mm", "y_mm", "r_mm", "vx_mm_s", "vy_mm_s", "speed_mm_s",
        "omega_deg_s", "mm_per_px", "xc_video_px", "yc_video_px", "x_video_px", "y_video_px", "espejo"]
YELLOW, GREEN, CYAN, WHITE, RED, BLACK = (0, 230, 255), (0, 200, 0), (255, 200, 0), (255, 255, 255), (0, 0, 255), (0, 0, 0)


def text(img, s, org, scale=0.5, col=WHITE, th=1):
    cv2.putText(img, s, org, cv2.FONT_HERSHEY_SIMPLEX, scale, BLACK, th + 2, cv2.LINE_AA)
    cv2.putText(img, s, org, cv2.FONT_HERSHEY_SIMPLEX, scale, col, th, cv2.LINE_AA)


def arrow(img, p0, p1, col, th=2):
    p0, p1 = tuple(int(round(v)) for v in p0), tuple(int(round(v)) for v in p1)
    cv2.arrowedLine(img, p0, p1, BLACK, th + 2, cv2.LINE_AA, tipLength=0.2)
    cv2.arrowedLine(img, p0, p1, col, th, cv2.LINE_AA, tipLength=0.2)


def draw_grid(img: np.ndarray, sc: "Scene", frame: int, x0: float, y0: float, zoom: float,
              minor: float, major: float, label: bool = True, alpha: float = 0.5,
              clip_r_mm: float | None = None, axis_step: float = 0.0, label_y: int = 14) -> np.ndarray:
    """mm grid of the enclosure frame on `img` = de-mirrored frame cropped at (x0, y0) and scaled by `zoom`.

    Labels go on the image border every `major` mm, or along the axes x = 0, y = 0 every `axis_step` mm.
    """
    h, w = img.shape[:2]
    cx, cy = sc.centre(frame)
    s = float(sc.s[frame])
    xmin, xmax = (x0 - cx) * s, (x0 + w / zoom - cx) * s
    ymax, ymin = (cy - y0) * s, (cy - (y0 + h / zoom)) * s
    over = img.copy()
    labels = []
    fs = 0.38 if zoom < 2 else 0.45

    def px(xm, ym):
        return (cx + xm / s - x0) * zoom, (cy - ym / s - y0) * zoom

    lim = clip_r_mm if clip_r_mm is not None else np.inf
    for k in range(int(np.floor(xmin / minor)), int(np.ceil(xmax / minor)) + 1):
        xm = k * minor
        if abs(xm) > lim:
            continue
        ext = np.sqrt(max(lim ** 2 - xm ** 2, 0.0)) if np.isfinite(lim) else None
        ya, yb = (ext, -ext) if ext is not None else (ymax, ymin)
        (u, va), (_, vb) = px(xm, ya), px(xm, yb)
        is_major = abs(xm / major - round(xm / major)) < 1e-6
        col = (255, 255, 255) if is_major else (210, 210, 210)
        if abs(xm) < 1e-9:
            col = (0, 0, 255)
        cv2.line(over, (int(round(u)), int(round(va))), (int(round(u)), int(round(vb))), col,
                 2 if is_major else 1, cv2.LINE_AA)
        if label and is_major:
            labels.append((f"{xm:+.0f}", (int(round(u)) + 3, label_y if ext is None else int(round(px(0, min(ext, ymax))[1])) + 14)))
    for k in range(int(np.floor(ymin / minor)), int(np.ceil(ymax / minor)) + 1):
        ym = k * minor
        if abs(ym) > lim:
            continue
        ext = np.sqrt(max(lim ** 2 - ym ** 2, 0.0)) if np.isfinite(lim) else None
        xa, xb = (-ext, ext) if ext is not None else (xmin, xmax)
        (ua, v), (ub, _) = px(xa, ym), px(xb, ym)
        is_major = abs(ym / major - round(ym / major)) < 1e-6
        col = (255, 255, 255) if is_major else (210, 210, 210)
        if abs(ym) < 1e-9:
            col = (0, 0, 255)
        cv2.line(over, (int(round(ua)), int(round(v))), (int(round(ub)), int(round(v))), col,
                 2 if is_major else 1, cv2.LINE_AA)
        if label and is_major:
            labels.append((f"{ym:+.0f}", (4 if ext is None else max(4, int(round(px(max(-ext, xmin), 0)[0])) + 4),
                                          int(round(v)) - 4)))
    out = cv2.addWeighted(over, alpha, img, 1 - alpha, 0)
    if axis_step > 0:
        labels = []
        top = min(xmax, lim) if np.isfinite(lim) else xmax
        for k in range(int(np.ceil(-top / axis_step)), int(np.floor(top / axis_step)) + 1):
            if k == 0:
                continue
            u, v = px(k * axis_step, 0.0)
            labels.append((f"{k * axis_step:+.0f}", (int(u) - 14, int(v) + 18)))
            u, v = px(0.0, k * axis_step)
            labels.append((f"{k * axis_step:+.0f}", (int(u) + 6, int(v) + 5)))
    for t, org in labels:
        text(out, t, org, fs, (255, 255, 255), 1 if axis_step <= 0 else 2)
    return out


class Scene:
    """Maps the CSV (real scene, mm, origin at the enclosure centre, y up) onto the de-mirrored frame."""

    def __init__(self, df: pd.DataFrame, width: int, height: int):
        self.mirror = str(df["espejo"].iloc[0]) if "espejo" in df.columns else "no"
        self.W, self.H = width, height
        f0 = df.groupby("frame")[["xc_video_px", "yc_video_px", "mm_per_px"]].first()
        self.cx, self.cy, self.s = f0["xc_video_px"], f0["yc_video_px"], f0["mm_per_px"]

    def real_image(self, img: np.ndarray) -> np.ndarray:
        if self.mirror == "horizontal":
            return cv2.flip(img, 1)
        if self.mirror == "vertical":
            return cv2.flip(img, 0)
        return img.copy()

    def centre(self, frame: int) -> tuple[float, float]:
        cx, cy = float(self.cx[frame]), float(self.cy[frame])
        if self.mirror == "horizontal":
            cx = self.W - 1 - cx
        elif self.mirror == "vertical":
            cy = self.H - 1 - cy
        return cx, cy

    def to_px(self, frame: int, x_mm, y_mm):
        """Real-scene mm -> pixel of the de-mirrored frame (x right, y down on screen)."""
        cx, cy = self.centre(frame)
        s = float(self.s[frame])
        return cx + np.asarray(x_mm) / s, cy - np.asarray(y_mm) / s


def read_frame(cap, idx: int) -> np.ndarray:
    cap.set(cv2.CAP_PROP_POS_FRAMES, int(idx))
    ok, img = cap.read()
    if not ok:
        raise IOError(f"No se pudo leer el cuadro {idx} del video.")
    return img


def panel_axes(cap, sc: Scene, df: pd.DataFrame, frame: int, r_in_mm: float, d_mm: float,
               zoom: float = 2.0) -> np.ndarray:
    """De-mirrored frame (x zoom) with the 10 mm grid, enclosure, axes and robots redrawn from x_mm, y_mm."""
    img = sc.real_image(read_frame(cap, frame))
    img = cv2.resize(img, None, fx=zoom, fy=zoom, interpolation=cv2.INTER_CUBIC)
    img = draw_grid(img, sc, frame, 0.0, 0.0, zoom, 10.0, 50.0, True, 0.6, clip_r_mm=r_in_mm, axis_step=20.0)
    rows = df[df["frame"] == frame]
    s = float(sc.s[frame]) / zoom              # mm per pixel of the zoomed image
    cx, cy = (v * zoom for v in sc.centre(frame))
    c = (int(round(cx)), int(round(cy)))
    cv2.circle(img, c, int(round(r_in_mm / s)), BLACK, 4, cv2.LINE_AA)
    cv2.circle(img, c, int(round(r_in_mm / s)), YELLOW, 2, cv2.LINE_AA)
    L = 0.3 * r_in_mm / s
    arrow(img, c, (cx + L, cy), WHITE, 2)
    arrow(img, c, (cx, cy - L), WHITE, 2)
    text(img, "+x", (int(cx + L) + 4, int(cy) - 6), 0.6)
    text(img, "+y", (int(cx) + 6, int(cy - L) - 4), 0.6)
    cv2.drawMarker(img, c, RED, cv2.MARKER_CROSS, 18, 2, cv2.LINE_AA)
    u, v = sc.to_px(frame, rows["x_mm"].to_numpy(), rows["y_mm"].to_numpy())
    u, v = u * zoom, v * zoom
    rr = int(round(0.5 * d_mm / s))
    for (_, row), ui, vi in zip(rows.iterrows(), u, v):
        col = GREEN if row["status"] == "detectado" else (0, 165, 255)
        cv2.circle(img, (int(round(ui)), int(round(vi))), rr, col, 2, cv2.LINE_AA)
        cv2.drawMarker(img, (int(round(ui)), int(round(vi))), RED, cv2.MARKER_CROSS, 12, 2, cv2.LINE_AA)
        text(img, str(int(row["particle"])), (int(ui) + 6, int(vi) + 20), 0.6)
    # Spell out three robots: their coordinates must match where they are with respect to the axes.
    pick = rows.assign(a=np.abs(rows["x_mm"]) + np.abs(rows["y_mm"])).nlargest(3, "a")
    W = img.shape[1]
    head = np.zeros((70, W, 3), np.uint8)
    text(head, f"A. Ejes y origen - cuadro {frame} (t = {rows['t_s'].iloc[0] / 60:.1f} min)", (10, 28), 0.8, WHITE, 2)
    text(head, "escena real" + (" (video des-espejado)" if sc.mirror != "no" else "") +
         "; cuadricula cada 10 mm (gruesa cada 50 mm), valores sobre los ejes en mm; rojo: x = 0, y = 0; "
         "cruz roja = (x_mm, y_mm) exportado", (10, 56), 0.5)
    foot = np.zeros((40, W, 3), np.uint8)
    text(foot, "   ".join(f"#{int(r_['particle'])}: x = {r_['x_mm']:+.1f}, y = {r_['y_mm']:+.1f} mm"
                          for _, r_ in pick.iterrows()), (10, 27), 0.65, YELLOW, 2)
    return np.vstack([head, img, foot])


def pick_moves(df: pd.DataFrame, robots: list[int], frame0: int, delta_f: int, n: int) -> list[tuple[int, int]]:
    """(robot, start frame) pairs with clear motion within +-10 min of frame0, both ends detected."""
    X = df.pivot(index="frame", columns="particle", values="x_mm")
    Y = df.pivot(index="frame", columns="particle", values="y_mm").to_numpy()
    D = (df.pivot(index="frame", columns="particle", values="status") == "detectado").to_numpy()
    frames, ids, X = X.index.to_numpy(), list(X.columns), X.to_numpy()
    lo = int(np.searchsorted(frames, frame0))
    i = np.arange(max(0, lo - 1800), min(len(frames) - delta_f, lo + 1800), 15)
    j = i + delta_f
    d = np.hypot(X[j] - X[i], Y[j] - Y[i])
    d[~(D[i] & D[j])] = -1
    out = []
    for c, k in enumerate(ids):
        if robots and k not in robots:
            continue
        b = int(np.argmax(d[:, c]))
        if d[b, c] > 0:
            out.append((float(d[b, c]), int(k), int(frames[i[b]])))
    out.sort(reverse=True)
    return [(k, f) for _, k, f in out[:n]]


def panel_moves(cap, sc: Scene, df: pd.DataFrame, moves, delta_f: int, d_mm: float, fps: float) -> tuple[np.ndarray, list[str]]:
    tiles, lines = [], []
    half = 120
    for k, f0 in moves:
        r = df[df["particle"] == k].set_index("frame").sort_index()
        seg = r.loc[f0:f0 + delta_f]
        dt = 1.0 / fps
        trap = lambda v: float(np.sum(0.5 * (v[1:] + v[:-1])) * dt)  # noqa: E731 (np.trapz/trapezoid differ by NumPy version)
        pred = np.array([trap(seg["vx_mm_s"].to_numpy()), trap(seg["vy_mm_s"].to_numpy())])
        meas = np.array([seg["x_mm"].iloc[-1] - seg["x_mm"].iloc[0], seg["y_mm"].iloc[-1] - seg["y_mm"].iloc[0]])
        f1 = int(seg.index[-1])
        p0 = sc.to_px(f0, seg["x_mm"].iloc[0], seg["y_mm"].iloc[0])
        pp = sc.to_px(f1, seg["x_mm"].iloc[0] + pred[0], seg["y_mm"].iloc[0] + pred[1])
        p1 = sc.to_px(f1, seg["x_mm"].iloc[-1], seg["y_mm"].iloc[-1])
        rr = int(round(0.5 * d_mm / float(sc.s[f0])))
        pair = []
        for f, mode in ((f0, 0), (f1, 1)):
            img = sc.real_image(read_frame(cap, f))
            ccx, ccy = int(round((p0[0] + p1[0]) / 2)), int(round((p0[1] + p1[1]) / 2))
            x0, y0 = max(0, ccx - half), max(0, ccy - half)
            crop = img[y0:y0 + 2 * half, x0:x0 + 2 * half].copy()
            crop = cv2.copyMakeBorder(crop, 0, 2 * half - crop.shape[0], 0, 2 * half - crop.shape[1],
                                      cv2.BORDER_CONSTANT, value=BLACK)
            crop = draw_grid(crop, sc, f, x0, y0, 1.0, 5.0, 20.0, True, 0.3, label_y=46)
            q = lambda p: (p[0] - x0, p[1] - y0)  # noqa: E731
            if mode == 0:
                cv2.circle(crop, tuple(int(round(v)) for v in q(p0)), rr, CYAN, 2, cv2.LINE_AA)
                arrow(crop, q(p0), q(pp), YELLOW, 2)
                text(crop, f"#{k} t={f0 / fps / 60:.2f} min", (6, 18), 0.5)
            else:
                cv2.circle(crop, tuple(int(round(v)) for v in q(pp)), rr, YELLOW, 2, cv2.LINE_AA)
                cv2.circle(crop, tuple(int(round(v)) for v in q(p1)), rr - 4, GREEN, 2, cv2.LINE_AA)
                text(crop, f"t+{delta_f / fps:.0f} s", (6, 18), 0.5)
            pair.append(crop)
        tile = np.hstack(pair)
        err = float(np.hypot(*(pred - meas)))
        bar = np.zeros((24, tile.shape[1], 3), np.uint8)
        text(bar, f"int v dt = ({pred[0]:+.1f}, {pred[1]:+.1f}) mm | dpos = ({meas[0]:+.1f}, {meas[1]:+.1f}) mm",
             (6, 17), 0.45, YELLOW)
        tile = np.vstack([tile, bar])
        tiles.append(tile)
        lines.append(f"robot {k}, cuadros {f0}-{f1}: integral de v = ({pred[0]:+.2f}, {pred[1]:+.2f}) mm, "
                     f"desplazamiento = ({meas[0]:+.2f}, {meas[1]:+.2f}) mm, diferencia {err:.2f} mm")
    cols = 2
    while len(tiles) % cols:
        tiles.append(np.zeros_like(tiles[0]))
    rows = [np.hstack(tiles[i:i + cols]) for i in range(0, len(tiles), cols)]
    grid = np.vstack(rows)
    head = np.zeros((34, grid.shape[1], 3), np.uint8)
    text(head, f"B. Desplazamiento: flecha amarilla = integral de v del CSV en {delta_f / fps:.0f} s; "
               "en t+dt: amarillo = prediccion, verde = posicion exportada; cuadricula 5 mm (gruesa y rotulada cada 20 mm)", (6, 22), 0.5)
    return np.vstack([head, grid]), lines


def _fit_circle(x: np.ndarray, y: np.ndarray) -> tuple[float, float, float]:
    A = np.c_[2 * x, 2 * y, np.ones_like(x)]
    (a, b, k), *_ = np.linalg.lstsq(A, x ** 2 + y ** 2, rcond=None)
    return float(a), float(b), float(np.sqrt(k + a * a + b * b))


def body_circle(gray: np.ndarray, r_px: float, n_rays: int = 180, thr: float = 8.0):
    """Independent centre: outer edge of the dark robot body, fitted as a circle (crop pixels).

    Rays from the crop centre; on each one, the strongest dark->bright step between 0.75 R and 1.3 R
    (subpixel), then a circle fit with MAD rejection (rays blocked by touching neighbours, LEDs or
    connectors are discarded). Radius is free: the fitted diameter is also an independent scale check.
    Returns (cx, cy, r, edge_x, edge_y) or None.
    """
    g = cv2.GaussianBlur(gray.astype(np.float32), (0, 0), 1.2)
    h, w = g.shape
    th = np.linspace(0, 2 * np.pi, n_rays, endpoint=False)
    dr = 0.25
    rr = np.arange(0.75 * r_px, 1.3 * r_px, dr)
    X = (w / 2 + np.cos(th)[:, None] * rr).astype(np.float32)
    Y = (h / 2 + np.sin(th)[:, None] * rr).astype(np.float32)
    der = np.gradient(cv2.remap(g, X, Y, cv2.INTER_LINEAR), axis=1) / dr
    j = np.argmax(der, axis=1)
    keep = (der[np.arange(n_rays), j] > thr) & (j > 0) & (j < len(rr) - 1)
    jj = j[keep]
    d0, d1, d2 = der[keep, jj - 1], der[keep, jj], der[keep, jj + 1]
    den = d0 - 2 * d1 + d2
    off = np.clip(0.5 * (d0 - d2) / np.where(np.abs(den) > 1e-9, den, -1e-9), -1, 1)
    r = rr[jj] + off * dr
    x, y = w / 2 + np.cos(th[keep]) * r, h / 2 + np.sin(th[keep]) * r
    if len(x) < 20:
        return None
    for _ in range(4):
        a, b, R = _fit_circle(x, y)
        res = np.hypot(x - a, y - b) - R
        dev = np.abs(res - np.median(res))
        k = dev < 2.5 * (1.4826 * np.median(dev) + 1e-6)
        if k.sum() < 20:
            return None
        x, y = x[k], y[k]
    a, b, R = _fit_circle(x, y)
    return (a, b, R, x, y) if 0.85 * r_px < R < 1.15 * r_px else None


def pick_centres(rows: pd.DataFrame, robots: list[int], n: int = 6) -> list[int]:
    """Robots spread over the layers (by r) and around the enclosure (by phi)."""
    rows = rows[rows["status"] == "detectado"]
    if robots:
        return [k for k in robots if k in set(rows["particle"])]
    r = np.hypot(rows["x_mm"], rows["y_mm"]).to_numpy()
    order = np.argsort(r)
    idx = np.unique(np.linspace(0, len(order) - 1, n).round().astype(int))
    return [int(rows["particle"].iloc[order[i]]) for i in idx]


def panel_centres(cap, sc: Scene, df: pd.DataFrame, frame: int, robots: list[int], d_mm: float,
                  half_mm: float = 26.0, zoom: float = 5.0) -> tuple[np.ndarray, list[str]]:
    img = sc.real_image(read_frame(cap, frame))
    rows = df[df["frame"] == frame]
    s = float(sc.s[frame])
    half = int(round(half_mm / s))
    tiles, lines = [], []
    for k in pick_centres(rows, robots):
        row = rows[rows["particle"] == k].iloc[0]
        u, v = sc.to_px(frame, row["x_mm"], row["y_mm"])
        x0, y0 = int(round(u)) - half, int(round(v)) - half
        pad = cv2.copyMakeBorder(img, half, half, half, half, cv2.BORDER_CONSTANT, value=BLACK)
        crop = pad[y0 + half:y0 + 3 * half, x0 + half:x0 + 3 * half].copy()
        ind = body_circle(cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY), 0.5 * d_mm / s)
        big = cv2.resize(crop, None, fx=zoom, fy=zoom, interpolation=cv2.INTER_CUBIC)
        big = draw_grid(big, sc, frame, x0, y0, zoom, 1.0, 5.0, True, 0.35)
        cu, cv_ = (u - x0) * zoom, (v - y0) * zoom
        H, W = big.shape[:2]
        cv2.line(big, (int(cu), 0), (int(cu), H), RED, 1, cv2.LINE_AA)
        cv2.line(big, (0, int(cv_)), (W, int(cv_)), RED, 1, cv2.LINE_AA)
        cv2.circle(big, (int(round(cu)), int(round(cv_))), int(round(0.5 * d_mm / s * zoom)), GREEN, 2, cv2.LINE_AA)
        cv2.circle(big, (int(round(cu)), int(round(cv_))), 6, RED, -1, cv2.LINE_AA)
        txt = f"#{k}  x = {row['x_mm']:+.2f} mm   y = {row['y_mm']:+.2f} mm"
        if ind is not None:
            iu, iv, ir, ex, ey = ind
            for px_, py_ in zip(ex, ey):
                cv2.circle(big, (int(round(px_ * zoom)), int(round(py_ * zoom))), 3, CYAN, -1, cv2.LINE_AA)
            for a0 in range(0, 360, 20):
                cv2.ellipse(big, (int(round(iu * zoom)), int(round(iv * zoom))),
                            (int(round(ir * zoom)), int(round(ir * zoom))), 0, a0, a0 + 10, CYAN, 2, cv2.LINE_AA)
            cv2.drawMarker(big, (int(round(iu * zoom)), int(round(iv * zoom))), CYAN, cv2.MARKER_TILTED_CROSS, 18, 2, cv2.LINE_AA)
            dx, dy = (iu - (u - x0)) * s, -(iv - (v - y0)) * s
            txt2 = (f"borde ajustado: dx = {dx:+.2f}, dy = {dy:+.2f} mm (|d| = {np.hypot(dx, dy):.2f} mm), "
                    f"D = {2 * ir * s:.1f} mm")
            lines.append(f"robot {k}: exportado ({row['x_mm']:+.2f}, {row['y_mm']:+.2f}) mm; centro del borde a "
                         f"{np.hypot(dx, dy):.2f} mm, D = {2 * ir * s:.1f} mm")
        else:
            txt2 = "borde: no se pudo ajustar un circulo (vecinos tapando el borde)"
            lines.append(f"robot {k}: exportado ({row['x_mm']:+.2f}, {row['y_mm']:+.2f}) mm; borde sin ajuste")
        bar = np.zeros((58, W, 3), np.uint8)
        text(bar, txt, (8, 22), 0.62, YELLOW, 2)
        text(bar, txt2, (8, 48), 0.5, CYAN)
        tiles.append(np.vstack([bar, big]))
    cols = 3
    while len(tiles) % cols:
        tiles.append(np.zeros_like(tiles[0]))
    sep = lambda t: np.hstack([t, np.zeros((t.shape[0], 6, 3), np.uint8)])  # noqa: E731
    grid = np.vstack([np.hstack([sep(t) for t in tiles[i:i + cols]]) for i in range(0, len(tiles), cols)])
    head = np.zeros((70, grid.shape[1], 3), np.uint8)
    text(head, f"C. Centros - cuadro {frame} (t = {rows['t_s'].iloc[0] / 60:.2f} min), escena real", (10, 28), 0.8, WHITE, 2)
    text(head, "rojo = centro exportado (x_mm, y_mm); verde = robot de 33 mm centrado ahi; celeste = borde del cuerpo "
               "medido en la imagen (puntos) y circulo ajustado (x); cuadricula 1 mm, rotulada cada 5 mm", (10, 56), 0.55)
    return np.vstack([head, grid]), lines


def centre_statistics(cap, sc: Scene, df: pd.DataFrame, d_mm: float, n_frames: int = 20) -> str:
    """Exported centre vs independent body-edge centre, over every detected robot of n_frames frames."""
    frames = np.sort(df["frame"].unique())
    pick = frames[np.linspace(0, len(frames) - 1, n_frames + 2).round().astype(int)[1:-1]]
    dist, diam, rad, rr, tried = [], [], [], [], 0
    for f in pick:
        img = sc.real_image(read_frame(cap, int(f)))
        s = float(sc.s[f])
        half = int(round(26.0 / s))
        pad = cv2.copyMakeBorder(img, half, half, half, half, cv2.BORDER_CONSTANT, value=BLACK)
        rows = df[(df["frame"] == f) & (df["status"] == "detectado")]
        u, v = sc.to_px(int(f), rows["x_mm"].to_numpy(), rows["y_mm"].to_numpy())
        for ui, vi, xm, ym in zip(u, v, rows["x_mm"].to_numpy(), rows["y_mm"].to_numpy()):
            x0, y0 = int(round(ui)) - half, int(round(vi)) - half
            crop = pad[y0 + half:y0 + 3 * half, x0 + half:x0 + 3 * half]
            tried += 1
            ind = body_circle(cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY), 0.5 * d_mm / s)
            if ind is not None:
                ex, ey = (ind[0] - (ui - x0)) * s, -(ind[1] - (vi - y0)) * s    # edge - exported, mm, y up
                r = float(np.hypot(xm, ym))
                dist.append(np.hypot(ex, ey))
                diam.append(2 * ind[2] * s)
                if r > 5:
                    rad.append((ex * xm + ey * ym) / r)
                    rr.append(r)
    if not dist:
        return "5. Centro independiente (borde del cuerpo): no se pudo ajustar ningún círculo."
    d, D = np.array(dist), np.array(diam)
    rad, rr = np.array(rad), np.array(rr)
    slope = float(np.sum(rad * rr) / np.sum(rr * rr)) if len(rr) else float("nan")
    return (f"5. Centro exportado vs centro independiente (borde del cuerpo ajustado en la imagen), {len(d)} robots "
            f"en {len(pick)} cuadros ({100 * len(d) / tried:.0f} % ajustados): distancia mediana {np.median(d):.2f} mm, "
            f"p90 {np.percentile(d, 90):.2f} mm -> {'OK' if np.median(d) < 1.0 else 'REVISAR'}\n"
            f"   diámetro del cuerpo medido = {np.median(D):.2f} mm (mediana; RIQ {np.percentile(D, 25):.2f}-"
            f"{np.percentile(D, 75):.2f}) vs {d_mm:g} mm nominal: escala {100 * (np.median(D) / d_mm - 1):+.1f} %\n"
            f"   componente radial (borde - exportado) = {slope:+.4f} * r (ajuste por el origen; {100 * slope:+.1f} % de r): "
            + ("sin sesgo radial apreciable" if abs(slope) < 0.01 else
               "sesgo radial: el centro exportado y el del borde se separan con r (perspectiva entre alturas)"))


def numeric_checks(df: pd.DataFrame, fps: float, r_in_mm: float, d_mm: float) -> list[str]:
    out = []
    mir = str(df["espejo"].iloc[0]) if "espejo" in df.columns else "no"
    sx = -1.0 if mir == "horizontal" else 1.0
    sy = -1.0 if mir == "vertical" else 1.0
    x = df["mm_per_px"] * sx * (df["x_video_px"] - df["xc_video_px"])
    y = -df["mm_per_px"] * sy * (df["y_video_px"] - df["yc_video_px"])
    e = max(float(np.nanmax(np.abs(x - df["x_mm"]))), float(np.nanmax(np.abs(y - df["y_mm"]))))
    out.append(f"1. Transformación: x_mm, y_mm reconstruidos desde los píxeles del video difieren como máximo "
               f"{e:.4f} mm (redondeo del CSV) -> {'OK' if e < 0.01 else 'REVISAR'}")
    # 2. integral of v vs displacement, 10 s windows every 30 s
    L, step = int(round(10 * fps)), int(round(30 * fps))
    errs, mags = [], []
    for _, r in df.groupby("particle"):
        r = r.sort_values("frame")
        vx, vy, X, Y = (r[c].to_numpy() for c in ("vx_mm_s", "vy_mm_s", "x_mm", "y_mm"))
        cvx = np.concatenate([[0], np.cumsum(0.5 * (vx[1:] + vx[:-1]) / fps)])
        cvy = np.concatenate([[0], np.cumsum(0.5 * (vy[1:] + vy[:-1]) / fps)])
        for i in range(0, len(r) - L, step):
            dp = np.array([X[i + L] - X[i], Y[i + L] - Y[i]])
            iv = np.array([cvx[i + L] - cvx[i], cvy[i + L] - cvy[i]])
            if np.all(np.isfinite(dp)) and np.all(np.isfinite(iv)):
                errs.append(np.hypot(*(iv - dp)))
                mags.append(np.hypot(*dp))
    errs, mags = np.array(errs), np.array(mags)
    big = mags > 2.0
    out.append(f"2. Integral de v en 10 s vs desplazamiento ({len(errs)} ventanas): error mediano "
               f"{np.median(errs):.3f} mm, p95 {np.percentile(errs, 95):.3f} mm; en ventanas con desplazamiento > 2 mm, "
               f"error relativo mediano {100 * np.median(errs[big] / mags[big]):.2f} % -> "
               f"{'OK' if np.median(errs) < 0.2 else 'REVISAR'}")
    # 3. exported v vs raw central difference of the video pixels (k = 3 frames each side)
    k = 3
    a, b = [], []
    for _, r in df.groupby("particle"):
        r = r.sort_values("frame").reset_index(drop=True)
        s = r["mm_per_px"].to_numpy()
        xr = sx * (r["x_video_px"] - r["xc_video_px"]).to_numpy() * s
        yr = -sy * (r["y_video_px"] - r["yc_video_px"]).to_numpy() * s
        vxr = (xr[2 * k:] - xr[:-2 * k]) * fps / (2 * k)
        vyr = (yr[2 * k:] - yr[:-2 * k]) * fps / (2 * k)
        ok = (r["status"].to_numpy()[k:-k] == "detectado")
        a.append(np.concatenate([vxr[ok], vyr[ok]]))
        b.append(np.concatenate([r["vx_mm_s"].to_numpy()[k:-k][ok], r["vy_mm_s"].to_numpy()[k:-k][ok]]))
    a, b = np.concatenate(a), np.concatenate(b)
    m = np.isfinite(a) & np.isfinite(b)
    slope = float(np.sum(a[m] * b[m]) / np.sum(a[m] ** 2))
    corr = float(np.corrcoef(a[m], b[m])[0, 1])
    out.append(f"3. Velocidad exportada vs diferencia finita cruda de los píxeles (+-{k} cuadros): "
               f"correlación {corr:.3f}, pendiente {slope:.3f} (signo y escala de los ejes) -> "
               f"{'OK' if slope > 0.8 and corr > 0.8 else 'REVISAR'}")
    rc = float(np.nanpercentile(df.loc[df["status"] == "detectado", "r_mm"], 99.5))
    out.append(f"4. Radio de contacto q99.5(r) = {rc:.1f} mm vs R_int - D/2 = {r_in_mm - d_mm / 2:.1f} mm "
               f"(diferencia {100 * (rc / (r_in_mm - d_mm / 2) - 1):+.1f} %: perspectiva, esperado ~ +2,5 %)")
    w = float(df["omega_deg_s"].mean())
    out.append(f"   omega media = {w:+.2f} grados/s ({'horario' if w < 0 else 'antihorario'}; en modo QR se espera horario)")
    return out


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("csv", type=Path, help="CSV largo exportado (VP_<código>_robots.csv)")
    ap.add_argument("--video", type=Path, required=True, help="video analizado (VC_<código>.MP4)")
    ap.add_argument("--cuadro", type=int, help="cuadro del panel A (por defecto, el del medio)")
    ap.add_argument("--robots", default="", help="robots del panel B separados por coma (por defecto, los 4 que más se mueven)")
    ap.add_argument("--delta", type=float, default=5.0, help="intervalo del panel B en segundos reales (def. 5)")
    ap.add_argument("--centros", default="", help="robots del panel C separados por coma (por defecto, 6 repartidos por capa)")
    ap.add_argument("--salida", type=Path, help="PNG de salida (por defecto datos/video/verificacion/cinematica_<código>.png)")
    a = ap.parse_args()

    try:
        df = pd.read_csv(a.csv, usecols=lambda c: c in COLS)
    except Exception as exc:
        sys.exit(f"No se pudo leer {a.csv}: {exc}")
    missing = set(COLS) - set(df.columns) - {"espejo"}
    if missing:
        sys.exit(f"Faltan columnas {sorted(missing)}: el CSV es anterior al recinto; reexportalo con tools/reexportar.py.")
    info_p = a.csv.with_name(a.csv.stem + "_info.json")
    info = json.loads(info_p.read_text(encoding="utf-8")) if info_p.exists() else {}
    rec = info.get("recinto") or {}
    r_in_mm = float(rec.get("d_int_mm", 185.0)) / 2
    d_mm = float(info.get("diametro_robot_mm") or 33.0)
    d1 = df.drop_duplicates("frame")
    fps = float(np.median(d1["frame"][d1["frame"] > 0] / d1["t_s"][d1["frame"] > 0]))

    cap = cv2.VideoCapture(str(a.video))
    if not cap.isOpened():
        sys.exit(f"No se pudo abrir el video {a.video}")
    W, H = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH)), int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    sc = Scene(df, W, H)
    frames = np.sort(df["frame"].unique())
    f_axes = a.cuadro if a.cuadro is not None else int(frames[len(frames) // 2])
    if f_axes not in set(frames.tolist()):
        sys.exit(f"El cuadro {f_axes} no está en el CSV.")
    robots = [int(v) for v in a.robots.split(",") if v.strip()]
    delta_f = int(round(a.delta * fps))

    A = panel_axes(cap, sc, df, f_axes, r_in_mm, d_mm)
    B, move_lines = panel_moves(cap, sc, df, pick_moves(df, robots, f_axes, delta_f, 4), delta_f, d_mm, fps)
    C, centre_lines = panel_centres(cap, sc, df, f_axes, [int(v) for v in a.centros.split(",") if v.strip()], d_mm)
    stat_line = centre_statistics(cap, sc, df, d_mm)
    cap.release()
    # A + B side by side at a common height
    h = max(A.shape[0], B.shape[0])
    A2 = cv2.resize(A, (int(round(A.shape[1] * h / A.shape[0])), h), interpolation=cv2.INTER_AREA)
    B2 = cv2.resize(B, (int(round(B.shape[1] * h / B.shape[0])), h), interpolation=cv2.INTER_CUBIC)
    out_img = np.hstack([A2, np.zeros((h, 8, 3), np.uint8), B2])

    code = a.csv.stem.replace("VP_", "").replace("_robots", "")
    out = a.salida or (a.csv.parents[1] / "verificacion" / f"cinematica_{code}.png")
    out.parent.mkdir(parents=True, exist_ok=True)

    def save(path: Path, im: np.ndarray) -> None:
        ok, buf = cv2.imencode(".png", im)      # imencode + write_bytes: safe with OneDrive / non-ASCII paths
        path.write_bytes(buf.tobytes())

    save(out, out_img)
    save(out.with_name(out.stem + "_ejes.png"), A)
    save(out.with_name(out.stem + "_centros.png"), C)
    lines = [f"Verificación de cinemática: {a.csv.name} (fr = {fps:g} cuadros/s, espejo: {sc.mirror})"]
    lines += numeric_checks(df, fps, r_in_mm, d_mm)
    lines += [stat_line]
    lines += ["Panel B:"] + ["   " + s_ for s_ in move_lines]
    lines += [f"Panel C (cuadro {f_axes}):"] + ["   " + s_ for s_ in centre_lines]
    out.with_suffix(".txt").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("\n".join(lines))
    print(f"Figuras: {out.name}, {out.stem}_ejes.png, {out.stem}_centros.png en {out.parent}")


if __name__ == "__main__":
    main()
