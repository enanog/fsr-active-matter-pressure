"""Measure the unrecorded gap between the parts of a video that was cut while recording.

Usage (from the repository root, needs ffprobe in PATH):
    python software/analisis_video/medir_corte.py 20263010_1600_22QL_60

The DJI camera writes the start time of each file in the MP4 header (creation_time, 1 s
resolution) and the time-lapse frames are taken every 1/f_r s (f_r = 2.997, see below). For
parts (1) and (2) of one test:

    gap = start(2) - start(1) - (frames(1) - 1) / f_r      [first frame of (2) - last frame of (1)]

f_r is checked on every complete VR file of the folder: (file mtime - creation_time) must equal
frames / f_r within ~1 s (mtime = moment the camera closed the file). A part whose residual is
much larger was not closed normally (frames lost at its end).

Writes/updates datos/video/cortes.json, which comparar_modos.py reads.
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
VR_DIR = ROOT / "datos" / "video" / "originales"
OUT = ROOT / "datos" / "video" / "cortes.json"
FR_NOMINAL = 30000 / 1001 / 10          # DJI time-lapse: 29.97 fps playback, x10


def probe(path: Path) -> dict:
    cmd = ["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries",
           "stream=nb_frames:format_tags=creation_time", "-of", "json", str(path)]
    try:
        js = json.loads(subprocess.run(cmd, capture_output=True, text=True, check=True).stdout)
    except (OSError, subprocess.CalledProcessError, ValueError) as exc:
        sys.exit(f"ffprobe falló con {path.name}: {exc}")
    ct = js.get("format", {}).get("tags", {}).get("creation_time")
    if not ct:
        sys.exit(f"{path.name}: el MP4 no trae creation_time.")
    start = datetime.fromisoformat(ct.replace("Z", "+00:00")).timestamp()
    frames = int(js["streams"][0]["nb_frames"])
    return {"archivo": path.name, "creation_time": ct, "inicio_s": start, "cuadros": frames,
            "mtime_s": path.stat().st_mtime}


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("codigo", help="código del ensayo (sin '(1)')")
    ap.add_argument("--fr", type=float, default=FR_NOMINAL, help="cuadros por segundo real (def. 2.997)")
    a = ap.parse_args()

    parts = sorted(VR_DIR.glob(f"VR_{a.codigo}(*).MP4")) or sorted(VR_DIR.glob(f"VR_{a.codigo}(*).mp4"))
    if len(parts) < 2:
        sys.exit(f"No hay partes VR_{a.codigo}(n).MP4 en {VR_DIR}")
    P = [probe(p) for p in parts]

    # f_r check on the complete (single) files
    checks = []
    for p in sorted(VR_DIR.glob("VR_*.MP4")):
        if "(" in p.name:
            continue
        q = probe(p)
        checks.append({"archivo": p.name, "residuo_s": round(q["mtime_s"] - q["inicio_s"] - q["cuadros"] / a.fr, 2)})
    for q in P:
        q["residuo_cierre_s"] = round(q["mtime_s"] - q["inicio_s"] - q["cuadros"] / a.fr, 2)

    huecos = []
    for p1, p2 in zip(P, P[1:]):
        g = p2["inicio_s"] - p1["inicio_s"] - (p1["cuadros"] - 1) / a.fr
        huecos.append(round(g, 2))
        print(f"{p1['archivo']} -> {p2['archivo']}: hueco = {g:.2f} s (±1 s), "
              f"≈ {round(g * a.fr) - 1} cuadros sin grabar")
    for c in checks:
        print(f"  control f_r: {c['archivo']}: mtime - inicio - cuadros/f_r = {c['residuo_s']:+.2f} s")
    for q in P:
        print(f"  {q['archivo']}: residuo de cierre {q['residuo_cierre_s']:+.2f} s")

    data = json.loads(OUT.read_text(encoding="utf-8")) if OUT.exists() else {}
    data[a.codigo] = {
        "partes": [q["archivo"] for q in P],
        "cuadros_VR": [q["cuadros"] for q in P],
        "creation_time": [q["creation_time"] for q in P],
        "hueco_s": huecos,
        "incertidumbre_s": 1.0,
        "fr": a.fr,
        "residuo_cierre_s": [q["residuo_cierre_s"] for q in P],
        "control_fr": checks,
        "metodo": "creation_time del MP4 (inicio, 1 s de resolución) + cuadros/f_r; ver medir_corte.py",
        "medido": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }
    OUT.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"Guardado en {OUT}")


if __name__ == "__main__":
    main()
