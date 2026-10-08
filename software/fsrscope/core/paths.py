"""Repository layout and trial (ensayo) discovery.

A trial is identified by its code AAAADDMM_HHMM_XXYY_TT (see the root README). Every file of
the same trial shares that code with a different prefix: R_ raw sensor log, P_ processed log,
VC_/VR_ cropped/original video, VP_ robot trajectories exported by VidFetch.
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

# This file lives in software/fsrscope/core/ -> repository root is three levels up.
REPO_ROOT = Path(__file__).resolve().parents[3]

RAW_DIR = REPO_ROOT / "datos" / "presion" / "crudos"
PROC_DIR = REPO_ROOT / "datos" / "presion" / "procesados"
CONFIG_DIR = REPO_ROOT / "datos" / "presion" / "config"
VIDEO_CROP_DIR = REPO_ROOT / "datos" / "video" / "recortados"
VIDEO_ORIG_DIR = REPO_ROOT / "datos" / "video" / "originales"
TRAJ_DIR = REPO_ROOT / "datos" / "video" / "trayectorias"

CODE_RE = re.compile(r"^(?:R_)?(\d{8}_\d{4}_\d{2}[A-Z]{1,2}_\d{2})$", re.IGNORECASE)
RAW_EXTS = {".csv", ".json"}
EXCLUDE_DIRNAMES = {"procesado", "procesados", ".git", "$recycle.bin", "no procesar"}
VIDEO_EXTS = (".MP4", ".mp4", ".mov", ".MOV", ".avi", ".mkv")


@dataclass(frozen=True)
class Trial:
    code: str                     # AAAADDMM_HHMM_XXYY_TT, or the file stem for uncoded logs
    raw_path: Path
    video_path: Optional[Path]    # VC_ preferred (lighter), VR_ as fallback
    traj_path: Optional[Path]

    @property
    def coded(self) -> bool:
        return CODE_RE.match(self.code) is not None

    @property
    def label(self) -> str:
        """Human-readable label: '24/09 16:00 · 22QR · 60 min'."""
        if not self.coded:
            return self.code
        date, hhmm, robots, minutes = self.code.split("_")
        a, b = date[4:6], date[6:8]
        # Older logs use AAAAMMDD, current ones AAAADDMM: pick the reading that is a valid month.
        day, month = (b, a) if int(a) <= 12 < int(b) else (a, b)
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
    cands = [VIDEO_CROP_DIR / f"VC_{code}{e}" for e in VIDEO_EXTS]
    cands += [VIDEO_ORIG_DIR / f"VR_{code}{e}" for e in VIDEO_EXTS]
    return _first_existing(*cands)


def find_trajectories(code: str) -> Optional[Path]:
    return _first_existing(TRAJ_DIR / f"VP_{code}_robots.csv")


def trial_from_path(path: Path) -> Trial:
    code = extract_code(path.stem) or path.stem
    coded = extract_code(path.stem) is not None
    return Trial(code, path, find_video(code) if coded else None,
                 find_trajectories(code) if coded else None)


def discover_trials(root: Path = RAW_DIR) -> list[Trial]:
    """Recursive scan of `root` for raw logs named with a valid trial code."""
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
