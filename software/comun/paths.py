"""Repository layout and trial (ensayo) discovery.

A trial is identified by its code AAAAMMDD_HHMM_XXYY_TT (see the root README). Every file of
the same trial shares that code with a different prefix: R_ raw sensor log, P_ processed log,
VC_/VR_ cropped/original video, VP_ robot trajectories exported by VidFetch.
"""

from __future__ import annotations

import json
import os
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

# --------------------------------------------------------------------------- repository root
# Source runs: software/comun/paths.py -> two levels up. Frozen apps (.exe): the repository is
# searched upwards from the executable, so an .exe built into software/empaquetado/dist/ (or
# copied anywhere inside the repository) finds its data. Override with the PRESION_REPO
# environment variable; a folder picked in the GUI is remembered in ~/.proyecto_presion.json.
ENV_VAR = "PRESION_REPO"
USER_CONFIG = Path.home() / ".proyecto_presion.json"
FROZEN = bool(getattr(sys, "frozen", False))


def is_repo(p: Path) -> bool:
    d = Path(p) / "datos"
    return (d / "presion").is_dir() or (d / "video").is_dir()


def _saved_root() -> Optional[Path]:
    try:
        v = json.loads(USER_CONFIG.read_text(encoding="utf-8")).get("repo")
        return Path(v) if v else None
    except (OSError, ValueError, AttributeError):
        return None


def _candidates():
    env = os.environ.get(ENV_VAR)
    if env:
        yield Path(env)
    here = Path(sys.executable).resolve().parent if FROZEN else Path(__file__).resolve().parent
    yield from (here, *here.parents)
    saved = _saved_root()
    if saved is not None:
        yield saved
    cwd = Path.cwd()
    yield from (cwd, *cwd.parents)


def locate_repo() -> Optional[Path]:
    for c in _candidates():
        try:
            if is_repo(c):
                return c.resolve()
        except OSError:
            continue
    return None


def set_repo_root(root: Path, remember: bool = False) -> None:
    """Point every data folder at `root`. Modules that copied a folder at import time (e.g.
    `from comun.paths import RAW_DIR`) keep the old value: GUI entry points call this before
    importing their windows."""
    global REPO_ROOT, REPO_FOUND, RAW_DIR, PROC_DIR, CONFIG_DIR, VIDEO_CROP_DIR, VIDEO_ORIG_DIR
    global TRAJ_DIR, CUTS_PATH
    REPO_ROOT = Path(root).resolve()
    REPO_FOUND = is_repo(REPO_ROOT)
    RAW_DIR = REPO_ROOT / "datos" / "presion" / "crudos"
    PROC_DIR = REPO_ROOT / "datos" / "presion" / "procesados"
    CONFIG_DIR = REPO_ROOT / "datos" / "presion" / "config"
    VIDEO_CROP_DIR = REPO_ROOT / "datos" / "video" / "recortados"
    VIDEO_ORIG_DIR = REPO_ROOT / "datos" / "video" / "originales"
    TRAJ_DIR = REPO_ROOT / "datos" / "video" / "trayectorias"
    CUTS_PATH = REPO_ROOT / "datos" / "video" / "cortes.json"      # gaps of split recordings
    if remember:
        try:
            USER_CONFIG.write_text(json.dumps({"repo": str(REPO_ROOT)}, ensure_ascii=False), encoding="utf-8")
        except OSError:
            pass


_found = locate_repo()
set_repo_root(_found or (Path(sys.executable).resolve().parent if FROZEN else Path(__file__).resolve().parents[2]))

CODE_RE = re.compile(r"^(?:R_)?(\d{8}_\d{4}_\d{2}[A-Z]{1,2}_\d{2})$", re.IGNORECASE)
RAW_EXTS = {".csv", ".json"}
EXCLUDE_DIRNAMES = {"procesado", "procesados", ".git", "$recycle.bin", "no procesar"}
VIDEO_EXTS = (".MP4", ".mp4", ".mov", ".MOV", ".avi", ".mkv")


@dataclass(frozen=True)
class Trial:
    code: str                     # AAAAMMDD_HHMM_XXYY_TT, or the file stem for uncoded logs
    raw_path: Path
    video_path: Optional[Path]    # VC_ preferred (lighter), VR_ as fallback
    traj_path: Optional[Path]

    @property
    def coded(self) -> bool:
        return CODE_RE.match(self.code) is not None

    @property
    def label(self) -> str:
        """Human-readable label: '24/09 16:00 · 22AH · 60 min'."""
        if not self.coded:
            return self.code
        date, hhmm, robots, minutes = self.code.split("_")
        month, day = date[4:6], date[6:8]
        return f"{day}/{month} {hhmm[:2]}:{hhmm[2:]} · {robots} · {minutes} min"


def extract_code(stem: str) -> Optional[str]:
    m = CODE_RE.match(stem.strip())
    return m.group(1) if m else None


def _first_existing(*candidates: Path) -> Optional[Path]:
    for c in candidates:
        if c.is_file():
            return c
    return None


def find_video(code: str) -> Optional[Path]:
    """VC_<code> (lighter) or VR_<code>; for a split recording, its first part (comun.cortes
    finds the others and the gap between them)."""
    cands = [VIDEO_CROP_DIR / f"VC_{code}{e}" for e in VIDEO_EXTS]
    cands += [VIDEO_ORIG_DIR / f"VR_{code}{e}" for e in VIDEO_EXTS]
    cands += [VIDEO_CROP_DIR / f"VC_{code}(1){e}" for e in VIDEO_EXTS]
    cands += [VIDEO_ORIG_DIR / f"VR_{code}(1){e}" for e in VIDEO_EXTS]
    return _first_existing(*cands)


def find_trajectories(code: str) -> Optional[Path]:
    """VP_<code>_robots.csv, or the first part of a split recording (VP_<code>(1)_robots.csv);
    comun.robots joins the parts."""
    single = _first_existing(TRAJ_DIR / f"VP_{code}_robots.csv")
    if single is not None or not TRAJ_DIR.is_dir():
        return single
    parts = sorted(TRAJ_DIR.glob(f"VP_{code}(*)_robots.csv"))
    return parts[0] if parts else None


def trial_from_path(path: Path) -> Trial:
    code = extract_code(path.stem) or path.stem
    coded = extract_code(path.stem) is not None
    return Trial(code, path, find_video(code) if coded else None,
                 find_trajectories(code) if coded else None)


def discover_trials(root: Optional[Path] = None) -> list[Trial]:
    """Recursive scan of `root` (default: datos/presion/crudos) for raw logs named with a valid
    trial code."""
    root = RAW_DIR if root is None else Path(root)
    out: list[Trial] = []
    if not root.is_dir():
        return out
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d.lower() not in EXCLUDE_DIRNAMES]
        for fn in filenames:
            p = Path(dirpath) / fn
            if p.suffix.lower() in RAW_EXTS and extract_code(p.stem):
                out.append(trial_from_path(p))
    return sorted(out, key=lambda t: t.code)


def processed_path(trial: Trial) -> Path:
    return PROC_DIR / f"P_{trial.code}.csv"


def config_path(trial: Trial) -> Path:
    return CONFIG_DIR / f"{trial.code}.json"


def code_label(code: str) -> str:
    """'20260924_1600_22AH_60' -> '24/09 16:00 · 22AH · 60 min' (code dates are AAAAMMDD)."""
    m = CODE_RE.match(code)
    if not m:
        return code
    date, hhmm, robots, minutes = m.group(1).split("_")
    return f"{date[6:8]}/{date[4:6]} {hhmm[:2]}:{hhmm[2:]} · {robots} · {minutes} min"
