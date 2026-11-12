"""Plots of velocidades.py: one plot per tab, its options in a bar above it.

Time plots use minutes of video on X (the conductance of the twin-axis plot is mapped with the
FSRScope synchronisation). Clic derecho sobre un gráfico: escalas y Export… (PNG, SVG, CSV).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Optional

import numpy as np
import pyqtgraph as pg
from PySide6.QtCore import QRectF, Qt, Signal
from PySide6.QtWidgets import (QCheckBox, QComboBox, QDoubleSpinBox, QHBoxLayout, QLabel, QToolButton,
                               QVBoxLayout, QWidget)

from comun.mobility import KinStats, MobilityData, rolling_mean
from comun.stats import decimate_survival

pg.setConfigOptions(background="w", foreground="k", antialias=False)

C_SPEED = "#2a7f62"
C_OMEGA = "#c0392b"
C_ETOT = "#222222"
C_ETR = "#2a7f62"
C_EROT = "#c0392b"
C_MED = "#1f5fa8"
C_P90 = "#e07b00"
C_G = "#1f5fa8"
C_RAW = (160, 160, 160)
C_THR = "#7b3fa0"
C_JAM = (123, 63, 160, 45)
G_LOG_FLOOR_US = 1e-3      # G below this is resampling round-off (< 10⁻³ ADC counts): hidden on log axes

SOURCES = {"V̄ por cuadro (media entre robots)": "colectiva", "media de cada robot": "robot",
           "|v| de cada robot y cuadro": "individual"}
COUNT_LABEL = {"colectiva": "cuadros", "robot": "robots", "individual": "muestras"}
SUBSETS = ("todo", "atasco", "fluido")


@dataclass(frozen=True)
class Opt:
    key: str
    label: str
    default: Any
    choices: tuple = ()
    maximum: float = 600.0


def _safe(y, log: bool) -> np.ndarray:
    y = np.asarray(y, dtype=float)
    if log:
        y = np.where(y > 0, y, np.nan)
    return np.where(np.isfinite(y), y, np.nan)


# =============================================================================================
class VelPlot(QWidget):
    """Title + option bar + plot. Subclasses implement draw()."""

    pid = ""
    title = ""
    OPTIONS: tuple = ()
    optionsChanged = Signal(str, dict)
    detachRequested = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.options = {o.key: o.default for o in self.OPTIONS}
        self.md: Optional[MobilityData] = None
        self.ks: Optional[KinStats] = None
        self.dirty = True
        self.head = QLabel(self.title)
        self.head.setStyleSheet("font-weight:600; padding:2px 4px;")
        self.b_detach = QToolButton()
        self.b_detach.setText("Ventana aparte")
        self.b_detach.setToolTip("Abrir este gráfico en su propia ventana (al cerrarla vuelve a su pestaña)")
        self.b_detach.clicked.connect(lambda: self.detachRequested.emit(self.pid))
        top = QHBoxLayout()
        top.setContentsMargins(0, 0, 0, 0)
        top.addWidget(self.head, 1)
        top.addWidget(self.b_detach)
        bar = QHBoxLayout()
        bar.setContentsMargins(4, 0, 4, 0)
        self._widgets: dict[str, QWidget] = {}
        for o in self.OPTIONS:
            bar.addWidget(self._make(o))
        bar.addStretch(1)
        self.pw = pg.PlotWidget()
        self.plot: pg.PlotItem = self.pw.getPlotItem()
        self.plot.showGrid(x=True, y=True, alpha=0.25)
        for ax in ("left", "bottom"):
            self.plot.getAxis(ax).enableAutoSIPrefix(False)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(2, 2, 2, 2)
        lay.addLayout(top)
        lay.addLayout(bar)
        lay.addWidget(self.pw, 1)

    # --- options ----------------------------------------------------------------------------------
    def _make(self, o: Opt) -> QWidget:
        if o.choices:
            w = QComboBox()
            w.addItems(list(o.choices))
            w.currentTextChanged.connect(lambda v, k=o.key: self._set(k, v))
            box = QWidget()
            h = QHBoxLayout(box)
            h.setContentsMargins(0, 0, 8, 0)
            h.addWidget(QLabel(o.label))
            h.addWidget(w)
            self._widgets[o.key] = w
            return box
        if isinstance(o.default, bool):
            w = QCheckBox(o.label)
            w.toggled.connect(lambda v, k=o.key: self._set(k, bool(v)))
            self._widgets[o.key] = w
            return w
        w = QDoubleSpinBox()
        w.setRange(0, o.maximum)
        w.setDecimals(1)
        w.setSingleStep(5)
        w.setKeyboardTracking(False)
        w.valueChanged.connect(lambda v, k=o.key: self._set(k, float(v)))
        box = QWidget()
        h = QHBoxLayout(box)
        h.setContentsMargins(0, 0, 8, 0)
        h.addWidget(QLabel(o.label))
        h.addWidget(w)
        self._widgets[o.key] = w
        return box

    def load_options(self, saved: dict) -> None:
        self.options = {o.key: o.default for o in self.OPTIONS}
        self.options.update({k: v for k, v in (saved or {}).items() if k in self.options})
        for o in self.OPTIONS:
            w, v = self._widgets[o.key], self.options[o.key]
            w.blockSignals(True)
            if isinstance(w, QComboBox):
                if v in o.choices:
                    w.setCurrentText(v)
                else:
                    self.options[o.key] = w.currentText()
            elif isinstance(w, QCheckBox):
                w.setChecked(bool(v))
            else:
                w.setValue(float(v))
            w.blockSignals(False)

    def _set(self, key: str, value) -> None:
        self.options[key] = value
        self.optionsChanged.emit(self.pid, dict(self.options))
        self.redraw()

    # --- data ---------------------------------------------------------------------------------------
    def set_data(self, md: Optional[MobilityData], ks: Optional[KinStats], visible: bool) -> None:
        self.md, self.ks, self.dirty = md, ks, True
        if visible:
            self.redraw()

    def redraw(self) -> None:
        self.dirty = False
        self.draw()

    def draw(self) -> None:
        pass

    def suffix(self, text: str) -> None:
        self.head.setText(self.title + (f"   <span style='font-weight:400;color:#666'>{text}</span>"
                                        if text else ""))

    def autorange(self) -> None:
        self.plot.enableAutoRange()


# =============================================================================================
# time plots (X = minutes of video)
# =============================================================================================
class TimePlot(VelPlot):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.plot.setLabel("bottom", "t video", units="min")
        self.plot.setClipToView(True)
        self.plot.setDownsampling(auto=True, mode="peak")
        self.legend = self.plot.addLegend(offset=(-10, 10))

    def reset(self) -> None:
        self.plot.clear()
        self.legend.clear()
        log = bool(self.options.get("log_y", False))
        self.plot.setLogMode(x=False, y=log)

    def hline(self, v: float, pen) -> None:
        log = bool(self.options.get("log_y", False))
        if log and not v > 0:
            return
        self.plot.addItem(pg.InfiniteLine(pos=np.log10(v) if log else v, angle=0, pen=pen), ignoreBounds=True)

    def curve(self, x, y, pen, name: str = "") -> pg.PlotDataItem:
        item = pg.PlotDataItem(x, _safe(y, bool(self.options.get("log_y", False))), pen=pen,
                               name=name or None, connect="finite")
        self.plot.addItem(item)
        return item

    def smoothed(self, t, x, color, name: str, show_raw: bool = True, width: float = 2.0) -> None:
        """Raw series in light grey behind its moving average (window of the settings)."""
        w = self.md.settings.smooth_s
        if show_raw and w > 0:
            self.curve(t, x, pg.mkPen(C_RAW, width=1), "")
        self.curve(t, self.md.smooth(x), pg.mkPen(color, width=width), name)

    def window_text(self) -> str:
        w = self.md.settings.smooth_s if self.md is not None else 0
        return f"media móvil {w:g} s" if w > 0 else "sin media móvil"

    def shade_jams(self) -> None:
        if not self.options.get("show_jams", False) or self.md is None:
            return
        for t0, t1 in self.md.jam_spans_min():
            r = pg.LinearRegionItem(values=(t0, t1), movable=False, brush=pg.mkBrush(*C_JAM), pen=pg.mkPen(None))
            r.setZValue(-10)
            self.plot.addItem(r, ignoreBounds=True)

    def shade_window(self) -> None:
        """Grey outside the analysis window."""
        if self.md is None:
            return
        s, dur = self.md.settings, self.md.duration_min
        for a, b in ((0.0, s.t_start_min), (s.t_end_min, dur)):
            if a is not None and b is not None and b > a:
                r = pg.LinearRegionItem(values=(a, b), movable=False, brush=pg.mkBrush(120, 120, 120, 60),
                                        pen=pg.mkPen(None))
                r.setZValue(-11)
                self.plot.addItem(r, ignoreBounds=True)


class VMeanPlot(TimePlot):
    pid, title = "vmean", "V̄(t): velocidad media del conjunto de robots"
    OPTIONS = (Opt("show_raw", "Por cuadro (gris)", True), Opt("show_median", "Mediana", False),
               Opt("show_p90", "Percentil 90", False), Opt("show_thr", "Umbral", True),
               Opt("show_jams", "Sombrear atascos", False), Opt("log_y", "Log Y", False))

    def draw(self):
        self.reset()
        md = self.md
        if md is None:
            return
        self.plot.setLabel("left", "V̄", units="mm/s")
        r, t = md.robots, md.frame_minutes
        self.smoothed(t, r.v_mean, C_SPEED, f"media V̄ ({self.window_text()})", self.options["show_raw"])
        if self.options["show_median"]:
            self.curve(t, md.smooth(r.v_median), pg.mkPen(C_MED, width=1.5), "mediana")
        if self.options["show_p90"]:
            self.curve(t, md.smooth(r.v_p90), pg.mkPen(C_P90, width=1.5), "p90")
        if self.options["show_thr"]:
            self.hline(md.settings.mobility.v_threshold_mm_s, pg.mkPen(C_THR, style=Qt.PenStyle.DashLine))
        self.shade_jams()
        self.shade_window()
        if self.ks is not None and self.ks.n_frames > 1:
            self.suffix(f"{self.window_text()} · V̄ media en la ventana = {self.ks.v_mean:.3f} mm/s "
                        f"(desvío temporal sin suavizar {self.ks.v_std:.3f})")


class VPressurePlot(TimePlot):
    pid, title = "v_G", "V̄(t) y G(t) en un mismo gráfico (doble eje)"
    OPTIONS = (Opt("log_G", "G en escala log", True), Opt("show_jams", "Sombrear atascos", True))

    def __init__(self, parent=None):
        super().__init__(parent)
        self.vb2 = pg.ViewBox()
        self.vb2.setZValue(-5)                    # V̄ (left axis) drawn on top of G
        self.plot.showAxis("right")
        ax = self.plot.getAxis("right")
        ax.enableAutoSIPrefix(False)
        self.plot.scene().addItem(self.vb2)
        ax.linkToView(self.vb2)
        self.vb2.setXLink(self.plot)
        self.plot.vb.sigResized.connect(self._sync)

    def _sync(self):
        self.vb2.setGeometry(self.plot.vb.sceneBoundingRect())
        self.vb2.linkedViewChanged(self.plot.vb, self.vb2.XAxis)

    def reset(self):
        super().reset()
        self.vb2.clear()

    def draw(self):
        self.reset()
        md = self.md
        if md is None:
            return
        w = float(md.settings.smooth_s or 0.0)
        self.plot.setLabel("left", "V̄", units="mm/s", color=C_SPEED)
        self.curve(md.frame_minutes, md.smooth(md.robots.v_mean), pg.mkPen(C_SPEED, width=2), "V̄ (izq.)")
        ax = self.plot.getAxis("right")
        if md.td is None:
            ax.setLabel("G (sin registro del sensor)")
            self.suffix(f"sin registro del sensor: {md.pressure_error}")
        else:
            s = md.td.series
            g = rolling_mean(s.G, max(1, int(round(w / s.step_s))))
            log = bool(self.options["log_G"])
            if log:
                g = np.where(g >= G_LOG_FLOOR_US, g, np.nan)
            item = pg.PlotDataItem(md.sensor_to_minutes(s.t), g, pen=pg.mkPen(C_G, width=1), connect="finite")
            item.setLogMode(False, log)
            self.vb2.addItem(item)
            self.legend.addItem(item, "G (der.)")
            ax.setLogMode(log)
            ax.setLabel("G", units="µS", color=C_G)
            ks = self.ks
            if ks is not None and np.isfinite(ks.G_fluid):
                self.suffix(f"{self.window_text()} en V̄ y G · G media: flujo {ks.G_fluid:.3g} µS · atasco "
                            + (f"{ks.G_jam:.3g} µS" if np.isfinite(ks.G_jam) else "—"))
        self.shade_jams()
        self.shade_window()
        self.vb2.enableAutoRange()


class VJamPlot(TimePlot):
    pid, title = "v_jam", "Umbral de velocidad: atasco / flujo"
    OPTIONS = (Opt("show_raw", "Estadístico sin suavizar", True), Opt("show_jams", "Sombrear atascos", True),
               Opt("log_y", "Log Y", False))
    thresholdChanged = Signal(float)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.thr = pg.InfiniteLine(angle=0, movable=True, pen=pg.mkPen(C_THR, width=2),
                                   hoverPen=pg.mkPen(C_THR, width=4), label="umbral {value:.3f} mm/s",
                                   labelOpts={"position": 0.04, "color": C_THR, "movable": True})
        self.thr.setZValue(45)
        self.thr.sigPositionChangeFinished.connect(self._dropped)

    def draw(self):
        self.reset()
        md = self.md
        if md is None:
            return
        mob, jm = md.settings.mobility, md.jams
        self.plot.setLabel("left", f"{mob.statistic} de |v| entre robots", units="mm/s")
        t = md.frame_minutes
        if self.options["show_raw"]:
            self.curve(t, md.robots.collective(mob.statistic), pg.mkPen(C_RAW, width=1), "por cuadro")
        self.curve(t, jm.signal, pg.mkPen(C_SPEED, width=2), f"mediana móvil {mob.smooth_s:g} s")
        log = bool(self.options["log_y"])
        v = mob.v_threshold_mm_s
        self.thr.blockSignals(True)
        self.thr.setValue(np.log10(v) if log else v)
        self.thr.label.setFormat(f"umbral {v:.3f} mm/s" if log else "umbral {value:.3f} mm/s")
        self.thr.blockSignals(False)
        self.plot.addItem(self.thr, ignoreBounds=True)
        self.shade_jams()
        self.shade_window()
        ks = self.ks
        if ks is not None and ks.n_frames > 1:
            d = ks.jam_dur_s
            self.suffix(f"{mob.statistic} &lt; {v:.3f} mm/s → {ks.n_jams} atascos, {100 * ks.jam_frac:.1f} % "
                        f"del tiempo" + (f" (máx. {d.max():.0f} s)" if len(d) else ""))

    def _dropped(self, line) -> None:
        v = float(line.value())
        if self.options.get("log_y", False):
            v = 10 ** v
        self.thresholdChanged.emit(round(max(v, 0.001), 3))


class OmegaPlot(TimePlot):
    pid, title = "omega", "⟨|ω|⟩(t): rotación media de los robots sobre su propio eje"
    OPTIONS = (Opt("show_raw", "Por cuadro (gris)", True), Opt("show_jams", "Sombrear atascos", False),
               Opt("log_y", "Log Y", False))

    def draw(self):
        self.reset()
        md = self.md
        if md is None:
            return
        w = md.w_abs_mean
        if w is None:
            self.suffix("las trayectorias no tienen ω (re-exportar con VidFetch)")
            return
        self.plot.setLabel("left", "⟨|ω|⟩", units="°/s")
        self.smoothed(md.frame_minutes, w, C_OMEGA, f"⟨|ω|⟩ ({self.window_text()})", self.options["show_raw"])
        self.shade_jams()
        self.shade_window()
        if self.ks is not None and np.isfinite(self.ks.w_mean):
            self.suffix(f"{self.window_text()} · media en la ventana = {self.ks.w_mean:.2f} °/s")


class EnergyPlot(TimePlot):
    pid, title = "energy", "Energía cinética del conjunto: traslación + rotación"
    OPTIONS = (Opt("show_parts", "Traslación y rotación", True), Opt("show_jams", "Sombrear atascos", False),
               Opt("log_y", "Log Y", False))

    def draw(self):
        self.reset()
        md = self.md
        if md is None:
            return
        e = md.energy()
        if e is None:
            self.suffix("las trayectorias no tienen ω (re-exportar con VidFetch)")
            return
        e_tr, e_rot = e
        s = md.settings
        unit = md.energy_unit
        self.plot.setLabel("left", "E" if s.mass_g > 0 else "E / m", units=unit)
        t = md.frame_minutes
        self.curve(t, md.smooth(e_tr + e_rot), pg.mkPen(C_ETOT, width=2.5), "total")
        if self.options["show_parts"]:
            self.curve(t, md.smooth(e_tr), pg.mkPen(C_ETR, width=1.5), "traslación Σ½mv²")
            self.curve(t, md.smooth(e_rot), pg.mkPen(C_EROT, width=1.5), "rotación Σ½Iω²")
        self.shade_jams()
        self.shade_window()
        ks = self.ks
        txt = (f"{self.window_text()} · {md.robots.n_robots} robots · I = {s.k_inertia:g}·m·R², "
               f"R = {md.robots.diameter_mm / 2:g} mm · " + (f"m = {s.mass_g:g} g" if s.mass_g > 0 else "por unidad de masa"))
        if ks is not None and np.isfinite(ks.e_tr) and ks.e_tr > 0:
            txt += (f" · medias: tras. {ks.e_tr:.3g}, rot. {ks.e_rot:.3g}, total {ks.e_tr + ks.e_rot:.3g} {unit} "
                    f"(rot/tras = {ks.e_rot / ks.e_tr:.2f})")
        self.suffix(txt)


# =============================================================================================
# distributions
# =============================================================================================
class DistPlot(VelPlot):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.plot.setLabel("bottom", "v", units="mm/s")
        self.item = pg.PlotDataItem(pen=pg.mkPen(C_SPEED, width=1.5))
        self.plot.addItem(self.item)
        self.vline = pg.InfiniteLine(angle=90, pen=pg.mkPen(C_THR, style=Qt.PenStyle.DashLine, width=1.5))
        self.plot.addItem(self.vline, ignoreBounds=True)

    def source(self) -> str:
        return SOURCES.get(self.options.get("source"), "colectiva")

    def dist(self):
        return self.ks.dist.get(self.source()) if self.ks is not None else None

    def draw(self):
        self.plot.setLogMode(x=bool(self.options.get("log_x", False)), y=bool(self.options.get("log_y", False)))
        d = self.dist()
        if d is None or d.n < 2:
            self.item.setData([], [])
            self.vline.hide()
            self.suffix("sin datos en la ventana" if self.md is not None else "")
            return
        self.fill(d)
        txt = f"n = {d.n} {COUNT_LABEL[self.source()]}"
        if self.md.settings.dist_smoothed:
            txt += (f" · <span style='color:#b00'>de V̄ suavizada {self.md.settings.smooth_s:g} s "
                    f"(cambia ancho y colas)</span>" if self.source() == "colectiva"
                    else " · (el suavizado solo se aplica a V̄ por cuadro)")
        self.suffix(txt)
        mob = self.md.settings.mobility
        # The threshold applies to the smoothed collective statistic: comparable to the V̄
        # distribution only when the criterion uses the mean.
        if self.options.get("mark_thr", True) and self.source() == "colectiva" and mob.statistic == "media":
            v = mob.v_threshold_mm_s
            self.vline.setValue(np.log10(v) if self.options.get("log_x", False) else v)
            self.vline.show()
        else:
            self.vline.hide()

    def fill(self, d) -> None:
        pass


class HistPlot(DistPlot):
    pid, title = "hist_v", "Histograma de velocidades medias"
    OPTIONS = (Opt("source", "Datos", "V̄ por cuadro (media entre robots)", tuple(SOURCES)),
               Opt("log_y", "Log Y", False), Opt("mark_thr", "Marcar umbral", True))

    def fill(self, d):
        self.plot.setLabel("left", "número de " + COUNT_LABEL[self.source()])
        edges, cnt = d.hist
        if self.options["log_y"]:
            xs = np.repeat(edges, 2)[1:-1]
            ys = np.repeat(np.where(cnt > 0, cnt, np.nan), 2)
            self.item.setFillLevel(None)
            self.item.setBrush(None)
            self.item.setData(xs, ys, connect="finite", stepMode=None)
        else:
            self.item.setFillLevel(0)
            self.item.setBrush(pg.mkBrush(42, 127, 98, 70))
            self.item.setData(edges, cnt, stepMode="center")


class PdfPlot(DistPlot):
    pid, title = "pdf_v", "Densidad de probabilidad P(v)"
    OPTIONS = (Opt("source", "Datos", "V̄ por cuadro (media entre robots)", tuple(SOURCES)),
               Opt("log_x", "Log X (clases logarítmicas)", False), Opt("log_y", "Log Y", True),
               Opt("mark_thr", "Marcar umbral", True))

    def __init__(self, parent=None):
        super().__init__(parent)
        self.plot.setLabel("left", "P(v)", units="s/mm")
        self.item.setSymbol("o")
        self.item.setSymbolSize(5)
        self.item.setSymbolBrush(pg.mkBrush(C_SPEED))
        self.item.setSymbolPen(None)

    def fill(self, d):
        x, y = d.pdf_log if self.options["log_x"] else d.pdf
        self.item.setData(_safe(x, self.options["log_x"]), _safe(y, self.options["log_y"]), connect="finite")


class CcdfPlot(DistPlot):
    pid, title = "ccdf_v", "1 − F(v) = P(V ≥ v)"
    OPTIONS = (Opt("source", "Datos", "V̄ por cuadro (media entre robots)", tuple(SOURCES)),
               Opt("log_x", "Log X", False), Opt("log_y", "Log Y", True), Opt("mark_thr", "Marcar umbral", True))

    def __init__(self, parent=None):
        super().__init__(parent)
        self.plot.setLabel("left", "1 − F(v)")

    def fill(self, d):
        x, y = decimate_survival(*d.ccdf)
        self.item.setData(_safe(x, self.options["log_x"]), _safe(y, self.options["log_y"]), connect="finite")


# =============================================================================================
# occupancy map
# =============================================================================================
def _viridis() -> pg.ColorMap:
    try:
        return pg.colormap.get("viridis")
    except Exception:   # older pyqtgraph without bundled maps
        return pg.ColorMap(np.linspace(0, 1, 5), [(68, 1, 84), (59, 82, 139), (33, 145, 140),
                                                   (94, 201, 98), (253, 231, 37)])


class HeatPlot(VelPlot):
    """Mean number of robot centres per cm² (x, y in the enclosure frame, observer view: the
    observer stands at the bottom of the map, y = −R, looking towards +y)."""

    pid, title = "heat", "Mapa de ocupación: dónde se acumulan los robots"
    OPTIONS = (Opt("subset", "Cuadros", "todo", SUBSETS), Opt("log_c", "Color log", False),
               Opt("show_ring", "Pared del recinto", True))

    def __init__(self, parent=None):
        super().__init__(parent)
        self.plot.setAspectLocked(True)
        self.plot.showGrid(x=False, y=False)
        self.plot.setLabel("bottom", "x", units="mm")
        self.plot.setLabel("left", "y", units="mm")
        self.img = pg.ImageItem()
        self.img.setZValue(-20)
        self.plot.addItem(self.img)
        self.ring = pg.PlotDataItem(pen=pg.mkPen((235, 235, 235), width=2))
        self.ring.setZValue(10)
        self.plot.addItem(self.ring)
        self.obs = pg.TextItem("observador", color=(90, 90, 90), anchor=(0.5, 0))
        self.plot.addItem(self.obs)
        self.cbar = pg.ColorBarItem(values=(0, 1), colorMap=_viridis(), interactive=False, width=14)
        self.cbar.setImageItem(self.img, insert_in=self.plot)
        self.cbar.axis.enableAutoSIPrefix(False)
        self._R = 92.5

    def draw(self):
        k, subset = self.ks, self.options["subset"]
        if k is None or subset not in k.heat:
            self.img.clear()
            self.ring.setData([], [])
            self.suffix("" if k is None else "sin cuadros de video en la ventana" if k.n_frames < 2
                        else "las trayectorias no tienen x_mm, y_mm (re-exportar con VidFetch)" if not k.heat
                        else f"sin cuadros de «{subset}»")
            return
        H, xe, ye = k.heat[subset]
        log = bool(self.options["log_c"])
        with np.errstate(divide="ignore", invalid="ignore"):
            img = np.where(H > 0, np.log10(H), np.nan) if log else H.astype(float)
        fin = img[np.isfinite(img)]
        lo, hi = (float(fin.min()), float(fin.max())) if len(fin) else (0.0, 1.0)
        hi = max(hi, lo + 1e-9)
        self.img.setImage(img, autoLevels=False, levels=(lo, hi))
        self.img.setRect(QRectF(float(xe[0]), float(ye[0]), float(xe[-1] - xe[0]), float(ye[-1] - ye[0])))
        self.cbar.setLevels((lo, hi))
        self.cbar.axis.setLabel("log₁₀(robots/cm²)" if log else "robots/cm²")
        R = self.md.robots.r_int_mm if np.isfinite(self.md.robots.r_int_mm) else float(xe[-1])
        a = np.linspace(0, 2 * np.pi, 361)
        self.ring.setData(*(R * np.cos(a), R * np.sin(a)) if self.options["show_ring"] else ([], []))
        self.obs.setPos(0.0, -R - 2.0)
        if R != self._R:
            self._R = R
            self.autorange()
        self.suffix(f"{subset}: {k.heat_frames.get(subset, 0)} cuadros · celda {xe[1] - xe[0]:.1f} mm · "
                    f"densidad media del recinto {self.md.robots.n_robots / (np.pi * R * R / 100):.3f} robots/cm²")

    def autorange(self) -> None:
        R = self._R
        self.plot.setRange(xRange=(-R - 4, R + 4), yRange=(-R - 16, R + 4), padding=0)


PLOT_CLASSES = (VMeanPlot, OmegaPlot, EnergyPlot, VPressurePlot, VJamPlot, HistPlot, PdfPlot, CcdfPlot,
                HeatPlot)
TAB_NAMES = {"vmean": "V̄(t)", "omega": "⟨|ω|⟩(t)", "energy": "Energía cinética", "v_G": "V̄ y presión",
             "v_jam": "Umbral de atasco", "hist_v": "Histograma", "pdf_v": "P(v)", "ccdf_v": "1 − F(v)",
             "heat": "Mapa de ocupación"}
