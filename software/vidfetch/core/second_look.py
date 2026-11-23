"""Second look at the frames where a robot was not cleanly detected.

After tracking, every robot-frame that is relaxed, interpolated or predicted is measured again on the
full-resolution frame with the battery-edge refinement (detection.refine_edge), searching +-8 px around
the tracked position: q = 0.4 first, then q = 0.6 for batteries whose edge is visible on only part of
the rim. An accepted centre replaces the candidate the tracker had used (relaxed) or is added to the
cache (gap), with its rotation signature; unassigned strays on the same robot are dropped. Tracking the
updated cache again turns those frames into detections. Only near a robot the tracker already follows,
so the permissive q never creates robots in gaps.

despike(): a robot cannot jump away for one or two frames and come back. Positions farther than
0.08 r_out (4 px at r_out = 50 px) from the running median of their own track (7 frames) are measured
again with the search limited to +-0.06 r_out around that median; the constrained centre replaces the
candidate when its edge score is at least 80 % of the free one (a bright tab or a dull battery rim had
pulled the free fit off-centre).
"""
from __future__ import annotations

import copy
from typing import Callable, Optional

import cv2
import numpy as np
from scipy.ndimage import median_filter

from vidfetch.core import detection as det
from vidfetch.core import rotation
from vidfetch.core.tracking import CandidateSet, Status, TrackingResult


def second_look(cands: CandidateSet, result: TrackingResult, src_path: str, roi, p: det.DetectionParams,
                progress: Optional[Callable[[int], None]] = None) -> tuple[CandidateSet, dict]:
    """Returns (updated copy of `cands`, counts). `result` must come from tracking `cands`."""
    need = np.argwhere((result.status >= Status.RELAXED) & (result.status != Status.MANUAL))
    by_row: dict[int, list[int]] = {}
    for i, k in need:
        by_row.setdefault(int(i), []).append(int(k))
    out = copy.deepcopy(cands)
    cand_idx = None if result.cand_idx is None else result.cand_idx.copy()
    counts = {"replaced": 0, "added": 0, "rejected": 0}
    if not by_row:
        return out, counts
    cap = cv2.VideoCapture(src_path)
    sep, ox, oy = p.separation, float(roi.x), float(roi.y)
    rows = sorted(by_row)
    try:
        for n, i in enumerate(rows):
            cap.set(cv2.CAP_PROP_POS_FRAMES, int(cands.frames[i]))
            ok, frame = cap.read()
            if not ok:
                continue
            gray = cv2.cvtColor(frame[roi.y:roi.y + roi.h, roi.x:roi.x + roi.w], cv2.COLOR_BGR2GRAY)
            g = cv2.GaussianBlur(gray.astype(np.float32), (0, 0), max(0.6, p.r_out / 50.0))
            gs = gray if p.scale == 1.0 else cv2.resize(gray, None, fx=p.scale, fy=p.scale,
                                                        interpolation=cv2.INTER_AREA)
            for k in by_row[i]:
                x0, y0 = result.x[i, k] - ox, result.y[i, k] - oy
                x, y, _, sc = det.refine_edge(g, x0, y0, p.r_out, search=8.0 * max(0.5, p.r_out / 50.0))
                if sc < p.edge_min:
                    x, y, _, sc = det.refine_edge(g, x0, y0, p.r_out, search=8.0 * max(0.5, p.r_out / 50.0),
                                                  q=0.6)
                if sc < p.edge_min:
                    counts["rejected"] += 1
                    continue
                ex = out.xy[i] - [ox, oy]
                assigned = set() if cand_idx is None else {int(j) for j in cand_idx[i] if j >= 0}
                j_own = int(cand_idx[i, k]) if (cand_idx is not None and result.status[i, k] == Status.RELAXED) else -1
                dist = np.hypot(ex[:, 0] - x, ex[:, 1] - y) if len(ex) else np.zeros(0)
                if any(dist[j] < 0.8 * sep for j in assigned if j != j_own):
                    counts["rejected"] += 1          # it is another robot's position
                    continue
                sig = rotation.signatures(gs, np.array([x * p.scale]), np.array([y * p.scale]), p.r_out * p.scale)
                cov = float(np.clip(sc / (1.6 * p.edge_min), 0.0, 1.0))
                if j_own >= 0:
                    out.xy[i][j_own] = (x + ox, y + oy)
                    out.mass[i][j_own], out.cov[i][j_own] = sc, cov
                    if out.sig is not None:
                        out.sig[i][j_own] = sig[0]
                    counts["replaced"] += 1
                    continue
                stray = np.array([(j not in assigned) and dist[j] < 0.5 * sep for j in range(len(ex))], bool)
                if stray.any():
                    keep = ~stray
                    remap = np.cumsum(keep) - 1
                    out.xy[i], out.mass[i], out.cov[i] = out.xy[i][keep], out.mass[i][keep], out.cov[i][keep]
                    if out.sig is not None:
                        out.sig[i] = out.sig[i][keep]
                    if cand_idx is not None:
                        ci = cand_idx[i]
                        cand_idx[i] = np.where(ci >= 0, remap[np.maximum(ci, 0)], -1)
                out.xy[i] = np.vstack([out.xy[i], [[x + ox, y + oy]]])
                out.mass[i] = np.append(out.mass[i], sc)
                out.cov[i] = np.append(out.cov[i], cov)
                if out.sig is not None:
                    out.sig[i] = np.concatenate([out.sig[i], sig])
                counts["added"] += 1
            if progress is not None:
                progress(int(100 * (n + 1) / len(rows)))
    finally:
        cap.release()
    return out, counts


