"""Main window of velocidades.py: trial list and mobility parameters (left), one plot per tab
(center) and a tab with the per-trial summary table."""

from __future__ import annotations

import traceback
from pathlib import Path
from typing import Optional

import numpy as np
import pandas as pd
from PySide6.QtCore import QSettings, Qt, QTimer, Signal
from PySide6.QtGui import QAction, QKeySequence
from PySide6.QtWidgets import (QAbstractItemView, QCheckBox, QComboBox, QDockWidget, QFileDialog, QFormLayout, QGroupBox,
                               QHBoxLayout, QLabel, QListWidget, QListWidgetItem, QMainWindow, QMessageBox,
                               QPushButton, QScrollArea, QSpinBox, QTableWidget, QTableWidgetItem, QTabWidget,
                               QVBoxLayout, QWidget)

from comun.mobility import Mobility, MobilityData, save_vel_settings, vel_config_path
from comun import paths
from comun.summary import trials_with_trajectories, write_summary
from comun.qt.widgets import dspin, note
from velocidades.gui.vel_plots import PLOT_CLASSES, TAB_NAMES, TimePlot, VelPlot
from comun.qt.worker import LatestJobRunner

NONE = -1.0
# Columns shown by default in the summary table (the CSV has all of them).
SUMMARY_COLS = ["ensayo", "modo", "minutos_video_usados", "v_media_mm_s", "v_media_desvio_temporal_mm_s",
                "v_individual_mediana_mm_s", "frac_tiempo_atasco", "n_atascos", "atasco_dur_max_s",
                "v_media_fluido_mm_s", "v_media_atasco_mm_s", "G_media_uS", "G_media_fluido_uS",
                "G_media_atasco_uS", "asimetria_dG", "omega_abs_media_deg_s", "E_traslacion_media",
                "E_rotacion_media", "E_total_media", "E_rot_sobre_E_tras", "energia_unidad", "frac_capa_pared"]


def _fmt(v) -> str:
    if isinstance(v, (float, np.floating)):
        if not np.isfinite(v):
            return ""
        return f"{v:.4g}"
    return str(v)


