"""Main window: parameter dock (left), plots (center), synchronised video (right dock) and a
transport bar driving a single clock in sensor time."""

from __future__ import annotations

import time
import traceback
from pathlib import Path
from typing import Optional

import numpy as np
from PySide6.QtCore import QSettings, Qt, QTimer
from PySide6.QtGui import QAction, QKeySequence
from PySide6.QtWidgets import (QCheckBox, QComboBox, QDockWidget, QFileDialog, QLabel, QMainWindow,
                               QMessageBox, QSlider, QStyle, QTabWidget, QToolBar, QToolButton)

from core import paths
from core.export import default_columns
from core.session import TrialData
from core.settings import TrialSettings, save_settings
from core.signal import true_runs
from core.stats import Stats
from gui.panels import (AnalysisPanel, CalibrationPanel, ExportPanel, PlotsPanel, SyncPanel,
                        TrialPanel, dspin)
from gui.plots import DeltaGPanel, PlotArea, normalized_plot_states
from gui.video_view import VideoPanel
from gui.worker import LatestJobRunner

SPEEDS = [0.5, 1, 2, 5, 10, 20, 50, 100, 200]
TICK_MS = 33
SHADE_CROP = (120, 120, 120, 70)
SHADE_EXCL = (214, 39, 40, 45)
VIDEO_FILTER = "Videos (*.mp4 *.MP4 *.mov *.avi *.mkv);;Todos los archivos (*)"


