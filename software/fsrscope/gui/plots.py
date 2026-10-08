"""Plot catalogue and panels (pyqtgraph: fast enough to redraw 80k-point series every frame).

Time panels share the X axis (sensor time) and carry the playback cursor; statistics panels
are recomputed over the analysed samples (whole crop, or up to the cursor in live mode).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Optional

import numpy as np
import pyqtgraph as pg
from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QLabel, QSplitter, QVBoxLayout, QWidget

from core.session import TrialData
from core.stats import Stats, decimate_survival

pg.setConfigOptions(background="w", foreground="k", antialias=False)

C_MAIN = "#1f5fa8"
C_SECOND = "#e07b00"
C_SAT = "#d62728"
C_REF = (150, 150, 150)
C_CURSOR = "#c2185b"
RAW_COLUMNS = "__raw_columns__"   # sentinel: choices are the numeric columns of the log


@dataclass(frozen=True)
class Opt:
    key: str
    label: str
    default: Any
    choices: Any = None            # tuple of choices, or RAW_COLUMNS
    minimum: float = 0.0
    maximum: float = 1e9


@dataclass(frozen=True)
class PlotSpec:
    id: str
    title: str
    kind: str                      # "time" | "stat"
    options: tuple = ()
    visible: bool = True
    needs_robots: bool = False


SPECS: list[PlotSpec] = [
    PlotSpec("G", "Conductancia G(t)", "time",
             (Opt("log_y", "Escala log en Y", False), Opt("show_sat", "Marcar saturación", True),
              Opt("show_gmax", "Línea de G máx. (saturación)", False))),
    PlotSpec("dG", "ΔG(t) con ventana fija", "time", (Opt("log_y", "Escala log en Y", False),)),
    PlotSpec("robots", "Robots: |v|(t)", "time",
             (Opt("show_p90", "Mostrar percentil 90", True),
              Opt("smooth_s", "Media móvil [s] (solo video)", 0.0, maximum=600.0)),
             needs_robots=True),
    PlotSpec("R", "Resistencia del FSR R(t)", "time",
             (Opt("log_y", "Escala log en Y", True), Opt("show_floor", "Línea de R mínima (saturación)", True)),
             visible=False),
    PlotSpec("ADC", "ADC(t)", "time", (Opt("show_fs", "Línea de fondo de escala", True),), visible=False),
    PlotSpec("raw", "Columna del registro", "time",
             (Opt("column", "Columna", "", RAW_COLUMNS), Opt("log_y", "Escala log en Y", False)),
             visible=False),
    PlotSpec("skew", "Asimetría de ΔG vs ΔT", "stat", (Opt("mark_fixed", "Marcar ΔT fija", True),)),
    PlotSpec("kurt", "Curtosis de ΔG vs ΔT", "stat", (Opt("mark_fixed", "Marcar ΔT fija", True),),
             visible=False),
    PlotSpec("surv", "Supervivencia P(G ≥ g)", "stat",
             (Opt("log_x", "Escala log en X", False), Opt("log_y", "Escala log en Y", True))),
    PlotSpec("hist_G", "Histograma de G", "stat", (Opt("log_y", "Escala log en Y", False),), visible=False),
    PlotSpec("hist_dG", "Histograma de ΔG", "stat", (Opt("log_y", "Escala log en Y", True),)),
]
SPEC_BY_ID = {s.id: s for s in SPECS}


def default_plot_states() -> list[dict]:
    return [{"id": s.id, "visible": s.visible, "options": {o.key: o.default for o in s.options}}
            for s in SPECS]


def normalized_plot_states(saved: list) -> list[dict]:
    """Saved states completed with new plots/options, unknown ids dropped, order kept."""
    out, seen = [], set()
    for st in saved or []:
        spec = SPEC_BY_ID.get(st.get("id"))
        if spec is None or spec.id in seen:
            continue
        opts = {o.key: o.default for o in spec.options}
        opts.update({k: v for k, v in (st.get("options") or {}).items() if k in opts})
        out.append({"id": spec.id, "visible": bool(st.get("visible", True)), "options": opts})
        seen.add(spec.id)
    out += [d for d in default_plot_states() if d["id"] not in seen]
    return out


def _edges(centers: np.ndarray) -> np.ndarray:
    w = centers[1] - centers[0] if len(centers) > 1 else 1.0
    return np.concatenate((centers - w / 2, [centers[-1] + w / 2]))


def _safe(y: np.ndarray, log: bool) -> np.ndarray:
    y = np.asarray(y, dtype=float)
    if log:
        y = np.where(y > 0, y, np.nan)
    return np.where(np.isfinite(y), y, np.nan)


class PlotPanel(QWidget):
    def __init__(self, spec: PlotSpec, parent=None):
        super().__init__(parent)
        self.spec = spec
        self.options: dict = {o.key: o.default for o in spec.options}
        self.pw = pg.PlotWidget()
        self.plot: pg.PlotItem = self.pw.getPlotItem()
        self.plot.showGrid(x=True, y=True, alpha=0.25)
        for ax in ("left", "bottom"):
            self.plot.getAxis(ax).enableAutoSIPrefix(False)   # keep plain units (s, µS)
        self.plot.setMenuEnabled(True)
        self.title = QLabel(spec.title)
        self.title.setStyleSheet("font-weight: 600; padding: 2px 4px;")
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)
        lay.addWidget(self.title)
        lay.addWidget(self.pw, 1)
        self.setMinimumHeight(140)
        self.td: Optional[TrialData] = None

    def set_title_suffix(self, text: str) -> None:
        self.title.setText(self.spec.title + (f"   <span style='font-weight:400;color:#666'>{text}</span>"
                                              if text else ""))

    def set_options(self, opts: dict) -> None:
        self.options.update(opts)
        self.plot.setLogMode(x=bool(self.options.get("log_x", False)), y=bool(self.options.get("log_y", False)))


# =============================================================================================
# Time panels
# =============================================================================================
class TimePanel(PlotPanel):
    seekRequested = Signal(float)
    selectionChanged = Signal(float, float)

    def __init__(self, spec: PlotSpec, parent=None):
        super().__init__(spec, parent)
        self.plot.setLabel("bottom", "t sensor", units="s")
        self.plot.setClipToView(True)
        self.plot.setDownsampling(auto=True, mode="peak")
        self._curves: list[tuple[pg.PlotDataItem, np.ndarray, np.ndarray]] = []
        self._shades: list[pg.LinearRegionItem] = []
        self._hlines: list[pg.InfiniteLine] = []
        self._until: Optional[float] = None
        self.cursor = pg.InfiniteLine(angle=90, movable=True, pen=pg.mkPen(C_CURSOR, width=2),
                                      hoverPen=pg.mkPen(C_CURSOR, width=4))
        self.cursor.setZValue(50)
        self.cursor.sigDragged.connect(lambda line: self.seekRequested.emit(float(line.value())))
        self.plot.addItem(self.cursor, ignoreBounds=True)
        self.selection = pg.LinearRegionItem(brush=pg.mkBrush(255, 200, 0, 60),
                                             pen=pg.mkPen(200, 140, 0, width=1))
        self.selection.setZValue(40)
        self.selection.hide()
        self.selection.sigRegionChanged.connect(
            lambda r: self.selectionChanged.emit(*map(float, r.getRegion())))
        self.plot.addItem(self.selection, ignoreBounds=True)
        self.plot.scene().sigMouseClicked.connect(self._on_click)

    # --- data ---------------------------------------------------------------------------------
    def curves(self, td: TrialData) -> list[tuple[np.ndarray, np.ndarray, Any, str]]:
        """[(x, y, pen, name)] for this panel. Override."""
        return []

    def hlines(self, td: TrialData) -> list[tuple[float, Any]]:
        return []

    def ylabel(self) -> tuple[str, str]:
        return "", ""

    def set_trial(self, td: Optional[TrialData]) -> None:
        self.td = td
        self.rebuild()

    def rebuild(self) -> None:
        for item, _, _ in self._curves:
            self.plot.removeItem(item)
        for ln in self._hlines:
            self.plot.removeItem(ln)
        self._curves, self._hlines = [], []
        if self.plot.legend is not None:
            if self.plot.legend.scene() is not None:
                self.plot.legend.scene().removeItem(self.plot.legend)
            self.plot.legend = None
        if self.td is None or self.td.series is None:
            return
        lab, units = self.ylabel()
        self.plot.setLabel("left", lab, units=units)
        data = self.curves(self.td)
        if len(data) > 1:
            self.plot.addLegend(offset=(-10, 10))
        log_y = bool(self.options.get("log_y", False))
        for x, y, pen, name in data:
            y = _safe(y, log_y)
            item = pg.PlotDataItem(x, y, pen=pen, name=name or None, connect="finite")
            self.plot.addItem(item)
            self._curves.append((item, np.asarray(x, float), y))
        for val, pen in self.hlines(self.td):
            if log_y:   # in log mode pyqtgraph positions items in log10 coordinates
                if not val > 0:
                    continue
                val = np.log10(val)
            ln = pg.InfiniteLine(pos=val, angle=0, pen=pen, movable=False)
            self.plot.addItem(ln, ignoreBounds=True)
            self._hlines.append(ln)
        self._until = None
        self.show_until(None, force=True)

    def show_until(self, t_now: Optional[float], force: bool = False,
                   t_from: Optional[float] = None) -> None:
        """Reveal data up to t_now (live mode) or everything (None). t_from limits what is handed
        to pyqtgraph to the visible live window, which keeps each frame cheap."""
        key = (t_now, t_from)
        if key == self._until and not force:
            return
        self._until = key
        for item, x, y in self._curves:
            if t_now is None:
                item.setData(x, y, connect="finite")
            else:
                i1 = int(np.searchsorted(x, t_now, side="right"))
                i0 = max(0, int(np.searchsorted(x, t_from)) - 1) if t_from is not None else 0
                item.setData(x[i0:i1], y[i0:i1], connect="finite")

    def set_options(self, opts: dict) -> None:
        super().set_options(opts)
        self.plot.setLogMode(x=False, y=bool(self.options.get("log_y", False)))
        self.rebuild()

    # --- overlays -----------------------------------------------------------------------------
    def set_cursor(self, t: float) -> None:
        self.cursor.blockSignals(True)
        self.cursor.setValue(t)
        self.cursor.blockSignals(False)

    def set_shading(self, spans: list[tuple[float, float, tuple]]) -> None:
        for r in self._shades:
            self.plot.removeItem(r)
        self._shades = []
        for t0, t1, rgba in spans:
            r = pg.LinearRegionItem(values=(t0, t1), movable=False, brush=pg.mkBrush(*rgba),
                                    pen=pg.mkPen(None))
            r.setZValue(-10)
            self.plot.addItem(r, ignoreBounds=True)
            self._shades.append(r)

    def set_selection(self, visible: bool, region: Optional[tuple[float, float]] = None) -> None:
        self.selection.blockSignals(True)
        if region is not None:
            self.selection.setRegion(region)
        self.selection.setVisible(visible)
        self.selection.blockSignals(False)

    def _on_click(self, ev) -> None:
        if ev.double() and ev.button() == Qt.MouseButton.LeftButton:
            vb = self.plot.getViewBox()
            if vb.sceneBoundingRect().contains(ev.scenePos()):
                self.seekRequested.emit(float(vb.mapSceneToView(ev.scenePos()).x()))


class GPanel(TimePanel):
    def ylabel(self):
        return "G", "µS"

    def curves(self, td):
        s = td.series
        out = [(s.t, s.G, pg.mkPen(C_MAIN, width=1), "G")]
        if self.options.get("show_sat", True) and s.sat.any():
            out.append((s.t, np.where(s.sat, s.G, np.nan), pg.mkPen(C_SAT, width=2), "saturado"))
        return out

    def hlines(self, td):
        if self.options.get("show_gmax", False):
            return [(td.series.g_max, pg.mkPen(C_SAT, style=Qt.PenStyle.DashLine))]
        return []


class DeltaGPanel(TimePanel):
    def ylabel(self):
        return f"ΔG (ΔT = {self.td.settings.analysis.deltaT_fixed_s:g} s)" if self.td else "ΔG", "µS"

    def __init__(self, spec, parent=None):
        super().__init__(spec, parent)
        self._dG: Optional[np.ndarray] = None

    def set_deltaG(self, dG: Optional[np.ndarray]) -> None:
        self._dG = dG
        self.rebuild()

    def curves(self, td):
        if self._dG is None or len(self._dG) != len(td.series.t):
            return []
        return [(td.series.t, self._dG, pg.mkPen(C_MAIN, width=1), "")]

    def hlines(self, td):
        return [(0.0, pg.mkPen(C_REF, style=Qt.PenStyle.DashLine))]


class RobotsPanel(TimePanel):
    def ylabel(self):
        return "|v| robots", "mm/s"

    def curves(self, td):
        r = td.robots
        if r is None:
            return []
        t = td.time_of_frame(r.frames)
        w = float(self.options.get("smooth_s", 0.0) or 0.0)
        k = max(1, int(round(w * td.settings.sync.frames_per_s)))

        def sm(v):
            if k <= 1:
                return v
            c = np.convolve(np.nan_to_num(v), np.ones(k) / k, mode="same")
            return np.where(np.isfinite(v), c, np.nan)

        out = [(t, sm(r.v_median), pg.mkPen(C_MAIN, width=1), "mediana")]
        if self.options.get("show_p90", True):
            out.append((t, sm(r.v_p90), pg.mkPen(C_SECOND, width=1), "p90"))
        return out


class RPanel(TimePanel):
    def ylabel(self):
        return "R FSR", "Ω"

    def curves(self, td):
        R = td.series.R
        return [(td.series.t, np.where(np.isfinite(R), R, np.nan), pg.mkPen(C_MAIN, width=1), "")]

    def hlines(self, td):
        if self.options.get("show_floor", True):
            return [(td.series.r_floor, pg.mkPen(C_SAT, style=Qt.PenStyle.DashLine))]
        return []


class AdcPanel(TimePanel):
    def ylabel(self):
        return "ADC", "cuentas"

    def curves(self, td):
        return [(td.series.t, td.series.adc, pg.mkPen(C_MAIN, width=1), "")]

    def hlines(self, td):
        if self.options.get("show_fs", True):
            return [(td.series.adc_fs, pg.mkPen(C_SAT, style=Qt.PenStyle.DashLine))]
        return []


class RawColumnPanel(TimePanel):
    def ylabel(self):
        return self.options.get("column") or "", ""

    def curves(self, td):
        cols = td.raw.numeric_columns()
        col = self.options.get("column")
        if col not in cols:
            col = cols[0] if cols else None
            self.options["column"] = col
        if col is None:
            return []
        return [(td.raw.t, td.raw.data[col].to_numpy(float), pg.mkPen(C_MAIN, width=1), "")]


# =============================================================================================
# Statistics panels
# =============================================================================================
class StatPanel(PlotPanel):
    def __init__(self, spec, parent=None):
        super().__init__(spec, parent)
        self.ref = pg.PlotDataItem(pen=pg.mkPen(C_REF, width=1.5))
        self.cur = pg.PlotDataItem(pen=pg.mkPen(C_MAIN, width=1.5))
        self.plot.addItem(self.ref)
        self.plot.addItem(self.cur)
        self.vline = pg.InfiniteLine(angle=90, movable=False, pen=pg.mkPen(C_SECOND, style=Qt.PenStyle.DashLine))
        self.vline.hide()
        self.plot.addItem(self.vline, ignoreBounds=True)
        self._last: tuple = (None, None)

    def xy(self, st: Stats) -> tuple[np.ndarray, np.ndarray]:
        return np.empty(0), np.empty(0)

    def update_stats(self, st: Optional[Stats], ref: Optional[Stats] = None) -> None:
        """st: stats to show; ref: full-record stats drawn in grey behind (live mode)."""
        self._last = (st, ref)
        for item, s in ((self.cur, st), (self.ref, ref)):
            if s is None:
                item.setData([], [])
                continue
            x, y = self.xy(s)
            self._set(item, x, y)
        if st is None:
            self.set_title_suffix("")
        elif st.t_now is not None:
            self.set_title_suffix(f"en vivo: hasta t = {st.t_now:.1f} s · n = {st.n_used}")
        else:
            self.set_title_suffix(f"n = {st.n_used}")
        self.decorate(st)

    def _set(self, item, x, y):
        y = _safe(y, bool(self.options.get("log_y")))
        x = _safe(x, bool(self.options.get("log_x")))
        item.setData(x, y, connect="finite")

    def decorate(self, st: Optional[Stats]) -> None:
        pass

    def set_options(self, opts: dict) -> None:
        super().set_options(opts)
        self.update_stats(*self._last)


class SkewPanel(StatPanel):
    attr = "skew"

    def __init__(self, spec, parent=None):
        super().__init__(spec, parent)
        self.plot.setLabel("bottom", "ΔT", units="s")
        self.plot.setLabel("left", "asimetría" if self.attr == "skew" else "curtosis en exceso")
        self.plot.addItem(pg.InfiniteLine(pos=0, angle=0, pen=pg.mkPen(C_REF, style=Qt.PenStyle.DashLine)),
                          ignoreBounds=True)

    def xy(self, st):
        return st.deltaT, getattr(st, self.attr)

    def decorate(self, st):
        if self.td is not None and self.options.get("mark_fixed", True):
            self.vline.setValue(self.td.settings.analysis.deltaT_fixed_s)
            self.vline.show()
        else:
            self.vline.hide()


class KurtPanel(SkewPanel):
    attr = "kurt"


class SurvPanel(StatPanel):
    def __init__(self, spec, parent=None):
        super().__init__(spec, parent)
        self.plot.setLabel("bottom", "g", units="µS")
        self.plot.setLabel("left", "P(G ≥ g)")
        self.set_options({})

    def xy(self, st):
        return decimate_survival(st.surv_G, st.surv_P)


class HistPanel(StatPanel):
    attr = "hist_G"

    def __init__(self, spec, parent=None):
        super().__init__(spec, parent)
        self.plot.setLabel("bottom", "G" if self.attr == "hist_G" else "ΔG", units="µS")
        self.plot.setLabel("left", "densidad", units="1/µS")
        self.set_options({})

    def _set(self, item, x, y):
        log = bool(self.options.get("log_y"))
        if len(x) == 0:
            item.setData([], [])
            return
        edges = _edges(np.asarray(x, dtype=float))
        y = np.asarray(y, dtype=float)
        if log:
            # Manual steps with gaps at empty bins (log of 0 is undefined).
            xs = np.repeat(edges, 2)[1:-1]
            ys = np.repeat(np.where(y > 0, y, np.nan), 2)
            item.setFillLevel(None)
            item.setBrush(None)
            item.setData(xs, ys, connect="finite", stepMode=None)
            return
        if item is self.cur:
            item.setFillLevel(0)
            item.setBrush(pg.mkBrush(31, 95, 168, 60))
        item.setData(edges, y, stepMode="center")

    def xy(self, st):
        return getattr(st, self.attr)


class HistDGPanel(HistPanel):
    attr = "hist_dG"


PANEL_CLASSES = {"G": GPanel, "dG": DeltaGPanel, "robots": RobotsPanel, "R": RPanel,
                 "ADC": AdcPanel, "raw": RawColumnPanel, "skew": SkewPanel, "kurt": KurtPanel,
                 "surv": SurvPanel, "hist_G": HistPanel, "hist_dG": HistDGPanel}


class PlotArea(QWidget):
    """Two columns: time panels (linked X, cursor) | statistics panels."""

    seekRequested = Signal(float)
    selectionChanged = Signal(float, float)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.panels: dict[str, PlotPanel] = {
            sid: cls(SPEC_BY_ID[sid]) for sid, cls in PANEL_CLASSES.items()}
        for p in self.time_panels(all_=True):
            p.seekRequested.connect(self.seekRequested)
            p.selectionChanged.connect(self._sync_selection)
        self.split = QSplitter(Qt.Orientation.Horizontal)
        self.col_time = QSplitter(Qt.Orientation.Vertical)
        self.col_stat = QSplitter(Qt.Orientation.Vertical)
        for c in (self.col_time, self.col_stat):
            c.setChildrenCollapsible(False)
        self.split.addWidget(self.col_time)
        self.split.addWidget(self.col_stat)
        self.split.setStretchFactor(0, 3)
        self.split.setStretchFactor(1, 2)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.addWidget(self.split)
        self._has_robots = False
        self._states: list[dict] = default_plot_states()

    def time_panels(self, all_: bool = False) -> list[TimePanel]:
        return [p for p in self.panels.values() if isinstance(p, TimePanel) and (all_ or p.isVisible())]

    def stat_panels(self) -> list[StatPanel]:
        return [p for p in self.panels.values() if isinstance(p, StatPanel) and p.isVisible()]

    def configure(self, states: list[dict], has_robots: bool) -> None:
        """Show/hide/reorder panels and apply their options."""
        self._states, self._has_robots = states, has_robots
        order = {"time": [], "stat": []}
        for st in states:
            p = self.panels[st["id"]]
            show = st["visible"] and (has_robots or not p.spec.needs_robots)
            p.setVisible(show)
            if st["options"] != p.options or not getattr(p, "_configured", False):
                p.set_options(dict(st["options"]))     # applies log scales and redraws
                p._configured = True
            order[p.spec.kind].append(p)
        for col, panels in ((self.col_time, order["time"]), (self.col_stat, order["stat"])):
            for i, p in enumerate(panels):
                col.insertWidget(i, p)
        self.col_stat.setVisible(any(p.isVisible() for p in order["stat"]))
        first = None
        for p in order["time"]:
            if p.isVisible():
                if first is None:
                    first = p
                    p.plot.setXLink(None)
                else:
                    p.plot.setXLink(first.plot)

    def apply_options(self, pid: str, opts: dict) -> None:
        self.panels[pid].set_options(opts)

    def _sync_selection(self, a: float, b: float) -> None:
        for p in self.time_panels(all_=True):
            if p is not self.sender():
                p.set_selection(p.selection.isVisible(), (a, b))
        self.selectionChanged.emit(a, b)
