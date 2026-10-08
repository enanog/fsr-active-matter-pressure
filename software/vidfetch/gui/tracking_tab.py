from __future__ import annotations

from typing import Optional

import numpy as np
from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtGui import QBrush, QColor, QKeySequence, QShortcut
from PySide6.QtWidgets import (QCheckBox, QComboBox, QDoubleSpinBox, QFormLayout, QGroupBox,
                               QHBoxLayout, QLabel, QListWidget, QListWidgetItem, QPushButton,
                               QScrollArea, QSpinBox, QVBoxLayout, QWidget)

from core.calibration import GAP_GROWTH_PER_R
from core.detection import DetectionParams
from core.kinematics import ARROW_NOTE, MIRROR_LABELS, MIRROR_NONE, KinematicsParams
from core.tracking import (CANDIDATE_MIN_COVERAGE, STATUS_COLORS, STATUS_LABELS, Status,
                           SessionView, TrackerParams, TrackingSession, draw_tracks)
from core.video_io import VideoInfo
from gui.frame_view import ClickFrameView
from gui.player import PlayerWidget
from gui.state import ProjectState

FILTER_ERRORS = "error"
FILTER_ALL = "all"


def _dur(seconds: float) -> str:
    return f"{seconds / 60:.1f} min" if seconds >= 120 else f"{seconds:.2f} s"


def _legend_html() -> str:
    parts = []
    for st in Status:
        if st == Status.MISSING:
            continue
        b, g, r = STATUS_COLORS[st]
        parts.append(f"<span style='color:rgb({r},{g},{b})'>■</span> {STATUS_LABELS[st]}")
    return "<br>".join(parts)


