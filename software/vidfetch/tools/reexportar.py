"""Re-export a saved VidFetch analysis (.npz) without the GUI: enclosure, centred CSV, per-robot CSVs.

Usage (from the repository root):
    python software/vidfetch/tools/reexportar.py datos/video/sesiones/VA_<código>_analisis.npz ^
        --video datos/video/recortados/VC_<código>.MP4 --espejo horizontal --ventana 5 ^
        --salida datos/video/trayectorias/VP_<código>_robots.csv --resumen --guardar-sesion

What it does:
  1. Loads the session (candidates, anchors, parameters) and re-runs the tracking (stage B, seconds).
  2. Enclosure: uses the one saved in the session; with --redetectar (or if the session has none)
     measures it on the video every --paso frames (needs --video or the path stored in the session).
  3. Kinematics with the given options and export of:
       <salida>                      long CSV, one row per robot and frame (all columns)
       <salida>_info.json            enclosure, scale, conventions
       <salida sin .csv>_resumen.csv per-robot summary (with --resumen)
       <--por-robot DIR>/<video>_robotNN.csv  one CSV per robot (with --por-robot)
  4. With --guardar-sesion, writes the session back (with the enclosure) so the GUI and later
     runs reuse it.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from dataclasses import replace
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))

from core import arena as ar  # noqa: E402
from core import kinematics as km  # noqa: E402
from core.models import TrimRange  # noqa: E402
from core.tracking import TrackingSession  # noqa: E402


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("sesion", type=Path, help="análisis guardado por la app (.npz)")
    ap.add_argument("--video", type=Path, help="video analizado (si no está en la ruta guardada en la sesión)")
    ap.add_argument("--salida", type=Path, help="CSV largo de salida (por defecto <sesión>_robots.csv)")
    ap.add_argument("--resumen", action="store_true", help="exportar también el resumen por robot")
    ap.add_argument("--por-robot", type=Path, metavar="CARPETA", help="un CSV por robot en esta carpeta")
    ap.add_argument("--espejo", choices=list(km.MIRROR_LABELS), help="video espejado (no/horizontal/vertical)")
    ap.add_argument("--ventana", type=int, help="ventana Savitzky-Golay [cuadros, impar]")
    ap.add_argument("--diametro-robot", type=float, help="diámetro real del robot [mm]")
    ap.add_argument("--escala", choices=list(km.SCALE_LABELS), help="fuente de la escala mm/px")
    ap.add_argument("--cuadros-por-segundo", type=float, help="escala de tiempo real (cuadros = 1 s)")
    ap.add_argument("--d-int", type=float, help=f"diámetro interior del recinto [mm] (def. {ar.D_IN_MM:g})")
    ap.add_argument("--d-ext", type=float, help=f"diámetro exterior del recinto [mm] (def. {ar.D_OUT_MM:g})")
    ap.add_argument("--redetectar", action="store_true", help="volver a medir el recinto en el video")
    ap.add_argument("--paso", type=int, default=ar.DEFAULT_STEP, help="cuadros entre mediciones del recinto")
    ap.add_argument("--guardar-sesion", nargs="?", const=True, default=False, metavar="NPZ",
                    help="guardar la sesión con el recinto (sobre la misma o en NPZ)")
    a = ap.parse_args()

    try:
        s = TrackingSession.load(str(a.sesion))
    except Exception as exc:
        sys.exit(f"No se pudo cargar la sesión: {type(exc).__name__}: {exc}")
    if a.video:
        s.src_path = str(a.video)
    if a.cuadros_por_segundo:
        s.fps = a.cuadros_por_segundo
    kp = s.kin_params or km.KinematicsParams()
    kp = replace(kp, **{k: v for k, v in (("mirror", a.espejo), ("window", a.ventana),
                                          ("robot_diameter_mm", a.diametro_robot),
                                          ("scale_source", a.escala)) if v is not None})
    if kp.window % 2 == 0:
        kp = replace(kp, window=kp.window + 1)
    s.kin_params = kp

    d_in = a.d_int or (s.arena.d_in_mm if s.arena else ar.D_IN_MM)
    d_out = a.d_ext or (s.arena.d_out_mm if s.arena else ar.D_OUT_MM)
    if a.redetectar or s.arena is None or not s.arena.defined:
        if not os.path.isfile(s.src_path):
            sys.exit(f"Para medir el recinto hace falta el video: {s.src_path} no existe (usá --video).")
        t0 = time.perf_counter()
        trim = TrimRange(int(s.candidates.frames[0]), int(s.candidates.frames[-1]))
        track, _ = ar.track_video(s.src_path, trim, s.roi, a.paso, d_in, d_out,
                                  progress=lambda v: print(f"\rRecinto: {v:3d} %", end="", flush=True))
        print(f"\rRecinto medido en {time.perf_counter() - t0:.0f} s.")
        if s.arena is not None and s.arena.manual is not None:
            track.manual, track.manual_frame = s.arena.manual, s.arena.manual_frame
            track.manual_points, track.follow_motion = s.arena.manual_points, s.arena.follow_motion
        s.arena = track
    else:
        s.arena = s.arena.with_diameters(d_in, d_out)
    print("Recinto:", s.arena.describe().replace("<br>", "\n         "))

    t0 = time.perf_counter()
    if s.run() is None:
        sys.exit("Seguimiento cancelado.")
    print(f"Seguimiento y cinemática: {time.perf_counter() - t0:.0f} s · escala {s.kin.scale_source} "
          f"{s.kin.mm_per_px:.4f} mm/px · κ medido {s.kin.kappa_measured:.4f}")

    out = a.salida or a.sesion.with_name(a.sesion.stem.replace("_analisis", "") + "_robots.csv")
    out.parent.mkdir(parents=True, exist_ok=True)
    df = s.to_dataframe()
    df.to_csv(out, index=False, float_format="%.6g")
    info = s.export_info()
    out.with_name(out.stem + "_info.json").write_text(json.dumps(info, ensure_ascii=False, indent=2, default=float),
                                                       encoding="utf-8")
    print(f"CSV: {out} ({len(df)} filas × {df.shape[1]} columnas)")
    if a.resumen:
        rpath = out.with_name(out.stem + "_resumen.csv")
        s.summary_dataframe().to_csv(rpath, index=False, float_format="%.6g")
        print(f"Resumen: {rpath}")
    if a.por_robot:
        a.por_robot.mkdir(parents=True, exist_ok=True)
        base = Path(s.src_path).stem
        n = s.result.n_objects
        w = max(2, len(str(n - 1)))
        for k in range(n):
            km.robot_table(df, k).to_csv(a.por_robot / f"{base}_robot{k:0{w}d}.csv", index=False, float_format="%.6g")
        print(f"{n} CSV por robot en {a.por_robot}")
    if a.guardar_sesion:
        dst = a.sesion if a.guardar_sesion is True else Path(a.guardar_sesion)
        s.save(str(dst))
        print(f"Sesión guardada: {dst}")


if __name__ == "__main__":
    main()