def despike(cands: CandidateSet, result: TrackingResult, src_path: str, roi, p: det.DetectionParams,
            progress: Optional[Callable[[int], None]] = None) -> tuple[CandidateSet, dict]:
    """Returns (updated copy of `cands`, counts). `result` must come from tracking `cands`."""
    out = copy.deepcopy(cands)
    counts = {"fixed": 0, "kept": 0}
    if result.cand_idx is None or len(result.frames) < 7:
        return out, counts
    mx = median_filter(result.x, size=(7, 1), mode="nearest")
    my = median_filter(result.y, size=(7, 1), mode="nearest")
    obs = (result.status == Status.DETECTED) | (result.status == Status.RELAXED)
    bad = obs & (np.hypot(result.x - mx, result.y - my) > 0.08 * p.r_out) & (result.cand_idx >= 0)
    rows = np.unique(np.nonzero(bad)[0])
    if len(rows) == 0:
        return out, counts
    cap = cv2.VideoCapture(src_path)
    ox, oy = float(roi.x), float(roi.y)
    search = max(1.0, 0.06 * p.r_out)
    try:
        for n, i in enumerate(rows):
            cap.set(cv2.CAP_PROP_POS_FRAMES, int(cands.frames[i]))
            ok, frame = cap.read()
            if not ok:
                continue
            gray = cv2.cvtColor(frame[roi.y:roi.y + roi.h, roi.x:roi.x + roi.w], cv2.COLOR_BGR2GRAY)
            g = cv2.GaussianBlur(gray.astype(np.float32), (0, 0), max(0.6, p.r_out / 50.0))
            gs = gray if p.scale == 1.0 else cv2.resize(gray, None, fx=p.scale, fy=p.scale,
                                                        interpolation=cv2.INTER_AREA)
            for k in np.flatnonzero(bad[i]):
                j = int(result.cand_idx[i, k])
                x, y, _, sc = det.refine_edge(g, mx[i, k] - ox, my[i, k] - oy, p.r_out, search=search)
                if sc < 0.8 * float(out.mass[i][j]):
                    counts["kept"] += 1
                    continue
                out.xy[i][j] = (x + ox, y + oy)
                out.mass[i][j] = sc
                out.cov[i][j] = float(np.clip(sc / (1.6 * p.edge_min), 0.0, 1.0))
                if out.sig is not None:
                    out.sig[i][j] = rotation.signatures(gs, np.array([x * p.scale]), np.array([y * p.scale]),
                                                        p.r_out * p.scale)[0]
                counts["fixed"] += 1
            if progress is not None:
                progress(int(100 * (n + 1) / len(rows)))
    finally:
        cap.release()
    return out, counts
