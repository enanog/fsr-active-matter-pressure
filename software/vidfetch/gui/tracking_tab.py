from __future__ import annotations

from typing import Optional

import cv2
import numpy as np
from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtGui import QBrush, QColor, QKeySequence, QShortcut
from PySide6.QtWidgets import (QCheckBox, QComboBox, QDoubleSpinBox, QFormLayout, QGroupBox,
                               QHBoxLayout, QLabel, QListWidget, QListWidgetItem, QPushButton,
                               QScrollArea, QSpinBox, QVBoxLayout, QWidget)

from core import arena as ar
from core import orientation as ori
from core.calibration import GAP_GROWTH_PER_R
from core.detection import DetectionParams
from core.kinematics import (ARROW_NOTE, MIRROR_LABELS, MIRROR_NONE, SCALE_ARENA, SCALE_LABELS,
                             KinematicsParams)
from core.tracking import (CANDIDATE_MIN_COVERAGE, STATUS_COLORS, STATUS_LABELS, Status,
                           SessionView, TrackerParams, TrackingSession, draw_oriented)
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
    arenaDetectRequested = Signal()
    arenaChanged = Signal()
    robotCsvRequested = Signal(int)
    allRobotsCsvRequested = Signal()

    def __init__(self, state: ProjectState, parent=None):
        super().__init__(parent)
        self.state = state
        self.session: Optional[TrackingSession] = None
        self._sv: Optional[SessionView] = None   # time-trimmed view of the session
        self._selected: Optional[int] = None
        self._issue_frames: np.ndarray = np.zeros(0, np.int64)
        self.arena: Optional[ar.ArenaTrack] = None   # enclosure; mirrored into session.arena
        self._manual_mode = False
        self._manual_pts: list[tuple[float, float]] = []

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

        # --- enclosure (origin and scale of every export)
        self.lbl_arena = QLabel("Recinto sin definir.")
        self.lbl_arena.setWordWrap(True)
        self.lbl_arena.setTextFormat(Qt.TextFormat.RichText)
        self.sp_din = QDoubleSpinBox(decimals=1); self.sp_din.setRange(1, 100000); self.sp_din.setSuffix(" mm")
        self.sp_din.setValue(ar.D_IN_MM)
        self.sp_din.setToolTip("Diámetro INTERIOR del recinto (borde interior del anillo). Fija la escala mm/px.")
        self.sp_dout = QDoubleSpinBox(decimals=1); self.sp_dout.setRange(1, 100000); self.sp_dout.setSuffix(" mm")
        self.sp_dout.setValue(ar.D_OUT_MM)
        self.sp_dout.setToolTip("Diámetro EXTERIOR del anillo. Solo se usa como control: r_ext/r_int medido "
                                "debe coincidir con D_ext/D_int.")
        self.chk_arena_auto = QCheckBox("Detectar el recinto al analizar"); self.chk_arena_auto.setChecked(True)
        self.chk_arena_auto.setToolTip(f"Mide el recinto cada {ar.DEFAULT_STEP} cuadros durante el análisis "
                                       "(sigue su movimiento y los cambios de zoom de la cámara).")
        self.btn_arena_detect = QPushButton("Detectar recinto automáticamente")
        self.btn_arena_manual = QPushButton("Marcar a mano (clics en el borde interior)")
        self.btn_arena_manual.setCheckable(True)
        self.btn_arena_apply = QPushButton("Ajustar círculo a los puntos")
        self.btn_arena_clear = QPushButton("Borrar puntos")
        self.lbl_pts = QLabel("Puntos: 0")
        self.chk_follow = QCheckBox("El círculo manual sigue el movimiento detectado")
        self.chk_follow.setChecked(True)
        self.chk_follow.setToolTip("Con un recinto automático disponible, el círculo marcado a mano se "
                                   "traslada y escala con el movimiento medido (útil si la detección del "
                                   "radio no es buena pero sí la del movimiento).")
        self.btn_arena_auto_only = QPushButton("Descartar el círculo manual")
        self.chk_show_arena = QCheckBox("Mostrar recinto y ejes"); self.chk_show_arena.setChecked(True)
        arena_box = QGroupBox("Recinto: origen (0, 0) y escala")
        af = QFormLayout(arena_box)
        af.addRow(self.lbl_arena)
        af.addRow("Diámetro interior", self.sp_din)
        af.addRow("Diámetro exterior", self.sp_dout)
        af.addRow(self.chk_arena_auto)
        af.addRow(self.btn_arena_detect)
        af.addRow(self.btn_arena_manual)
        row_pts = QHBoxLayout(); row_pts.addWidget(self.lbl_pts); row_pts.addWidget(self.btn_arena_clear)
        af.addRow(row_pts)
        af.addRow(self.btn_arena_apply)
        af.addRow(self.chk_follow)
        af.addRow(self.btn_arena_auto_only)
        af.addRow(self.chk_show_arena)
        arena_hint = QLabel("Origen en el centro del recinto de cada cuadro, x a la derecha, y hacia arriba. "
                            "Marcado a mano: activá el botón y hacé ≥ 3 clics (mejor 6–8, repartidos) "
                            "sobre el borde interior del anillo.")
        arena_hint.setWordWrap(True)
        af.addRow(arena_hint)

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
        self.cb_mirror.setToolTip("Cómo se muestra la escena y en qué sistema se exporta. 'Rotada 180°': el "
                                  "observador está parado en el borde superior del video (y = 0) mirando hacia "
                                  "el inferior; la imagen se gira para verla desde ahí, x queda a su derecha, y "
                                  "hacia la pared de enfrente y el sentido de giro no cambia. 'Espejada': para "
                                  "cámaras que graban la escena reflejada (invierte el sentido de θ y ω). El "
                                  "análisis siempre se hace sobre la imagen original.")
        self.chk_vel = QCheckBox("Mostrar vector velocidad"); self.chk_vel.setChecked(True)
        self.chk_rot = QCheckBox("Mostrar orientación"); self.chk_rot.setChecked(True)
        self.lbl_kin = QLabel(ARROW_NOTE)
        self.lbl_kin.setWordWrap(True)
        kin_box = QGroupBox("Cinemática")
        kf = QFormLayout(kin_box)
        kf.addRow("Suavizado", self.sp_window)
        kf.addRow("Diámetro real", self.sp_diam)
        kf.addRow("Orientación de la escena", self.cb_mirror)
        self.cb_scale = QComboBox()
        for key, text in SCALE_LABELS.items():
            self.cb_scale.addItem(text, key)
        self.cb_scale.setToolTip("Fuente de la escala mm/px. Recinto: D_int / (2 r_int) en cada cuadro "
                                 "(recomendado). Perspectiva: además lleva el radio de contacto de los robots "
                                 "con la pared a R_int − D/2. Robot: diámetro real / diámetro medido (constante).")
        kf.addRow("Escala desde", self.cb_scale)
        kf.addRow(self.chk_vel)
        kf.addRow(self.chk_rot)
        kf.addRow(self.lbl_kin)

        # --- outputs
        self.btn_csv = QPushButton("Exportar CSV (todos los robots)…")
        self.btn_csv.setToolTip("Un único archivo con todos los robots. En el diálogo elegís el formato: "
                                "una fila por robot y cuadro, o una fila por cuadro con columnas por robot.")
        self.btn_csv_robot = QPushButton("Exportar resumen por robot (CSV)…")
        self.cb_export_robot = QComboBox()
        self.btn_csv_one = QPushButton("Exportar un robot (todos los datos)…")
        self.btn_csv_one.setToolTip("CSV con todas las columnas del seguimiento, una fila por cuadro, solo para "
                                    "el robot elegido (posición, velocidad, rotación, distancia a la pared…).")
        self.btn_csv_each = QPushButton("Exportar cada robot en su propio archivo…")
        self.btn_video = QPushButton("Exportar video con seguimiento…")
        self.btn_save = QPushButton("Guardar análisis…")
        self.btn_load = QPushButton("Cargar análisis…")
        out_box = QGroupBox("Resultados")
        o = QVBoxLayout(out_box)
        o.addWidget(self.btn_csv)
        o.addWidget(self.btn_csv_robot)
        row_one = QHBoxLayout(); row_one.addWidget(QLabel("Robot")); row_one.addWidget(self.cb_export_robot, 1)
        o.addLayout(row_one)
        for b in (self.btn_csv_one, self.btn_csv_each, self.btn_video, self.btn_save, self.btn_load):
            o.addWidget(b)

        side = QWidget()
        sl = QVBoxLayout(side)
        sl.setContentsMargins(0, 0, 0, 0)
        for w in (par_box, res_box, cor_box, arena_box, kin_box, out_box):
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
        self.cb_mirror.currentIndexChanged.connect(lambda _i: self.player.refresh())
        self.cb_scale.currentIndexChanged.connect(self._kin_debounce.start)
        self.btn_arena_detect.clicked.connect(self.arenaDetectRequested)
        self.btn_arena_manual.toggled.connect(self._set_manual_mode)
        self.btn_arena_apply.clicked.connect(self._apply_manual)
        self.btn_arena_clear.clicked.connect(self._clear_points)
        self.btn_arena_auto_only.clicked.connect(self._drop_manual)
        self.chk_follow.toggled.connect(self._on_follow)
        self.chk_show_arena.toggled.connect(lambda _: self.player.refresh())
        self.sp_din.valueChanged.connect(self._on_diameters)
        self.sp_dout.valueChanged.connect(self._on_diameters)
        self.btn_csv_one.clicked.connect(lambda: self.robotCsvRequested.emit(int(self.cb_export_robot.currentData() or 0)))
        self.btn_csv_each.clicked.connect(self.allRobotsCsvRequested)
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
                                mirror=self.cb_mirror.currentData() or MIRROR_NONE,
                                scale_source=self.cb_scale.currentData() or SCALE_ARENA)

    def set_kinematics_from(self, p: Optional[KinematicsParams]) -> None:
        if p is None:
            return
        for w, v in ((self.sp_window, p.window), (self.sp_diam, p.robot_diameter_mm)):
            w.blockSignals(True)
            w.setValue(v)
            w.blockSignals(False)
        for cb, key in ((self.cb_mirror, getattr(p, "mirror", MIRROR_NONE)),
                        (self.cb_scale, getattr(p, "scale_source", SCALE_ARENA))):
            cb.blockSignals(True)
            cb.setCurrentIndex(max(0, cb.findData(key)))
            cb.blockSignals(False)

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
        if session.arena is not None:
            self.arena = session.arena
            for w, v in ((self.sp_din, session.arena.d_in_mm), (self.sp_dout, session.arena.d_out_mm)):
                w.blockSignals(True); w.setValue(v); w.blockSignals(False)
        elif self.arena is not None:
            session.arena = self.arena          # circle marked before analysing
        self._update_arena_label()
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
                  self.btn_clear, self.btn_csv, self.btn_csv_robot, self.btn_video, self.btn_save,
                  self.cb_export_robot, self.btn_csv_one, self.btn_csv_each):
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
        if self.cb_export_robot.count() != n:
            cur = self.cb_export_robot.currentData()
            self.cb_export_robot.clear()
            for k in range(n):
                self.cb_export_robot.addItem(f"#{k}", k)
            if cur is not None and cur < n:
                self.cb_export_robot.setCurrentIndex(int(cur))
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
        if self._manual_mode:
            self.lbl_hint.setText("Modo recinto: los clics marcan puntos del borde interior del anillo "
                                  "(no corrigen robots). Desactivá 'Marcar a mano' para volver.")
            return
        if self.session is None or self.session.result is None:
            self.lbl_hint.setText("Analizá el video para habilitar las correcciones.")
        elif self._selected is None:
            self.lbl_hint.setText("1) Hacé clic sobre un robot (o elegilo en la lista) para seleccionarlo.")
        else:
            self.lbl_hint.setText(f"2) Robot <b>#{self._selected}</b> seleccionado: hacé clic en su centro "
                                  "real. El seguimiento continúa desde ese punto. Esc cancela.")

    def _orientation(self) -> str:
        return ori.valid(self.cb_mirror.currentData())

    def _on_click(self, x: float, y: float) -> None:
        roi0 = self.session.roi if self.session is not None else self.state.roi
        x, y = (float(v) for v in ori.points(x, y, roi0.w, roi0.h, self._orientation()))   # display -> image
        if self._manual_mode:
            roi = self.session.roi if self.session is not None else self.state.roi
            self._manual_pts.append((x + roi.x, y + roi.y))
            self.lbl_pts.setText(f"Puntos: {len(self._manual_pts)}")
            self.btn_arena_apply.setEnabled(len(self._manual_pts) >= 3)
            self.player.refresh()
            return
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
        return self._draw_arena(self._transform_tracks(frame))

    def _draw_arena(self, img: np.ndarray) -> np.ndarray:
        if not self.chk_show_arena.isChecked() and not self._manual_mode:
            return img
        roi = self.session.roi if self.session is not None else self.state.roi
        a = self.arena.arena_at(self.player.current_index) if (self.arena is not None and self.arena.defined) else None
        key = self._orientation()
        h, w = img.shape[:2]
        if a is None:
            if not self._manual_pts:
                return img
            out = img.copy() if img.ndim == 3 else cv2.cvtColor(img, cv2.COLOR_GRAY2BGR)
            for (px, py) in self._manual_pts:
                qx, qy = ori.points(px - roi.x, py - roi.y, w, h, key)
                cv2.circle(out, (int(round(float(qx))), int(round(float(qy)))), 4, (255, 0, 255), -1, cv2.LINE_AA)
            return out
        a, pts = ar.oriented(a, (roi.x, roi.y), (w, h), key, self._manual_pts)
        return ar.draw(img, a, (roi.x, roi.y), ori.NONE, pts)     # img is already oriented

    def _transform_tracks(self, frame: np.ndarray) -> np.ndarray:
        s, v = self.session, self._sv
        roi = s.roi if s is not None else self.state.roi
        crop = roi.apply(frame)
        key = self._orientation()
        if s is None or v is None:
            return ori.image(crop, key)
        i = v.result.row_of(self.player.current_index)
        if i is None:
            return ori.image(crop, key)
        res, kin = v.result, v.kin
        xy = np.stack([res.x[i], res.y[i]], 1) - np.array([roi.x, roi.y])
        vel = np.stack([kin.vx[i], kin.vy[i]], 1) if (kin is not None and self.chk_vel.isChecked()) else None
        ang = kin.theta[i] if (kin is not None and self.chk_rot.isChecked() and s.has_rotation) else None
        return draw_oriented(crop, key, xy, res.status[i], s.detection.r_out, self._selected, vel, ang, fps=s.fps)

    # ------------------------------------------------------------------ enclosure
    def diameters(self) -> tuple[float, float]:
        return self.sp_din.value(), self.sp_dout.value()

    def set_arena(self, track: Optional[ar.ArenaTrack]) -> None:
        """New automatic result (keeps a manual circle if there is one)."""
        if track is not None and self.arena is not None and self.arena.manual is not None:
            track.manual, track.manual_frame = self.arena.manual, self.arena.manual_frame
            track.manual_points, track.follow_motion = self.arena.manual_points, self.chk_follow.isChecked()
        self.arena = track
        if self.session is not None:
            self.session.arena = track
        self._update_arena_label()
        self.player.refresh()

    def _update_arena_label(self) -> None:
        a = self.arena
        if a is None or not a.defined:
            self.lbl_arena.setText("<span style='color:#c33'>Recinto sin definir</span>: el origen de las "
                                   "exportaciones es el centro del recorte y la escala sale del diámetro del robot.")
        else:
            st = a.static()
            warn = "" if (st is not None and (st.reliable or a.manual is not None)) else \
                "<br><span style='color:#c60'>Detección dudosa: revisá el círculo o marcalo a mano.</span>"
            self.lbl_arena.setText(a.describe() + warn)
        self.btn_arena_auto_only.setEnabled(a is not None and a.manual is not None)
        self.chk_follow.setEnabled(a is not None and a.has_auto)

    def _set_manual_mode(self, on: bool) -> None:
        self._manual_mode = on
        if on:
            self._select(None)
        self.btn_arena_apply.setEnabled(len(self._manual_pts) >= 3)
        self._update_hint()
        self.player.refresh()

    def _clear_points(self) -> None:
        self._manual_pts.clear()
        self.lbl_pts.setText("Puntos: 0")
        self.btn_arena_apply.setEnabled(False)
        self.player.refresh()

    def _apply_manual(self) -> None:
        if len(self._manual_pts) < 3:
            return
        d_in, d_out = self.diameters()
        try:
            circ = ar.fit_points(self._manual_pts, d_in, d_out)
        except ValueError as exc:
            self.lbl_arena.setText(f"<span style='color:#c33'>{exc}</span>")
            return
        t = self.arena if self.arena is not None else ar.ArenaTrack.empty(d_in, d_out)
        t.manual, t.manual_frame = circ, int(self.player.current_index)
        t.manual_points = tuple(self._manual_pts)
        t.follow_motion = self.chk_follow.isChecked()
        self.arena = t
        if self.session is not None:
            self.session.arena = t
        self.btn_arena_manual.setChecked(False)
        self._manual_pts.clear()
        self.lbl_pts.setText("Puntos: 0")
        self._update_arena_label()
        self.arenaChanged.emit()
        self.player.refresh()

    def _drop_manual(self) -> None:
        if self.arena is None or self.arena.manual is None:
            return
        self.arena.manual = None
        self.arena.manual_frame = None
        self.arena.manual_points = ()
        if not self.arena.has_auto:
            self.arena = None
            if self.session is not None:
                self.session.arena = None
        self._update_arena_label()
        self.arenaChanged.emit()
        self.player.refresh()

    def _on_follow(self, on: bool) -> None:
        if self.arena is not None and self.arena.manual is not None:
            self.arena.follow_motion = on
            self._update_arena_label()
            self.arenaChanged.emit()
            self.player.refresh()

    def _on_diameters(self) -> None:
        if self.arena is None:
            return
        d_in, d_out = self.diameters()
        self.arena = self.arena.with_diameters(d_in, d_out)
        if self.session is not None:
            self.session.arena = self.arena
        self._update_arena_label()
        self._kin_debounce.start()

    def _on_loaded(self, info: VideoInfo) -> None:
        self.setEnabled(True)
        self.player.load(info.path)
        self.set_session(None)
        self.arena = None
        self._manual_pts.clear()
        self.lbl_pts.setText("Puntos: 0")
        self._update_arena_label()
        self._sv = None
        self.lbl_summary.setText("Sin análisis.")
        self.list_issues.clear()
        self._update_hint()
