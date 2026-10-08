from __future__ import annotations

import os
from typing import Optional

from dataclasses import replace

from PySide6.QtCore import Qt
from PySide6.QtGui import QAction, QKeySequence
from PySide6.QtWidgets import (QFileDialog, QMainWindow, QMessageBox, QProgressDialog, QTabWidget)

from core.analysis import detect_video, save_tracks_csv
from core.detection import TRACKPY_ERROR, link_tracks
from core.calibration import (Calibration, calibrate_frames, calibrate_video, derive_tracker_values,
                              describe, sample_frames)
from core import kinematics as km
from core.models import TrimRange
from core.tracking import TrackingSession, extract_candidates, track
from core.video_io import VideoReader, export_video
from gui.export_worker import TaskWorker
from gui.state import ProjectState
from gui.tabs import EditTab, OriginalTab, ProcessTab
from gui.tracking_tab import TrackingTab

VIDEO_FILTER = "Videos (*.mp4 *.avi *.mov *.mkv *.m4v *.wmv);;Todos los archivos (*)"
SAVE_FILTERS = {"MP4 (*.mp4)": ".mp4", "AVI – MJPG (*.avi)": ".avi"}
# Larger frames are probably uncropped (cables, screws, etc.): auto-calibration would be slow and
# miscount robots (measured on full 4K: N≈54 instead of 22), so it waits for the user's crop.
AUTO_CALIBRATE_MAX_SIDE = 1500
CSV_LAYOUTS = {"CSV – una fila por robot y cuadro (*.csv)": "long",
               "CSV – una fila por cuadro, columnas por robot (*.csv)": "wide"}


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Editor de video")
        self.resize(1280, 780)
        self.state = ProjectState(self)
        self._worker: Optional[TaskWorker] = None
        self._last_dir = os.path.expanduser("~")
        self._retrack_pending = False

        self.tab_original = OriginalTab(self.state)
        self.tab_edit = EditTab(self.state)
        self.tab_process = ProcessTab(self.state)
        self.tab_tracking = TrackingTab(self.state)
        self.tabs = QTabWidget()
        self.tabs.addTab(self.tab_original, "1 · Original")
        self.tabs.addTab(self.tab_edit, "2 · Recortar")
        self.tabs.addTab(self.tab_process, "3 · Procesar")
        self.tabs.addTab(self.tab_tracking, "4 · Seguimiento")
        self.tabs.currentChanged.connect(self._stop_all_players)
        self.setCentralWidget(self.tabs)

        self.act_open = QAction("Abrir video…", self, shortcut=QKeySequence.StandardKey.Open,
                                triggered=self.open_dialog)
        act_quit = QAction("Salir", self, shortcut=QKeySequence.StandardKey.Quit, triggered=self.close)
        act_play = QAction("Reproducir/pausar", self, shortcut=Qt.Key.Key_Space,
                           triggered=lambda: self._current_player().toggle_play())
        self.addAction(act_play)
        m = self.menuBar().addMenu("&Archivo")
        m.addAction(self.act_open)
        m.addSeparator()
        m.addAction(act_quit)

        self.tab_edit.saveRequested.connect(lambda: self.export(processed=False))
        self.tab_process.saveRequested.connect(lambda: self.export(processed=True))
        self.tab_process.csvRequested.connect(self.export_csv)
        self.tab_process.calibrateRequested.connect(lambda: self.calibrate(auto=False))
        tt = self.tab_tracking
        tt.analyzeRequested.connect(self.analyze_tracking)
        tt.retrackRequested.connect(self.retrack)
        tt.csvRequested.connect(self.export_tracking_csv)
        tt.videoRequested.connect(self.export_tracking_video)
        tt.saveRequested.connect(self.save_session)
        tt.loadRequested.connect(self.load_session)
        tt.kinematicsRequested.connect(self.recompute_kinematics)
        tt.summaryCsvRequested.connect(self.export_summary_csv)
        self.state.timeScaleChanged.connect(self._on_time_scale)
        self.statusBar().showMessage("Listo")

    # --- loading ---
    def open_dialog(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "Abrir video", self._last_dir, VIDEO_FILTER)
        if path:
            self.open_video(path)

    def open_video(self, path: str) -> None:
        try:
            with VideoReader(path) as r:
                info = r.info
        except Exception as exc:
            QMessageBox.critical(self, "Error al abrir", str(exc))
            return
        self._last_dir = os.path.dirname(path)
        self.state.load(info)
        self._apply_time_scale_to_players()
        self.setWindowTitle(f"Editor de video — {os.path.basename(path)}")
        self.statusBar().showMessage(f"Cargado: {path}")
        if TRACKPY_ERROR is None:
            if max(info.width, info.height) <= AUTO_CALIBRATE_MAX_SIDE:
                self.calibrate(auto=True)
            else:
                self.tab_process.det_panel.lbl_calib.setText(
                    f"Video de {info.width}×{info.height} px: recortá la arena en 'Recortar' y después "
                    "calibrá (o analizá con calibración automática).")

    # --- time scale ---
    def _apply_time_scale_to_players(self) -> None:
        for t in self._all_tabs():
            t.player.set_time_fps(self.state.time_fps)

    def _on_time_scale(self, fps: float) -> None:
        """Re-express times, velocities and ω with the new frames-per-real-second (no re-analysis)."""
        self._apply_time_scale_to_players()
        s = self.tab_tracking.session
        if s is not None and s.result is not None and abs(s.fps - fps) > 1e-9:
            s.fps = fps
            self.recompute_kinematics()
        self.statusBar().showMessage(f"Escala de tiempo: {fps:g} cuadros = 1 s real "
                                     f"(archivo ×{self.state.acceleration:.2f})")

    # --- calibration ---
    def calibrate(self, auto: bool) -> None:
        if self.state.info is None or self._worker is not None or TRACKPY_ERROR:
            return
        self._stop_all_players()
        proc = self.tab_process.build_processor()
        self._run_task(
            "Midiendo el tamaño de los robots…", calibrate_video,
            lambda res: self._apply_calibration(res[0], res[1], quiet=auto),
            src_path=self.state.info.path, trim=self.state.trim, roi=self.state.roi,
            pipeline=proc.pipeline if proc.pipeline else None,
            base=replace(proc.detection, enabled=True), n_hint=self.tab_tracking.sp_n.value())

    def _apply_calibration(self, cal: Calibration, params, quiet: bool) -> None:
        text = describe(cal)
        self.tab_process.det_panel.apply_params(params)
        self.tab_process.det_panel.lbl_calib.setText(text)
        self.tab_tracking.lbl_calib.setText(text)
        self.tab_tracking.set_search_range(derive_tracker_values(cal.r_out)["search_range"])
        self.statusBar().showMessage(f"Calibrado: diámetro de robot ≈ {cal.diameter:.1f} px")
        n_user = self.tab_tracking.sp_n.value()
        problems = []
        if not cal.reliable:
            problems.append("La calibración es poco confiable (tamaño inconsistente entre cuadros o poco "
                            "contraste). Revisá que el recorte contenga solo la arena.")
        if cal.n_estimate is not None and cal.n_estimate != n_user:
            problems.append(f"Se detectan ≈ {cal.n_estimate} robots por cuadro, pero N = {n_user}.")
        if problems and not quiet:
            QMessageBox.warning(self, "Calibración", text + "\n\n" + "\n".join(problems))

    # --- export ---
    def _ask_save_path(self, title: str, suffix: str, filters: dict[str, str]) -> Optional[str]:
        base = os.path.splitext(os.path.basename(self.state.info.path))[0]
        first_ext = next(iter(filters.values()))
        suggested = os.path.join(self._last_dir, f"{base}_{suffix}{first_ext}")
        path, flt = QFileDialog.getSaveFileName(self, title, suggested, ";;".join(filters))
        if not path:
            return None
        if os.path.splitext(path)[1].lower() not in filters.values():
            path += filters.get(flt, first_ext)
        self._last_dir = os.path.dirname(path)
        return path

    def export(self, processed: bool) -> None:
        if self.state.info is None or self._worker is not None:
            return
        self._stop_all_players()
        path = self._ask_save_path("Guardar video", "procesado" if processed else "recorte", SAVE_FILTERS)
        if not path:
            return
        processor = self.tab_process.build_processor() if processed else None
        self._run_task(
            "Exportando video…", _export_task,
            lambda res: QMessageBox.information(
                self, "Exportación completa", f"Se guardaron {res[1]} cuadros en:\n{res[0]}"),
            src=self.state.info.path, dst=path, trim=self.state.trim, roi=self.state.roi,
            processor=processor if processor else None,
        )

    def export_csv(self) -> None:
        if self.state.info is None or self._worker is not None:
            return
        processor = self.tab_process.build_processor()
        if not processor.detection.enabled:
            QMessageBox.warning(self, "Detección desactivada",
                                TRACKPY_ERROR or "Activá 'Detección de robots (Trackpy)' en la pestaña Procesar.")
            return
        self._stop_all_players()
        path = self._ask_save_path("Guardar posiciones", "posiciones", {"CSV (*.csv)": ".csv"})
        if not path:
            return

        def done(res):
            dst, n_rows, n_frames, n_tracks = res
            extra = f"\nTrayectorias: {n_tracks}" if n_tracks is not None else ""
            QMessageBox.information(self, "Detección completa",
                                    f"{n_rows} detecciones en {n_frames} cuadros.{extra}\n\nArchivo:\n{dst}")

        self._run_task(
            "Detectando robots en el rango seleccionado…", _detect_task, done,
            src=self.state.info.path, dst=path, trim=self.state.trim, roi=self.state.roi,
            processor=processor, link=self.tab_process.det_panel.link_params(), fps=self.state.time_fps,
        )

    # --- tracking ---
    def analyze_tracking(self) -> None:
        if self.state.info is None or self._worker is not None:
            return
        if TRACKPY_ERROR:
            QMessageBox.critical(self, "trackpy", TRACKPY_ERROR)
            return
        self._stop_all_players()
        proc = self.tab_process.build_processor()
        proc = replace(proc, detection=replace(proc.detection, enabled=True))
        tparams = self.tab_tracking.tracker_params(proc.detection)
        info = self.state.info
        n_frames = self.state.trim.length
        mins = n_frames * 0.09 / 60  # ~90 ms/frame measured on 4K + 800x800 ROI
        if n_frames > 1000 and QMessageBox.question(
                self, "Analizar video",
                f"Se van a analizar {n_frames} cuadros (estimado ≈ {mins:.0f} min). ¿Continuar?"
        ) != QMessageBox.StandardButton.Yes:
            return

        def done(res):
            session, cal = res
            if cal is not None:
                self._apply_calibration(cal, session.detection, quiet=True)
            self.tab_tracking.set_session(session)
            self.tabs.setCurrentWidget(self.tab_tracking)
            self._warn_issues(session, cal)

        self._run_task("Analizando video (calibración + detección + seguimiento)…", _analyze_task, done,
                       src=info.path, trim=self.state.trim, roi=self.state.roi, processor=proc,
                       tparams=tparams, autocal=self.tab_tracking.chk_autocal.isChecked(),
                       kin_params=self.tab_tracking.kinematics_params(), time_fps=self.state.time_fps)

    def retrack(self) -> None:
        session = self.tab_tracking.session
        if session is None:
            return
        if self._worker is not None:
            self._retrack_pending = True
            return
        det = session.detection
        session.params = self.tab_tracking.tracker_params(det)
        session.kin_params = self.tab_tracking.kinematics_params()

        def done(res):
            if self.tab_tracking.session is session:
                session.result, session.kin = res
                self.tab_tracking.on_result_updated()

        self._run_task("Recalculando seguimiento…", _track_task, done,
                       cands=session.candidates, params=session.params, anchors=dict(session.anchors),
                       fps=session.fps, kin_params=session.kin_params, r_out=det.r_out)

    def recompute_kinematics(self) -> None:
        session = self.tab_tracking.session
        if session is None or session.result is None:
            return
        if self._worker is not None:
            self._retrack_pending = True
            return
        session.kin_params = self.tab_tracking.kinematics_params()

        def done(kin):
            if self.tab_tracking.session is session:
                session.kin = kin
                self.tab_tracking.on_result_updated()

        self._run_task("Calculando velocidades y rotación…", _kin_task, done,
                       result=session.result, sig=session.candidates.sig, fps=session.fps,
                       kin_params=session.kin_params, r_out=session.detection.r_out)

    def _warn_issues(self, session: TrackingSession, cal: Optional[Calibration] = None) -> None:
        sm = session.result.summary()
        head = (f"Calibración: {describe(cal)}\n\n") if cal is not None else ""
        n = session.params.n_objects
        if cal is not None and cal.n_estimate is not None and cal.n_estimate != n:
            head += f"⚠ La calibración estima ≈ {cal.n_estimate} robots por cuadro y N = {n}.\n\n"
        if sm["frames_error"] or sm["frames_warning"]:
            QMessageBox.warning(
                self, "Cuadros con problemas",
                head + f"No se detectaron los {n} robots en todos los cuadros.\n\n"
                f"• {sm['frames_error']} cuadros con posiciones predichas o perdidas (revisar).\n"
                f"• {sm['frames_warning']} cuadros con posiciones interpoladas entre detecciones.\n\n"
                "Revisalos en la lista 'Cuadros con problemas'. Podés corregir un centro con dos clics: "
                "primero sobre el robot y después en su centro real.")
        elif head:
            QMessageBox.information(self, "Seguimiento completo",
                                    head + f"Los {n} robots se detectaron en todos los cuadros.")
        else:
            self.statusBar().showMessage(f"Seguimiento completo: {n} robots detectados en todos los cuadros.")

    def export_tracking_csv(self) -> None:
        """Single CSV with every robot; layout chosen in the save dialog."""
        s, v = self.tab_tracking.session, self.tab_tracking.current_view()
        if s is None or v is None or self._worker is not None:
            return
        base = os.path.splitext(os.path.basename(s.src_path))[0]
        suggested = os.path.join(self._last_dir, f"{base}_robots.csv")
        path, flt = QFileDialog.getSaveFileName(self, "Guardar CSV (todos los robots)", suggested,
                                                ";;".join(CSV_LAYOUTS))
        if not path:
            return
        if not path.lower().endswith(".csv"):
            path += ".csv"
        self._last_dir = os.path.dirname(path)
        wide = CSV_LAYOUTS.get(flt) == "wide"
        try:
            df = s.to_dataframe(v)
            out = km.wide_table(df) if wide else df
            out.to_csv(path, index=False, float_format="%.6g")
        except (OSError, ValueError) as exc:
            QMessageBox.critical(self, "Error al guardar", str(exc))
            return
        f = v.result.frames
        layout = ("una fila por cuadro; columnas r00_…, r01_… por robot" if wide
                  else "una fila por robot y cuadro (columna 'particle')")
        QMessageBox.information(
            self, "CSV guardado",
            f"{os.path.basename(path)}\n{v.result.n_objects} robots · cuadros {f[0]}–{f[-1]} · "
            f"{len(out)} filas × {out.shape[1]} columnas\nFormato: {layout}\n\n"
            "Ejes: x a la derecha, y hacia abajo. vel_dir_deg, theta_deg y ω: antihorario. "
            + ("Video espejado corregido: x, y, v, θ y ω están en la escena real (columna 'espejo'). "
               if "espejo" in out.columns else "")
            + "'status' indica si cada posición fue detectada o estimada.")

    def export_summary_csv(self) -> None:
        s, v = self.tab_tracking.session, self.tab_tracking.current_view()
        if s is None or v is None or self._worker is not None:
            return
        path = self._ask_save_path("Guardar resumen por robot", "resumen_robots", {"CSV (*.csv)": ".csv"})
        if not path:
            return
        try:
            s.summary_dataframe(v).to_csv(path, index=False, float_format="%.6g")
        except OSError as exc:
            QMessageBox.critical(self, "Error al guardar", str(exc))
            return
        self.statusBar().showMessage(f"Resumen guardado: {path}")

    def export_tracking_video(self) -> None:
        s, v = self.tab_tracking.session, self.tab_tracking.current_view()
        if s is None or v is None or self._worker is not None:
            return
        self._stop_all_players()
        path = self._ask_save_path("Guardar video con seguimiento", "seguimiento", SAVE_FILTERS)
        if not path:
            return
        frames = v.result.frames
        tt = self.tab_tracking
        self._run_task(
            "Exportando video con seguimiento…", _export_task,
            lambda res: QMessageBox.information(
                self, "Exportación completa", f"Se guardaron {res[1]} cuadros en:\n{res[0]}"),
            src=s.src_path, dst=path, trim=TrimRange(int(frames[0]), int(frames[-1])), roi=s.roi,
            processor=None, annotate=s.annotator(v, tt.chk_vel.isChecked(), tt.chk_rot.isChecked()),
        )

    def save_session(self) -> None:
        s = self.tab_tracking.session
        if s is None:
            return
        path = self._ask_save_path("Guardar análisis", "analisis", {"Análisis (*.npz)": ".npz"})
        if not path:
            return
        try:
            s.save(path)
        except OSError as exc:
            QMessageBox.critical(self, "Error al guardar", str(exc))
            return
        self.statusBar().showMessage(f"Análisis guardado: {path}")

    def load_session(self) -> None:
        if self.state.info is None or self._worker is not None:
            QMessageBox.information(self, "Cargar análisis", "Primero abrí el video correspondiente.")
            return
        path, _ = QFileDialog.getOpenFileName(self, "Cargar análisis", self._last_dir, "Análisis (*.npz)")
        if not path:
            return
        try:
            s = TrackingSession.load(path)
        except Exception as exc:
            QMessageBox.critical(self, "Error al cargar", f"{type(exc).__name__}: {exc}")
            return
        if os.path.basename(s.src_path) != os.path.basename(self.state.info.path):
            if QMessageBox.question(
                    self, "Video distinto",
                    f"El análisis se hizo sobre '{os.path.basename(s.src_path)}' y el video abierto es "
                    f"'{os.path.basename(self.state.info.path)}'. ¿Cargar igual?"
            ) != QMessageBox.StandardButton.Yes:
                return
        s.src_path = self.state.info.path
        if abs(s.fps - self.state.time_fps) > 1e-9:
            QMessageBox.information(
                self, "Escala de tiempo",
                f"El análisis se guardó con {s.fps:g} cuadros/s; se recalcula con la escala actual "
                f"({self.state.time_fps:g} cuadros = 1 s real). Cambiala en la pestaña Original si no es correcta.")
            s.fps = self.state.time_fps

        def done(res):
            s.result, s.kin = res
            self.tab_process.det_panel.apply_params(s.detection)
            self.tab_tracking.set_session(s)
            self.tabs.setCurrentWidget(self.tab_tracking)
            self._warn_issues(s)

        if s.kin_params is None:
            s.kin_params = self.tab_tracking.kinematics_params()
        if not s.has_rotation:
            QMessageBox.information(self, "Análisis antiguo",
                                    "Este análisis no tiene datos de rotación (versión anterior). "
                                    "Velocidades disponibles; para θ y ω volvé a analizar el video.")
        self._run_task("Recalculando seguimiento…", _track_task, done,
                       cands=s.candidates, params=s.params, anchors=dict(s.anchors), fps=s.fps,
                       kin_params=s.kin_params, r_out=s.detection.r_out)

    def _run_task(self, text: str, func, on_success, **kwargs) -> None:
        self._worker = TaskWorker(func, self, **kwargs)
        dlg = QProgressDialog(text, "Cancelar", 0, 100, self)
        dlg.setWindowModality(Qt.WindowModality.WindowModal)
        dlg.setMinimumDuration(0)
        dlg.setAutoClose(False)
        dlg.setAutoReset(False)
        dlg.canceled.connect(self._worker.requestInterruption)
        self._worker.progress.connect(dlg.setValue)
        self._worker.succeeded.connect(on_success)
        self._worker.cancelled.connect(lambda: self.statusBar().showMessage("Operación cancelada"))
        self._worker.failed.connect(lambda msg: QMessageBox.critical(self, "Error", msg))
        self._worker.finished.connect(dlg.close)
        self._worker.finished.connect(self._on_worker_done)
        self.act_open.setEnabled(False)
        self._worker.start()

    def _on_worker_done(self) -> None:
        self._worker.deleteLater()
        self._worker = None
        self.act_open.setEnabled(True)
        if self._retrack_pending:
            self._retrack_pending = False
            self.retrack()

    # --- helpers ---
    def _all_tabs(self):
        return (self.tab_original, self.tab_edit, self.tab_process, self.tab_tracking)

    def _current_player(self):
        return self.tabs.currentWidget().player

    def _stop_all_players(self, *_):
        for t in self._all_tabs():
            t.player.stop()

    def closeEvent(self, e):
        if self._worker is not None:
            self._worker.requestInterruption()
            self._worker.wait(5000)
        for t in self._all_tabs():
            t.player.close_source()
        super().closeEvent(e)


