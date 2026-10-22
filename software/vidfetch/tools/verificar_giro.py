"""Visual check of the accumulated rotation theta over long spans (>= 10 min).

For a few robots, crops the robot from the cropped video (VC_) every few minutes and shows three rows:
  1. the crop as recorded,
  2. the crop rotated back by -theta computed with short links only (previous method),
  3. the crop rotated back by -theta computed with long-range links (current method).
If theta is right, rows 2/3 look identical across columns (same marks in the same place).
The red tick marks 12 o'clock; theta is relative to the first column, CCW positive. The crops are shown
in the orientation of the session (core.orientation; rot180 = as the observer sees the scene), and the
printed angles follow it (a rotation keeps their sign, a mirror reverses it).

Usage (from the repository root):
  python software/vidfetch/tools/verificar_giro.py datos/video/sesiones/VA_<code>_analisis.npz \
      --video datos/video/recortados/VC_<code>.MP4 [--robots 3,7,12] [--inicio 0] [--cada 2.5] [--duracion 15]
Output: <session folder>/../verificacion/giro_<code>.png unless --salida is given.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import cv2
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from core import kinematics as km  # noqa: E402
from core import orientation as ori  # noqa: E402
from core.tracking import TrackingSession  # noqa: E402
from core.video_io import VideoReader  # noqa: E402

SNAP_FRAMES = 15        # look this far for a frame where the robot's rotation was measured
CROP_PER_R = 1.35       # crop half-size / r_out


def _pick_robots(kin: km.Kinematics, n: int) -> list[int]:
    measured = (kin.rot_status == km.ROT_MEASURED).mean(axis=0)
    spin = np.abs(kin.theta[-1] - kin.theta[0])
    score = np.where(measured > 0.9, spin, -1.0)  # well-measured robots that turn a lot show drift best
    return [int(k) for k in np.argsort(-score)[:n]]


def _snap(rot_status: np.ndarray, row: int) -> int | None:
    for d in range(SNAP_FRAMES + 1):
        for r in (row + d, row - d):
            if 0 <= r < len(rot_status) and rot_status[r] == km.ROT_MEASURED:
                return r
    return None


def _crop(frame: np.ndarray, cx: float, cy: float, half: int, angle_deg: float) -> np.ndarray:
    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY) if frame.ndim == 3 else frame
    M = cv2.getRotationMatrix2D((float(cx), float(cy)), float(angle_deg), 1.0)
    M[0, 2] += half - cx
    M[1, 2] += half - cy
    return cv2.warpAffine(gray, M, (2 * half + 1, 2 * half + 1), flags=cv2.INTER_LINEAR,
                          borderMode=cv2.BORDER_REPLICATE)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("sesion")
    ap.add_argument("--video", required=True, help="video recortado (VC_) usado en el análisis")
    ap.add_argument("--robots", default="", help="índices separados por coma (por defecto, 4 automáticos)")
    ap.add_argument("--inicio", type=float, default=0.0, help="minuto de la primera columna")
    ap.add_argument("--cada", type=float, default=2.5, help="minutos entre columnas")
    ap.add_argument("--duracion", type=float, default=15.0, help="minutos cubiertos (>= 10 recomendado)")
    ap.add_argument("--salida", default="")
    a = ap.parse_args()

    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    sess = TrackingSession.load(a.sesion)
    print("Reconstruyendo el seguimiento y θ (puede tardar 1-2 min)...")
    res = sess.run()
    if res is None or sess.kin is None:
        print("No se pudo reconstruir el seguimiento.")
        return 1
    kin = sess.kin
    theta_old, _ = km._rotation_uncached(res, sess.candidates.sig, long_range=False)
    theta_new = kin.theta
    fps = sess.fps
    robots = [int(r) for r in a.robots.split(",") if r.strip()] or _pick_robots(kin, 4)
    times = np.arange(a.inicio, a.inicio + a.duracion + 1e-9, a.cada)
    half = int(round(CROP_PER_R * sess.detection.r_out))
    ox, oy = sess.roi.x, sess.roi.y
    code = Path(a.sesion).stem.replace("VA_", "").replace("_analisis", "")
    key = ori.valid(getattr(sess.kin_params, "mirror", ori.NONE) if sess.kin_params is not None else ori.NONE)
    s_rot = ori.signs(key)[2]

    fig, axes = plt.subplots(3 * len(robots), len(times), figsize=(1.45 * len(times) + 1.2, 1.55 * 3 * len(robots)),
                             squeeze=False)
    labels = ("grabado", "θ anterior", "θ nuevo")
    with VideoReader(a.video) as reader:
        for ri, k in enumerate(robots):
            row0 = None
            for ci, tmin in enumerate(times):
                target = int(round(tmin * 60 * fps))
                r = _snap(kin.rot_status[:, k], min(target, len(res.frames) - 1)) if target < len(res.frames) else None
                if ci == 0:
                    row0 = r
                cells = [axes[3 * ri + j, ci] for j in range(3)]
                if r is None or row0 is None:
                    for c in cells:
                        c.axis("off")
                    continue
                frame = reader.read(int(res.frames[r]))
                if frame is None:
                    for c in cells:
                        c.axis("off")
                    continue
                cx, cy = res.x[r, k] + ox, res.y[r, k] + oy
                t_old = theta_old[r, k] - theta_old[row0, k]
                t_new = theta_new[r, k] - theta_new[row0, k]
                imgs = tuple(ori.image(_crop(frame, cx, cy, half, t), key) for t in (0.0, -t_old, -t_new))
                for j, (c, im) in enumerate(zip(cells, imgs)):
                    c.imshow(im, cmap="gray", vmin=0, vmax=255)
                    c.plot([half, half], [half - 0.95 * half, half - 0.55 * half], color="#e34948", lw=1.6)
                    c.set_xticks([]); c.set_yticks([])
                    for sp in c.spines.values():
                        sp.set_visible(False)
                    if j == 0:
                        c.set_title(f"{tmin:g} min", fontsize=8)
                    if j > 0:
                        c.text(0.5, -0.04, f"{s_rot * (t_old if j == 1 else t_new):+.0f}°", transform=c.transAxes,
                               ha="center", va="top", fontsize=7, color="#3f3f3c")
                    if ci == 0:
                        c.set_ylabel(f"robot {k}\n{labels[j]}" if j == 0 else labels[j], fontsize=8)
    fig.suptitle(f"{code}: robots desgirados por −θ (si θ es correcto, filas 2 y 3 quedan quietas); "
                 f"{ori.DESCRIPTION[key]}, θ > 0 antihorario", fontsize=10)
    fig.tight_layout(rect=(0, 0, 1, 0.97))
    out = Path(a.salida) if a.salida else Path(a.sesion).resolve().parents[1] / "verificacion" / f"giro_{code}.png"
    out.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out, dpi=150)
    print(f"Guardado: {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
