"""Split recordings: a trial filmed in several files (VC_<code>(1).mp4, (2), ...) because the camera
stopped and started again. Finds the parts, measures the unrecorded gap between them and places
every part on one frame axis, so the video, the robot overlay and the pressure stay in sync.

Gap between part k and k+1 (first frame of k+1 minus last frame of k):

    gap = start(k+1) - start(k) - (frames(k) - 1) / f_r

start = creation time written by the DJI camera in the MP4 header (1 s resolution, read here from
the 'mvhd' box: no ffprobe needed), frames = frames of the ORIGINAL file VR_<code>(k) and
f_r = 2.997 real frames per second (time-lapse x10). The cropped VC_ files lose the creation time
and VC_(1) is trimmed at its start (sync LED), so the originals are required to measure; the
result is stored in datos/video/cortes.json and reused afterwards (also by Velocidades, MATLAB
and comparar_modos.py).

Frame axis (same rule as comun.robots): part k+1 starts at
    start_frame(k+1) = start_frame(k) + frames_VC(k) - 1 + round(gap * f_r)
"""

from __future__ import annotations

import json
import re
import struct
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from comun import paths

FR_DJI = 30000 / 1001 / 10               # DJI time-lapse: 29.97 fps playback, x10 -> 2.997 real fps
GAP_UNCERTAINTY_S = 1.0                  # creation time has 1 s resolution
_MP4_EPOCH = datetime(1904, 1, 1, tzinfo=timezone.utc).timestamp()
_PART_RE = re.compile(r"\((\d+)\)$")


@dataclass
class SplitInfo:
    """Parts of one trial and where each starts on the common frame axis."""
    code: str
    parts: list[Path]                    # files actually played (VC_ preferred)
    frames: list[int]                    # frames of each part
    gaps_s: list[float]                  # len(parts) - 1
    fr: float
    source: str                          # "cortes.json" | "medido ahora" | "manual" | "sin medir"
    notes: list[str] = field(default_factory=list)

    @property
    def split(self) -> bool:
        return len(self.parts) > 1

    @property
    def measured(self) -> bool:
        return len(self.gaps_s) >= len(self.parts) - 1

    @property
    def starts(self) -> list[int]:
        return part_starts(self.frames, self.gaps_s, self.fr)

    def describe(self) -> str:
        if not self.split:
            return ""
        txt = f"Video partido en {len(self.parts)} partes (" + ", ".join(
            f"{p.name}: {n} cuadros" for p, n in zip(self.parts, self.frames)) + "). "
        if self.measured:
            txt += "Hueco " + "; ".join(f"{g:.1f} s ≈ {round(g * self.fr) - 1} cuadros sin grabar"
                                       for g in self.gaps_s)
            txt += f" ({self.source}"
            txt += f", ±{GAP_UNCERTAINTY_S:g} s)." if self.source != "manual" else ")."
        else:
            txt += "Hueco sin medir: faltan los originales VR_ (con la hora de inicio) y no figura en cortes.json."
        if self.notes:
            txt += " " + " ".join(self.notes)
        return txt


# =============================================================================================
# files
# =============================================================================================
def _parts_in(folder: Path, prefix: str, code: str) -> list[Path]:
    if not folder.is_dir():
        return []
    found = {}
    for p in folder.iterdir():
        if p.suffix in paths.VIDEO_EXTS and p.stem.startswith(f"{prefix}_{code}("):
            m = _PART_RE.search(p.stem)
            if m and p.stem == f"{prefix}_{code}({m.group(1)})":
                found[int(m.group(1))] = p
    return [found[k] for k in sorted(found)]


