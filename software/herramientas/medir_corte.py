"""Measure the unrecorded gap between the parts of a video that was cut while recording and store it
in datos/video/cortes.json (FSRScope and Velocidades also do it on their own when it is missing).

    python software/herramientas/medir_corte.py 20261030_1600_22AH_60
    python software/herramientas/medir_corte.py            # every split trial found

Method (comun/cortes.py): the DJI camera writes the start time of each file in the MP4 header
(creation_time, 1 s resolution) and the time-lapse frames are taken every 1/f_r s (f_r = 2.997):

    gap = start(k+1) - start(k) - (frames(k) - 1) / f_r     [first frame of k+1 - last frame of k]

The original files VR_<code>(k) are needed (the cropped VC_ lose the start time). Also prints, for
every complete VR file, mtime - start - frames/f_r (~0 when the camera closed the file normally),
as a check of f_r; a part with a much larger residual lost frames at its end (already in the gap).
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))   # software/: comun, vidfetch, ...
from comun import cortes, paths  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("codigos", nargs="*", help="código(s) del ensayo (sin '(1)'); vacío = todos los partidos")
    ap.add_argument("--fr", type=float, default=cortes.FR_DJI, help="cuadros por segundo real (def. 2.997)")
    a = ap.parse_args()

    codes = a.codigos or sorted({re.sub(r"\(\d+\)$", "", p.stem)[3:]
                                 for p in paths.VIDEO_ORIG_DIR.glob("VR_*(*).*")})
    if not codes:
        print(f"No hay videos partidos (VR_<código>(n)) en {paths.VIDEO_ORIG_DIR}")
        return 1
    ok = 0
    for code in codes:
        entry, msg = cortes.measure(code, a.fr)
        if entry is None:
            print(f"{code}: no se pudo medir: {msg}")
            continue
        cortes.save_cut(code, entry)
        ok += 1
        for (p1, p2), g in zip(zip(entry["partes"], entry["partes"][1:]), entry["hueco_s"]):
            print(f"{p1} -> {p2}: hueco = {g:.2f} s (±1 s), ≈ {round(g * a.fr) - 1} cuadros sin grabar")
        for p, r in zip(entry["partes"], entry["residuo_cierre_s"]):
            print(f"  {p}: residuo de cierre {r:+.2f} s")
    for p in sorted(paths.VIDEO_ORIG_DIR.glob("VR_*.*")):
        if "(" in p.stem or p.suffix not in paths.VIDEO_EXTS:
            continue
        t = cortes.mp4_creation_time(p)
        if t is not None:
            print(f"  control f_r: {p.name}: mtime - inicio - cuadros/f_r = "
                  f"{p.stat().st_mtime - t - cortes.frame_count(p) / a.fr:+.2f} s")
    print(f"{ok} medido(s); guardado en {paths.CUTS_PATH}")
    return 0 if ok == len(codes) else 2


if __name__ == "__main__":
    sys.exit(main())