# =============================================================================================
class SummaryTab(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.b_calc = QPushButton("Calcular resumen de todos los ensayos")
        self.b_calc.setStyleSheet("font-weight:600;")
        self.b_open = QPushButton("Abrir CSV…")
        self.b_all = QPushButton("Mostrar todas las columnas")
        self.b_all.setCheckable(True)
        self.b_all.toggled.connect(lambda _: self.show_df(self.df))
        self.info = note()
        self.table = QTableWidget()
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setSortingEnabled(True)
        self.table.setAlternatingRowColors(True)
        row = QHBoxLayout()
        for b in (self.b_calc, self.b_open, self.b_all):
            row.addWidget(b)
        row.addStretch(1)
        lay = QVBoxLayout(self)
        lay.addWidget(note("Una fila por ensayo con sus valores medios (no por robot). Cada ensayo usa su "
                           "configuración guardada: ventana y umbral de esta aplicación "
                           "(datos/video/config/) y calibración, recorte y exclusiones de FSRScope para G. "
                           "El ensayo abierto entra con lo que se ve en pantalla."))
        lay.addLayout(row)
        lay.addWidget(self.info)
        lay.addWidget(self.table, 1)
        self.df: Optional[pd.DataFrame] = None
        self.path: Optional[Path] = None

    def load_csv(self, path: Path) -> None:
        try:
            self.df, self.path = pd.read_csv(path), Path(path)
        except Exception as exc:
            self.info.setText(f"No se pudo leer {path}: {exc}")
            return
        self.show_df(self.df)

    def show_df(self, df: Optional[pd.DataFrame]) -> None:
        if df is None:
            return
        cols = list(df.columns) if self.b_all.isChecked() else [c for c in SUMMARY_COLS if c in df.columns]
        self.table.setSortingEnabled(False)
        self.table.clear()
        self.table.setRowCount(len(df))
        self.table.setColumnCount(len(cols))
        self.table.setHorizontalHeaderLabels(cols)
        for i, (_, r) in enumerate(df.iterrows()):
            for j, c in enumerate(cols):
                v = r[c]
                it = QTableWidgetItem()
                if isinstance(v, (int, float, np.integer, np.floating)) and np.isfinite(v):
                    it.setData(Qt.ItemDataRole.DisplayRole, float(f"{float(v):.4g}"))
                else:
                    it.setText(_fmt(v) if not (isinstance(v, float) and np.isnan(v)) else "")
                self.table.setItem(i, j, it)
        self.table.resizeColumnsToContents()
        self.table.setSortingEnabled(True)
        self.info.setText(f"{len(df)} ensayos · {len(df.columns)} columnas"
                          + (f" · {self.path}" if self.path else ""))


# =============================================================================================
class DetachedWindow(QMainWindow):
    """A plot in its own window; closing it hands the plot back to its tab."""

    closed = Signal(object)

    def __init__(self, plot: VelPlot, title: str, parent=None):
        super().__init__(parent)
        self.plot = plot
        self.setWindowTitle(title)
        self.setCentralWidget(plot)
        self.resize(1050, 650)

    def closeEvent(self, ev) -> None:
        self.takeCentralWidget()
        self.closed.emit(self.plot)
        super().closeEvent(ev)


# =============================================================================================
class VelWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Velocidades de los robots")
        self.resize(1500, 900)
        self.md: Optional[MobilityData] = None
        self._saved_json = ""
        self.loader = LatestJobRunner(self)
        self.loader.finished.connect(self._on_loaded)
        self.loader.failed.connect(self._on_load_failed)
        self.batch = LatestJobRunner(self)
        self.batch.finished.connect(self._on_summary_done)
        self.batch.failed.connect(lambda tag, msg: QMessageBox.critical(self, "Resumen", msg))

        # --- center: one plot per tab --------------------------------------------------------
        self.tabs = QTabWidget()
        self.plots: dict[str, VelPlot] = {}
        self._detached: dict[str, DetachedWindow] = {}
        for cls in PLOT_CLASSES:
            p = cls()
            p.optionsChanged.connect(self._on_plot_options)
            p.detachRequested.connect(self._detach)
            self.plots[p.pid] = p
            self.tabs.addTab(p, TAB_NAMES[p.pid])
        self.plots["v_jam"].thresholdChanged.connect(self._on_threshold_dropped)
        self.summary_tab = SummaryTab()
        self.summary_tab.b_calc.clicked.connect(self.compute_summary)
        self.summary_tab.b_open.clicked.connect(self._open_summary_csv)
        self.tabs.addTab(self.summary_tab, "Resumen de ensayos")
        self.tabs.currentChanged.connect(self._on_tab)
        self.setCentralWidget(self.tabs)
        if paths.SUMMARY_PATH.is_file():
            self.summary_tab.load_csv(paths.SUMMARY_PATH)

        # --- left dock ---------------------------------------------------------------------------
        self.dock = QDockWidget("Ensayo y parámetros", self)
        self.dock.setObjectName("dock_params")
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(self._build_params())
        self.dock.setWidget(scroll)
        self.addDockWidget(Qt.DockWidgetArea.LeftDockWidgetArea, self.dock)
        self.resizeDocks([self.dock], [360], Qt.Orientation.Horizontal)
        self._build_menu()

        self.recalc = QTimer(self, singleShot=True, interval=120)
        self.recalc.timeout.connect(self.update_stats)
        st = QSettings("ITBA", "Velocidades")
        if st.value("geometry") is not None:
            self.restoreGeometry(st.value("geometry"))
            self.restoreState(st.value("state"))
        last = st.value("last_code")
        if last:
            for i in range(self.list.count()):
                if self.list.item(i).data(Qt.ItemDataRole.UserRole).code == last:
                    self.list.setCurrentRow(i)
                    QTimer.singleShot(0, lambda it=self.list.item(i): self._pick(it))
        self.statusBar().showMessage("Elegí un ensayo de la lista.")

    # =========================================================================================
    def _build_params(self) -> QWidget:
        self.list = QListWidget()
        self.list.itemClicked.connect(self._pick)
        self.list.itemActivated.connect(self._pick)
        for tr in trials_with_trajectories():
            it = QListWidgetItem(tr.label + ("   [config]" if vel_config_path(tr).is_file() else ""))
            it.setData(Qt.ItemDataRole.UserRole, tr)
            it.setToolTip(str(tr.traj_path))
            self.list.addItem(it)
        self.info = note()

        self.stat = QComboBox()
        for key, text in (("media", "media entre robots (V̄)"), ("mediana", "mediana entre robots"),
                          ("p90", "percentil 90 entre robots")):
            self.stat.addItem(text, key)
        self.thr = dspin(0.001, 50, 3, 0.01, "mm/s", "Por debajo de este valor (suavizado) es atasco. También "
                                                      "se ajusta arrastrando la línea de «Umbral de atasco».")
        self.smooth = dspin(0, 600, 1, 5, "s", "Mediana móvil centrada antes de comparar con el umbral")
        self.min_dur = dspin(0, 3600, 1, 5, "s", "Duración mínima por debajo del umbral")
        f1 = QFormLayout()
        f1.addRow("Estadístico", self.stat)
        f1.addRow("Umbral", self.thr)
        f1.addRow("Suavizado", self.smooth)
        f1.addRow("Duración mínima", self.min_dur)
        b_def = QPushButton("Por defecto (media < 0,35)")
        b_ref = QPushButton("Informes (p90 < 0,52)")
        b_def.clicked.connect(lambda: self._set_criterion(Mobility()))
        b_ref.clicked.connect(lambda: self._set_criterion(Mobility(statistic="p90", v_threshold_mm_s=0.52)))
        r = QHBoxLayout()
        r.addWidget(b_def)
        r.addWidget(b_ref)
        f1.addRow(r)
        g1 = QGroupBox("Umbral de atasco")
        g1.setLayout(f1)

        self.t0 = dspin(NONE, 1e4, 2, 1, "min")
        self.t1 = dspin(NONE, 1e4, 2, 1, "min")
        self.t0.setSpecialValueText("inicio del video")
        self.t1.setSpecialValueText("fin del video")
        f2 = QFormLayout()
        f2.addRow("Desde", self.t0)
        f2.addRow("Hasta", self.t1)
        b_all, b_view = QPushButton("Todo"), QPushButton("Vista actual")
        b_all.clicked.connect(lambda: self._set_window(None, None))
        b_view.clicked.connect(self._window_from_view)
        r2 = QHBoxLayout()
        r2.addWidget(b_all)
        r2.addWidget(b_view)
        f2.addRow(r2)
        g2 = QGroupBox("Ventana de análisis (minutos de video)")
        g2.setLayout(f2)

        self.bins = QSpinBox()
        self.bins.setRange(5, 2000)
        self.bins.setKeyboardTracking(False)
        self.heat_bin = dspin(0.5, 50, 1, 0.5, "mm", "Lado de cada celda del mapa de ocupación")
        f3 = QFormLayout()
        f3.addRow("Clases de histograma / P(v)", self.bins)
        f3.addRow("Celda del mapa", self.heat_bin)
        g3 = QGroupBox("Distribuciones y mapa")
        g3.setLayout(f3)

        self.plot_smooth = dspin(0, 600, 1, 5, "s", "Media móvil centrada de todos los gráficos de tiempo "
                                                   "(la serie cruda queda en gris de fondo). 0 = sin suavizar")
        self.dist_smooth = QCheckBox("Distribuciones de V̄ suavizada")
        self.dist_smooth.setToolTip("Histograma, P(v) y 1 − F(v) de V̄ con la media móvil. Cambia el ancho y las "
                                    "colas (con 30 s el desvío baja ~55 %): úsese solo para comparar.")
        f4 = QFormLayout()
        f4.addRow("Media móvil", self.plot_smooth)
        f4.addRow(self.dist_smooth)
        g4 = QGroupBox("Visualización")
        g4.setLayout(f4)

        self.mass = dspin(0, 1000, 2, 0.5, "g", "Masa de cada robot. 0 = energía por unidad de masa [µJ/kg]")
        self.mass.setSpecialValueText("por unidad de masa")
        self.k_I = dspin(0.01, 1.0, 3, 0.05, "", "I = k·m·R² alrededor del eje propio (0,5 = disco uniforme)")
        f5 = QFormLayout()
        f5.addRow("Masa del robot", self.mass)
        f5.addRow("k (I = k·m·R²)", self.k_I)
        g5 = QGroupBox("Energía cinética")
        g5.setLayout(f5)

        self.result = note()
        for w in (self.thr, self.smooth, self.min_dur, self.t0, self.t1, self.heat_bin, self.plot_smooth,
                  self.mass, self.k_I):
            w.valueChanged.connect(self._on_params)
        self.bins.valueChanged.connect(self._on_params)
        self.stat.currentIndexChanged.connect(self._on_params)
        self.dist_smooth.toggled.connect(self._on_params)
        self._loading = False

        box = QWidget()
        lay = QVBoxLayout(box)
        lay.addWidget(QLabel("Ensayos con trayectorias (VidFetch)"))
        self.list.setMinimumHeight(130)
        lay.addWidget(self.list, 1)
        lay.addWidget(self.info)
        lay.addWidget(g4)
        lay.addWidget(g1)
        lay.addWidget(g2)
        lay.addWidget(g3)
        lay.addWidget(g5)
        lay.addWidget(self.result)
        return box

    def _build_menu(self) -> None:
        m = self.menuBar().addMenu("&Archivo")
        for text, key, fn in (("Guardar configuración del ensayo", QKeySequence.StandardKey.Save, self.save_config),
                              ("Calcular resumen de todos los ensayos", None, self.compute_summary),
                              ("Salir", QKeySequence.StandardKey.Quit, self.close)):
            a = QAction(text, self, triggered=fn)
            if key is not None:
                a.setShortcut(key)
            m.addAction(a)
        v = self.menuBar().addMenu("&Ver")
        v.addAction(self.dock.toggleViewAction())
        v.addAction(QAction("Autoescalar gráfico", self, triggered=self._autorange, shortcut=QKeySequence("Ctrl+0")))

    # =========================================================================================
    # loading
    # =========================================================================================
    def _pick(self, it: QListWidgetItem) -> None:
        tr = it.data(Qt.ItemDataRole.UserRole)
        if self.md is not None and self.md.trial == tr:
            return
        self.save_config(quiet=True)
        self.setCursor(Qt.CursorShape.WaitCursor)
        self.statusBar().showMessage(f"Cargando {tr.code}…")
        self.loader.submit(tr.code, MobilityData.open, tr)

    def _on_load_failed(self, tag, msg: str) -> None:
        self.unsetCursor()
        QMessageBox.critical(self, "No se pudo abrir el ensayo", f"{tag}\n\n{msg}")

    def _on_loaded(self, tag, md: MobilityData) -> None:
        self.unsetCursor()
        self.md = md
        self._load_params()
        for p in self.plots.values():
            p.load_options(md.settings.plots.get(p.pid, {}))
        self._saved_json = md.settings.to_json()
        r = md.robots
        lines = [f"<b>{md.trial.code}</b>",
                 f"{r.n_robots} robots · {len(r.frames)} cuadros · {md.duration_min:.1f} min de video"
                 + (f" · {len(r.parts)} partes (hueco {r.gap_frames} cuadros)" if len(r.parts) > 1 else ""),
                 f"Sincronía (de FSRScope): cuadro 0 = {md.offset_s:.2f} s del sensor, {md.fps:g} cuadros/s"]
        if md.td is None:
            lines.append(f"<span style='color:#b00'>Sin registro del sensor: {md.pressure_error}</span>")
        self.info.setText("<br>".join(lines))
        self.setWindowTitle(f"Velocidades de los robots — {md.trial.label}")
        for pid, w in self._detached.items():
            w.setWindowTitle(f"{TAB_NAMES[pid]} — {md.trial.label}")
        self.update_stats()
        self._autorange()
        self.statusBar().showMessage(f"Abierto {md.trial.code}", 5000)

    def _load_params(self) -> None:
        s, m = self.md.settings, self.md.settings.mobility
        self._loading = True
        self.stat.setCurrentIndex(max(0, self.stat.findData(m.statistic)))
        self.thr.setValue(m.v_threshold_mm_s)
        self.smooth.setValue(m.smooth_s)
        self.min_dur.setValue(m.min_duration_s)
        self.bins.setValue(m.hist_bins)
        self.heat_bin.setValue(m.heat_bin_mm)
        for w in (self.t0, self.t1):
            w.setMaximum(max(self.md.duration_min, 1.0))
        self.t0.setValue(NONE if s.t_start_min is None else s.t_start_min)
        self.t1.setValue(NONE if s.t_end_min is None else s.t_end_min)
        self.plot_smooth.setValue(s.smooth_s)
        self.dist_smooth.setChecked(s.dist_smoothed)
        self.mass.setValue(s.mass_g)
        self.k_I.setValue(s.k_inertia)
        self._loading = False

    # =========================================================================================
    # parameters
    # =========================================================================================
    def _on_params(self, *_) -> None:
        if self._loading or self.md is None:
            return
        s, m = self.md.settings, self.md.settings.mobility
        m.statistic = self.stat.currentData()
        m.v_threshold_mm_s = self.thr.value()
        m.smooth_s, m.min_duration_s = self.smooth.value(), self.min_dur.value()
        m.hist_bins, m.heat_bin_mm = self.bins.value(), self.heat_bin.value()
        s.t_start_min = None if self.t0.value() <= NONE else self.t0.value()
        s.t_end_min = None if self.t1.value() <= NONE else self.t1.value()
        s.smooth_s, s.dist_smoothed = self.plot_smooth.value(), self.dist_smooth.isChecked()
        s.mass_g, s.k_inertia = self.mass.value(), self.k_I.value()
        self.recalc.start()

    def _set_criterion(self, ref: Mobility) -> None:
        self._loading = True
        self.stat.setCurrentIndex(max(0, self.stat.findData(ref.statistic)))
        self.thr.setValue(ref.v_threshold_mm_s)
        self.smooth.setValue(ref.smooth_s)
        self.min_dur.setValue(ref.min_duration_s)
        self._loading = False
        self._on_params()

    def _set_window(self, a: Optional[float], b: Optional[float]) -> None:
        self._loading = True
        self.t0.setValue(NONE if a is None else a)
        self.t1.setValue(NONE if b is None else b)
        self._loading = False
        self._on_params()

    def _window_from_view(self) -> None:
        p = self.tabs.currentWidget()
        if self.md is None or not isinstance(p, TimePlot):
            self.statusBar().showMessage("Elegí un gráfico de tiempo (V̄(t), V̄ y presión o Umbral).", 5000)
            return
        x0, x1 = p.plot.getViewBox().viewRange()[0]
        self._set_window(max(0.0, x0), min(self.md.duration_min, x1))

    def _on_threshold_dropped(self, v: float) -> None:
        if self.md is None:
            return
        self._loading = True
        self.thr.setValue(v)
        self._loading = False
        self._on_params()
        self.statusBar().showMessage(f"Umbral de atasco = {v:.3f} mm/s", 4000)

    def _on_plot_options(self, pid: str, opts: dict) -> None:
        if self.md is not None:
            self.md.settings.plots[pid] = opts

    # =========================================================================================
    # statistics and drawing
    # =========================================================================================
    def update_stats(self) -> None:
        if self.md is None:
            return
        try:
            ks = self.md.stats()
        except Exception as exc:
            self.statusBar().showMessage(f"Error de cálculo: {exc}", 8000)
            traceback.print_exc()
            return
        cur = self.tabs.currentWidget()
        for p in self.plots.values():
            p.set_data(self.md, ks, visible=p is cur or p.pid in self._detached)
        self._show_result(ks)

    def _on_tab(self, _i: int) -> None:
        p = self.tabs.currentWidget()
        if isinstance(p, VelPlot) and p.dirty:
            p.redraw()

    def _show_result(self, k) -> None:
        if k is None or k.n_frames < 2:
            self.result.setText("Sin cuadros de video en la ventana.")
            return
        f = lambda v, d=3: "—" if not np.isfinite(v) else f"{v:.{d}g}"
        d = k.jam_dur_s
        lines = [f"En la ventana: {k.n_frames} cuadros ({k.n_frames / self.md.fps / 60:.1f} min)",
                 f"V̄ media = <b>{f(k.v_mean)} mm/s</b> (desvío temporal {f(k.v_std)})",
                 f"Atascos: <b>{k.n_jams}</b>, {100 * k.jam_frac:.1f} % del tiempo"
                 + (f" (media {d.mean():.0f} s, máx. {d.max():.0f} s)" if len(d) else ""),
                 f"V̄ en flujo / atasco: {f(k.v_mean_fluid)} / {f(k.v_mean_jam)} mm/s"]
        if self.md.td is not None:
            lines.append(f"G media en flujo / atasco: {f(k.G_fluid)} / {f(k.G_jam)} µS")
        if np.isfinite(k.w_mean):
            lines.append(f"⟨|ω|⟩ media = {f(k.w_mean)} °/s")
        if np.isfinite(k.e_tr) and k.e_tr > 0:
            u = self.md.energy_unit
            lines.append(f"Energía cinética media: tras. {f(k.e_tr)}, rot. {f(k.e_rot)} {u} "
                         f"(rot/tras = {k.e_rot / k.e_tr:.2f})")
        self.result.setText("<br>".join(lines))

    # =========================================================================================
    # plots in their own windows
    # =========================================================================================
    def _detach(self, pid: str) -> None:
        if pid in self._detached:
            self._detached[pid].raise_()
            self._detached[pid].activateWindow()
            return
        p = self.plots[pid]
        i = self.tabs.indexOf(p)
        if i >= 0:
            self.tabs.removeTab(i)
        title = TAB_NAMES[pid] + (f" — {self.md.trial.label}" if self.md is not None else "")
        w = DetachedWindow(p, title, self)
        w.closed.connect(self._reattach)
        self._detached[pid] = w
        p.b_detach.setEnabled(False)
        w.show()
        p.show()
        if p.dirty:
            p.redraw()

    def _reattach(self, p: VelPlot) -> None:
        self._detached.pop(p.pid, None)
        order = [c.pid for c in PLOT_CLASSES]
        pos = sum(1 for pid in order[:order.index(p.pid)] if pid not in self._detached)
        self.tabs.insertTab(pos, p, TAB_NAMES[p.pid])
        p.b_detach.setEnabled(True)

    def _autorange(self) -> None:
        for p in self.plots.values():
            p.autorange()
            if hasattr(p, "vb2"):
                p.vb2.enableAutoRange()

    # =========================================================================================
    # summary and persistence
    # =========================================================================================
    def compute_summary(self) -> None:
        if self.batch.busy:
            return
        path, _ = QFileDialog.getSaveFileName(self, "Resumen de todos los ensayos", str(paths.SUMMARY_PATH), "CSV (*.csv)")
        if not path:
            return
        self.save_config(quiet=True)
        current = self.md

        def job():
            lines = []
            out, _ = write_summary(Path(path), lines.append, current=current)
            return out, lines
        self.statusBar().showMessage("Calculando el resumen de los ensayos…")
        self.summary_tab.b_calc.setEnabled(False)
        self.batch.submit("summary", job)

    def _on_summary_done(self, tag, result) -> None:
        out, lines = result
        self.summary_tab.b_calc.setEnabled(True)
        self.summary_tab.load_csv(out)
        self.tabs.setCurrentWidget(self.summary_tab)
        fails = [ln for ln in lines if ln.startswith("FAIL")]
        self.statusBar().showMessage(lines[-1] if lines else "Listo.", 8000)
        if fails:
            QMessageBox.warning(self, "Resumen", "\n".join(fails))

    def _open_summary_csv(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "Abrir resumen", str(paths.SUMMARY_PATH.parent), "CSV (*.csv)")
        if path:
            self.summary_tab.load_csv(Path(path))

    def save_config(self, quiet: bool = False) -> None:
        """Explicit save always writes; automatic (quiet) saves only when something changed."""
        if self.md is None:
            return
        js = self.md.settings.to_json()
        if quiet and js == self._saved_json:
            return
        try:
            p = save_vel_settings(self.md.trial, self.md.settings)
            self._saved_json = js
            if not quiet:
                self.statusBar().showMessage(f"Configuración guardada en {p}", 6000)
        except OSError as exc:
            self.statusBar().showMessage(f"No se pudo guardar la configuración: {exc}", 8000)

    def closeEvent(self, ev) -> None:
        for w in list(self._detached.values()):
            w.close()
        self.save_config(quiet=True)
        st = QSettings("ITBA", "Velocidades")
        st.setValue("geometry", self.saveGeometry())
        st.setValue("state", self.saveState())
        if self.md is not None:
            st.setValue("last_code", self.md.trial.code)
        for w in (self.loader, self.batch):
            w.shutdown()
        super().closeEvent(ev)
