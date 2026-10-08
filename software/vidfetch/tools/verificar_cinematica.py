"""Visual and numeric check of positions, axes, displacements and velocities exported by VidFetch.

Works only from the exported CSV (+ its _info.json) and the analysed video, i.e. it checks the data
as the reports use them. Needs only OpenCV, NumPy and pandas (no SciPy / matplotlib).

Usage (from the repository root):
  python software/vidfetch/tools/verificar_cinematica.py datos/video/trayectorias/VP_<code>_robots.csv ^
      --video datos/video/recortados/VC_<code>.MP4 [--cuadro 6000] [--robots 3,7,12] [--delta 5]
Output: datos/video/verificacion/cinematica_<code>.png and .txt (or --salida).

Panel A (axes and origin): the frame is flipped back to the REAL scene (if the video is mirrored) and
every robot is redrawn from x_mm, y_mm only: u = xc' + x/s, v = yc - y/s. The enclosure, its centre and
the +x (right) / +y (up) axes are drawn too. If origin, mirror, axis signs or scale were wrong, the
circles would not sit on the robots.
Panel B (displacement and velocity): for a few moving robots, the CSV velocity is integrated over
[t, t + delta] (trapezoid): the yellow arrow on frame t ends where the robot should be at t + delta.
On frame t + delta the yellow circle is that prediction and the green one the exported position: the
real robot must be inside both.
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


def panel_axes(cap, sc: Scene, df: pd.DataFrame, frame: int, r_in_mm: float, d_mm: float) -> np.ndarray:
    img = sc.real_image(read_frame(cap, frame))
    rows = df[df["frame"] == frame]
    s = float(sc.s[frame])
    cx, cy = sc.centre(frame)
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
    rr = int(round(0.5 * d_mm / s))
    for (_, row), ui, vi in zip(rows.iterrows(), u, v):
        col = GREEN if row["status"] == "detectado" else (0, 165, 255)
        cv2.circle(img, (int(round(ui)), int(round(vi))), rr, col, 2, cv2.LINE_AA)
        text(img, str(int(row["particle"])), (int(ui) - 8, int(vi) + 6), 0.5)
    # Spell out three robots: their coordinates must match where they are with respect to the axes.
    pick = rows.assign(a=np.abs(rows["x_mm"]) + np.abs(rows["y_mm"])).nlargest(3, "a")
    for k, (_, row) in enumerate(pick.iterrows()):
        text(img, f"#{int(row['particle'])}: x={row['x_mm']:+.1f} y={row['y_mm']:+.1f} mm",
             (8, img.shape[0] - 12 - 20 * k), 0.5, YELLOW)
    text(img, f"A. Ejes y origen - cuadro {frame} (t = {rows['t_s'].iloc[0] / 60:.1f} min)", (8, 20), 0.55)
    text(img, "escena real" + (" (video des-espejado)" if sc.mirror != "no" else ""), (8, 40), 0.5)
    return img


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
        text(tile, f"int v dt = ({pred[0]:+.1f}, {pred[1]:+.1f}) mm | dpos = ({meas[0]:+.1f}, {meas[1]:+.1f}) mm",
             (6, tile.shape[0] - 10), 0.42, YELLOW)
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
               "en t+dt: amarillo = prediccion, verde = posicion exportada", (6, 22), 0.5)
    return np.vstack([head, grid]), lines


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
    cap.release()
    # Side by side at a common height (the taller panel keeps its resolution)
    h = max(A.shape[0], B.shape[0])
    A = cv2.resize(A, (int(round(A.shape[1] * h / A.shape[0])), h), interpolation=cv2.INTER_CUBIC)
    B = cv2.resize(B, (int(round(B.shape[1] * h / B.shape[0])), h), interpolation=cv2.INTER_CUBIC)
    out_img = np.hstack([A, np.zeros((h, 8, 3), np.uint8), B])

    code = a.csv.stem.replace("VP_", "").replace("_robots", "")
    out = a.salida or (a.csv.parents[1] / "verificacion" / f"cinematica_{code}.png")
    out.parent.mkdir(parents=True, exist_ok=True)
    ok, buf = cv2.imencode(".png", out_img)      # imencode + write_bytes: safe with OneDrive / non-ASCII paths
    out.write_bytes(buf.tobytes())
    lines = [f"Verificación de cinemática: {a.csv.name} (fr = {fps:g} cuadros/s, espejo: {sc.mirror})"]
    lines += numeric_checks(df, fps, r_in_mm, d_mm)
    lines += ["Panel B:"] + ["   " + s for s in move_lines]
    out.with_suffix(".txt").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("\n".join(lines))
    print(f"Figura: {out}")


if __name__ == "__main__":
    main()
