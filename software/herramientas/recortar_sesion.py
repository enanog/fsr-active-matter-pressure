"""Cut a saved VidFetch analysis (.npz) to a frame range without re-reading the video.

Use it when the video has a cut (frames missing in the middle) or a stretch that should not be
analysed: tracking, rotation and velocities are recomputed only with the frames kept, so nothing
after a cut leaks into the derivatives or into the global rotation solver.

Usage (from the repository root):
    python software/herramientas/recortar_sesion.py raro/hyperlapse_final_recorte_analisis.npz --hasta 11198
    python software/herramientas/recortar_sesion.py <sesion.npz> --desde 11199 --salida <otra.npz>

Writes <sesion>_<desde>-<hasta>.npz (or --salida) with the candidates, corrections and enclosure of
the range and the rotation already solved (opens in seconds). The input file is not modified.
"""
from __future__ import annotations

import argparse
import sys
import time
from dataclasses import replace
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))

from vidfetch.core.models import TrimRange          # noqa: E402
from vidfetch.core.tracking import CandidateSet, TrackingSession   # noqa: E402


def cut(s: TrackingSession, a: int, b: int) -> TrackingSession:
    c = s.candidates
    keep = [i for i, f in enumerate(c.frames) if a <= int(f) <= b]
    if not keep:
        raise ValueError(f"No hay cuadros analizados entre {a} y {b}.")
    sub = CandidateSet(c.frames[keep].copy(), [c.xy[i] for i in keep], [c.mass[i] for i in keep],
                       [c.cov[i] for i in keep], None if c.sig is None else [c.sig[i] for i in keep])
    lo, hi = int(sub.frames[0]), int(sub.frames[-1])
    anchors = {k: v for k, v in s.anchors.items() if lo <= k[0] <= hi}
    return replace(s, candidates=sub, anchors=anchors, trim=TrimRange(lo, hi), result=None, kin=None,
                   applied_anchors={})


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("sesion", type=Path)
    ap.add_argument("--desde", type=int, default=None, help="primer cuadro que se conserva (def.: el primero)")
    ap.add_argument("--hasta", type=int, default=None, help="último cuadro que se conserva (def.: el último)")
    ap.add_argument("--salida", type=Path, default=None)
    ap.add_argument("--sin-giro", action="store_true", help="no resolver θ ahora (se calcula al abrir Resultados)")
    args = ap.parse_args()

    s = TrackingSession.load(str(args.sesion))
    f = s.candidates.frames
    a = int(f[0]) if args.desde is None else args.desde
    b = int(f[-1]) if args.hasta is None else args.hasta
    t = time.time()
    sub = cut(s, a, b)
    dropped = len(s.anchors) - len(sub.anchors)
    sub.run(kinematics=not args.sin_giro)
    out = args.salida or args.sesion.with_name(f"{args.sesion.stem}_{sub.trim.start}-{sub.trim.end}.npz")
    if out.resolve() == args.sesion.resolve():
        raise SystemExit("La salida no puede ser el mismo archivo de entrada.")
    sub.save(str(out))
    sm = sub.result.summary()
    print(f"Cuadros {sub.trim.start}–{sub.trim.end} ({len(sub.candidates.frames)}) · correcciones "
          f"{len(sub.anchors)} (fuera del tramo: {dropped}) · cuadros con error {sm['frames_error']}, "
          f"con advertencia {sm['frames_warning']} · {time.time() - t:.0f} s\n→ {out}")


if __name__ == "__main__":
    main()
