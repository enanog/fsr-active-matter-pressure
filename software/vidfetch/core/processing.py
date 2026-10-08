"""Frame processing registry. Add an OperationSpec to OPERATIONS and the GUI builds its controls."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable

import cv2
import numpy as np


@dataclass(frozen=True)
class ParamSpec:
    key: str
    label: str
    minimum: float
    maximum: float
    default: float
    step: float = 1
    decimals: int = 0  # 0 -> integer spinbox


@dataclass(frozen=True)
class OperationSpec:
    key: str
    label: str
    func: Callable[[np.ndarray, dict], np.ndarray]
    params: tuple[ParamSpec, ...] = ()


def to_gray(frame: np.ndarray) -> np.ndarray:
    return frame if frame.ndim == 2 else cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)


def _grayscale(f: np.ndarray, p: dict) -> np.ndarray:
    return to_gray(f)


def _brightness_contrast(f: np.ndarray, p: dict) -> np.ndarray:
    # out = alpha * in + beta, saturated to uint8
    return cv2.convertScaleAbs(f, alpha=float(p["alpha"]), beta=float(p["beta"]))


def _gaussian_blur(f: np.ndarray, p: dict) -> np.ndarray:
    k = int(p["ksize"])
    k = k if k % 2 else k + 1
    return cv2.GaussianBlur(f, (k, k), 0)


def _threshold(f: np.ndarray, p: dict) -> np.ndarray:
    _, out = cv2.threshold(to_gray(f), float(p["thresh"]), 255, cv2.THRESH_BINARY)
    return out


def _canny(f: np.ndarray, p: dict) -> np.ndarray:
    return cv2.Canny(to_gray(f), float(p["low"]), float(p["high"]))


# Applied in this order when enabled.
OPERATIONS: tuple[OperationSpec, ...] = (
    OperationSpec("gray", "Escala de grises", _grayscale),
    OperationSpec(
        "bc", "Brillo / contraste", _brightness_contrast,
        (ParamSpec("alpha", "Contraste (α)", 0.1, 5.0, 1.0, 0.05, 2),
         ParamSpec("beta", "Brillo (β)", -255, 255, 0)),
    ),
    OperationSpec(
        "blur", "Desenfoque gaussiano", _gaussian_blur,
        (ParamSpec("ksize", "Kernel [px, impar]", 1, 99, 5, 2),),
    ),
    OperationSpec(
        "thresh", "Umbral binario", _threshold,
        (ParamSpec("thresh", "Umbral", 0, 255, 128),),
    ),
    OperationSpec(
        "canny", "Bordes (Canny)", _canny,
        (ParamSpec("low", "Umbral bajo", 0, 1000, 50),
         ParamSpec("high", "Umbral alto", 0, 1000, 150)),
    ),
)


@dataclass
class Pipeline:
    """Immutable snapshot of enabled ops + params; safe to use from a worker thread."""

    steps: list[tuple[OperationSpec, dict]] = field(default_factory=list)

    def __call__(self, frame: np.ndarray) -> np.ndarray:
        for op, params in self.steps:
            frame = op.func(frame, params)
        return frame

    def __bool__(self) -> bool:
        return bool(self.steps)
