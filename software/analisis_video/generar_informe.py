"""Generate the per-video data and LaTeX section for the robot tracking report.

Usage (from the repository root):
    python software/analisis_video/generar_informe.py datos/video/trayectorias/VP_<código>_robots.csv \
        --video datos/video/recortados/VC_<código>.MP4 --nombre <código>
    (add --cuadros-por-segundo 3 to re-express a CSV exported with another time scale)

Input: the "una fila por robot y cuadro" CSV exported by the app (pestaña Seguimiento) and, if present,
its side-car <csv>_info.json (enclosure, scale). Positions are taken relative to the enclosure centre
(x right, y up, mm) when the CSV has x_mm / y_mm (VidFetch >= 2026-10-08); older CSVs still work.
Output: informes/ensayos/generado/<nombre>/ with datos.tex, resultados.tex, CSV series for PGFPlots,
an optional annotated frame (captura.png), and a notas.tex for manual remarks (never overwritten).
informes/ensayos/generado/lista_ensayos.tex is rebuilt so informe_ensayos.tex includes every processed video.
The annotated frame is read from --video, or from --imagen (a frame already extracted, e.g. with
ffmpeg, when the video is not at hand). Then compile informes/ensayos/informe_ensayos.tex (twice).
"""
from __future__ import annotations

import argparse
import json
import math
import re
import sys
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]                                  # repository root (software/analisis_video/..)
DEFAULT_REPORT = ROOT / "informes" / "ensayos"
MAX_SERIES_POINTS = 600      # PGFPlots stays fast and the PDF light
MAX_TRAJ_POINTS = 400
TRAJ_WINDOW_S = 300.0        # long recordings: trajectories of the first 5 real minutes only
OBSERVED = {"detectado", "detectado (umbral relajado)", "manual"}
ERROR_STATUS = {"predicho (revisar)", "perdido"}


# --------------------------------------------------------------------------- helpers

# Orientation of the scene (as software/vidfetch/core/orientation.py): image-axis signs and angle factor.
ORIENT = {"no": (1, 1, 1), "rot180": (-1, -1, 1), "horizontal": (-1, 1, -1), "vertical": (1, -1, -1)}
ORIENT_TXT = {"no": "imagen tal como la graba la cámara", "rot180": "imagen rotada 180° (vista del observador)",
              "horizontal": "video espejado corregido", "vertical": "video espejado corregido"}


def orientation_of(df: pd.DataFrame) -> str:
    """'orientacion' column (or the older 'espejo'); 'no' when absent."""
    for c in ("orientacion", "espejo"):
        if c in df.columns and str(df[c].iloc[0]) in ORIENT:
            return str(df[c].iloc[0])
    return "no"


def orient_image(img: np.ndarray, key: str) -> np.ndarray:
    import cv2
    sx, sy, _ = ORIENT.get(key, (1, 1, 1))
    if sx < 0 and sy < 0:
        return cv2.rotate(img, cv2.ROTATE_180)
    if sx < 0:
        return cv2.flip(img, 1)
    if sy < 0:
        return cv2.flip(img, 0)
    return img


def tex_escape(s: str) -> str:
    rep = {"\\": r"\textbackslash{}", "_": r"\_", "%": r"\%", "&": r"\&", "#": r"\#",
           "$": r"\$", "{": r"\{", "}": r"\}", "~": r"\textasciitilde{}", "^": r"\textasciicircum{}"}
    return "".join(rep.get(c, c) for c in s)


def slug(s: str) -> str:
    s = re.sub(r"[^A-Za-z0-9_-]+", "_", s).strip("_")
    return s or "video"


def num(v: float, digits: int = 3) -> str:
    """Plain number for \\num{} (siunitx handles the decimal comma)."""
    if v is None or not np.isfinite(v):
        return "nan"
    return f"{v:.{digits}g}" if abs(v) < 1e4 else f"{v:.0f}"


def qty(v: float, unit: str, digits: int = 3) -> str:
    """\\SI{v}{unit}, or an em dash when the value is missing (siunitx rejects 'nan')."""
    if v is None or not np.isfinite(v):
        return "---"
    return f"\\SI{{{num(v, digits)}}}{{{unit}}}"


def load_long_csv(path: Path) -> pd.DataFrame:
    try:
        df = pd.read_csv(path)
    except Exception as exc:
        sys.exit(f"No se pudo leer el CSV: {exc}")
    required = {"frame", "t_s", "particle", "status"}
    missing = required - set(df.columns)
    if not ({"x_mm", "y_mm"} <= set(df.columns) or {"x_px", "y_px"} <= set(df.columns)):
        missing |= {"x_mm", "y_mm"}
    if missing:
        hint = (" Parece el formato 'una fila por cuadro'; exportá con 'una fila por robot y cuadro'."
                if any(c.startswith("r00_") for c in df.columns) else "")
        sys.exit(f"Faltan columnas {sorted(missing)} en {path.name}.{hint}")
    df = df.sort_values(["particle", "frame"]).reset_index(drop=True)
    for c in ("x_px", "y_px", "vx_px_s", "vy_px_s", "speed_px_s", "theta_deg", "omega_deg_s",
              "x_mm", "y_mm", "speed_mm_s", "vx_mm_s", "vy_mm_s", "mm_per_px", "xc_video_px", "yc_video_px"):
        if c in df.columns:
            df[c] = pd.to_numeric(df[c], errors="coerce")
    if "theta_deg" in df.columns:
        # theta = 0 at each robot's first frame of THIS file (the CSV may be a sub-range).
        df["theta_deg"] -= df.groupby("particle")["theta_deg"].transform("first")
    return df


