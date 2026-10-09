"""Method figures of the application report (informes/aplicacion/figuras/metodo/f1..f9), drawn in the
scene orientation of the exported data (core/orientation.py; rot180 = the camera image rotated 180 deg,
as the observer standing at the top edge of the video sees it).

The analysis quantities (detection map, ring coverage, rotation signatures, tracks) are computed as in
VidFetch; every image is then shown oriented, and every coordinate / angle is expressed in the export
frame (x to the observer's right, y away from them, counter-clockwise positive).

Usage (from the repository root; needs the VidFetch environment: OpenCV, trackpy, SciPy, matplotlib):
  python software/analisis_video/figuras_metodo.py ^
      --csv datos/video/trayectorias/VP_20262409_1600_22QR_60_robots.csv ^
      --sesion datos/video/sesiones/VA_20262409_1600_22QR_60_analisis.npz ^
      --video datos/video/recortados/VC_20262409_1600_22QR_60.MP4
  (--cuadros FILE.npz with an array 'f' of frames 0..N can replace --video.)
Uses the first 60 s (frames 0-180 at 3 frames/s).
"""
from __future__ import annotations

import argparse
import json
import sys
from dataclasses import replace
from pathlib import Path

import cv2
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "software" / "vidfetch"))
from core import arena as ar  # noqa: E402
from core import calibration as cal  # noqa: E402
from core import detection as det  # noqa: E402
from core import orientation as ori  # noqa: E402
from core import rotation as rot  # noqa: E402
from core.tracking import Status, draw_oriented  # noqa: E402

import matplotlib  # noqa: E402
matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
from scipy.signal import savgol_filter  # noqa: E402

plt.rcParams.update({"font.size": 9, "axes.spines.top": False, "axes.spines.right": False,
                     "axes.edgecolor": "#777", "axes.grid": True, "grid.color": "#e6e6e6",
                     "grid.linewidth": 0.6, "axes.axisbelow": True})
BLUE, ORANGE, GREEN, RED, GRAY, YELLOW = "#2a78d6", "#eb6834", "#1baf7a", "#d63a3a", "#9a9a9a", "#f2c200"
N_FRAMES = 181


def rgb(img: np.ndarray) -> np.ndarray:
    return cv2.cvtColor(img, cv2.COLOR_BGR2RGB) if img.ndim == 3 else img


def off(ax) -> None:
    ax.set_axis_off()


class Data:
    def __init__(self, a):
        self.df = pd.read_csv(a.csv)
        self.key = ori.from_frame(self.df)
        self.sx, self.sy, self.srot = ori.signs(self.key)
        meta = json.loads(str(np.load(a.sesion, allow_pickle=False)["meta"]))
        self.p = det.DetectionParams(**meta["detection"])
        self.fps = float(meta["fps"])
        if a.cuadros:
            self.frames = np.load(a.cuadros)["f"][:N_FRAMES]
        else:
            cap = cv2.VideoCapture(str(a.video))
            fr = []
            for _ in range(N_FRAMES):
                ok, im = cap.read()
                if not ok:
                    break
                fr.append(im)
            cap.release()
            self.frames = np.stack(fr)
        self.H, self.W = self.frames.shape[1:3]
        d = self.df[self.df["frame"] < len(self.frames)]
        self.pv = {c: d.pivot(index="frame", columns="particle", values=c) for c in
                   ("x_video_px", "y_video_px", "x_mm", "y_mm", "vx_px_s", "vy_px_s", "theta_deg",
                    "status_code", "rot_status")}
        self.t = self.pv["x_mm"].index.to_numpy() / self.fps

    def img(self, f: int) -> np.ndarray:
        return ori.image(self.frames[f], self.key)

    def gray(self, f: int) -> np.ndarray:
        return cv2.cvtColor(self.img(f), cv2.COLOR_BGR2GRAY)

    def pt(self, x, y):
        """Raw video px -> oriented image px."""
        return ori.points(x, y, self.W, self.H, self.key)

    def pos(self, f: int, k: int) -> tuple[float, float]:
        return tuple(float(v) for v in self.pt(self.pv["x_video_px"].loc[f, k], self.pv["y_video_px"].loc[f, k]))