def sibling_parts(path: Path) -> list[Path]:
    """All parts of the split video `path` belongs to, in its own folder (any prefix: VC_, VR_ or the
    annotated VS_ of VidFetch): '.../VS_<code>(1).mp4' -> [VS_<code>(1), VS_<code>(2), ...]. [] if `path`
    is not a part '(n)'."""
    path = Path(path)
    m = _PART_RE.search(path.stem)
    if not m:
        return []
    base = path.stem[:m.start()]
    found = {}
    for p in path.parent.iterdir():
        if p.suffix in paths.VIDEO_EXTS and p.stem.startswith(base + "("):
            mm = _PART_RE.search(p.stem)
            if mm and p.stem == f"{base}({mm.group(1)})":
                found[int(mm.group(1))] = p
    return [found[k] for k in sorted(found)]


def video_parts(code: str) -> list[Path]:
    """VC_<code>(1..n) if present, else VR_<code>(1..n); [] if the trial is not split."""
    return _parts_in(paths.VIDEO_CROP_DIR, "VC", code) or _parts_in(paths.VIDEO_ORIG_DIR, "VR", code)


def original_parts(code: str) -> list[Path]:
    return _parts_in(paths.VIDEO_ORIG_DIR, "VR", code)


def frame_count(path: Path) -> int:
    import cv2
    cap = cv2.VideoCapture(str(path))
    try:
        return int(cap.get(cv2.CAP_PROP_FRAME_COUNT)) if cap.isOpened() else 0
    finally:
        cap.release()


def mp4_creation_time(path: Path) -> Optional[float]:
    """Creation time [Unix s] from the 'moov/mvhd' box of an MP4/MOV, or None (0 = not set)."""
    try:
        with open(path, "rb") as f:
            size = f.seek(0, 2)
            pos = 0
            while pos + 8 <= size:                       # top-level boxes
                f.seek(pos)
                n, kind = struct.unpack(">I4s", f.read(8))
                head = 8
                if n == 1:
                    n = struct.unpack(">Q", f.read(8))[0]
                    head = 16
                elif n == 0:
                    n = size - pos
                if n < head:
                    return None
                if kind == b"moov":
                    end, p = pos + n, pos + head
                    while p + 8 <= end:                  # boxes inside moov
                        f.seek(p)
                        m, sub = struct.unpack(">I4s", f.read(8))
                        if m < 8:
                            return None
                        if sub == b"mvhd":
                            version = f.read(1)[0]
                            f.read(3)
                            t = struct.unpack(">Q" if version == 1 else ">I", f.read(8 if version == 1 else 4))[0]
                            return _MP4_EPOCH + t if t > 0 else None
                        p += m
                    return None
                pos += n
    except (OSError, struct.error, IndexError):
        return None
    return None