def fmt_t(t: float) -> str:
    sign = "−" if t < 0 else ""
    t = abs(t)
    return f"{sign}{int(t // 60)}:{t % 60:04.1f}"


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("FSRScope — presión en el recinto circular")
        self.resize(1600, 950)
        self.td: Optional[TrialData] = None
        self.t_now = 0.0
        self.full_stats: Optional[Stats] = None
        self._gen = 0                    # bumps on every change that invalidates pending stats
        self._last_live_req = 0.0
        self._video_path: Optional[Path] = None
        self._saved_json = ""
        # Separate runners: a live request must never replace a pending full-record one.
        self.worker = LatestJobRunner(self)
        self.worker_live = LatestJobRunner(self)
        for w in (self.worker, self.worker_live):
            w.finished.connect(self._on_stats)
            w.failed.connect(lambda tag, msg: self.statusBar().showMessage(f"Error de cálculo: {msg}", 8000))
        self.batch_worker = LatestJobRunner(self)
        self.batch_worker.finished.connect(self._on_batch_done)

        # --- central plots -----------------------------------------------------------------
        self.area = PlotArea()
        self.area.seekRequested.connect(lambda t: self.set_time(t))
        self.area.selectionChanged.connect(self._on_selection)
        self._selection = (0.0, 0.0)
        self.setCentralWidget(self.area)

        # --- left dock: parameters ---------------------------------------------------------
        self.p_trial = TrialPanel()
        self.p_cal = CalibrationPanel()
        self.p_ana = AnalysisPanel()
        self.p_sync = SyncPanel()
        self.p_plots = PlotsPanel()
        self.p_exp = ExportPanel()
        self.tabs = QTabWidget()
        for w, name in ((self.p_trial, "Ensayo"), (self.p_cal, "Calibración"), (self.p_ana, "Análisis"),
                        (self.p_sync, "Video"), (self.p_plots, "Gráficos"), (self.p_exp, "Exportar")):
            self.tabs.addTab(w, name)
        self.dock_params = QDockWidget("Parámetros", self)
        self.dock_params.setObjectName("dock_params")
        self.dock_params.setWidget(self.tabs)
        self.addDockWidget(Qt.DockWidgetArea.LeftDockWidgetArea, self.dock_params)

        # --- right dock: video ---------------------------------------------------------------
        self.video = VideoPanel()
        self.video.openRequested.connect(self.open_video_dialog)
        self.dock_video = QDockWidget("Video", self)
        self.dock_video.setObjectName("dock_video")
        self.dock_video.setWidget(self.video)
        self.addDockWidget(Qt.DockWidgetArea.RightDockWidgetArea, self.dock_video)
        self.resizeDocks([self.dock_params, self.dock_video], [380, 470], Qt.Orientation.Horizontal)

        self._build_transport()
        self._build_menu()
        self._connect_panels()

        self.play_timer = QTimer(self)
        self.play_timer.setInterval(TICK_MS)
        self.play_timer.timeout.connect(self._tick)
        self._wall = 0.0
        self.recalc_timer = QTimer(self, singleShot=True, interval=200)
        self.recalc_timer.timeout.connect(self.request_full_stats)

        st = QSettings("ITBA", "FSRScope")
        if st.value("geometry") is not None:
            self.restoreGeometry(st.value("geometry"))
            self.restoreState(st.value("state"))
        self.statusBar().showMessage("Elegí un ensayo en la pestaña «Ensayo».")
        last = st.value("last_code")
        if last:
            self.p_trial.select_code(last)
            for tr in self.p_trial._trials:
                if tr.code == last:
                    QTimer.singleShot(0, lambda tr=tr: self.open_trial(tr))

    # =========================================================================================
    # construction
    # =========================================================================================
    def _build_transport(self) -> None:
        tb = QToolBar("Reproducción", self)
        tb.setObjectName("transport")
        tb.setMovable(False)
        st = self.style()
        self.b_back = QToolButton(icon=st.standardIcon(QStyle.StandardPixmap.SP_MediaSeekBackward))
        self.b_play = QToolButton(icon=st.standardIcon(QStyle.StandardPixmap.SP_MediaPlay))
        self.b_fwd = QToolButton(icon=st.standardIcon(QStyle.StandardPixmap.SP_MediaSeekForward))
        self.b_start = QToolButton(icon=st.standardIcon(QStyle.StandardPixmap.SP_MediaSkipBackward))
        self.b_start.setToolTip("Ir al inicio del recorte")
        self.b_back.setToolTip("Cuadro anterior (←) · Mayús+← = −10 s")
        self.b_fwd.setToolTip("Cuadro siguiente (→) · Mayús+→ = +10 s")
        self.b_play.setToolTip("Reproducir / pausar (Espacio)")
        self.b_play.clicked.connect(self.toggle_play)
        self.b_back.clicked.connect(lambda: self.step(-1))
        self.b_fwd.clicked.connect(lambda: self.step(1))
        self.b_start.clicked.connect(lambda: self.set_time(self._t_range()[0]))
        self.slider = QSlider(Qt.Orientation.Horizontal)
        self.slider.setMinimumWidth(300)
        self.slider.valueChanged.connect(lambda v: self.set_time(v / 10.0, from_slider=True))
        self.lbl_t = QLabel("—")
        self.lbl_t.setMinimumWidth(270)
        self.speed = QComboBox()
        for s in SPEEDS:
            self.speed.addItem(f"×{s:g}", s)
        self.speed.setToolTip("Segundos del ensayo por segundo de reproducción (×10 = velocidad del time-lapse)")
        self.speed.setCurrentIndex(SPEEDS.index(10))
        self.cb_live = QCheckBox("En vivo")
        self.cb_live.setToolTip("Como si se estuviera midiendo: los gráficos muestran solo hasta el "
                                "cursor y la estadística se acumula (en gris, la del ensayo completo)")
        self.cb_live.toggled.connect(self._on_live_toggled)
        self.live_win = dspin(0, 1e5, 0, 10, "s", "Ancho visible en vivo (0 = desde el inicio)")
        self.live_win.setValue(120)
        self.cb_follow = QCheckBox("Seguir cursor")
        self.cb_follow.setChecked(True)
        for w in (self.b_start, self.b_back, self.b_play, self.b_fwd):
            tb.addWidget(w)
        tb.addWidget(self.slider)
        tb.addWidget(self.lbl_t)
        tb.addSeparator()
        tb.addWidget(QLabel(" Velocidad "))
        tb.addWidget(self.speed)
        tb.addSeparator()
        tb.addWidget(self.cb_live)
        tb.addWidget(QLabel(" ventana "))
        tb.addWidget(self.live_win)
        tb.addWidget(self.cb_follow)
        self.addToolBar(Qt.ToolBarArea.BottomToolBarArea, tb)
        self.transport = tb

    def _build_menu(self) -> None:
        m = self.menuBar().addMenu("&Archivo")
        acts = [
            ("Abrir registro…", QKeySequence.StandardKey.Open, self.open_log_dialog),
            ("Abrir video…", None, self.open_video_dialog),
            (None, None, None),
            ("Guardar configuración del ensayo", QKeySequence.StandardKey.Save, self.save_config),
            ("Exportar P_<código>.csv", QKeySequence("Ctrl+E"), self.export_default),
            ("Exportar como…", None, self.export_as),
            ("Procesar todos los registros (lote)", None, self.run_batch),
            (None, None, None),
            ("Salir", QKeySequence.StandardKey.Quit, self.close),
        ]
        for text, key, fn in acts:
            if text is None:
                m.addSeparator()
                continue
            a = QAction(text, self, triggered=fn)
            if key is not None:
                a.setShortcut(key)
            m.addAction(a)
        v = self.menuBar().addMenu("&Ver")
        v.addAction(self.dock_params.toggleViewAction())
        v.addAction(self.dock_video.toggleViewAction())
        v.addAction(QAction("Autoescalar gráficos", self, triggered=self.autorange,
                            shortcut=QKeySequence("Ctrl+0")))
        for key, fn in ((Qt.Key.Key_Space, self.toggle_play),
                        (Qt.Key.Key_Left, lambda: self.step(-1)), (Qt.Key.Key_Right, lambda: self.step(1)),
                        (QKeySequence("Shift+Left"), lambda: self.set_time(self.t_now - 10)),
                        (QKeySequence("Shift+Right"), lambda: self.set_time(self.t_now + 10))):
            a = QAction(self, triggered=fn)
            a.setShortcut(key)
            a.setShortcutContext(Qt.ShortcutContext.ApplicationShortcut)
            self.addAction(a)

    def _connect_panels(self) -> None:
        self.p_trial.trialSelected.connect(self.open_trial)
        self.p_trial.openLogRequested.connect(self.open_log_dialog)
        self.p_trial.openVideoRequested.connect(self.open_video_dialog)
        self.p_cal.changed.connect(self._on_calibration)
        self.p_cal.copyDetected.connect(self._copy_detected_rfb)
        self.p_ana.changed.connect(self._on_analysis)
        self.p_ana.cropFromLed.connect(self._crop_from_led)
        self.p_ana.cropToView.connect(self._crop_to_view)
        self.p_ana.cropAll.connect(lambda: self._set_crop(None, None))
        self.p_ana.cropToSelection.connect(lambda: self._set_crop(*sorted(self._selection)))
        self.p_ana.excludeSelection.connect(self._exclude_selection)
        self.p_ana.selectionToggled.connect(self._toggle_selection)
        self.p_sync.changed.connect(self._on_sync)
        self.p_plots.statesChanged.connect(self._on_plot_states)
        self.p_plots.optionChanged.connect(self._on_plot_option)
        self.p_exp.exportRequested.connect(self.export_default)
        self.p_exp.exportAsRequested.connect(self.export_as)
        self.p_exp.saveConfigRequested.connect(self.save_config)
        self.p_exp.resetRequested.connect(self.reset_settings)
        self.p_exp.batchRequested.connect(self.run_batch)

    # =========================================================================================
    # trial loading
    # =========================================================================================
    def open_log_dialog(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "Abrir registro del sensor", str(paths.RAW_DIR),
                                              "Registros (*.csv *.json);;Todos los archivos (*)")
        if path:
            self.open_trial(paths.trial_from_path(Path(path)))

    def open_trial(self, trial: paths.Trial) -> None:
        if self.td is not None and self.td.trial == trial:
            return
        self.stop()
        self.save_config(quiet=True)
        self.setCursor(Qt.CursorShape.WaitCursor)
        try:
            td = TrialData.open(trial)
        except Exception as exc:
            self.unsetCursor()
            QMessageBox.critical(self, "No se pudo abrir el registro", f"{trial.raw_path}\n\n{exc}")
            return
        self.unsetCursor()
        self.td = td
        self._gen += 1
        self.full_stats = None
        s = td.settings
        s.plots = normalized_plot_states(s.plots)
        self.p_trial.select_code(trial.code)
        self.p_ana.sel.setChecked(False)
        self._load_panels()
        self.speed.setCurrentIndex(SPEEDS.index(s.playback.speed) if s.playback.speed in SPEEDS else SPEEDS.index(10))
        self.cb_live.blockSignals(True)
        self.cb_live.setChecked(s.playback.live)
        self.cb_live.blockSignals(False)
        self.live_win.setValue(s.playback.live_window_s)

        self._open_video()
        self.area.configure(s.plots, td.robots is not None)
        for p in self.area.panels.values():
            p.td = td
        for p in self.area.time_panels(all_=True):
            p.set_trial(td)
            p.plot.getViewBox().setAutoVisible(y=True)
        self._update_shading()
        dur = td.raw.duration_s
        self.slider.blockSignals(True)
        self.slider.setRange(0, int(np.ceil(dur * 10)))
        self.slider.blockSignals(False)
        t0, _ = self._t_range()
        self.set_time(t0)
        self.autorange()
        self.request_full_stats()
        self._saved_json = self._collect_settings().to_json()
        self.setWindowTitle(f"FSRScope — {trial.label}")
        msg = f"Abierto {trial.raw_path.name}"
        if td.raw.warnings:
            msg += " · " + "; ".join(td.raw.warnings)
        self.statusBar().showMessage(msg, 8000)

    def _load_panels(self) -> None:
        td, s = self.td, self.td.settings
        self.p_cal.load(s, td)
        self.p_ana.load(s, td)
        self.p_sync.load(s, td)
        self.p_plots.load(s.plots, td.robots is not None, td.raw.numeric_columns())
        self.p_exp.load(s, td)

    def _open_video(self) -> None:
        td = self.td
        manual = Path(td.settings.sync.video_path) if td.settings.sync.video_path else None
        path = manual if manual is not None and manual.is_file() else td.trial.video_path
        err = self.video.set_source(td, path)
        self._video_path = path if not err else None
        n = self.video.src.frame_count if self.video.src is not None else None
        self.p_sync.update_summary(td, n)
        self.p_trial.show_info(td, self._video_path, err)
        self.dock_video.setWindowTitle(f"Video — {path.name}" if self._video_path else "Video")

    def open_video_dialog(self) -> None:
        if self.td is None:
            return
        start = self._video_path.parent if self._video_path else paths.VIDEO_CROP_DIR
        path, _ = QFileDialog.getOpenFileName(self, "Abrir video del ensayo", str(start), VIDEO_FILTER)
        if path:
            self.td.settings.sync.video_path = path
            self._open_video()
            self.set_time(self.t_now)

    # =========================================================================================
    # parameter changes
    # =========================================================================================
    def _on_calibration(self) -> None:
        if self.td is None:
            return
        self.p_cal.store(self.td.settings)
        self._rebuild_series()
        self.p_cal.update_summary(self.td)
        self.p_trial.show_info(self.td, self._video_path)

    def _copy_detected_rfb(self) -> None:
        if self.td is None or self.td.raw.k_firmware is None:
            return
        c = self.td.settings.calibration
        c.r_feedback = round(c.r_feedback_from_k(self.td.raw.k_firmware), 1)
        c.mode = "manual"
        self.p_cal.load(self.td.settings, self.td)
        self._rebuild_series()

    def _rebuild_series(self) -> None:
        try:
            self.td.rebuild()
        except ValueError as exc:
            self.statusBar().showMessage(str(exc), 6000)
            return
        self._gen += 1
        for p in self.area.time_panels(all_=True):
            p.rebuild()
        self._apply_live_view()
        self.recalc_timer.start()

    def _on_analysis(self) -> None:
        if self.td is None:
            return
        old_step = self.td.settings.analysis.step_s
        self.p_ana.store(self.td.settings)
        self.p_exp.store(self.td.settings)
        self.p_exp.load(self.td.settings, self.td)      # deltaG column name may change
        self._update_shading()
        if self.td.settings.analysis.step_s != old_step:
            self._rebuild_series()
        else:
            self._gen += 1
            self.recalc_timer.start()

    def _on_sync(self) -> None:
        if self.td is None:
            return
        self.p_sync.store(self.td.settings)
        n = self.video.src.frame_count if self.video.src is not None else None
        self.p_sync.update_summary(self.td, n)
        self.area.panels["robots"].rebuild()
        self._apply_live_view()
        self.set_time(self.t_now)

    def _on_plot_states(self) -> None:
        if self.td is None:
            return
        self.td.settings.plots = self.p_plots.states()
        self.area.configure(self.td.settings.plots, self.td.robots is not None)
        self._refresh_stat_panels()
        self._apply_live_view()
        self.set_time(self.t_now)

    def _on_plot_option(self, pid: str, opts: dict) -> None:
        if self.td is None:
            return
        self.td.settings.plots = self.p_plots.states()
        self.area.apply_options(pid, opts)
        if pid in ("G", "dG", "R", "ADC", "raw", "robots"):
            self._apply_live_view()

    # --- crop / selection -----------------------------------------------------------------
    def _set_crop(self, t0: Optional[float], t1: Optional[float]) -> None:
        if self.td is None:
            return
        a = self.td.settings.analysis
        a.t_start, a.t_end = t0, t1
        self.p_ana.load(self.td.settings, self.td)
        self._on_analysis()

    def _crop_from_led(self) -> None:
        if self.td is None:
            return
        led = self.td.led_offset
        if led is None:
            self.statusBar().showMessage("Este registro no tiene pulso LED.", 5000)
            return
        self._set_crop(led, self.td.settings.analysis.t_end)

    def _crop_to_view(self) -> None:
        panels = self.area.time_panels()
        if self.td is None or not panels:
            return
        x0, x1 = panels[0].plot.getViewBox().viewRange()[0]
        dur = self.td.raw.duration_s
        self._set_crop(max(0.0, x0), min(dur, x1))

    def _toggle_selection(self, on: bool) -> None:
        panels = self.area.time_panels()
        if on and panels:
            x0, x1 = panels[0].plot.getViewBox().viewRange()[0]
            w = x1 - x0
            self._selection = (x0 + 0.4 * w, x0 + 0.6 * w)
        for p in self.area.time_panels(all_=True):
            p.set_selection(on, self._selection if on else None)

    def _on_selection(self, a: float, b: float) -> None:
        self._selection = (a, b)

    def _exclude_selection(self) -> None:
        if self.td is None or not self.p_ana.sel.isChecked():
            self.statusBar().showMessage("Activá «Mostrar selección» y ubicá la región amarilla.", 5000)
            return
        a, b = sorted(self._selection)
        self.td.settings.analysis.exclusions.append([round(a, 2), round(b, 2)])
        self.p_ana.load(self.td.settings, self.td)
        self._on_analysis()

    def _update_shading(self) -> None:
        if self.td is None:
            return
        a, dur = self.td.settings.analysis, self.td.raw.duration_s
        spans = []
        if a.t_start is not None and a.t_start > 0:
            spans.append((0.0, a.t_start, SHADE_CROP))
        if a.t_end is not None and a.t_end < dur:
            spans.append((a.t_end, dur, SHADE_CROP))
        for seg in a.exclusions:
            spans.append((float(seg[0]), float(seg[1]), SHADE_EXCL))
        if a.exclude_saturated:
            spans += [(t0, t1 + self.td.series.step_s, SHADE_EXCL)
                      for t0, t1 in true_runs(self.td.series.sat, self.td.series.t)[:300]]
        for p in self.area.time_panels(all_=True):
            p.set_shading(spans)

    # =========================================================================================
    # statistics
    # =========================================================================================
    def request_full_stats(self) -> None:
        if self.td is None:
            return
        td = self.td
        self.worker.submit(("full", self._gen), td.stats, None, True)
        if self.cb_live.isChecked():
            self.request_live_stats(force=True)

    def request_live_stats(self, force: bool = False) -> None:
        if self.td is None or not self.cb_live.isChecked():
            return
        now = time.monotonic()
        period = self.td.settings.playback.stats_period_s if self.play_timer.isActive() else 0.15
        if not force and now - self._last_live_req < period:
            return
        self._last_live_req = now
        self.worker_live.submit(("live", self._gen), self.td.stats, self.t_now, True)

    def _on_stats(self, tag, st: Stats) -> None:
        kind, gen = tag
        if gen != self._gen or self.td is None:
            return      # computed with parameters that are no longer current
        if kind == "full":
            self.full_stats = st
            dg = self.area.panels["dG"]
            if isinstance(dg, DeltaGPanel):
                dg.set_deltaG(st.deltaG)
                self._apply_live_view()
            a = self.td.settings.analysis
            extra = (f"<br>G media = {st.G_mean:.3g} µS, desvío = {st.G_std:.3g} µS, "
                     f"saturadas = {100 * st.sat_frac:.2f} %" if st.n_used > 3 else "")
            self.p_ana.show_summary(st.n_used, len(self.td.series.t), a.step_s, extra)
            if not self.cb_live.isChecked():
                self._refresh_stat_panels()
        elif self.cb_live.isChecked():
            for p in self.area.stat_panels():
                p.update_stats(st, self.full_stats)

    def _refresh_stat_panels(self) -> None:
        for p in self.area.stat_panels():
            p.update_stats(self.full_stats, None)

    # =========================================================================================
    # clock and playback
    # =========================================================================================
    def _t_range(self) -> tuple[float, float]:
        if self.td is None:
            return 0.0, 0.0
        a, dur = self.td.settings.analysis, self.td.raw.duration_s
        return (a.t_start if a.t_start is not None else 0.0,
                a.t_end if a.t_end is not None else dur)

    def set_time(self, t: float, from_slider: bool = False) -> None:
        if self.td is None:
            return
        dur = self.td.raw.duration_s
        self.t_now = float(np.clip(t, 0.0, dur))
        for p in self.area.time_panels():
            p.set_cursor(self.t_now)
        self.video.show_time(self.t_now)
        if not from_slider:
            self.slider.blockSignals(True)
            self.slider.setValue(int(round(self.t_now * 10)))
            self.slider.blockSignals(False)
        tv = self.t_now - self.td.offset_s
        frame = self.td.frame_at(self.t_now)
        self.lbl_t.setText(f" t = {fmt_t(self.t_now)} / {fmt_t(dur)}   ·   video {fmt_t(tv)} (cuadro {frame})")
        self._apply_live_view()
        self.request_live_stats()

    def _apply_live_view(self) -> None:
        panels = self.area.time_panels()
        if self.td is None or not panels:
            return
        live = self.cb_live.isChecked()
        vb = panels[0].plot.getViewBox()
        x0, x1 = vb.viewRange()[0]
        if live:
            w = self.live_win.value()
            lo = max(self._t_range()[0], self.t_now - w) if w > 0 else self._t_range()[0]
            hi = self.t_now + (0.03 * w if w > 0 else 0.03 * max(self.t_now - lo, 1.0))
            for p in panels:
                p.show_until(self.t_now, t_from=lo if w > 0 else None)
            vb.setXRange(lo, max(hi, lo + 1.0), padding=0)
            return
        for p in panels:
            p.show_until(None)
        if self.cb_follow.isChecked() and not (x0 <= self.t_now <= x1):
            w = x1 - x0
            vb.setXRange(self.t_now - 0.1 * w, self.t_now + 0.9 * w, padding=0)

    def _on_live_toggled(self, on: bool) -> None:
        if self.td is None:
            return
        self.td.settings.playback.live = on
        if on:
            self.request_live_stats(force=True)
        else:
            self._refresh_stat_panels()
            for p in self.area.time_panels():
                p.show_until(None)
            self.autorange()
        self._apply_live_view()

    def toggle_play(self) -> None:
        if self.play_timer.isActive():
            self.stop()
            return
        if self.td is None:
            return
        t0, t1 = self._t_range()
        if self.t_now >= t1 - 1e-6 or self.t_now < t0:
            self.set_time(t0)
        self._wall = time.monotonic()
        self.play_timer.start()
        self.b_play.setIcon(self.style().standardIcon(QStyle.StandardPixmap.SP_MediaPause))

    def stop(self) -> None:
        self.play_timer.stop()
        self.b_play.setIcon(self.style().standardIcon(QStyle.StandardPixmap.SP_MediaPlay))
        if self.cb_live.isChecked():
            self.request_live_stats(force=True)

    def _tick(self) -> None:
        now = time.monotonic()
        dt, self._wall = now - self._wall, now
        t1 = self._t_range()[1]
        t = self.t_now + dt * float(self.speed.currentData())
        if t >= t1:
            self.set_time(t1)
            self.stop()
            return
        self.set_time(t)

    def step(self, n: int) -> None:
        if self.td is None:
            return
        self.stop()
        if self.video.src is not None:
            frame = self.td.frame_at(self.t_now) + n
            self.set_time(float(self.td.time_of_frame(frame)) + 1e-6)
        else:
            self.set_time(self.t_now + n * max(self.td.settings.analysis.step_s, 0.1))

    def autorange(self) -> None:
        for p in list(self.area.time_panels()) + list(self.area.stat_panels()):
            p.plot.enableAutoRange()

    # =========================================================================================
    # persistence and export
    # =========================================================================================
    def _collect_settings(self) -> Optional[TrialSettings]:
        if self.td is None:
            return None
        s = self.td.settings
        s.plots = self.p_plots.states()
        self.p_exp.store(s)
        s.playback.speed = float(self.speed.currentData())
        s.playback.live = self.cb_live.isChecked()
        s.playback.live_window_s = self.live_win.value()
        return s

    def save_config(self, quiet: bool = False) -> None:
        """Explicit save always writes; automatic (quiet) saves only when something changed."""
        s = self._collect_settings()
        if s is None:
            return
        if quiet and s.to_json() == self._saved_json:
            return
        path = paths.config_path(self.td.trial)
        try:
            save_settings(path, s)
            self._saved_json = s.to_json()
            if not quiet:
                self.statusBar().showMessage(f"Configuración guardada en {path}", 6000)
        except OSError as exc:
            self.statusBar().showMessage(f"No se pudo guardar la configuración: {exc}", 8000)

    def reset_settings(self) -> None:
        if self.td is None:
            return
        if QMessageBox.question(self, "Restablecer", "¿Volver todos los parámetros de este ensayo a "
                                "los valores por defecto?") != QMessageBox.StandardButton.Yes:
            return
        trial = self.td.trial
        s = TrialSettings()
        s.export_columns = default_columns()
        s.plots = normalized_plot_states([])
        self.td.settings = s
        self._load_panels()
        self.area.configure(s.plots, self.td.robots is not None)
        self._open_video()
        self._update_shading()
        self._rebuild_series()
        self.statusBar().showMessage(f"Parámetros por defecto en {trial.code} (sin guardar).", 6000)

    def export_default(self) -> None:
        if self.td is None:
            return
        out = paths.processed_path(self.td.trial)
        if out.exists() and QMessageBox.question(
                self, "Exportar", f"{out.name} ya existe. ¿Reemplazarlo?") != QMessageBox.StandardButton.Yes:
            return
        self._export(out)

    def export_as(self) -> None:
        if self.td is None:
            return
        path, _ = QFileDialog.getSaveFileName(self, "Exportar CSV procesado",
                                              str(paths.processed_path(self.td.trial)), "CSV (*.csv)")
        if path:
            self._export(Path(path))

    def _export(self, path: Path) -> None:
        self._collect_settings()
        try:
            self.setCursor(Qt.CursorShape.WaitCursor)
            out, df = self.td.export(path, self.full_stats)
            self.save_config(quiet=True)
            self.statusBar().showMessage(f"Exportado {out} ({len(df)} filas, {len(df.columns)} columnas). "
                                         f"Configuración guardada.", 8000)
        except Exception as exc:
            QMessageBox.critical(self, "Error al exportar", f"{exc}\n\n{traceback.format_exc(limit=3)}")
        finally:
            self.unsetCursor()

    def run_batch(self) -> None:
        if self.batch_worker.busy:
            return
        self.save_config(quiet=True)
        trials = paths.discover_trials()
        if QMessageBox.question(self, "Procesar todos", f"Se van a (re)generar {len(trials)} archivos "
                                f"P_<código>.csv en {paths.PROC_DIR}. ¿Continuar?") != QMessageBox.StandardButton.Yes:
            return
        from procesar_lote import run_batch

        def job():
            lines = []
            run_batch(trials, paths.PROC_DIR, lines.append)
            return lines
        self.statusBar().showMessage("Procesando todos los registros…")
        self.batch_worker.submit("batch", job)

    def _on_batch_done(self, tag, lines) -> None:
        self.statusBar().showMessage(lines[-1] if lines else "Listo.", 8000)
        QMessageBox.information(self, "Procesamiento por lotes", "\n".join(lines))
        self.p_trial.refresh()

    def closeEvent(self, ev) -> None:
        self.stop()
        self.save_config(quiet=True)
        st = QSettings("ITBA", "FSRScope")
        st.setValue("geometry", self.saveGeometry())
        st.setValue("state", self.saveState())
        if self.td is not None:
            st.setValue("last_code", self.td.trial.code)
        for w in (self.worker, self.worker_live, self.batch_worker):
            w.shutdown()
        self.video.close_source()
        super().closeEvent(ev)