def crop(img: np.ndarray, cx: float, cy: float, half: int) -> np.ndarray:
    pad = cv2.copyMakeBorder(img, half, half, half, half, cv2.BORDER_REPLICATE)
    x0, y0 = int(round(cx)), int(round(cy))
    return pad[y0:y0 + 2 * half + 1, x0:x0 + 2 * half + 1].copy()


# --------------------------------------------------------------------------- f1 calibration
def f1(D: Data, out: Path) -> None:
    g = D.gray(0)
    otsu, _ = cv2.threshold(g, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    gate = max(float(otsu) * 1.1, 1.0)
    gf = g.astype(np.float32)
    rs = np.arange(25.0, 75.01, 0.5)
    sc = np.array([cal._score(gf, r, gate, 22) for r in rs])
    rb = float(rs[int(np.argmax(sc))])
    k = int(D.df[(D.df.frame == 0) & (D.df.status == "detectado")].assign(
        d=lambda q: np.hypot(q.x_mm, q.y_mm)).sort_values("d")["particle"].iloc[1])
    cx, cy = D.pos(0, k)
    half = int(1.55 * rb)
    c = crop(D.img(0), cx, cy, half)
    fig, (a0, a1) = plt.subplots(1, 2, figsize=(7.6, 3.4), gridspec_kw={"width_ratios": [1, 1.7]},
                                 constrained_layout=True)
    a0.imshow(rgb(c))
    for r, col in ((cal.RING_RATIO * rb, YELLOW), (rb, BLUE)):
        a0.add_patch(plt.Circle((half, half), r, fill=False, lw=2.5, color=col))
    off(a0)
    a0.set_title(f"Plantilla: disco r_int = {cal.RING_RATIO * rb:.1f} px (amarillo)\n"
                 f"anillo hasta r_ext = {rb:.1f} px (azul)", fontsize=9)
    a1.plot(rs, sc, color=BLUE, lw=1.5)
    a1.axvline(rb, color=RED, ls="--", lw=1)
    a1.text(rb + 1, sc.max() * 0.95, f"máximo: r_ext = {rb:.1f} px", color=RED)
    a1.set_xlabel("radio exterior de prueba r_ext [px]")
    a1.set_ylabel("respuesta media de los 22 picos [niveles de gris]")
    a1.set_title("Barrido de radios: la plantilla encaja con el robot real", fontsize=9)
    fig.savefig(out / "f1_calibracion.png", dpi=200)
    plt.close(fig)
    print(f"f1: r_ext = {rb:.1f} px (sesión {D.p.r_out}), robot {k}")


# --------------------------------------------------------------------------- f2 detection, f3 coverage
def candidates(D: Data, f: int) -> pd.DataFrame:
    p = D.p
    raw = D.frames[f]
    g = cv2.cvtColor(raw, cv2.COLOR_BGR2GRAY)
    c = det.locate(raw, replace(p, validate_ring=False))
    m = max(0.5, 0.17 * (p.r_out - p.r_in))
    r0, r1 = p.r_in + m, max(p.r_in + m + 1.0, p.r_out - m)
    c["cov"] = [det.ring_coverage(g, x, y, r0, r1, p.ring_pixel_dark) for x, y in zip(c.x, c.y)]
    c["ok"] = c["cov"] >= p.min_coverage
    c["xo"], c["yo"] = D.pt(c.x.to_numpy(), c.y.to_numpy())
    return c, (r0, r1)


def f2(D: Data, out: Path, f: int = 0):
    p = D.p
    raw = D.frames[f]
    g = cv2.cvtColor(raw, cv2.COLOR_BGR2GRAY)
    small = cv2.resize(g, None, fx=p.scale, fy=p.scale, interpolation=cv2.INTER_AREA)
    R = det.robot_response(small, p)
    R = ori.image(cv2.resize(R, (D.W, D.H), interpolation=cv2.INTER_CUBIC), D.key)
    c, band = candidates(D, f)
    fig, ax = plt.subplots(1, 3, figsize=(10.5, 3.6), constrained_layout=True)
    ax[0].imshow(D.gray(f), cmap="gray")
    ax[0].set_title("(a) Entrada en escala de grises")
    ax[1].imshow(R, cmap="magma")
    ax[1].set_title("(b) Mapa del filtro de anillo R(x, y)")
    ax[2].imshow(rgb(D.img(f)))
    for _, r in c.iterrows():
        col = "#22c55e" if r.ok else "#ef4444"
        ax[2].add_patch(plt.Circle((r.xo, r.yo), p.r_out, fill=False, lw=1.6, color=col))
        ax[2].text(r.xo, r.yo, f"{r['cov']:.2f}", color="#ffe14d" if r.ok else "#ff6b6b", fontsize=6.5,
                   ha="center", va="center", fontweight="bold")
    ax[2].set_title(f"(c) validación (cuadro {f}): {int(c.ok.sum())} aceptados (verde),\n"
                    f"{int((~c.ok).sum())} candidatos rechazados (rojo)")
    for a in ax:
        off(a)
    fig.savefig(out / "f2_deteccion.png", dpi=200)
    plt.close(fig)
    print(f"f2: cuadro {f}: {len(c)} candidatos, {int(c.ok.sum())} aceptados (cobertura {c[c.ok]['cov'].min():.2f}-"
          f"{c[c.ok]['cov'].max():.2f}), {int((~c.ok).sum())} rechazados ({c[~c.ok]['cov'].min():.2f}-{c[~c.ok]['cov'].max():.2f})")
    return c, band


def f3(D: Data, out: Path, c: pd.DataFrame, band, f: int = 0) -> None:
    p = D.p
    g = D.gray(f)
    r0, r1 = band
    good = c[c.ok].iloc[(c[c.ok]["cov"] - 0.97).abs().argsort().iloc[0]]
    bad = c[~c.ok].sort_values("cov").iloc[-1] if (~c.ok).any() else None
    cases = [("robot", good)] + ([("hueco entre robots", bad)] if bad is not None else [])
    fig, ax = plt.subplots(2, len(cases), figsize=(3.7 * len(cases), 4.4),
                           gridspec_kw={"height_ratios": [2.2, 1]}, constrained_layout=True, squeeze=False)
    half = int(1.7 * p.r_out)
    r1i, r0i = int(np.ceil(r1)), int(max(0, np.floor(r0)))
    for j, (name, r) in enumerate(cases):
        a = ax[0, j]
        a.imshow(rgb(crop(D.img(f), r.xo, r.yo, half)))
        for rr in (r0, r1):
            a.add_patch(plt.Circle((half, half), rr, fill=False, lw=1.5, color="#00b4e6"))
        a.set_title(f"{name}: cobertura = {r['cov']:.2f}")
        off(a)
        pol = cv2.warpPolar(g, (r1i + 1, 360), (float(r.xo), float(r.yo)), r1i + 1, cv2.WARP_POLAR_LINEAR)
        dark = pol[:, r0i:r1i].min(axis=1) < p.ring_pixel_dark
        dark_ccw = dark[(-np.arange(360)) % 360]          # warpPolar turns clockwise on screen
        b = ax[1, j]
        b.imshow(np.where(dark_ccw, 0.13, 1.0)[None, :], cmap="gray", vmin=0, vmax=1, aspect="auto",
                 extent=(0, 360, 0, 1))
        b.set_yticks([])
        b.grid(False)
        b.set_xlabel("ángulo [°, antihorario desde +x]")
        b.set_title("rayos con anillo oscuro (negro) / sin anillo (blanco)", fontsize=8)
    fig.savefig(out / "f3_cobertura.png", dpi=200)
    plt.close(fig)


# --------------------------------------------------------------------------- f4 tracking gaps
def f4(D: Data, out: Path) -> None:
    g0, g1, fa = 60, 90, 75                      # gap [g0, g1) = 20-30 s, anchor at 25 s
    X = D.pv["x_mm"]
    st = D.pv["status_code"]
    best, kbest = -1.0, None
    for k in X.columns:
        x = X[k].to_numpy()
        if not np.all(np.isfinite(x[: g1 + 30])) or (st[k].to_numpy()[: g1 + 30] > 1).any():
            continue
        lin = np.interp(np.arange(g0, g1), [g0 - 1, g1], [x[g0 - 1], x[g1]])
        dev = float(np.max(np.abs(x[g0:g1] - lin)))
        if dev > best:
            best, kbest = dev, k
    k = kbest
    x = X[k].to_numpy()
    t = D.t
    fr = np.arange(len(x))
    no_anchor = x.copy()
    no_anchor[g0:g1] = np.interp(fr[g0:g1], [g0 - 1, g1], [x[g0 - 1], x[g1]])
    anchor = x.copy()
    anchor[g0:g1] = np.interp(fr[g0:g1], [g0 - 1, fa, g1], [x[g0 - 1], x[fa], x[g1]])
    # left: frame inside the gap, robot k drawn as interpolated (orange dashed)
    fshow = fa
    xr = D.pv["x_video_px"].loc[fshow].to_numpy().astype(float)
    yr = D.pv["y_video_px"].loc[fshow].to_numpy().astype(float)
    xv, yv = D.pv["x_video_px"][k].to_numpy(), D.pv["y_video_px"][k].to_numpy()
    xr[k] = np.interp(fshow, [g0 - 1, g1], [xv[g0 - 1], xv[g1]])
    yr[k] = np.interp(fshow, [g0 - 1, g1], [yv[g0 - 1], yv[g1]])
    status = np.where(D.pv["status_code"].loc[fshow].to_numpy() <= 1, int(Status.DETECTED), int(Status.INTERPOLATED))
    status[k] = int(Status.INTERPOLATED)
    vx, vy, th = img_kin(D, fshow)
    left = draw_oriented(D.frames[fshow], D.key, np.column_stack([xr, yr]), status, D.p.r_out,
                         velocity=np.column_stack([vx, vy]), theta_deg=th, fps=D.fps)
    fig, (a0, a1) = plt.subplots(1, 2, figsize=(10.4, 4.0), gridspec_kw={"width_ratios": [1, 1.45]},
                                 constrained_layout=True)
    a0.imshow(rgb(left))
    a0.set_title(f"Cuadro {fshow}: robot {k} interpolado (naranja) dentro del hueco simulado", fontsize=9)
    off(a0)
    a1.axvspan(t[g0], t[g1 - 1], color=ORANGE, alpha=0.12, lw=0, label=f"{g1 - g0} cuadros sin detección")
    a1.plot(t, x, color="#bdbdbd", lw=3.2, label="referencia (sin faltantes)")
    a1.plot(t, no_anchor, color=RED, lw=1.2, label="sin corrección (interpolación lineal)")
    a1.plot(t, anchor, color=BLUE, lw=1.2, label=f"con 1 ancla manual en t = {t[fa]:.0f} s")
    a1.plot([t[fa]], [x[fa]], "o", color="#c300c3", ms=7, label="ancla manual")
    a1.set_xlabel("t [s, tiempo real]")
    a1.set_ylabel(f"x del robot {k} [mm] (sistema del recinto)")
    a1.set_title("Hueco largo: interpolado sin ancla vs con ancla", fontsize=9)
    a1.legend(fontsize=7.5, frameon=True, loc="best")
    fig.savefig(out / "f4_seguimiento.png", dpi=200)
    plt.close(fig)
    print(f"f4: robot {k}, desvío máx. sin ancla {best:.1f} mm, con ancla {np.max(np.abs(anchor - x)):.1f} mm")


def img_kin(D: Data, f: int):
    """Velocity (image px/s) and theta (image CCW, relative to frame 0) for draw_oriented."""
    vxs = D.pv["vx_px_s"].loc[f].to_numpy()
    vys = D.pv["vy_px_s"].loc[f].to_numpy()
    th = D.pv["theta_deg"].loc[f].to_numpy() - D.pv["theta_deg"].loc[0].to_numpy()
    # export: vx_s = sx * vx_img, vy_s = -sy * vy_img (y up); theta_s = s_rot * theta_img
    return D.sx * vxs, -D.sy * vys, D.srot * th


# --------------------------------------------------------------------------- f5 velocity
def f5(D: Data, out: Path) -> None:
    X, Y = D.pv["x_mm"], D.pv["y_mm"]
    path = {k: float(np.nansum(np.hypot(np.diff(X[k]), np.diff(Y[k])))) for k in X.columns}
    k = max(path, key=path.get)
    x, y = X[k].to_numpy(), Y[k].to_numpy()
    u, v = D.pt(D.pv["x_video_px"][k].to_numpy(), D.pv["y_video_px"][k].to_numpy())
    pad = 2.2 * D.p.r_out
    x0, x1 = int(max(0, np.nanmin(u) - pad)), int(min(D.W, np.nanmax(u) + pad))
    y0, y1 = int(max(0, np.nanmin(v) - pad)), int(min(D.H, np.nanmax(v) + pad))
    img = D.img(0)[y0:y1, x0:x1]
    fig, (a0, a1) = plt.subplots(1, 2, figsize=(10.4, 4.2), gridspec_kw={"width_ratios": [1, 1.6]},
                                 constrained_layout=True)
    a0.imshow(rgb(img))
    a0.plot(u - x0, v - y0, color="cyan", lw=1.3)
    for f in range(0, len(u), 12):
        dx = D.pv["vx_px_s"][k].iloc[f] * 7.5 / D.fps                 # scene px/s (x right)
        dy = -D.pv["vy_px_s"][k].iloc[f] * 7.5 / D.fps                # scene y up -> image down
        if np.isfinite(dx) and np.isfinite(dy):
            a0.annotate("", (u[f] - x0 + dx, v[f] - y0 + dy), (u[f] - x0, v[f] - y0),
                        arrowprops=dict(arrowstyle="-|>", color="#ffe600", lw=1.4))
    off(a0)
    a0.set_title(f"Robot {k}: trayectoria (cian) y v cada 12 cuadros\n(flecha = desplazamiento en 7,5 cuadros)")
    dt = 1.0 / D.fps
    raw = np.hypot(np.gradient(x, dt), np.gradient(y, dt))
    for w, col, ls, lab in ((7, BLUE, "-", "ventana 7 cuadros (2,3 s)"), (15, RED, "--", "ventana 15 cuadros (5 s)")):
        vx = savgol_filter(x, w, 2, deriv=1, delta=dt)
        vy = savgol_filter(y, w, 2, deriv=1, delta=dt)
        a1.plot(D.t, np.hypot(vx, vy), color=col, ls=ls, lw=1.6 if ls == "-" else 1.3,
                label=f"Savitzky–Golay, {lab}")
    a1.plot(D.t, raw, color=GRAY, lw=0.9, alpha=0.8, label="diferencia finita (sin suavizar)", zorder=1)
    v7 = np.hypot(savgol_filter(x, 7, 2, deriv=1, delta=dt), savgol_filter(y, 7, 2, deriv=1, delta=dt))
    v15 = np.hypot(savgol_filter(x, 15, 2, deriv=1, delta=dt), savgol_filter(y, 15, 2, deriv=1, delta=dt))
    print(f"f5: |v| media {np.mean(v7):.2f} mm/s, dispersión dif. finita - SG7 {np.std(raw - v7):.2f} mm/s, "
          f"pico SG7 {v7.max():.1f} -> SG15 {v15[np.argmax(v7)]:.1f} mm/s en t = {D.t[np.argmax(v7)]:.1f} s")
    a1.set_xlabel("t [s, tiempo real]")
    a1.set_ylabel("|v| [mm/s]")
    a1.set_title("Rapidez: el suavizado elimina el ruido de posición", fontsize=9)
    a1.legend(fontsize=7.5)
    fig.savefig(out / "f5_velocidad.png", dpi=200)
    plt.close(fig)
    print(f"f5: robot {k}, recorrido {path[k]:.0f} mm en 60 s")


# --------------------------------------------------------------------------- f6 rotation, f7 de-rotation
def f6(D: Data, out: Path, fa: int = 30, fb: int = 36) -> list[int]:
    TH = D.pv["theta_deg"]
    RS = D.pv["rot_status"]
    R = int(np.ceil(D.p.r_out))
    ga, gb = D.gray(fa), D.gray(fb)
    best = None                                   # largest clear turn with a reliable match
    for kk_ in TH.columns:
        if not (RS.loc[fa, kk_] == "medida" and RS.loc[fb, kk_] == "medida"):
            continue
        (xa, ya), (xb, yb) = D.pos(fa, kk_), D.pos(fb, kk_)
        sa_ = rot.signatures(ga, np.array([xa]), np.array([ya]), D.p.r_out)[0]
        sb_ = rot.signatures(gb, np.array([xb]), np.array([yb]), D.p.r_out)[0]
        d_, q_ = rot.rel_angle(sa_, sb_)
        score = (float(q_) >= 0.75, abs(float(d_)) if float(q_) >= 0.75 else float(q_))
        if best is None or score > best[0]:
            best = (score, int(kk_), sa_, sb_, d_, q_)
    _, k, sa, sb, dccw, q = best
    (xa, ya), (xb, yb) = D.pos(fa, k), D.pos(fb, k)
    C = (np.asarray(sb, complex) * np.conj(np.asarray(sa, complex))).sum(0)
    kk = np.arange(1, C.size + 1)
    dd = np.radians(np.linspace(-180, 180, 721))
    norm = np.sqrt((np.abs(sa) ** 2).sum() * (np.abs(sb) ** 2).sum())
    corr = np.real((C[None, :] * np.exp(1j * kk[None, :] * (-dd[:, None]))).sum(1)) / norm   # d_ccw = -d_cw
    fig = plt.figure(figsize=(10.4, 6.0), constrained_layout=True)
    gs = fig.add_gridspec(2, 4)
    half = int(1.3 * R)
    for j, (f, g, x, y) in enumerate(((fa, ga, xa, ya), (fb, gb, xb, yb))):
        a = fig.add_subplot(gs[0, j])
        a.imshow(rgb(crop(D.img(f), x, y, half)))
        for (b0, b1), col in zip(rot.BANDS, (YELLOW, BLUE)):
            for rr in (b0 * R, b1 * R):
                a.add_patch(plt.Circle((half, half), rr, fill=False, lw=1.1, color=col))
        a.set_title(f"cuadro {f}\nbandas: pila (amarillo), anillo (azul)", fontsize=8)
        off(a)
        pol = cv2.warpPolar(g, (R, 360), (float(x), float(y)), float(R), cv2.WARP_POLAR_LINEAR)
        pol = pol[(-np.arange(360)) % 360]           # rows = angle, now counter-clockwise
        b = fig.add_subplot(gs[0, 2 + j])
        b.imshow(pol.T, cmap="gray", aspect="auto", extent=(0, 360, R, 0))
        b.grid(False)
        b.set_xlabel("ángulo polar [°, antihorario]")
        b.set_ylabel("radio [px]")
        b.set_title(f"cuadro {f} desenrollado en polares", fontsize=8)
    a = fig.add_subplot(gs[1, :2])
    a.plot(np.degrees(dd), corr, color=BLUE, lw=1.5)
    a.axvline(float(dccw), color=RED, ls="--", lw=1.2)
    a.text(float(dccw) + (5 if dccw < 40 else -5), 0.92 * corr.max(),
           f"máximo: Δθ = {float(dccw):+.1f}°\n(similitud {float(q):.2f})", color=RED,
           ha="left" if dccw < 40 else "right", va="top")
    a.set_xlabel("giro de prueba Δθ [°, antihorario]")
    a.set_ylabel("correlación normalizada")
    a.set_title(f"Correlación de firmas del robot {k} entre cuadros {fa} y {fb}", fontsize=9)
    th = TH.loc[:, :] - TH.loc[0]
    fin = th.iloc[-1]
    pick = [int(fin.idxmax()), int((fin - fin.median()).abs().idxmin()), int(fin.abs().idxmin())]
    pick = list(dict.fromkeys(pick))
    b = fig.add_subplot(gs[1, 2:])
    for kk_, col in zip(pick, (RED, BLUE, GREEN)):
        b.plot(D.t, th[kk_], color=col, lw=1.5, label=f"robot {kk_}: θ final {fin[kk_]:+.0f}°")
    b.set_xlabel("t [s, tiempo real]")
    b.set_ylabel("θ acumulado [°, antihorario]")
    b.set_title("Orientación acumulada (multivuelta), θ = 0 en el primer cuadro", fontsize=9)
    b.legend(fontsize=7.5)
    fig.savefig(out / "f6_rotacion.png", dpi=200)
    plt.close(fig)
    print(f"f6: robot {k}, Δθ = {float(dccw):+.1f}° (q {float(q):.2f}); θ CSV {float(TH.loc[fb, k] - TH.loc[fa, k]):+.1f}°")
    return pick


def f7(D: Data, out: Path, robots: list[int]) -> None:
    TH = D.pv["theta_deg"]
    frames = list(range(0, 161, 20))
    half = int(1.35 * D.p.r_out)
    fig, ax = plt.subplots(2 * len(robots), len(frames), figsize=(1.25 * len(frames) + 1.4, 1.3 * 2 * len(robots)),
                           squeeze=False)
    for ri, k in enumerate(robots):
        for ci, f in enumerate(frames):
            x, y = D.pos(f, k)
            c = crop(D.img(f), x, y, half)
            t = float(TH.loc[f, k] - TH.loc[0, k])           # scene CCW = displayed CCW
            M = cv2.getRotationMatrix2D((half, half), -t, 1.0)
            dr = cv2.warpAffine(c, M, c.shape[1::-1], flags=cv2.INTER_LINEAR, borderMode=cv2.BORDER_REPLICATE)
            for j, im in enumerate((c, dr)):
                a = ax[2 * ri + j, ci]
                a.imshow(rgb(im))
                a.axvline(half, color="#22e05a", lw=1)
                a.set_xticks([]); a.set_yticks([]); a.grid(False)
                for s in a.spines.values():
                    s.set_visible(False)
                if ri == 0 and j == 0:
                    a.set_title(f"cuadro {f}", fontsize=8)
                if ci == 0:
                    a.set_ylabel(f"robot {k}\ntal cual" if j == 0 else f"robot {k}\ndesrotado por −θ",
                                 fontsize=8, rotation=0, ha="right", va="center")
    fig.subplots_adjust(left=0.1, right=0.995, top=0.95, bottom=0.01, wspace=0.02, hspace=0.04)
    fig.savefig(out / "f7_desrotacion.png", dpi=200)
    plt.close(fig)


# --------------------------------------------------------------------------- f8 overlay, f9 enclosure
def f8(D: Data, out: Path, f: int = 90) -> None:
    xr = D.pv["x_video_px"].loc[f].to_numpy().astype(float)
    yr = D.pv["y_video_px"].loc[f].to_numpy().astype(float)
    st = D.pv["status_code"].loc[f].to_numpy().astype(int)
    vx, vy, th = img_kin(D, f)
    im = draw_oriented(D.frames[f], D.key, np.column_stack([xr, yr]), st, D.p.r_out,
                       velocity=np.column_stack([vx, vy]), theta_deg=th, fps=D.fps)
    cv2.imwrite(str(out / "f8_superposicion.png"), im)


def f9(D: Data, out: Path, f: int = 90) -> None:
    COL = {"in": BLUE, "out": ORANGE}
    img = D.img(f)                                   # enclosure detection is rotation-equivariant
    mask, sat, hue = ar.ring_mask(img)
    res = ar.detect_one(img)
    cx, cy, ri, ro = res[:4]
    ang, r_in, r_out = ar._cast(mask, sat, cx, cy, ri)
    fig = plt.figure(figsize=(7.4, 5.2), constrained_layout=True)
    gs = fig.add_gridspec(2, 3)
    a0 = fig.add_subplot(gs[:, :2]); a1 = fig.add_subplot(gs[0, 2]); a2 = fig.add_subplot(gs[1, 2])
    over = rgb(img).copy()
    over[mask] = (0.45 * over[mask] + 0.55 * np.array([255, 0, 255])).astype(np.uint8)
    a0.imshow(over); off(a0)
    k, ko = np.isfinite(r_in), np.isfinite(r_out)
    a0.plot(cx + r_in[k][::3] * np.cos(ang[k][::3]), cy + r_in[k][::3] * np.sin(ang[k][::3]), ".", ms=2.2,
            color=COL["in"], label="borde interior (por rayo)")
    a0.plot(cx + r_out[ko][::3] * np.cos(ang[ko][::3]), cy + r_out[ko][::3] * np.sin(ang[ko][::3]), ".", ms=2.2,
            color=COL["out"], label="borde exterior (por rayo)")
    t = np.linspace(0, 2 * np.pi, 400)
    a0.plot(cx + ri * np.cos(t), cy + ri * np.sin(t), "-", lw=0.9, color="w")
    a0.plot(cx + ro * np.cos(t), cy + ro * np.sin(t), "--", lw=0.9, color="w")
    a0.plot(cx, cy, "+", color="r", ms=10, mew=1.6)
    cand = [d for d in range(150, 211, 2) if np.isfinite(r_out[int(np.argmin(np.abs(ang - np.radians(d))))])
            and np.isfinite(r_in[int(np.argmin(np.abs(ang - np.radians(d))))])]
    th = np.radians(cand[len(cand) // 2] if cand else 180)
    a0.plot([cx, cx + 1.45 * ri * np.cos(th)], [cy, cy + 1.45 * ri * np.sin(th)], "-", color="#ffd400", lw=1.0)
    a0.set_xlim(0, img.shape[1]); a0.set_ylim(img.shape[0], 0)
    a0.legend(loc="lower center", bbox_to_anchor=(0.5, -0.09), ncol=2, frameon=False, fontsize=8, markerscale=4)
    a0.set_title("(a) máscara del anillo (magenta), bordes por rayo y círculos ajustados", fontsize=9, loc="left")
    yc = int(cy)
    x0, x1, y0, y1 = 0, 80, yc - 55, yc + 55
    a1.imshow(rgb(img)[y0:y1, x0:x1], extent=[x0, x1, y1, y0]); off(a1)
    a1.plot(cx + ri * np.cos(t), cy + ri * np.sin(t), "-", lw=1.2, color=COL["in"])
    a1.plot(cx + ro * np.cos(t), cy + ro * np.sin(t), "--", lw=1.2, color=COL["out"])
    a1.set_xlim(x0, x1); a1.set_ylim(y1, y0)
    a1.set_title("(b) detalle del borde izquierdo", fontsize=9, loc="left")
    rr = np.arange(0.35 * ri, 1.6 * ri, 0.5)
    px, py = cx + rr * np.cos(th), cy + rr * np.sin(th)
    okp = (px >= 0) & (px < img.shape[1] - 1) & (py >= 0) & (py < img.shape[0] - 1)
    sp = cv2.remap(sat.astype(np.float32), px[okp].astype(np.float32)[None], py[okp].astype(np.float32)[None],
                   cv2.INTER_LINEAR)[0]
    a2.plot(rr[okp], sp, color="#333", lw=1.2)
    j = int(np.argmin(np.abs(ang - (th % (2 * np.pi)))))
    for val, c_, lab in ((r_in[j], COL["in"], "r interior"), (r_out[j], COL["out"], "r exterior")):
        if np.isfinite(val):
            a2.axvline(val, color=c_, lw=1.2, ls="-" if lab == "r interior" else "--", label=f"{lab} = {val:.1f} px")
    a2.set_xlim(0.85 * ri, 1.12 * ro); a2.set_xlabel("distancia al centro [px]"); a2.set_ylabel("saturación S")
    a2.legend(frameon=False, fontsize=7.5, loc="upper left")
    a2.set_title("(c) saturación sobre el rayo amarillo", fontsize=9, loc="left")
    fig.savefig(out / "f9_recinto.png", dpi=200)
    plt.close(fig)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--csv", type=Path, required=True)
    ap.add_argument("--sesion", type=Path, required=True)
    ap.add_argument("--video", type=Path)
    ap.add_argument("--cuadros", type=Path, help="npz con 'f' = cuadros 0..180 (en lugar de --video)")
    ap.add_argument("--salida", type=Path, default=ROOT / "informes" / "aplicacion" / "figuras" / "metodo")
    a = ap.parse_args()
    if not (a.video or a.cuadros):
        sys.exit("Indicá --video o --cuadros.")
    D = Data(a)
    a.salida.mkdir(parents=True, exist_ok=True)
    print(f"Orientación: {D.key} ({ori.DESCRIPTION[D.key]}); {len(D.frames)} cuadros")
    f1(D, a.salida)
    # illustrative frame: all N robots accepted and as many rejected gaps as possible
    n = int(D.df["particle"].nunique())
    scores = []
    for fr in range(0, len(D.frames), 10):
        cc, _ = candidates(D, fr)
        scores.append((int(cc.ok.sum()) == n, int((~cc.ok).sum()), -fr, fr))
    fsel = max(scores)[3]
    c, band = f2(D, a.salida, fsel)
    f3(D, a.salida, c, band, fsel)
    f4(D, a.salida)
    f5(D, a.salida)
    pick = f6(D, a.salida)
    f7(D, a.salida, pick[:2])
    f8(D, a.salida)
    f9(D, a.salida)
    print(f"Figuras en {a.salida}")


if __name__ == "__main__":
    main()