RATE_COLUMNS = ("vx_px_s", "vy_px_s", "speed_px_s", "omega_deg_s", "omega_rad_s",
                "vx_m_s", "vy_m_s", "speed_m_s", "vx_mm_s", "vy_mm_s", "speed_mm_s", "v_rad_mm_s", "v_tan_mm_s")


def load_info(csv_path: Path) -> dict:
    """Side-car written by VidFetch next to each export (empty dict if absent or unreadable)."""
    p = csv_path.with_name(csv_path.stem + "_info.json")
    try:
        return json.loads(p.read_text(encoding="utf-8")) if p.exists() else {}
    except (OSError, ValueError) as exc:
        print(f"Aviso: no se pudo leer {p.name}: {exc}")
        return {}


def csv_frame_rate(df: pd.DataFrame) -> float:
    """Frames per real second implied by the CSV's own t_s column (t_s = frame / f)."""
    d = df.drop_duplicates("frame")
    ok = d["frame"] > 0
    r = (d.loc[ok, "frame"] / d.loc[ok, "t_s"]).replace([np.inf, -np.inf], np.nan).dropna()
    return float(r.median()) if len(r) else float("nan")


def rescale_time(df: pd.DataFrame, new_fps: float) -> tuple[pd.DataFrame, float]:
    """Re-express time and every rate (v, ω) with a different frames-per-real-second.

    Positions and angles are per-frame quantities and do not change; rates scale with new/old.
    """
    old = csv_frame_rate(df)
    if not np.isfinite(old) or old <= 0:
        sys.exit("No se pudo deducir la escala de tiempo del CSV (columna t_s).")
    k = new_fps / old
    df = df.copy()
    df["t_s"] = df["frame"] / new_fps
    for c in RATE_COLUMNS:
        if c in df.columns:
            df[c] = pd.to_numeric(df[c], errors="coerce") * k
    return df, old


def scale_m_per_px(df: pd.DataFrame, diam_mm: float, diam_px: float | None,
                   info: dict | None = None) -> tuple[float | None, str]:
    """Metres per pixel and a description of where it came from."""
    if "mm_per_px" in df.columns and df["mm_per_px"].notna().any() and not diam_px:
        info = info or {}
        rec = info.get("recinto") or {}
        src = info.get("fuente_escala", "recinto")
        if src in ("recinto", "perspectiva") and rec.get("d_int_mm"):
            txt = (f"recinto: diámetro interior de {rec['d_int_mm']:g} mm sobre su radio en px de cada cuadro"
                   + (f", con corrección de perspectiva κ = {info.get('kappa_perspectiva_aplicado', 1):.4f}"
                      if src == "perspectiva" else ""))
        else:
            txt = f"exportada por la app ({src})"
        return float(df["mm_per_px"].median()) / 1000.0, txt
    if diam_px:
        return diam_mm / 1000.0 / diam_px, f"diámetro de {diam_mm:g} mm sobre {diam_px:g} px (indicado)"
    if "x_m" in df.columns:
        r = (pd.to_numeric(df["x_m"], errors="coerce") / df["x_px"]).replace([np.inf, -np.inf], np.nan)
        r = r[(df["x_px"] > 1) & r.notna()]
        if len(r):
            return float(r.median()), "escala exportada por la app (diámetro real cargado en la pestaña Seguimiento)"
    return None, "sin escala: magnitudes en píxeles"


def binned(t: np.ndarray, cols: dict[str, np.ndarray], max_points: int) -> pd.DataFrame:
    n = len(t)
    if n == 0:
        return pd.DataFrame({"t": []})
    step = max(1, math.ceil(n / max_points))
    idx = np.arange(n) // step
    out = {"t": pd.Series(t).groupby(idx).mean().to_numpy()}
    for k, v in cols.items():
        out[k] = pd.Series(v).groupby(idx).mean().to_numpy()
    return pd.DataFrame(out)


# --------------------------------------------------------------------------- snapshot
IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".bmp", ".tif", ".tiff"}