# =============================================================================================
# cortes.json
# =============================================================================================
def load_cuts() -> dict:
    try:
        return json.loads(paths.CUTS_PATH.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def save_cut(code: str, entry: dict) -> None:
    data = load_cuts()
    data[code] = entry
    paths.CUTS_PATH.parent.mkdir(parents=True, exist_ok=True)
    paths.CUTS_PATH.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")


def measure(code: str, fr: float = FR_DJI) -> tuple[Optional[dict], str]:
    """Gap(s) from the original files' creation time. Returns (cortes.json entry, message); the
    entry is None when it cannot be measured."""
    orig = original_parts(code)
    if len(orig) < 2:
        return None, f"no están los originales VR_{code}(n) en {paths.VIDEO_ORIG_DIR}"
    starts, frames = [], []
    for p in orig:
        t = mp4_creation_time(p)
        if t is None:
            return None, f"{p.name} no trae la hora de inicio en el encabezado MP4"
        starts.append(t)
        frames.append(frame_count(p))
    if min(frames) <= 0:
        return None, "no se pudo contar los cuadros de los originales"
    gaps = [round(s2 - s1 - (n1 - 1) / fr, 2) for s1, s2, n1 in zip(starts, starts[1:], frames)]
    if min(gaps) < -GAP_UNCERTAINTY_S:
        return None, (f"hueco negativo ({min(gaps):.1f} s): las horas de inicio de los archivos no son "
                      "consistentes (¿se cambió el reloj de la cámara?)")
    closing = []
    for p, t, n in zip(orig, starts, frames):
        closing.append(round(p.stat().st_mtime - t - n / fr, 2))   # ~0 if the camera closed it normally
    entry = {
        "partes": [p.name for p in orig],
        "cuadros_VR": frames,
        "creation_time": [datetime.fromtimestamp(t, timezone.utc).isoformat(timespec="seconds") for t in starts],
        "hueco_s": [max(g, 0.0) for g in gaps],
        "incertidumbre_s": GAP_UNCERTAINTY_S,
        "fr": fr,
        "residuo_cierre_s": closing,
        "metodo": "creation_time del MP4 (inicio, 1 s de resolución) + cuadros/f_r (comun/cortes.py)",
        "medido": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }
    return entry, "medido de los originales"


def split_info(code: str, manual_gaps: Optional[list] = None, remeasure: bool = False,
               save: bool = True, parts: Optional[list] = None) -> SplitInfo:
    """Parts, frames and gaps of a trial. Priority: manual gaps (if given) > cortes.json > measured
    now from the originals (saved to cortes.json when save=True). `parts`: the files to play
    (default VC_<code>(n), else VR_<code>(n)); e.g. the annotated VS_ parts chosen by hand."""
    parts = [Path(p) for p in parts] if parts else video_parts(code)
    if len(parts) < 2:
        return SplitInfo(code, parts, [frame_count(p) for p in parts], [], FR_DJI, "")
    frames = [frame_count(p) for p in parts]
    notes: list[str] = []
    cut = load_cuts().get(code, {})
    fr = float(cut.get("fr") or FR_DJI)
    gaps, source = [], "sin medir"
    if manual_gaps:
        gaps, source = [float(g) for g in manual_gaps], "manual"
    elif cut.get("hueco_s") and not remeasure:
        gaps, source = [float(g) for g in cut["hueco_s"]], "cortes.json"
    else:
        entry, msg = measure(code, fr)
        if entry is not None:
            gaps, source = entry["hueco_s"], "medido ahora de los originales"
            if save:
                save_cut(code, entry)
                source += ", guardado en cortes.json"
            cut = entry
        else:
            notes.append(f"No se pudo medir: {msg}.")
            if cut.get("hueco_s"):
                gaps, source = [float(g) for g in cut["hueco_s"]], "cortes.json"
    # cropped / annotated parts must keep the original length except the start of part 1 (sync trim)
    vr = cut.get("cuadros_VR") or []
    if not parts[0].name.startswith("VR_") and len(vr) == len(parts):
        for k, (nvc, nvr) in enumerate(zip(frames, vr), 1):
            if k > 1 and nvc != nvr:
                notes.append(f"Atención: la parte {k} tiene {nvc} cuadros y el original {nvr}: si se recortó, "
                             f"el desfase puede estar corrido hasta {abs(nvr - nvc)} cuadros.")
        if frames[0] < vr[0]:
            notes.append(f"Parte 1 recortada al inicio ({vr[0] - frames[0]} cuadros, el pulso LED): no afecta el hueco.")
    closing = cut.get("residuo_cierre_s") or []
    for k, r in enumerate(closing[:-1], 1):
        if r > 5:
            notes.append(f"La parte {k} se cerró de forma anormal (~{r:.0f} s finales perdidos): ya incluidos en el hueco.")
    return SplitInfo(code, parts, frames, gaps, fr, source, notes)


def part_starts(frames: list[int], gaps_s: list[float], fr: float) -> list[int]:
    """Global frame where each part starts (part 1 at 0). Missing gaps count as 0 s (parts butted
    together: only for showing a trial whose gap is still unknown)."""
    gaps = list(gaps_s) + [0.0] * max(0, len(frames) - 1 - len(gaps_s))
    starts = [0]
    for n, g in zip(frames[:-1], gaps):
        starts.append(starts[-1] + n - 1 + max(1, int(round(g * fr))))
    return starts
