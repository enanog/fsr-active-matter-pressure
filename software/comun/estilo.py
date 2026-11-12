"""Shared visual style: colours per trial / mode and the matplotlib settings for report and
poster figures (figuras/ scripts and the Comparador export).

Colours follow the entity (a trial keeps its colour whatever else is selected) and come in a
fixed order from a palette validated for colour-vision deficiencies; past 8 series, line style
is the secondary encoding. Modes use the first three slots (AH blue, HO orange, AL aqua), as in
comparar_modos.py.
"""

from __future__ import annotations

from pathlib import Path
from typing import Iterable

SERIES = ["#2a78d6", "#eb6834", "#1baf7a", "#eda100", "#e87ba4", "#008300", "#6250d6", "#e34948"]
LINESTYLES = ["-", "--", ":", "-."]
MODE_COLOR = {"AH": "#2a78d6", "HO": "#eb6834", "AL": "#1baf7a"}   # antihorario, horario, aleatorio
INK, INK2, MUTED, GRID = "#0b0b0b", "#52514e", "#8a8984", "#e4e3df"
JAM_SHADE = "#d9d8d3"

# figure widths [cm]: one column of an article / full page / poster panel
WIDTH_CM = {"columna": 8.6, "pagina": 17.0, "poster": 25.0}


def series_style(i: int) -> tuple[str, str]:
    """(colour, matplotlib linestyle) of the i-th entity (0-based, stable order)."""
    return SERIES[i % len(SERIES)], LINESTYLES[(i // len(SERIES)) % len(LINESTYLES)]


def qt_dash(i: int):
    """Qt pen style matching series_style(i) (imported lazily: no Qt needed for matplotlib)."""
    from PySide6.QtCore import Qt
    return [Qt.PenStyle.SolidLine, Qt.PenStyle.DashLine, Qt.PenStyle.DotLine,
            Qt.PenStyle.DashDotLine][(i // len(SERIES)) % 4]


def mpl_rc(size_pt: float = 9.0) -> dict:
    """rcParams for figures embedded in LaTeX (Computer Modern-like maths, no LaTeX install
    needed). Use with `matplotlib.rc_context(mpl_rc())` or `apply_mpl()`."""
    return {
        "font.family": "serif", "font.serif": ["CMU Serif", "Computer Modern Roman", "DejaVu Serif"],
        "mathtext.fontset": "cm", "axes.unicode_minus": False,
        "font.size": size_pt, "axes.titlesize": size_pt, "axes.labelsize": size_pt,
        "xtick.labelsize": size_pt - 1, "ytick.labelsize": size_pt - 1, "legend.fontsize": size_pt - 1,
        "axes.edgecolor": INK2, "axes.labelcolor": INK, "xtick.color": INK2, "ytick.color": INK2,
        "text.color": INK, "axes.grid": True, "grid.color": GRID, "grid.linewidth": 0.6,
        "axes.spines.top": False, "axes.spines.right": False, "lines.linewidth": 1.2,
        "legend.frameon": False, "figure.dpi": 150, "savefig.dpi": 300, "savefig.bbox": "tight",
        "pdf.fonttype": 42, "svg.fonttype": "none",
    }


def apply_mpl(size_pt: float = 9.0) -> None:
    import matplotlib
    matplotlib.rcParams.update(mpl_rc(size_pt))


def figsize(width: str | float = "pagina", aspect: float = 0.6) -> tuple[float, float]:
    """(w, h) in inches from a named width (WIDTH_CM) or centimetres, and h/w."""
    w_cm = WIDTH_CM[width] if isinstance(width, str) else float(width)
    return w_cm / 2.54, w_cm * aspect / 2.54


def save(fig, path: Path | str, formats: Iterable[str] = ("pdf", "png")) -> list[Path]:
    """Save `fig` as path.<fmt> for every format (path may carry an extension: it is replaced)."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    out = []
    for f in formats:
        p = path.with_suffix("." + f.lstrip("."))
        fig.savefig(p)
        out.append(p)
    return out