def annotated_frame(video: Path, df: pd.DataFrame, frame: int, radius_px: float, out: Path,
                    fps: float = 30.0, r_in_mm: float | None = None) -> bool:
    """`video` is either the analysed video or an image of that exact frame."""
    try:
        import cv2
    except ImportError:
        print("OpenCV no disponible: se omite la captura.")
        return False
    if video.suffix.lower() in IMAGE_EXTS:
        img = cv2.imread(str(video))
        if img is None:
            print(f"No se pudo leer la imagen {video}: se omite la captura.")
            return False
    else:
        cap = cv2.VideoCapture(str(video))
        if not cap.isOpened():
            print(f"No se pudo abrir el video {video}: se omite la captura.")
            return False
        cap.set(cv2.CAP_PROP_POS_FRAMES, frame)
        ok, img = cap.read()
        cap.release()
        if not ok or img is None:
            print(f"No se pudo leer el cuadro {frame}: se omite la captura.")
            return False
    rows = df[df["frame"] == frame]
    mir = orientation_of(df)
    sx, sy, sr = ORIENT[mir]
    centred = "x_mm" in df.columns          # new format: v and theta in the displayed scene, y UP
    has_video_xy = {"x_video_px", "y_video_px"} <= set(df.columns)
    xs = rows["x_video_px"] if has_video_xy else rows["x_px"]
    ys = rows["y_video_px"] if has_video_xy else rows["y_px"]
    circle = None
    if centred and r_in_mm and {"xc_video_px", "yc_video_px", "mm_per_px"} <= set(rows.columns) and len(rows):
        r0 = rows.iloc[0]
        circle = (float(r0["xc_video_px"]), float(r0["yc_video_px"]), r_in_mm / float(r0["mm_per_px"]))
    oriented = centred and has_video_xy
    if oriented:
        # Show the scene as the observer sees it (e.g. camera image rotated 180 deg): the CSV is in
        # that frame, so after this everything is drawn with x right, y up, CCW positive.
        H, W = img.shape[:2]
        img = orient_image(img, mir)
        xs = (W - 1) - xs if sx < 0 else xs
        ys = (H - 1) - ys if sy < 0 else ys
        if circle is not None:
            circle = ((W - 1) - circle[0] if sx < 0 else circle[0], (H - 1) - circle[1] if sy < 0 else circle[1],
                      circle[2])
        sx = sy = sr = 1
    # Crop around the robots and the enclosure (the app's ROI is not stored in the CSV).
    m = int(2.5 * radius_px)
    x0, y0 = int(np.nanmin(xs)) - m, int(np.nanmin(ys)) - m
    x1, y1 = int(np.nanmax(xs)) + m, int(np.nanmax(ys)) + m
    if circle is not None:
        R = 1.07 * circle[2]
        x0, y0 = min(x0, int(circle[0] - R)), min(y0, int(circle[1] - R))
        x1, y1 = max(x1, int(circle[0] + R)), max(y1, int(circle[1] + R))
    x0, y0, x1, y1 = max(0, x0), max(0, y0), min(img.shape[1], x1), min(img.shape[0], y1)
    crop = img[y0:y1, x0:x1].copy()
    th = max(2, int(round(min(crop.shape[:2]) / 400)))
    if circle is not None:
        cc = (int(round(circle[0] - x0)), int(round(circle[1] - y0)))
        cv2.circle(crop, cc, int(round(circle[2])), (0, 0, 0), th + 2, cv2.LINE_AA)
        cv2.circle(crop, cc, int(round(circle[2])), (0, 255, 255), th, cv2.LINE_AA)
        L = int(0.22 * circle[2])
        for d in (((sx * L, 0)), ((0, -sy * L))):      # exported +x and +y drawn on the image
            tip = (cc[0] + int(d[0]), cc[1] + int(d[1]))
            cv2.arrowedLine(crop, cc, tip, (0, 0, 0), th + 2, cv2.LINE_AA, tipLength=0.15)
            cv2.arrowedLine(crop, cc, tip, (255, 255, 255), th, cv2.LINE_AA, tipLength=0.15)
        cv2.drawMarker(crop, cc, (0, 0, 255), cv2.MARKER_CROSS, 16, th + 1, cv2.LINE_AA)
    r = int(round(radius_px))
    for (_, row), x, y in zip(rows.iterrows(), xs, ys):
        if not (np.isfinite(x) and np.isfinite(y)):
            continue
        c = (int(round(x - x0)), int(round(y - y0)))
        observed = row["status"] in OBSERVED
        col = (0, 200, 0) if observed else (0, 165, 255)
        cv2.circle(crop, c, r, col, th, cv2.LINE_AA)
        if "theta_deg" in row and np.isfinite(row["theta_deg"]):
            t = math.radians(sr * row["theta_deg"])
            tip = (int(round(c[0] - 0.85 * r * math.sin(t))), int(round(c[1] - 0.85 * r * math.cos(t))))
            cv2.line(crop, c, tip, (0, 0, 0), th + 2, cv2.LINE_AA)
            cv2.line(crop, c, tip, (255, 255, 255), th, cv2.LINE_AA)
        if {"vx_px_s", "vy_px_s"} <= set(row.index) and np.isfinite(row["vx_px_s"]):
            if centred:   # displayed scene, y up -> image
                v = np.array([sx * row["vx_px_s"], -sy * row["vy_px_s"]]) * (7.5 / fps)
            else:         # legacy CSV: image axes with x (or y) un-mirrored
                v = np.array([sx * row["vx_px_s"], sy * row["vy_px_s"]]) * (7.5 / fps)
            n = float(np.hypot(*v))
            if n > 1:
                v *= min(1.0, 2.5 * r / n)
                tip = (int(round(c[0] + v[0])), int(round(c[1] + v[1])))
                cv2.arrowedLine(crop, c, tip, (0, 0, 0), th + 2, cv2.LINE_AA, tipLength=0.3)
                cv2.arrowedLine(crop, c, tip, (0, 230, 255), th, cv2.LINE_AA, tipLength=0.3)
        fs = max(0.45, r / 60)
        cv2.putText(crop, str(int(row["particle"])), (c[0] - 8, c[1] + int(0.6 * r)),
                    cv2.FONT_HERSHEY_SIMPLEX, fs, (0, 0, 0), th + 3, cv2.LINE_AA)
        cv2.putText(crop, str(int(row["particle"])), (c[0] - 8, c[1] + int(0.6 * r)),
                    cv2.FONT_HERSHEY_SIMPLEX, fs, (255, 255, 255), th, cv2.LINE_AA)
    cv2.imwrite(str(out), crop)
    return True


