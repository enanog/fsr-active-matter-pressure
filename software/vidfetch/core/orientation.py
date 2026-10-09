"""Orientation of the recorded image with respect to the scene as the experimenter sees it.

The analysis (detection, tracking, rotation) always runs on the file pixels, so that it does not
depend on this choice. The orientation only decides how the scene is SHOWN (tracking view, exported
video, report figures) and in which frame positions and angles are EXPORTED:

  key          image -> displayed scene       sx  sy  angles   use
  no           unchanged                      +1  +1   +1      camera image = view of the observer
  rot180       rotated 180 deg                -1  -1   +1      observer standing at the TOP edge of
                                                               the video, looking towards its bottom
                                                               (fixed overhead camera of this project)
  horizontal   flipped about the vertical     -1  +1   -1      mirrored recording
  vertical     flipped about the horizontal   +1  -1   -1      mirrored recording

sx, sy act on image axes (x right, y DOWN). The export frame is the displayed scene with x to the
right and y UP (away from the observer), origin at the enclosure centre:
    x = s * sx * (X - Xc),     y = -s * sy * (Y - Yc)
A rotation keeps the handedness (counter-clockwise stays counter-clockwise); a mirror reverses it,
which is why angles and angular velocities are multiplied by the last column.
All four transforms are involutions: the same function maps image -> display and display -> image.
"""
from __future__ import annotations

from typing import Optional

import cv2
import numpy as np

NONE, ROT180, MIRROR_H, MIRROR_V = "no", "rot180", "horizontal", "vertical"
LABELS = {
    ROT180: "Rotada 180° (observador en el borde superior del video)",
    NONE: "Como la graba la cámara",
    MIRROR_H: "Espejada horizontal (respecto del eje y)",
    MIRROR_V: "Espejada vertical (respecto del eje x)",
}
_SIGNS = {NONE: (1.0, 1.0, 1.0), ROT180: (-1.0, -1.0, 1.0),
          MIRROR_H: (-1.0, 1.0, -1.0), MIRROR_V: (1.0, -1.0, -1.0)}
DESCRIPTION = {
    NONE: "imagen tal como la graba la cámara",
    ROT180: "imagen rotada 180° (vista del observador)",
    MIRROR_H: "video espejado corregido (horizontal)",
    MIRROR_V: "video espejado corregido (vertical)",
}


def valid(key: Optional[str]) -> str:
    return key if key in _SIGNS else NONE


def signs(key: Optional[str]) -> tuple[float, float, float]:
    """(sx, sy, s_rot): image-axis flips and the factor for angles / angular velocities."""
    return _SIGNS[valid(key)]


def is_identity(key: Optional[str]) -> bool:
    return valid(key) == NONE


def image(img: np.ndarray, key: Optional[str]) -> np.ndarray:
    """Image as displayed (a new array unless the orientation is the identity)."""
    k = valid(key)
    if k == ROT180:
        return cv2.rotate(img, cv2.ROTATE_180)
    if k == MIRROR_H:
        return cv2.flip(img, 1)
    if k == MIRROR_V:
        return cv2.flip(img, 0)
    return img


def points(x, y, w: float, h: float, key: Optional[str]):
    """Pixel coordinates in an image of size (w, h) <-> displayed image (pixel centres at integers)."""
    sx, sy, _ = signs(key)
    x = np.asarray(x, float)
    y = np.asarray(y, float)
    return (x if sx > 0 else (w - 1) - x), (y if sy > 0 else (h - 1) - y)


def vectors(vx, vy, key: Optional[str]):
    sx, sy, _ = signs(key)
    return sx * np.asarray(vx, float), sy * np.asarray(vy, float)


def from_frame(df_or_info) -> str:
    """Orientation stored in an exported CSV ('orientacion', or the old 'espejo' column) or JSON dict."""
    for col in ("orientacion", "espejo"):
        try:
            if isinstance(df_or_info, dict):
                v = df_or_info.get(col)
            elif col in df_or_info.columns:
                v = df_or_info[col].iloc[0]
            else:
                v = None
        except Exception:      # noqa: BLE001 (any malformed input -> no orientation)
            v = None
        if v is not None and str(v) in _SIGNS:
            return str(v)
    return NONE
