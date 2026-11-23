"""Re-analyse a saved session with the battery-edge detector, without the GUI.

    python -m vidfetch.reanalizar datos/video/sesiones/VA_<código>.npz [--salida OTRA.npz] [--procesos 4]

Keeps the session's video, crop, trim, enclosure and kinematics settings, and redoes:
  1. candidates with detection method 'edge' (battery edge, sub-pixel centre), in parallel;
  2. tracking (N from the session, max gap 30, interpolation on);
  3. second look (core.second_look) at the frames not cleanly detected, and tracking again;
  4. two passes of core.second_look.despike (one-to-three-frame jumps measured again near the track).
Manual corrections are dropped (robot numbers can change); --mantener-correcciones keeps them.
Overwrites the session unless --salida is given; the old file is kept as <name>_antes.npz.
"""
from __future__ import annotations

import argparse
import os
import shutil
import sys
import time
from dataclasses import replace
from multiprocessing import Pool

import numpy as np

from vidfetch.core import detection as det
from vidfetch.core import tracking as trk
from vidfetch.core.analysis import FrameProcessor
from vidfetch.core.calibration import derive_tracker_values
from vidfetch.core.models import TrimRange
from vidfetch.core.second_look import despike, second_look

_JOB: dict = {}


def _extract(ab):
    a, b = ab
    c, fps, _, _ = trk.extract_candidates(_JOB["src"], TrimRange(a, b), _JOB["roi"],
                                          FrameProcessor(detection=_JOB["det"]))
    return c, fps


def _init(src, roi, d):
    _JOB.update(src=src, roi=roi, det=d)


def _counts(r: trk.TrackingResult) -> str:
    s = r.status
    return (f"detectados {int((s == trk.Status.DETECTED).sum())}, relajados {int((s == trk.Status.RELAXED).sum())}, "
            f"interpolados {int((s == trk.Status.INTERPOLATED).sum())}, predichos/perdidos {int((s >= trk.Status.PREDICTED).sum())} "
            f"(cuadros con error {int((s >= trk.Status.PREDICTED).any(1).sum())})")


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("sesion")
    ap.add_argument("--video", help="video si se movió (por defecto el guardado en la sesión)")
    ap.add_argument("--salida", help="archivo de sesión de salida (por defecto sobrescribe)")
    ap.add_argument("--procesos", type=int, default=max(1, min(8, (os.cpu_count() or 2))))
    ap.add_argument("--mantener-correcciones", action="store_true")
    a = ap.parse_args(argv)

    s0 = trk.TrackingSession.load(a.sesion)
    src = a.video or s0.src_path
    if not os.path.isfile(src):
        print(f"No encuentro el video {src}; pasalo con --video.", file=sys.stderr)
        return 1
    d = replace(s0.detection, enabled=True, method=det.METHOD_EDGE, validate_ring=True,
                min_coverage=max(s0.detection.min_coverage, 0.82))
    t0 = time.time()
    a0, b0 = s0.trim.start, s0.trim.end
    n = max(1, a.procesos)
    cuts = np.linspace(a0, b0 + 1, n + 1).round().astype(int)
    parts = [(int(cuts[i]), int(cuts[i + 1]) - 1) for i in range(n) if cuts[i + 1] - 1 >= cuts[i]]
    print(f"Candidatos (borde de pila) en {len(parts)} procesos, cuadros {a0}–{b0}…", flush=True)
    with Pool(len(parts), initializer=_init, initargs=(src, s0.roi, d)) as pool:
        res = pool.map(_extract, parts)
    cs = res[0][0]
    for c, _ in res[1:]:
        cs = trk.CandidateSet(np.concatenate([cs.frames, c.frames]), cs.xy + c.xy, cs.mass + c.mass,
                              cs.cov + c.cov, (cs.sig + c.sig) if cs.sig is not None else None)
    print(f"  {len(cs.frames)} cuadros, {np.mean([len(x) for x in cs.xy]):.1f} candidatos por cuadro "
          f"({time.time() - t0:.0f} s)", flush=True)

    tv = derive_tracker_values(d.r_out)
    params = replace(s0.params, search_range=tv["search_range"], gap_growth=tv["gap_growth"],
                     min_separation=round(0.8 * d.separation, 2), max_gap=max(30, s0.params.max_gap),
                     interpolate=True)
    anchors = dict(s0.anchors) if a.mantener_correcciones else {}
    r1 = trk.track(cs, params, anchors)
    print("Seguimiento:", _counts(r1), flush=True)
    cs2, cnt = second_look(cs, r1, src, s0.roi, d)
    r2 = trk.track(cs2, params, anchors)
    print(f"Segunda mirada: {cnt['replaced']} recentrados, {cnt['added']} agregados, {cnt['rejected']} sin borde claro")
    for _ in range(2):
        cs2, cnt = despike(cs2, r2, src, s0.roi, d)
        r2 = trk.track(cs2, params, anchors)
        print(f"Saltos de 1-3 cuadros remedidos: {cnt['fixed']}")
    print("Seguimiento final:", _counts(r2), flush=True)

    s1 = trk.TrackingSession(src_path=src, roi=s0.roi, trim=s0.trim, fps=s0.fps, detection=d, candidates=cs2,
                             params=params, anchors=anchors, kin_params=s0.kin_params, arena=s0.arena)
    s1.result = r2
    out = a.salida or a.sesion
    if os.path.abspath(out) == os.path.abspath(a.sesion):
        shutil.copy2(a.sesion, os.path.splitext(a.sesion)[0] + "_antes.npz")
    s1.save(out)
    print(f"Guardado {out} ({time.time() - t0:.0f} s en total)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