class TrackingTab(QWidget):
    """Fixed-N tracking review: issues list, navigation and manual centre correction."""

    analyzeRequested = Signal()
    retrackRequested = Signal()
    csvRequested = Signal()
    videoRequested = Signal()
    saveRequested = Signal()
    loadRequested = Signal()
    kinematicsRequested = Signal()
    summaryCsvRequested = Signal()

    def __init__(self, state: ProjectState, parent=None):
        super().__init__(parent)
        self.state = state
        self.session: Optional[TrackingSession] = None
        self._sv: Optional[SessionView] = None   # time-trimmed view of the session
        self._selected: Optional[int] = None
        self._issue_frames: np.ndarray = np.zeros(0, np.int64)

        self.view = ClickFrameView()
        self.player = PlayerWidget(self.view)
        self.player.set_transform(self._transform)
        self.view.clicked.connect(self._on_click)
        esc = QShortcut(QKeySequence(Qt.Key.Key_Escape), self, lambda: self._select(None))
        esc.setContext(Qt.ShortcutContext.WidgetWithChildrenShortcut)

        tp = TrackerParams()
        # --- parameters
        self.sp_n = QSpinBox(); self.sp_n.setRange(1, 1000); self.sp_n.setValue(tp.n_objects)
        self.sp_search = QDoubleSpinBox(decimals=1); self.sp_search.setRange(1, 1000)
        self.sp_search.setValue(tp.search_range); self.sp_search.setSuffix(" px")
        self.sp_gap = QSpinBox(); self.sp_gap.setRange(1, 100000); self.sp_gap.setValue(tp.max_gap)
        self.sp_gap.setSuffix(" cuadros")
        self.sp_r1 = QDoubleSpinBox(decimals=2); self.sp_r1.setRange(CANDIDATE_MIN_COVERAGE, 1.0)
        self.sp_r1.setSingleStep(0.05); self.sp_r1.setValue(tp.relax_coverages[0])
        self.sp_r2 = QDoubleSpinBox(decimals=2); self.sp_r2.setRange(CANDIDATE_MIN_COVERAGE, 1.0)
        self.sp_r2.setSingleStep(0.05); self.sp_r2.setValue(tp.relax_coverages[1])
        self.chk_interp = QCheckBox("Interpolar entre cuadros detectados"); self.chk_interp.setChecked(True)
        self.chk_autocal = QCheckBox("Calibrar tamaño automáticamente al analizar")
        self.chk_autocal.setChecked(True)
        self.chk_autocal.setToolTip("Antes de analizar mide el diámetro aparente de los robots en el recorte "
                                    "y escala todos los parámetros en función de él.")
        self.lbl_calib = QLabel()
        self.lbl_calib.setWordWrap(True)
        self.btn_analyze = QPushButton("Analizar video")
        self.btn_analyze.setMinimumHeight(32)
        par_box = QGroupBox("Seguimiento con N fijo")
        f = QFormLayout(par_box)
        f.addRow("Cantidad de robots (N)", self.sp_n)
        f.addRow("Radio de búsqueda", self.sp_search)
        f.addRow("Hueco máx. interpolable", self.sp_gap)
        f.addRow("Cobertura relajada 1", self.sp_r1)
        f.addRow("Cobertura relajada 2", self.sp_r2)
        f.addRow(self.chk_interp)
        f.addRow(self.chk_autocal)
        f.addRow(self.lbl_calib)
        hint = QLabel("Se analiza solo el recorte y el tramo definidos en 'Recortar'. "
                      "Detección: parámetros de la pestaña Procesar.")
        hint.setWordWrap(True)
        f.addRow(hint)
        f.addRow(self.btn_analyze)

        # --- results
        self.lbl_summary = QLabel("Sin análisis.")
        self.lbl_summary.setWordWrap(True)
        self.lbl_stale = QLabel()
        self.lbl_stale.setWordWrap(True)
        self.lbl_stale.setStyleSheet("color:#c60")
        self.cb_filter = QComboBox()
        self.cb_filter.addItem("Solo errores (revisar)", FILTER_ERRORS)
        self.cb_filter.addItem("Errores y advertencias", FILTER_ALL)
        self.list_issues = QListWidget()
        self.list_issues.setMinimumHeight(160)
        self.btn_prev = QPushButton("◀ Anterior")
        self.btn_next = QPushButton("Siguiente ▶")
        res_box = QGroupBox("Cuadros con problemas")
        v = QVBoxLayout(res_box)
        v.addWidget(self.lbl_summary)
        v.addWidget(self.lbl_stale)
        v.addWidget(self.cb_filter)
        v.addWidget(self.list_issues, 1)
        row = QHBoxLayout(); row.addWidget(self.btn_prev); row.addWidget(self.btn_next)
        v.addLayout(row)
        legend = QLabel(_legend_html())
        v.addWidget(legend)

        # --- manual correction
        self.cb_robot = QComboBox()
        self.lbl_hint = QLabel()
        self.lbl_hint.setWordWrap(True)
        self.btn_clear = QPushButton("Quitar correcciones de este cuadro")
        self.lbl_anchors = QLabel("Correcciones: 0")
        cor_box = QGroupBox("Corrección manual del centro")
        g = QFormLayout(cor_box)
        g.addRow("Robot", self.cb_robot)
        g.addRow(self.lbl_hint)
        g.addRow(self.btn_clear)
        g.addRow(self.lbl_anchors)

        # --- kinematics
        kp = KinematicsParams()
        self.sp_window = QSpinBox(); self.sp_window.setRange(3, 301); self.sp_window.setSingleStep(2)
        self.sp_window.setValue(kp.window); self.sp_window.setSuffix(" cuadros")
        self.sp_window.setToolTip("Ventana del filtro de Savitzky–Golay (orden 2) usado para derivar "
                                  "posición y ángulo. Más grande = menos ruido, menos resolución temporal.")
        self.sp_diam = QDoubleSpinBox(decimals=2); self.sp_diam.setRange(0, 10000)
        self.sp_diam.setSuffix(" mm"); self.sp_diam.setSpecialValueText("sin conversión (px)")
        self.sp_diam.setValue(kp.robot_diameter_mm)
        self.sp_diam.setToolTip("Diámetro real del robot. Con el diámetro medido en px se obtiene la "
                                "escala mm/px y se exportan columnas en m y m/s.")
        self.cb_mirror = QComboBox()
        for key, text in MIRROR_LABELS.items():
            self.cb_mirror.addItem(text, key)
        self.cb_mirror.setToolTip("Si la cámara graba la escena espejada, las exportaciones (CSV, resumen e "
                                  "informes) se pasan a la escena real: se refleja la posición y se invierte el "
                                  "sentido de θ y ω. La superposición sobre el video no cambia.")
        self.chk_vel = QCheckBox("Mostrar vector velocidad"); self.chk_vel.setChecked(True)
        self.chk_rot = QCheckBox("Mostrar orientación"); self.chk_rot.setChecked(True)
        self.lbl_kin = QLabel(ARROW_NOTE)
        self.lbl_kin.setWordWrap(True)
        kin_box = QGroupBox("Cinemática")
        kf = QFormLayout(kin_box)
        kf.addRow("Suavizado", self.sp_window)
        kf.addRow("Diámetro real", self.sp_diam)
        kf.addRow("Video espejado", self.cb_mirror)
        kf.addRow(self.chk_vel)
        kf.addRow(self.chk_rot)
        kf.addRow(self.lbl_kin)

        # --- outputs
        self.btn_csv = QPushButton("Exportar CSV (todos los robots)…")
        self.btn_csv.setToolTip("Un único archivo con todos los robots. En el diálogo elegís el formato: "
                                "una fila por robot y cuadro, o una fila por cuadro con columnas por robot.")
        self.btn_csv_robot = QPushButton("Exportar resumen por robot (CSV)…")
        self.btn_video = QPushButton("Exportar video con seguimiento…")
        self.btn_save = QPushButton("Guardar análisis…")
        self.btn_load = QPushButton("Cargar análisis…")
        out_box = QGroupBox("Resultados")
        o = QVBoxLayout(out_box)
        for b in (self.btn_csv, self.btn_csv_robot, self.btn_video, self.btn_save, self.btn_load):
            o.addWidget(b)

        side = QWidget()
        sl = QVBoxLayout(side)
        sl.setContentsMargins(0, 0, 0, 0)
        for w in (par_box, res_box, cor_box, kin_box, out_box):
            sl.addWidget(w)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(side)
        scroll.setFixedWidth(360)

        lay = QHBoxLayout(self)
        lay.addWidget(self.player, 1)
        lay.addWidget(scroll)

        # Debounced re-tracking when tracker params change (tracking is cheap, but not free).
        self._debounce = QTimer(self, singleShot=True, interval=400)
        self._debounce.timeout.connect(self._emit_retrack)
        for w in (self.sp_n, self.sp_search, self.sp_gap, self.sp_r1, self.sp_r2):
            w.valueChanged.connect(self._debounce.start)
        self.chk_interp.toggled.connect(self._debounce.start)

        self.btn_analyze.clicked.connect(self.analyzeRequested)
        self.btn_csv.clicked.connect(self.csvRequested)
        self.btn_csv_robot.clicked.connect(self.summaryCsvRequested)
        self._kin_debounce = QTimer(self, singleShot=True, interval=400)
        self._kin_debounce.timeout.connect(lambda: self.session is not None and self.kinematicsRequested.emit())
        self.sp_window.valueChanged.connect(self._kin_debounce.start)
        self.sp_diam.valueChanged.connect(self._kin_debounce.start)
        self.cb_mirror.currentIndexChanged.connect(self._kin_debounce.start)
        self.chk_vel.toggled.connect(lambda _: self.player.refresh())
        self.chk_rot.toggled.connect(lambda _: self.player.refresh())
        self.btn_video.clicked.connect(self.videoRequested)
        self.btn_save.clicked.connect(self.saveRequested)
        self.btn_load.clicked.connect(self.loadRequested)
        self.cb_filter.currentIndexChanged.connect(self._fill_issues)
        self.list_issues.currentItemChanged.connect(self._on_issue_selected)
        self.btn_prev.clicked.connect(lambda: self._jump_issue(-1))
        self.btn_next.clicked.connect(lambda: self._jump_issue(+1))
        self.cb_robot.currentIndexChanged.connect(self._on_robot_combo)
        self.btn_clear.clicked.connect(self._clear_frame_anchors)

        state.loaded.connect(self._on_loaded)
        state.roiChanged.connect(lambda _: self._update_stale())
        state.trimChanged.connect(lambda _: self._refresh_view())
        self._set_session_enabled(False)
        self._fill_robot_combo(tp.n_objects)
        self.setEnabled(False)

    # ------------------------------------------------------------------ params
    def tracker_params(self, det: DetectionParams) -> TrackerParams:
        return TrackerParams(
            n_objects=self.sp_n.value(), search_range=self.sp_search.value(),
            min_separation=0.8 * det.separation,
            strict_coverage=det.min_coverage if det.validate_ring else 0.0,
            min_mass=det.minmass, gap_growth=GAP_GROWTH_PER_R * det.r_out,
            relax_coverages=(self.sp_r1.value(), self.sp_r2.value()),
            max_gap=self.sp_gap.value(), interpolate=self.chk_interp.isChecked(),
        )

    def set_params_from(self, p: TrackerParams) -> None:
        widgets = (self.sp_n, self.sp_search, self.sp_gap, self.sp_r1, self.sp_r2, self.chk_interp)
        for w in widgets:
            w.blockSignals(True)
        self.sp_n.setValue(p.n_objects)
        self.sp_search.setValue(p.search_range)
        self.sp_gap.setValue(p.max_gap)
        rc = list(p.relax_coverages) + [CANDIDATE_MIN_COVERAGE] * 2
        self.sp_r1.setValue(rc[0])
        self.sp_r2.setValue(rc[1])
        self.chk_interp.setChecked(p.interpolate)
        for w in widgets:
            w.blockSignals(False)

    def kinematics_params(self) -> KinematicsParams:
        w = self.sp_window.value()
        return KinematicsParams(window=w if w % 2 else w + 1, robot_diameter_mm=self.sp_diam.value(),
                                mirror=self.cb_mirror.currentData() or MIRROR_NONE)

    def set_kinematics_from(self, p: Optional[KinematicsParams]) -> None:
        if p is None:
            return
        for w, v in ((self.sp_window, p.window), (self.sp_diam, p.robot_diameter_mm)):
            w.blockSignals(True)
            w.setValue(v)
            w.blockSignals(False)
        i = self.cb_mirror.findData(getattr(p, "mirror", MIRROR_NONE))
        self.cb_mirror.blockSignals(True)
        self.cb_mirror.setCurrentIndex(max(0, i))
        self.cb_mirror.blockSignals(False)

    def set_search_range(self, value: float) -> None:
        self.sp_search.blockSignals(True)
        self.sp_search.setValue(value)
        self.sp_search.blockSignals(False)

    def _emit_retrack(self) -> None:
        if self.session is not None:
            self.retrackRequested.emit()

    # ------------------------------------------------------------------ session
    def set_session(self, session: Optional[TrackingSession]) -> None:
        self.session = session
        self._selected = None
        self._set_session_enabled(session is not None)
        if session is None:
            return
        self.set_params_from(session.params)
        self.set_kinematics_from(session.kin_params)
        self.on_result_updated()

    def current_view(self) -> Optional[SessionView]:
        return self._sv

    def _refresh_view(self) -> None:
        """Re-slice the full analysis to the current time trim (no re-analysis)."""
        s = self.session
        if s is None or s.result is None or self.state.info is None:
            self._sv = None
            self._update_stale()
            return
        self._sv = s.view(self.state.trim.clamped(self.state.info.frame_count))
        f = self._sv.result.frames
        self.player.set_range(int(f[0]), int(f[-1]))
        self._update_summary()
        self._fill_issues()
        self._update_stale()
        self.player.refresh()

    def on_result_updated(self) -> None:
        s = self.session
        if s is None or s.result is None:
            return
        self._fill_robot_combo(s.result.n_objects)
        self.lbl_anchors.setText(f"Correcciones: {len(s.anchors)}")
        self._update_hint()
        self._refresh_view()

    def _update_summary(self) -> None:
        s, v = self.session, self._sv
        if s is None or v is None:
            return
        res = v.result
        sm = res.summary()
        c = sm["counts"]
        pts = max(1, sm["points"])
        ok = c[Status.DETECTED] + c[Status.RELAXED] + c[Status.MANUAL]
        f = res.frames
        kin_txt = ""
        if v.kin is not None:
            sp = v.kin.speed
            unit = "px/s"
            scale = 1.0
            if v.kin.mm_per_px > 0:
                unit, scale = "mm/s", v.kin.mm_per_px
            kin_txt = (f"<br>|v| mediana {np.nanmedian(sp) * scale:.1f} {unit} · "
                       f"|ω| mediana {np.nanmedian(np.abs(v.kin.omega)):.0f} °/s"
                       + ("" if s.has_rotation else " (sin rotación: análisis antiguo)"))
        self.lbl_summary.setText(
            f"Área analizada: {s.roi.w}×{s.roi.h} px · diámetro robot {2 * s.detection.r_out:.0f} px<br>"
            f"Cuadros {f[0]}–{f[-1]} ({len(f)}, {_dur(len(f) / s.fps)} reales a {s.fps:g} cuadros/s) · "
            f"N = {res.n_objects}<br>"
            f"Observados: {100 * ok / pts:.2f} % (relajados {c[Status.RELAXED]}, manuales {c[Status.MANUAL]})<br>"
            f"Interpolados: {c[Status.INTERPOLATED]} · Predichos: {c[Status.PREDICTED]} · Perdidos: {c[Status.MISSING]}<br>"
            f"<span style='color:#c33'><b>{sm['frames_error']}</b> cuadros con error</span> · "
            f"<span style='color:#c80'>{sm['frames_warning']} con advertencia</span>" + kin_txt)

    def _set_session_enabled(self, on: bool) -> None:
        for w in (self.cb_filter, self.list_issues, self.btn_prev, self.btn_next, self.cb_robot,
                  self.btn_clear, self.btn_csv, self.btn_csv_robot, self.btn_video, self.btn_save):
            w.setEnabled(on)

    def _update_stale(self) -> None:
        s = self.session
        if s is None or self.state.info is None:
            self.lbl_stale.clear()
            return
        msgs = []
        if s.roi != self.state.roi:
            msgs.append("El recorte espacial cambió después del análisis: se muestra el recorte analizado. "
                        "Volvé a analizar para aplicar el nuevo.")
        if self._sv is not None and self._sv.message:
            msgs.append(self._sv.message)
        self.lbl_stale.setText("<br>".join(msgs))

    # ------------------------------------------------------------------ issues list
    def _fill_issues(self) -> None:
        self.list_issues.blockSignals(True)
        self.list_issues.clear()
        s, v = self.session, self._sv
        if s is None or v is None:
            self.list_issues.blockSignals(False)
            return
        iss = v.result.issues()
        if self.cb_filter.currentData() == FILTER_ERRORS:
            iss = iss[iss["severity"] == "error"]
        self._issue_frames = iss["frame"].to_numpy(np.int64)
        red, orange = QBrush(QColor(200, 40, 40)), QBrush(QColor(200, 120, 0))
        for r in iss.itertuples(index=False):
            parts = []
            if r.n_interpolated:
                parts.append(f"{r.n_interpolated} interp.")
            if r.n_predicted:
                parts.append(f"{r.n_predicted} pred.")
            if r.n_missing:
                parts.append(f"{r.n_missing} perdidos")
            ids = " ".join(f"#{k}" for k in r.objects.split())
            it = QListWidgetItem(f"cuadro {r.frame} · t={r.frame / s.fps:.2f} s · {', '.join(parts)} · {ids}")
            it.setData(Qt.ItemDataRole.UserRole, int(r.frame))
            it.setForeground(red if r.severity == "error" else orange)
            self.list_issues.addItem(it)
        self.list_issues.blockSignals(False)

    def _on_issue_selected(self, item: Optional[QListWidgetItem], _prev=None) -> None:
        if item is not None:
            self.player.stop()
            self.player.seek(int(item.data(Qt.ItemDataRole.UserRole)))

    def _jump_issue(self, direction: int) -> None:
        if len(self._issue_frames) == 0:
            return
        cur = self.player.current_index
        if direction > 0:
            i = int(np.searchsorted(self._issue_frames, cur, side="right"))
            i = i if i < len(self._issue_frames) else 0
        else:
            i = int(np.searchsorted(self._issue_frames, cur, side="left")) - 1
            i = i if i >= 0 else len(self._issue_frames) - 1
        self.list_issues.setCurrentRow(i)

    # ------------------------------------------------------------------ manual correction
    def _fill_robot_combo(self, n: int) -> None:
        if self.cb_robot.count() == n + 1:
            return
        self.cb_robot.blockSignals(True)
        self.cb_robot.clear()
        self.cb_robot.addItem("— (clic sobre un robot)", None)
        for k in range(n):
            self.cb_robot.addItem(f"#{k}", k)
        self.cb_robot.blockSignals(False)
        self._select(None)

    def _select(self, k: Optional[int]) -> None:
        self._selected = k
        self.cb_robot.blockSignals(True)
        self.cb_robot.setCurrentIndex(0 if k is None else k + 1)
        self.cb_robot.blockSignals(False)
        self._update_hint()
        self.player.refresh()

    def _on_robot_combo(self, idx: int) -> None:
        self._selected = self.cb_robot.itemData(idx)
        self._update_hint()
        self.player.refresh()

    def _update_hint(self) -> None:
        if self.session is None or self.session.result is None:
            self.lbl_hint.setText("Analizá el video para habilitar las correcciones.")
        elif self._selected is None:
            self.lbl_hint.setText("1) Hacé clic sobre un robot (o elegilo en la lista) para seleccionarlo.")
        else:
            self.lbl_hint.setText(f"2) Robot <b>#{self._selected}</b> seleccionado: hacé clic en su centro "
                                  "real. El seguimiento continúa desde ese punto. Esc cancela.")

    def _on_click(self, x: float, y: float) -> None:
        s = self.session
        if s is None or s.result is None:
            return
        frame = self.player.current_index
        if s.result.row_of(frame) is None:
            return
        fx, fy = x + s.roi.x, y + s.roi.y
        if self._selected is None:
            xy, _ = s.result.at(frame)
            d = np.hypot(xy[:, 0] - fx, xy[:, 1] - fy)
            d[~np.isfinite(d)] = np.inf
            k = int(np.argmin(d))
            if np.isfinite(d[k]) and d[k] <= s.detection.r_out * 1.2:
                self._select(k)
            return
        s.set_anchor(frame, self._selected, fx, fy)
        self._select(None)
        self.lbl_anchors.setText(f"Correcciones: {len(s.anchors)}")
        self.retrackRequested.emit()

    def _clear_frame_anchors(self) -> None:
        s = self.session
        if s is None:
            return
        if s.remove_anchors(self.player.current_index, None):
            self.lbl_anchors.setText(f"Correcciones: {len(s.anchors)}")
            self.retrackRequested.emit()

    # ------------------------------------------------------------------ rendering
    def _transform(self, frame: np.ndarray) -> np.ndarray:
        s, v = self.session, self._sv
        roi = s.roi if s is not None else self.state.roi
        crop = roi.apply(frame)
        if s is None or v is None:
            return crop
        i = v.result.row_of(self.player.current_index)
        if i is None:
            return crop
        res, kin = v.result, v.kin
        xy = np.stack([res.x[i], res.y[i]], 1) - np.array([roi.x, roi.y])
        vel = np.stack([kin.vx[i], kin.vy[i]], 1) if (kin is not None and self.chk_vel.isChecked()) else None
        ang = kin.theta[i] if (kin is not None and self.chk_rot.isChecked() and s.has_rotation) else None
        return draw_tracks(crop, xy, res.status[i], s.detection.r_out, self._selected, vel, ang, fps=s.fps)

    def _on_loaded(self, info: VideoInfo) -> None:
        self.setEnabled(True)
        self.player.load(info.path)
        self.set_session(None)
        self._sv = None
        self.lbl_summary.setText("Sin análisis.")
        self.list_issues.clear()
        self._update_hint()
