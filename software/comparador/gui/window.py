"""Comparador main window: pick trials, common parameters, one tab per overlaid plot."""

from __future__ import annotations

import copy
import threading
from dataclasses import asdict
from pathlib import Path

import numpy as np
import pandas as pd
import pyqtgraph as pg
from PySide6.QtCore import QSettings, Qt, QTimer
from PySide6.QtGui import QBrush, QColor, QIcon, QPixmap
from PySide6.QtWidgets import (QAbstractItemView, QCheckBox, QComboBox, QFileDialog, QFormLayout,
                               QGroupBox, QHBoxLayout, QLabel, QListWidget, QListWidgetItem,
                               QMainWindow, QMessageBox, QPushButton, QScrollArea, QSpinBox,
                               QSplitter, QTableWidget, QTableWidgetItem, QTabWidget, QVBoxLayout,
                               QWidget)

from comun import estilo, paths
from comun.mobility import STAT_LABELS
from comun.qt.widgets import dspin, note
from comun.qt.worker import LatestJobRunner
from comun.summary import trials_with_trajectories
from comparador import core

pg.setConfigOptions(antialias=True, background="#fcfcfb", foreground=estilo.INK2)

TABS = [("v", "V̄(t)"), ("w", "⟨|ω|⟩(t)"), ("e", "Energía cinética"), ("hist", "Histograma"),
        ("pdf", "P(v)"), ("ccdf", "1 − F(v)"), ("vg", "G vs V̄"), ("tabla", "Resumen")]


class PlotTab(QWidget):
    """A pyqtgraph plot with a row of options above it and a hover read-out."""

    def __init__(self, options: list[tuple[str, str, bool]], parent=None):
        super().__init__(parent)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(4, 4, 4, 4)
        row = QHBoxLayout()
        self.title = QLabel()
        self.title.setWordWrap(True)
        lay.addWidget(self.title)
        self.checks: dict[str, QCheckBox] = {}
        for key, text, on in options:
            cb = QCheckBox(text)
            cb.setChecked(on)
            self.checks[key] = cb
            row.addWidget(cb)
        row.addStretch(1)
        self.readout = QLabel()
        self.readout.setStyleSheet(f"color:{estilo.INK2};")
        row.addWidget(self.readout)
        lay.addLayout(row)
        self.plot = pg.PlotWidget()
        self.plot.showGrid(x=True, y=True, alpha=0.25)
        self.legend = self.plot.addLegend(offset=(-10, 10), labelTextColor=estilo.INK)
        lay.addWidget(self.plot, 1)
        self.plot.scene().sigMouseMoved.connect(self._moved)
        self._fmt = ("x", "y")

    def opt(self, key: str) -> bool:
        return self.checks[key].isChecked()

    def set_axes(self, x: str, y: str, logx: bool = False, logy: bool = False) -> None:
        self.plot.setLabel("bottom", x)
        self.plot.setLabel("left", y)
        self.plot.setLogMode(logx, logy)
        self._fmt = (x.split(" [")[0], y.split(" [")[0])
        self._log = (logx, logy)

    def clear(self) -> None:
        self.plot.clear()
        self.legend.clear()

    def _moved(self, pos) -> None:
        vb = self.plot.getPlotItem().vb
        if not self.plot.sceneBoundingRect().contains(pos):
            return
        p = vb.mapSceneToView(pos)
        x, y = p.x(), p.y()
        lx, ly = getattr(self, "_log", (False, False))
        x, y = (10 ** x if lx else x), (10 ** y if ly else y)
        self.readout.setText(f"{self._fmt[0]} = {x:.4g}   {self._fmt[1]} = {y:.4g}")


class ComparadorWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Comparador de ensayos")
        self.opts = core.Options()
        self._cache: dict[str, object] = {}          # code -> MobilityData (worker thread only)
        self._lock = threading.Lock()
        self.curves: list[core.TrialCurves] = []
        self.runner = LatestJobRunner(self)
        self.runner.finished.connect(self._computed)
        self.runner.failed.connect(lambda tag, msg: self.statusBar().showMessage(f"Error: {msg}"))
        self._timer = QTimer(self, singleShot=True, interval=250)
        self._timer.timeout.connect(self.recompute)

        split = QSplitter()
        split.addWidget(self._side())
        self.tabs = QTabWidget()
        self.plots: dict[str, PlotTab] = {}
        tab_opts = {
            "v": [("jams", "Sombrear atascos", False), ("raw", "Sin suavizar (gris)", False)],
            "w": [("jams", "Sombrear atascos", False)],
            "e": [("split", "Traslación (—) y rotación (···)", False), ("logy", "Log Y", False)],
            "hist": [],
            "pdf": [("logy", "Log Y", True), ("logx", "Clases logarítmicas (log X)", False)],
            "ccdf": [("logy", "Log Y", True), ("logx", "Log X", False)],
            "vg": [("logy", "Log Y", True), ("iqr", "Rango intercuartil", True)],
        }
        for key, name in TABS:
            if key == "tabla":
                self.table = QTableWidget()
                self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
                self.table.setSortingEnabled(True)
                w = QWidget()
                lay = QVBoxLayout(w)
                lay.addWidget(note("Un renglón por ensayo con los mismos parámetros para todos (los de la "
                                   "izquierda). Atasco, capa de pared y saturado en % del tiempo usado."))
                lay.addWidget(self.table)
                self.tabs.addTab(w, name)
                continue
            t = PlotTab(tab_opts[key])
            for cb in t.checks.values():
                cb.toggled.connect(self.redraw)
            self.plots[key] = t
            self.tabs.addTab(t, name)
        split.addWidget(self.tabs)
        split.setStretchFactor(1, 1)
        split.setSizes([390, 1100])
        self.setCentralWidget(split)
        self._restore()
        self.reload_list()

    # ------------------------------------------------------------------------------ side panel
    def _side(self) -> QWidget:
        inner = QWidget()
        lay = QVBoxLayout(inner)
        lay.addWidget(QLabel("<b>Ensayos con trayectorias (VidFetch)</b>"))
        self.list = QListWidget()
        self.list.setMinimumHeight(180)
        self.list.itemChanged.connect(lambda *_: self._timer.start())
        lay.addWidget(self.list)
        row = QHBoxLayout()
        for text, fn in (("Todos", lambda: self._check_all(True)), ("Ninguno", lambda: self._check_all(False)),
                         ("Recargar", self.reload_list)):
            b = QPushButton(text)
            b.clicked.connect(fn)
            row.addWidget(b)
        lay.addLayout(row)
        lay.addWidget(note("Clic en una entrada de la leyenda: ocultar o mostrar esa curva. "
                           "Clic derecho en un gráfico: escala, exportar imagen o datos."))

        o = self.opts
        g = QGroupBox("Series de tiempo y distribuciones")
        f = QFormLayout(g)
        self.smooth = dspin(0, 600, 1, 5, "s", "Media móvil centrada de las series de tiempo y de V̄–G")
        self.source = QComboBox()
        for k, v in core.SOURCES.items():
            self.source.addItem(v, k)
        self.dist_s = QCheckBox("Distribución de V̄ suavizada")
        self.dist_s.setToolTip("Cambia el ancho y las colas de la distribución.")
        self.bins = QSpinBox()
        self.bins.setRange(5, 400)
        self.norm = QCheckBox("1 − F de v dividida por su media")
        f.addRow("Media móvil", self.smooth)
        f.addRow("Distribución de", self.source)
        f.addRow("", self.dist_s)
        f.addRow("Clases", self.bins)
        f.addRow("", self.norm)
        lay.addWidget(g)

        g = QGroupBox("Atascos (mismo criterio que Velocidades)")
        f = QFormLayout(g)
        self.stat = QComboBox()
        for k, v in STAT_LABELS.items():
            self.stat.addItem(v, k)
        self.thr = dspin(0.001, 50, 3, 0.01, "mm/s")
        self.jam_s = dspin(0, 600, 1, 5, "s", "Mediana móvil del estadístico antes de comparar con el umbral")
        self.jam_min = dspin(0, 3600, 1, 5, "s")
        f.addRow("Estadístico", self.stat)
        f.addRow("Umbral", self.thr)
        f.addRow("Suavizado", self.jam_s)
        f.addRow("Duración mínima", self.jam_min)
        lay.addWidget(g)

        g = QGroupBox("G vs V̄ y energía")
        f = QFormLayout(g)
        self.vg_bins = QSpinBox()
        self.vg_bins.setRange(3, 200)
        self.vg_min = QSpinBox()
        self.vg_min.setRange(1, 100000)
        self.vg_min.setSuffix(" cuadros")
        self.mass = dspin(0, 1000, 2, 0.5, "g", "0 = energía por unidad de masa [µJ/kg]")
        self.mass.setSpecialValueText("por unidad de masa")
        self.k_in = dspin(0.01, 1, 2, 0.05, "", "I = k m R² (0,5 = disco uniforme: suposición)")
        self.own_win = QCheckBox("Ventana guardada en Velocidades")
        self.own_win.setToolTip("Si no, se usa el video completo de cada ensayo.")
        f.addRow("Clases de V̄", self.vg_bins)
        f.addRow("Mínimo por clase", self.vg_min)
        f.addRow("Masa del robot", self.mass)
        f.addRow("k (inercia)", self.k_in)
        f.addRow("", self.own_win)
        lay.addWidget(g)

        g = QGroupBox("Exportar")
        f = QFormLayout(g)
        self.width = QComboBox()
        for k, cm in estilo.WIDTH_CM.items():
            self.width.addItem(f"{k} ({cm:g} cm)", k)
        self.width.setCurrentIndex(1)
        b_fig = QPushButton("Figura de la pestaña (PDF/PNG/SVG)…")
        b_fig.clicked.connect(self.export_figure)
        b_tab = QPushButton("Resumen completo (CSV)…")
        b_tab.clicked.connect(self.export_table)
        b_cur = QPushButton("Series de tiempo (CSV)…")
        b_cur.clicked.connect(self.export_series)
        f.addRow("Ancho", self.width)
        f.addRow(b_fig)
        f.addRow(b_tab)
        f.addRow(b_cur)
        lay.addWidget(g)
        lay.addStretch(1)

        self._load_opts(o)
        for w in (self.smooth, self.thr, self.jam_s, self.jam_min, self.mass, self.k_in):
            w.valueChanged.connect(self._timer.start)
        for w in (self.bins, self.vg_bins, self.vg_min):
            w.valueChanged.connect(self._timer.start)
        for w in (self.source, self.stat):
            w.currentIndexChanged.connect(self._timer.start)
        for w in (self.dist_s, self.norm, self.own_win):
            w.toggled.connect(self._timer.start)

        sc = QScrollArea()
        sc.setWidgetResizable(True)
        sc.setWidget(inner)
        sc.setMinimumWidth(370)
        return sc

    def _load_opts(self, o: core.Options) -> None:
        self.smooth.setValue(o.smooth_s)
        self.source.setCurrentIndex(max(0, self.source.findData(o.source)))
        self.dist_s.setChecked(o.dist_smoothed)
        self.bins.setValue(o.bins)
        self.norm.setChecked(o.normalize_ccdf)
        self.stat.setCurrentIndex(max(0, self.stat.findData(o.statistic)))
        self.thr.setValue(o.threshold_mm_s)
        self.jam_s.setValue(o.jam_smooth_s)
        self.jam_min.setValue(o.jam_min_s)
        self.vg_bins.setValue(o.vg_bins)
        self.vg_min.setValue(o.vg_min_frames)
        self.mass.setValue(o.mass_g)
        self.k_in.setValue(o.k_inertia)
        self.own_win.setChecked(o.own_window)

    def _read_opts(self) -> core.Options:
        return core.Options(self.smooth.value(), self.source.currentData(), self.dist_s.isChecked(),
                            self.bins.value(), self.norm.isChecked(), self.stat.currentData(),
                            self.thr.value(), self.jam_s.value(), self.jam_min.value(),
                            self.vg_bins.value(), self.vg_min.value(), self.mass.value(),
                            self.k_in.value(), self.own_win.isChecked())

    # ------------------------------------------------------------------------------ trial list
    def reload_list(self) -> None:
        checked = set(self.checked_codes()) or set(QSettings("ITBA", "Comparador").value("checked", []) or [])
        self.list.blockSignals(True)
        self.list.clear()
        self._index: dict[str, int] = {}
        for i, tr in enumerate(trials_with_trajectories()):
            self._index[tr.code] = i
            color, _ = estilo.series_style(i)
            pm = QPixmap(14, 14)
            pm.fill(QColor(color))
            it = QListWidgetItem(QIcon(pm), tr.label)
            it.setData(Qt.ItemDataRole.UserRole, tr)
            it.setFlags(it.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            it.setCheckState(Qt.CheckState.Checked if tr.code in checked else Qt.CheckState.Unchecked)
            self.list.addItem(it)
        self.list.blockSignals(False)
        with self._lock:
            self._cache.clear()       # files may have changed
        self.recompute()

    def _check_all(self, on: bool) -> None:
        self.list.blockSignals(True)
        for i in range(self.list.count()):
            self.list.item(i).setCheckState(Qt.CheckState.Checked if on else Qt.CheckState.Unchecked)
        self.list.blockSignals(False)
        self.recompute()

    def checked_trials(self) -> list:
        return [self.list.item(i).data(Qt.ItemDataRole.UserRole) for i in range(self.list.count())
                if self.list.item(i).checkState() == Qt.CheckState.Checked]

    def checked_codes(self) -> list[str]:
        return [t.code for t in self.checked_trials()] if self.list.count() else []

    # ------------------------------------------------------------------------------ compute
    def recompute(self) -> None:
        self.opts = self._read_opts()
        trials, opts = self.checked_trials(), copy.deepcopy(self.opts)

        def job():
            out, errors = [], []
            for tr in trials:
                try:
                    with self._lock:
                        md = self._cache.get(tr.code)
                    if md is None:
                        md = core.open_trial(tr)
                        with self._lock:
                            self._cache[tr.code] = md
                    out.append(core.curves(md, opts))
                except Exception as exc:
                    errors.append(f"{tr.code}: {exc}")
            return out, errors
        self.statusBar().showMessage(f"Calculando {len(trials)} ensayo(s)…")
        self.runner.submit("curves", job)

    def _computed(self, tag, result) -> None:
        self.curves, errors = result
        self.redraw()
        msg = f"{len(self.curves)} ensayo(s)."
        notes = [f"{c.code}: {c.pressure_note}" for c in self.curves if c.pressure_note]
        if errors or notes:
            msg += "  " + " | ".join(errors + notes)
        self.statusBar().showMessage(msg)

    # ------------------------------------------------------------------------------ drawing
    def _pen(self, c: core.TrialCurves, style=None, width=2.0):
        color, _ = estilo.series_style(self._index.get(c.code, 0))
        dash = style if style is not None else estilo.qt_dash(self._index.get(c.code, 0))
        return pg.mkPen(color, width=width, style=dash)

    def _name(self, c: core.TrialCurves) -> str:
        return c.label.rsplit(" · ", 1)[0]          # drop the nominal minutes

    def redraw(self) -> None:
        o, C = self.opts, self.curves
        for t in self.plots.values():
            t.clear()
        sm = f"media móvil {o.smooth_s:g} s" if o.smooth_s > 0 else "sin suavizar"
        src = core.SOURCES[o.source] + (" suavizada" if o.dist_smoothed and o.source == "colectiva" else "")

        # --- V̄(t), <|ω|>(t), energy -----------------------------------------------------
        t = self.plots["v"]
        t.title.setText(f"<b>V̄(t)</b>: velocidad media del conjunto ({sm}); umbral de atasco en violeta")
        t.set_axes("t video [min]", "V̄ [mm/s]")
        for c in C:
            if t.opt("raw"):
                t.plot.plot(c.t_min, c.v, pen=pg.mkPen("#c9c8c3", width=1), connect="finite")
            self._shade(t, c)
            t.plot.plot(c.t_min, c.v_s, pen=self._pen(c), name=self._name(c), connect="finite")
        if C:
            t.plot.addItem(pg.InfiniteLine(o.threshold_mm_s, angle=0,
                                           pen=pg.mkPen("#6250d6", width=1, style=Qt.PenStyle.DashLine)))

        t = self.plots["w"]
        t.title.setText(f"<b>⟨|ω|⟩(t)</b>: giro propio medio de los robots ({sm})")
        t.set_axes("t video [min]", "⟨|ω|⟩ [°/s]")
        for c in C:
            if c.w_s is not None:
                self._shade(t, c)
                t.plot.plot(c.t_min, c.w_s, pen=self._pen(c), name=self._name(c), connect="finite")

        t = self.plots["e"]
        unit = C[0].energy_unit if C else "µJ/kg"
        lab = "E [nJ]" if unit == "nJ" else "E / m [µJ/kg]"
        t.title.setText(f"<b>Energía cinética del conjunto</b> ({sm}; I = {o.k_inertia:g} m R²)")
        t.set_axes("t video [min]", lab, logy=t.opt("logy"))
        for c in C:
            if c.e_tr_s is None:
                continue
            if t.opt("split"):
                t.plot.plot(c.t_min, self._pos(c.e_tr_s, t.opt("logy")), pen=self._pen(c, Qt.PenStyle.SolidLine),
                            name=self._name(c), connect="finite")
                t.plot.plot(c.t_min, self._pos(c.e_rot_s, t.opt("logy")), pen=self._pen(c, Qt.PenStyle.DotLine),
                            connect="finite")
            else:
                t.plot.plot(c.t_min, self._pos(c.e_tr_s + c.e_rot_s, t.opt("logy")), pen=self._pen(c),
                            name=self._name(c), connect="finite")

        # --- distributions ---------------------------------------------------------------
        sets = [c.samples for c in C]
        edges = core.common_edges(sets, o.bins)
        t = self.plots["hist"]
        t.title.setText(f"<b>Histograma</b>: {src} (clases comunes a todos los ensayos)")
        t.set_axes("v [mm/s]", "fracción de las muestras")
        for c in C:
            if len(c.samples):
                x, y = core.hist_fraction(c.samples, edges)
                t.plot.plot(edges, y, stepMode="center", pen=self._pen(c), name=self._name(c))

        t = self.plots["pdf"]
        logx = t.opt("logx")
        t.title.setText(f"<b>P(v)</b>: densidad de probabilidad, {src}")
        t.set_axes("v [mm/s]", "P(v) [s/mm]", logx=logx, logy=t.opt("logy"))
        for c in C:
            if len(c.samples):
                x, y = core.pdf(c.samples, edges, log_bins=logx)
                ok = (y > 0) if (t.opt("logy") or logx) else np.ones(len(y), bool)
                t.plot.plot(x[ok], y[ok], pen=self._pen(c), symbol="o", symbolSize=5,
                            symbolBrush=self._pen(c).color(), symbolPen=None, name=self._name(c))

        t = self.plots["ccdf"]
        xl = "v / ⟨v⟩" if o.normalize_ccdf else "v [mm/s]"
        t.title.setText(f"<b>1 − F</b> = P(V ≥ v): {src}"
                        + (", normalizada por la media de cada ensayo" if o.normalize_ccdf else ""))
        t.set_axes(xl, "1 − F", logx=t.opt("logx"), logy=t.opt("logy"))
        for c in C:
            x, p = core.ccdf(c.samples, o.normalize_ccdf)
            ok = (x > 0) if t.opt("logx") else np.ones(len(x), bool)
            t.plot.plot(x[ok], p[ok], pen=self._pen(c), name=self._name(c))

        # --- G vs V̄ ------------------------------------------------------------------------
        t = self.plots["vg"]
        ve = core.vg_edges(C, o.vg_bins)
        t.title.setText(f"<b>G mediana por clase de V̄</b> (ambas con {sm}; clases con ≥ {o.vg_min_frames} cuadros; "
                        "ρ = correlación de Spearman)")
        logy = t.opt("logy")
        t.set_axes("V̄ [mm/s]", "G [µS]", logy=logy)
        for c in C:
            x, med, q25, q75, n = core.g_by_v(c, ve, o.vg_min_frames)
            if not len(x):
                continue
            rho = core.correlation_vg(c)
            y = np.where(med > 0, med, np.nan) if logy else med
            pen = self._pen(c)
            t.plot.plot(x, y, pen=pen, symbol="o", symbolSize=7, symbolBrush=pen.color(), connect="finite",
                        symbolPen=pg.mkPen("#fcfcfb", width=1.5), name=f"{self._name(c)}  (ρ = {rho:.2f})")
            ok = np.isfinite(y) & np.isfinite(q25) & np.isfinite(q75)
            if t.opt("iqr") and ok.any():
                lo = np.log10(np.maximum(q25[ok], 1e-12)) if logy else q25[ok]
                hi = np.log10(np.maximum(q75[ok], 1e-12)) if logy else q75[ok]
                mid = np.log10(med[ok]) if logy else med[ok]
                t.plot.addItem(pg.ErrorBarItem(x=x[ok], y=mid, top=hi - mid, bottom=mid - lo, beam=0.0,
                                               pen=pg.mkPen(pen.color(), width=1)))
        self._fill_table()

    @staticmethod
    def _pos(y, log: bool):
        return np.where(y > 0, y, np.nan) if log else y

    def _shade(self, t: PlotTab, c: core.TrialCurves) -> None:
        if "jams" not in t.checks or not t.opt("jams"):
            return
        color = QColor(estilo.series_style(self._index.get(c.code, 0))[0])
        color.setAlpha(45)
        for a, b in c.jam_spans:
            r = pg.LinearRegionItem((a, b), movable=False, brush=QBrush(color), pen=pg.mkPen(None))
            r.setZValue(-10)
            t.plot.addItem(r)

    def _fill_table(self) -> None:
        cols = core.SUMMARY_COLUMNS
        self.table.setSortingEnabled(False)
        self.table.clear()
        self.table.setColumnCount(len(cols))
        self.table.setRowCount(len(self.curves))
        unit = self.curves[0].energy_unit if self.curves else "µJ/kg"
        self.table.setHorizontalHeaderLabels([c[1].replace("unidad", unit) for c in cols])
        for i, cv in enumerate(self.curves):
            row = dict(cv.summary)
            row["rho_vg"] = core.correlation_vg(cv)
            for j, (key, _, spec) in enumerate(cols):
                v = row.get(key)
                it = QTableWidgetItem(self._name(cv) if key == "ensayo" else core.fmt(v, spec))
                try:
                    fv = float(v)
                    if key != "ensayo" and np.isfinite(fv):
                        it.setData(Qt.ItemDataRole.UserRole, fv)
                except (TypeError, ValueError):
                    pass
                if j == 0:
                    pm = QPixmap(12, 12)
                    pm.fill(QColor(estilo.series_style(self._index.get(cv.code, 0))[0]))
                    it.setIcon(QIcon(pm))
                else:
                    it.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
                self.table.setItem(i, j, it)
        self.table.resizeColumnsToContents()
        self.table.setSortingEnabled(True)

    # ------------------------------------------------------------------------------ export
    def _ask_save(self, title: str, name: str, filt: str) -> str:
        st = QSettings("ITBA", "Comparador")
        start = st.value("export_dir", str(paths.REPO_ROOT / "informes"))
        path, _ = QFileDialog.getSaveFileName(self, title, str(Path(start) / name), filt)
        if path:
            st.setValue("export_dir", str(Path(path).parent))
        return path

    def export_figure(self) -> None:
        key = TABS[self.tabs.currentIndex()][0]
        if key == "tabla":
            return self.export_table()
        if not self.curves:
            return
        path = self._ask_save("Exportar figura", f"comparacion_{key}.pdf", "PDF (*.pdf);;PNG (*.png);;SVG (*.svg)")
        if not path:
            return
        from comparador.exportar import figure
        t = self.plots[key]
        flags = {k: cb.isChecked() for k, cb in t.checks.items()}
        try:
            fig = figure(key, self.curves, self.opts, flags, self._index, self.width.currentData())
            ext = Path(path).suffix.lstrip(".") or "pdf"
            estilo.save(fig, path, (ext,))
            self.statusBar().showMessage(f"Figura guardada: {path}")
        except Exception as exc:
            QMessageBox.warning(self, "Exportar figura", f"{type(exc).__name__}: {exc}")

    def export_table(self) -> None:
        if not self.curves:
            return
        path = self._ask_save("Exportar resumen", "comparacion_resumen.csv", "CSV (*.csv)")
        if path:
            rows = []
            for c in self.curves:
                r = dict(c.summary)
                r["rho_V_G_spearman"] = core.correlation_vg(c)
                r.update({f"opcion_{k}": v for k, v in asdict(self.opts).items()})
                rows.append(r)
            pd.DataFrame(rows).to_csv(path, index=False, float_format="%.6g")
            self.statusBar().showMessage(f"Resumen guardado: {path}")

    def export_series(self) -> None:
        if not self.curves:
            return
        path = self._ask_save("Exportar series de tiempo", "comparacion_series.csv", "CSV (*.csv)")
        if not path:
            return
        frames = []
        for c in self.curves:
            d = {"codigo": c.code, "t_video_min": c.t_min, "V_media_mm_s": c.v, "V_media_suav_mm_s": c.v_s}
            if c.w_s is not None:
                d["omega_abs_suav_deg_s"] = c.w_s
            if c.e_tr_s is not None:
                d[f"E_tras_suav_{c.energy_unit}"], d[f"E_rot_suav_{c.energy_unit}"] = c.e_tr_s, c.e_rot_s
            if c.G_s is not None:
                d["G_suav_uS"] = c.G_s
            df = pd.DataFrame(d)
            frames.append(df[c.used])
        pd.concat(frames).to_csv(path, index=False, float_format="%.6g")
        self.statusBar().showMessage(f"Series guardadas: {path}")

    # ------------------------------------------------------------------------------ settings
    def _restore(self) -> None:
        st = QSettings("ITBA", "Comparador")
        g = st.value("geometry")
        if g is not None:
            self.restoreGeometry(g)
        else:
            self.resize(1500, 950)
        d = st.value("options")
        if isinstance(d, dict):
            try:
                self._load_opts(core.Options(**{k: v for k, v in d.items() if k in asdict(core.Options())}))
            except (TypeError, ValueError):
                pass

    def closeEvent(self, ev) -> None:
        st = QSettings("ITBA", "Comparador")
        st.setValue("geometry", self.saveGeometry())
        st.setValue("options", asdict(self._read_opts()))
        st.setValue("checked", self.checked_codes())
        self.runner.shutdown()
        super().closeEvent(ev)