# --------------------------------------------------------------------------- main
def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("csv", type=Path, help="CSV 'una fila por robot y cuadro' exportado por la app")
    ap.add_argument("--video", type=Path, help="video analizado (para la captura anotada)")
    ap.add_argument("--nombre", help="identificador del ensayo (por defecto, el nombre del CSV)")
    ap.add_argument("--titulo", help="título de la sección (por defecto, el nombre)")
    ap.add_argument("--frame", type=int, help="cuadro de la captura (por defecto, el del medio)")
    ap.add_argument("--imagen", type=Path, help="imagen de ese cuadro ya extraída (en lugar de --video); "
                                                 "requiere --frame")
    ap.add_argument("--diametro-mm", type=float, help="diámetro real del robot [mm] (def.: el del _info.json, o 33)")
    ap.add_argument("--diametro-px", type=float, help="diámetro del robot en px (si el CSV no trae escala)")
    ap.add_argument("--informe-dir", type=Path, default=DEFAULT_REPORT,
                    help="carpeta del informe de ensayos (por defecto informes/ensayos)")
    ap.add_argument("--cuadros-por-segundo", type=float,
                    help="escala de tiempo real: cuadros que equivalen a 1 s (p. ej. 3 en time-lapse x10); "
                         "por defecto se usa la del CSV")
    a = ap.parse_args()

    df = load_long_csv(a.csv)
    info = load_info(a.csv)
    rec = info.get("recinto") or {}
    if a.diametro_mm is None:
        a.diametro_mm = float(info.get("diametro_robot_mm") or 33.0)
    centred = {"x_mm", "y_mm"} <= set(df.columns)
    r_in_mm = float(rec["d_int_mm"]) / 2 if (centred and rec.get("d_int_mm")) else None
    rescaled_from = None
    if a.cuadros_por_segundo:
        if a.cuadros_por_segundo <= 0:
            sys.exit("--cuadros-por-segundo debe ser positivo.")
        df, rescaled_from = rescale_time(df, a.cuadros_por_segundo)
        print(f"Escala de tiempo: {rescaled_from:.4g} -> {a.cuadros_por_segundo:g} cuadros/s "
              f"(t, v y ω reescalados x{a.cuadros_por_segundo / rescaled_from:.4g})")
    name = slug(a.nombre or a.csv.stem)
    title = a.titulo or (a.nombre or a.csv.stem)
    if a.imagen and a.frame is None:
        sys.exit("--imagen requiere --frame (el cuadro que muestra la imagen).")
    out = a.informe_dir / "generado" / name
    out.mkdir(parents=True, exist_ok=True)

    frames = np.sort(df["frame"].unique())
    n_rob = int(df["particle"].nunique())
    fps = csv_frame_rate(df)                       # frames per REAL second
    duration = len(frames) / fps if np.isfinite(fps) else float("nan")
    # Long recordings (time-lapse of ~1 h): plot time in minutes.
    t_div, t_unit_tex = (60.0, "\\minute") if duration > 600 else (1.0, "\\second")

    s, scale_src = scale_m_per_px(df, a.diametro_mm, a.diametro_px, info)
    # Readable SI submultiples: positions in cm, speeds in mm/s (px when there is no scale).
    unit_l, unit_v = ("cm", "mm/s") if s else ("px", "px/s")
    kl, kv = (s * 100.0, s * 1000.0) if s else (1.0, 1.0)
    diam_px = (a.diametro_mm / 1000.0 / s) if s else (a.diametro_px or float("nan"))

    obs = df["status"].isin(OBSERVED)
    has_v = "speed_px_s" in df.columns or "speed_mm_s" in df.columns
    has_rot = "theta_deg" in df.columns and "rot_status" in df.columns and df["theta_deg"].notna().any()
    if centred and "speed_mm_s" in df.columns:
        speed = df["speed_mm_s"]
    else:
        speed = df["speed_px_s"] * kv if has_v else pd.Series(np.nan, index=df.index)
    sp_obs = speed[obs & speed.notna()]

    # ---- time series (all robots per frame)
    g = df.assign(speed=speed, wabs=df["omega_deg_s"].abs() if has_rot else np.nan,
                  obs=obs.astype(int)).groupby("frame")
    per_frame = pd.DataFrame({"t": g["t_s"].first() / t_div, "v_mean": g["speed"].mean(),
                              "v_q25": g["speed"].quantile(0.25), "v_q75": g["speed"].quantile(0.75),
                              "w_mean": g["wabs"].mean(), "n_obs": g["obs"].sum()})
    series = binned(per_frame["t"].to_numpy(), {c: per_frame[c].to_numpy() for c in per_frame if c != "t"},
                    MAX_SERIES_POINTS)
    series.to_csv(out / "serie.csv", index=False, float_format="%.6g")

    # ---- speed histogram (observed points only)
    if len(sp_obs):
        hi = float(np.nanpercentile(sp_obs, 99.5))
        counts, edges = np.histogram(sp_obs.clip(upper=hi), bins=30, range=(0, hi))
        dens = counts / counts.sum() / np.diff(edges)
        # Left edges + closing right edge, for a left-constant step plot.
        pd.DataFrame({"v": edges, "dens": np.append(dens, dens[-1])}).to_csv(
            out / "hist_v.csv", index=False, float_format="%.6g")

    # ---- trajectories and theta, wide + downsampled
    if centred:   # mm, origin at the enclosure centre, y up -> cm
        piv_x = df.pivot(index="frame", columns="particle", values="x_mm") / 10.0
        piv_y = df.pivot(index="frame", columns="particle", values="y_mm") / 10.0
    else:
        piv_x = df.pivot(index="frame", columns="particle", values="x_px") * kl
        piv_y = df.pivot(index="frame", columns="particle", values="y_px") * kl
    step = max(1, math.ceil(len(piv_x) / MAX_TRAJ_POINTS))
    traj = pd.DataFrame({"t": per_frame["t"]})
    for p in piv_x.columns:
        traj[f"x{int(p)}"] = piv_x[p]
        traj[f"y{int(p)}"] = piv_y[p]
    # Long recordings: 22 trajectories over an hour fill the arena; show a 5-minute window.
    traj_window = duration > 2 * TRAJ_WINDOW_S
    if traj_window:
        n_win = int(round(TRAJ_WINDOW_S * fps))
        traj_part = traj.iloc[:n_win]
        traj_part.iloc[::max(1, math.ceil(len(traj_part) / MAX_TRAJ_POINTS))].to_csv(
            out / "tray.csv", index=False, float_format="%.6g")
    else:
        traj.iloc[::step].to_csv(out / "tray.csv", index=False, float_format="%.6g")
    if has_rot:
        piv_t = df.pivot(index="frame", columns="particle", values="theta_deg") / 360.0
        th = pd.DataFrame({"t": per_frame["t"]})
        for p in piv_t.columns:
            th[f"th{int(p)}"] = piv_t[p]
        th.iloc[::step].to_csv(out / "theta.csv", index=False, float_format="%.6g")

    # ---- per-robot summary
    rows = []
    for p, gr in df.groupby("particle"):
        if centred:
            x, y = gr["x_mm"].to_numpy() / 10.0, gr["y_mm"].to_numpy() / 10.0
        else:
            x, y = gr["x_px"].to_numpy() * kl, gr["y_px"].to_numpy() * kl
        ok = np.isfinite(x) & np.isfinite(y)
        path = float(np.nansum(np.hypot(np.diff(x), np.diff(y))))
        net = float(np.hypot(x[ok][-1] - x[ok][0], y[ok][-1] - y[ok][0])) if ok.sum() > 1 else np.nan
        if centred and "speed_mm_s" in gr.columns:
            sp = gr["speed_mm_s"].to_numpy()
        else:
            sp = gr["speed_px_s"].to_numpy() * kv if has_v else np.array([np.nan])
        row = {"id": int(p), "obs": 100.0 * gr["status"].isin(OBSERVED).mean(),
               "vmed": float(np.nanmean(sp)), "vmax": float(np.nanmax(sp)) if np.isfinite(sp).any() else np.nan,
               "rec": path, "net": net}
        if has_rot:
            thv = gr["theta_deg"].to_numpy()
            row["vueltas"] = float(thv[np.isfinite(thv)][-1] / 360.0) if np.isfinite(thv).any() else np.nan
            row["wabs"] = float(np.nanmean(np.abs(gr["omega_deg_s"].to_numpy())))
        rows.append(row)
    summ = pd.DataFrame(rows)
    summ.to_csv(out / "resumen.csv", index=False, float_format="%.4g")

    # ---- facts for the text
    iss = df.groupby("frame")["status"].agg(lambda s_: s_.isin(ERROR_STATUS).any())
    adv = df.groupby("frame")["status"].agg(lambda s_: (s_ == "interpolado").any())
    n_err, n_adv = int(iss.sum()), int((adv & ~iss).sum())
    pct_obs = 100.0 * obs.mean()
    pct_rot = 100.0 * (df["rot_status"] == "medida").mean() if has_rot else float("nan")
    fastest = summ.loc[summ["vmed"].idxmax()] if summ["vmed"].notna().any() else None
    if has_rot:
        spinner = summ.loc[summ["wabs"].idxmax()]
        n_ccw = int((summ["vueltas"] > 0.5).sum())
        n_cw = int((summ["vueltas"] < -0.5).sum())
        n_still = n_rob - n_ccw - n_cw
    density_ratio = float("nan")
    if has_v and len(sp_obs):
        density_ratio = float(np.nanpercentile(sp_obs, 95) / max(np.nanmedian(sp_obs), 1e-12))

    # ---- datos.tex (macros consumed by resultados.tex)
    mm_u, pct_u = "\\milli\\metre", "\\percent"   # no backslash inside f-string expressions (py<3.12)
    recinto_txt = "no definido"
    if r_in_mm:
        recinto_txt = (f"$D_{{\\mathrm{{int}}}}$ = {qty(2 * r_in_mm, mm_u)}; se desplazó "
                       f"{qty(rec.get('desplazamiento_x_mm', float('nan')), mm_u, 2)} en $x$ y "
                       f"{qty(rec.get('desplazamiento_y_mm', float('nan')), mm_u, 2)} en $y$; "
                       f"variación de escala (zoom de la cámara): {qty(rec.get('variacion_escala_pct', float('nan')), pct_u, 2)}")
    dt_q = qty(1.0 / fps, "\\second") if np.isfinite(fps) else "---"   # no backslash inside f-string (py<3.12)
    macros = {
        "VTitulo": tex_escape(title), "VArchivo": tex_escape(a.csv.name),
        "VVideo": (tex_escape(a.video.name) if a.video else
                   tex_escape(f"VC_{name}.MP4") + " (captura de una imagen extraída)" if a.imagen else "---"),
        "VFrameIni": str(int(frames[0])), "VFrameFin": str(int(frames[-1])), "VCuadros": str(len(frames)),
        "VFps": num(fps, 4), "VDuracion": num(duration, 3), "VN": str(n_rob),
        "VUnidadL": unit_l, "VUnidadV": unit_v,
        "VEscala": num(s * 1000.0, 4) if s else "---", "VEscalaFuente": tex_escape(scale_src),
        "VEscalaQ": qty(s * 1000.0 if s else float("nan"), "\\milli\\metre\\per px", 4),
        "VFpsQ": (f"\\num{{{num(fps, 4)}}} cuadros = \\SI{{1}}{{\\second}} real "
                  f"($\\Delta t = {dt_q}$)" if np.isfinite(fps) else "---"),
        "VDuracionQ": (qty(duration / 60.0, "\\minute") if duration > 600 else qty(duration, "\\second")),
        "VRescala": (f"reescalada desde \\num{{{num(rescaled_from, 4)}}} cuadros/s del CSV"
                     if rescaled_from else "tomada del CSV exportado"),
        "VDiamQ": qty(a.diametro_mm, "\\milli\\metre") + (
            f" $\\equiv$ {qty(diam_px, 'px')}" if np.isfinite(diam_px) else ""),
        "VUL": "\\centi\\metre" if s else "px", "VUV": "\\milli\\metre\\per\\second" if s else "px\\per\\second",
        "VDiamMM": num(a.diametro_mm, 3), "VDiamPx": num(diam_px, 3),
        "VPctObs": num(pct_obs, 4), "VPctRot": num(pct_rot, 4),
        "VNErr": str(n_err), "VNAdv": str(n_adv),
        "VVmedia": num(float(np.nanmean(sp_obs)) if len(sp_obs) else float("nan")),
        "VVmediana": num(float(np.nanmedian(sp_obs)) if len(sp_obs) else float("nan")),
        "VVpNoventaycinco": num(float(np.nanpercentile(sp_obs, 95)) if len(sp_obs) else float("nan")),
        "VRecMedio": num(float(summ["rec"].mean())), "VNetoMedio": num(float(summ["net"].mean())),
        "VOrigen": ("centro del recinto en cada cuadro ($x$ a la derecha, $y$ hacia arriba)" if r_in_mm
                    else ("centro del recorte" if centred else "esquina del recorte ($y$ hacia abajo)")),
        "VRecinto": recinto_txt,
    }
    lines = ["% Generated by generar_informe.py -- do not edit; re-run the script instead."]
    lines += [f"\\def\\{k_}{{{v}}}" for k_, v in macros.items()]
    (out / "datos.tex").write_text("\n".join(lines) + "\n", encoding="utf-8")

    # ---- observations paragraph (auto) — numbers via siunitx
    obs_txt = [
        f"Se siguieron \\num{{{n_rob}}} robots durante \\num{{{len(frames)}}} cuadros "
        f"({macros['VDuracionQ']}). El \\SI{{{macros['VPctObs']}}}{{\\percent}} de las posiciones "
        "fue observado (detectado o corregido a mano); el resto se estimó por interpolación o predicción.",
    ]
    if n_err or n_adv:
        obs_txt.append(f"Hubo \\num{{{n_err}}} cuadros con posiciones predichas o perdidas y \\num{{{n_adv}}} "
                       "cuadros con posiciones interpoladas; conviene excluirlos de los análisis sensibles "
                       "usando la columna \\texttt{status}.")
    else:
        obs_txt.append("No hubo cuadros con posiciones estimadas.")
    if has_v and len(sp_obs):
        u = "\\milli\\metre\\per\\second" if s else "px\\per\\second"
        obs_txt.append(f"La rapidez mediana fue \\SI{{{macros['VVmediana']}}}{{{u}}} y el percentil 95, "
                       f"\\SI{{{macros['VVpNoventaycinco']}}}{{{u}}}: la cola rápida es "
                       f"\\num{{{num(density_ratio, 2)}}} veces la mediana, lo que indica movimiento "
                       f"{'intermitente, con episodios cortos de alta velocidad' if density_ratio > 2.5 else 'relativamente uniforme'}.")
        if fastest is not None:
            obs_txt.append(f"El robot más rápido en promedio fue el \\num{{{int(fastest['id'])}}} "
                           f"(\\SI{{{num(fastest['vmed'])}}}{{{u}}}).")
    if has_rot:
        obs_txt.append(f"En rotación, \\num{{{n_ccw}}} robots giraron en neto en sentido antihorario, "
                       f"\\num{{{n_cw}}} en sentido horario y \\num{{{n_still}}} giraron menos de media vuelta. "
                       f"El que más giró fue el \\num{{{int(spinner['id'])}}}, con "
                       f"$|\\omega|$ media de \\SI{{{num(spinner['wabs'])}}}{{\\degree\\per\\second}}. "
                       f"La rotación se midió directamente en el \\SI{{{macros['VPctRot']}}}{{\\percent}} de los puntos.")
    else:
        obs_txt.append("El CSV no contiene datos de rotación (análisis anterior a la medición de $\\theta$).")

    # ---- resultados.tex
    N1 = n_rob - 1
    rel = f"generado/{name}"
    lu = "\\centi\\metre" if s else "px"
    vu = "\\milli\\metre\\per\\second" if s else "px\\per\\second"
    tex = []
    tex.append(f"% Generated by generar_informe.py for {a.csv.name}. Manual remarks go in notas.tex.")
    tex.append("\\begingroup")
    tex.append(f"\\input{{{rel}/datos.tex}}")
    tex.append(f"\\section{{Ensayo \\VTitulo}}\\label{{sec:{name}}}")
    tex.append(r"""
\begin{table}[H]
  \centering
  \caption{Datos del ensayo \VTitulo.}
  \begin{tabular}{@{}lp{0.58\linewidth}@{}}
    \toprule
    Archivo de datos & \texttt{\VArchivo} \\
    Video & \texttt{\VVideo} \\
    Cuadros analizados & \VFrameIni\,--\,\VFrameFin{} (\num{\VCuadros}) \\
    Escala de tiempo & \VFpsQ\newline{\footnotesize\VRescala} \\
    Duración real & \VDuracionQ \\
    Robots seguidos ($N$) & \num{\VN} \\
    Diámetro del robot & \VDiamQ \\
    Escala & \VEscalaQ\newline{\footnotesize\VEscalaFuente} \\
    Origen de coordenadas & \VOrigen \\
    Recinto & \VRecinto \\
    Posiciones observadas & \SI{\VPctObs}{\percent} \\
    Cuadros con error / con advertencia & \num{\VNErr} / \num{\VNAdv} \\
    \bottomrule
  \end{tabular}
\end{table}
""")
    tex.append(f"\\IfFileExists{{{rel}/captura.png}}{{%")
    tex.append(r"""\begin{figure}[H]
  \centering
  \includegraphics[width=0.62\linewidth]{""" + rel + r"""/captura.png}
  \caption{Cuadro de ejemplo con identificador, vector velocidad (amarillo, largo = desplazamiento en 7,5 cuadros) y orientación (aguja blanca). Círculo verde: posición observada; naranja: estimada."""
    + (f" {ORIENT_TXT[orientation_of(df)].capitalize()}: $x$ a la derecha, $y$ hacia arriba (lejos del observador)." if "x_mm" in df.columns else "")
    + r"""}
\end{figure}}{}""")
    tex.append(r"""
\begin{figure}[H]
  \centering
  \begin{tikzpicture}
    \begin{axis}[width=0.97\linewidth, height=5.2cm, xlabel={$t$ [\si{""" + t_unit_tex + r"""}]},
        ylabel={$|\vec v|$ [\si{""" + vu + r"""}]}, ymin=0, grid=major, grid style={gray!20}, scaled ticks=false, tick label style={/pgf/number format/fixed, /pgf/number format/precision=3},
        legend pos=north east, legend style={font=\footnotesize}, enlarge x limits=false]
      \addplot [name path=q75, draw=none, forget plot] table [x=t, y=v_q75, col sep=comma] {""" + rel + r"""/serie.csv};
      \addplot [name path=q25, draw=none, forget plot] table [x=t, y=v_q25, col sep=comma] {""" + rel + r"""/serie.csv};
      \addplot [azul!25] fill between [of=q25 and q75];
      \addlegendentry{rango intercuartil}
      \addplot [azul, thick] table [x=t, y=v_mean, col sep=comma] {""" + rel + r"""/serie.csv};
      \addlegendentry{media de los $N$ robots}
    \end{axis}
  \end{tikzpicture}
  \caption{Rapidez de los robots en función del tiempo.}
\end{figure}
""")
    if has_v and len(sp_obs):
        tex.append(r"""\begin{figure}[H]
  \centering
  \begin{tikzpicture}
    \begin{axis}[width=0.8\linewidth, height=5cm, xlabel={$|\vec v|$ [\si{""" + vu + r"""}]},
        ylabel={densidad [\si{""" + ("\\second\\per\\milli\\metre" if s else "\\second\\per px") + r"""}]},
        ymin=0, enlarge x limits=false, grid=major, grid style={gray!20},
        scaled ticks=false, tick label style={/pgf/number format/fixed, /pgf/number format/precision=3}]
      \addplot [fill=azul!35, draw=azul, const plot mark left] table [x=v, y=dens, col sep=comma] {""" + rel + r"""/hist_v.csv} \closedcycle;
    \end{axis}
  \end{tikzpicture}
  \caption{Distribución de la rapidez (solo posiciones observadas).}
\end{figure}
""")
    tex.append(r"""\begin{figure}[H]
  \centering
  \begin{tikzpicture}
    \begin{axis}[width=0.72\linewidth, axis equal image,""" + ("" if centred else " y dir=reverse,") + r""" xlabel={$x$ [\si{""" + lu + r"""}]},
        ylabel={$y$ [\si{""" + lu + r"""}]}, grid=major, grid style={gray!20}, cycle list name=robots,
        tick label style={font=\footnotesize}]
      \pgfplotsinvokeforeach{0,...,""" + str(N1) + r"""}{%
        \addplot+ [thin, no markers] table [x=x#1, y=y#1, col sep=comma] {""" + rel + r"""/tray.csv};}""" + (
        r"""
      \draw [gray, thick] (axis cs:0,0) circle [radius=""" + f"{r_in_mm / 10.0:.4g}" + r"""];
      \addplot [only marks, mark=+, mark size=3pt, black] coordinates {(0,0)};""" if r_in_mm else "") + r"""
    \end{axis}
  \end{tikzpicture}
  \caption{Trayectorias de los """ + str(n_rob) + r""" robots (""" + (ORIENT_TXT[orientation_of(df)] if "x_mm" in df.columns
                   else "como en el video") + (r"""; origen en el centro del recinto, $y$ hacia arriba; círculo gris: pared interior"""
                   if r_in_mm else r"""; $y$ hacia abajo""") + r""")"""
    + (f", primeros {TRAJ_WINDOW_S / 60:g} minutos reales" if traj_window else "") + r""".}
\end{figure}
""")
    if has_rot:
        tex.append(r"""\begin{figure}[H]
  \centering
  \begin{tikzpicture}
    \begin{axis}[width=0.97\linewidth, height=5.4cm, xlabel={$t$ [\si{""" + t_unit_tex + r"""}]},
        ylabel={$\theta$ [vueltas]}, grid=major, grid style={gray!20}, cycle list name=robots, enlarge x limits=false]
      \pgfplotsinvokeforeach{0,...,""" + str(N1) + r"""}{%
        \addplot+ [thin, no markers] table [x=t, y=th#1, col sep=comma] {""" + rel + r"""/theta.csv};}
    \end{axis}
  \end{tikzpicture}
  \caption{Orientación acumulada de cada robot ($\theta=0$ en el primer cuadro; positivo = antihorario).}
\end{figure}
""")
    # Decimals so that the typical speed keeps >= 2 significant digits (works for mm/s and px/s).
    v_ref = float(np.nanmedian(summ["vmed"])) if summ["vmed"].notna().any() else 1.0
    v_prec = int(min(4, max(1, 1 - math.floor(math.log10(v_ref))))) if v_ref > 0 else 1
    w_ref = float(np.nanmedian(summ["wabs"])) if has_rot and summ["wabs"].notna().any() else 10.0
    w_prec = int(min(4, max(0, 1 - math.floor(math.log10(w_ref))))) if w_ref > 0 else 0
    cols_rot = (r""" columns/vueltas/.style={column name={$\theta_{\mathrm{final}}$ [vueltas]}, fixed, precision=2},
      columns/wabs/.style={column name={$\overline{|\omega|}$ [\si{\degree\per\second}]}, fixed, fixed zerofill, precision=""" + str(w_prec) + r"""},""" if has_rot else "")
    shown = "id,obs,vmed,vmax,rec,net" + (",vueltas,wabs" if has_rot else "")
    tex.append(r"""\begin{table}[H]
  \centering
  \caption{Resumen por robot.}
  \footnotesize
  \pgfplotstabletypeset[col sep=comma, columns={""" + shown + r"""},
      every head row/.style={before row=\toprule, after row=\midrule}, every last row/.style={after row=\bottomrule},
      columns/id/.style={column name={Robot}, int detect},
      columns/obs/.style={column name={Obs. [\si{\percent}]}, fixed, precision=1},
      columns/vmed/.style={fixed, fixed zerofill, precision=""" + str(v_prec) + r""", column name={$\overline{|\vec v|}$ [\si{""" + vu + r"""}]}},
      columns/vmax/.style={fixed, fixed zerofill, precision=""" + str(v_prec) + r""", column name={$|\vec v|_{\max}$ [\si{""" + vu + r"""}]}},
      columns/rec/.style={fixed, fixed zerofill, precision=2, column name={Recorrido [\si{""" + lu + r"""}]}},
      columns/net/.style={fixed, fixed zerofill, precision=2, column name={Despl. neto [\si{""" + lu + r"""}]}},""" + cols_rot + r"""
    ]{""" + rel + r"""/resumen.csv}
\end{table}
""")
    tex.append("\\subsection{Lo observado}")
    tex.append("\n".join(obs_txt))
    tex.append(f"\n\\IfFileExists{{{rel}/notas.tex}}{{\\input{{{rel}/notas.tex}}}}{{}}")
    tex.append("\\endgroup\n")
    (out / "resultados.tex").write_text("\n".join(tex), encoding="utf-8")

    notes = out / "notas.tex"
    if not notes.exists():
        notes.write_text("% Observaciones propias sobre este ensayo (este archivo no se sobrescribe).\n"
                         "% Ejemplo:\n% \\paragraph{Notas.} A partir de $t\\approx\\SI{3}{\\second}$ los robots se\n"
                         "% agrupan contra la pared norte de la arena.\n", encoding="utf-8")

    src_img = a.imagen or a.video
    if src_img:
        f = a.frame if a.frame is not None else int(frames[len(frames) // 2])
        if f not in set(frames.tolist()):
            print(f"El cuadro {f} no está en el CSV; se usa el del medio.")
            f = int(frames[len(frames) // 2])
        radius = (diam_px / 2) if np.isfinite(diam_px) else 20.0
        if annotated_frame(src_img, df, f, radius, out / "captura.png", fps if np.isfinite(fps) else 30.0,
                           r_in_mm):
            print(f"Captura anotada: cuadro {f}")

    # ---- rebuild the list of videos
    vids = sorted(p.parent.name for p in (a.informe_dir / "generado").glob("*/resultados.tex"))
    (a.informe_dir / "generado" / "lista_ensayos.tex").write_text(
        "% Generated by generar_informe.py: one line per processed video.\n"
        + "".join(f"\\input{{generado/{v}/resultados.tex}}\n" for v in vids), encoding="utf-8")
    print(f"Listo: {out}  ({len(vids)} ensayo(s) en el informe). Compilá informe_ensayos.tex dos veces.")


if __name__ == "__main__":
    main()