# --- worker task functions (run off the GUI thread; only value arguments) ---
def _export_task(src, dst, trim, roi, processor, progress, should_cancel, annotate=None):
    n, cancelled = export_video(src, dst, trim, roi, processor, progress=progress,
                                should_cancel=should_cancel, annotate=annotate)
    return (dst, n), cancelled


def _analyze_task(src, trim, roi, processor, tparams, autocal, progress, should_cancel, kin_params=None,
                  time_fps=None):
    cal = None
    if autocal:
        frames = sample_frames(src, trim, roi, processor.pipeline if processor.pipeline else None, 5)
        cal, dparams = calibrate_frames(frames, processor.detection, n_hint=tparams.n_objects)
        processor = replace(processor, detection=replace(dparams, enabled=True))
        tparams = replace(tparams, min_separation=0.8 * dparams.separation, **derive_tracker_values(cal.r_out))
        progress(5)
        if should_cancel():
            return None, True
    cands, fps, cancelled = extract_candidates(
        src, trim, roi, processor, progress=lambda v: progress(5 + int(v * 0.90)), should_cancel=should_cancel)
    if cancelled:
        return None, True
    if len(cands) == 0:
        raise IOError("No se pudo leer ningún cuadro del tramo seleccionado.")
    # Time base = frames per REAL second (time-lapse aware), not the container's playback fps.
    session = TrackingSession(src, roi, trim, time_fps or fps, processor.detection, cands, tparams,
                              kin_params=kin_params)
    res = session.run(progress=lambda v: progress(95 + v // 20), should_cancel=should_cancel)
    return (None, True) if res is None else ((session, cal), False)


def _track_task(cands, params, anchors, progress, should_cancel, fps=30.0, kin_params=None, r_out=1.0):
    res = track(cands, params, anchors, progress=progress, should_cancel=should_cancel)
    if res is None:
        return None, True
    kin = km.compute(res, cands.sig, fps, kin_params or km.KinematicsParams(), r_out)
    return (res, kin), False


def _kin_task(result, sig, fps, kin_params, r_out, progress, should_cancel):
    return km.compute(result, sig, fps, kin_params, r_out), False


def _detect_task(src, dst, trim, roi, processor, link, progress, should_cancel, fps=None):
    df, cancelled = detect_video(src, trim, roi, processor, progress=progress, should_cancel=should_cancel,
                                 fps=fps)
    if cancelled:
        return None, True
    n_tracks = None
    if link is not None:
        df = link_tracks(df, search_range=link[0], memory=link[1], min_length=link[2])
        n_tracks = int(df["particle"].nunique()) if len(df) else 0
    save_tracks_csv(df, dst)
    n_frames = int(df["frame"].nunique()) if len(df) else 0
    return (dst, len(df), n_frames, n_tracks), False
