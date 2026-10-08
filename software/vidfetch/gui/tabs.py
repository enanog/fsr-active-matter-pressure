from __future__ import annotations

import os
import re
import time
from typing import Optional

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (QCheckBox, QComboBox, QDoubleSpinBox, QFormLayout, QGroupBox, QHBoxLayout,
                               QInputDialog, QLabel, QPushButton, QScrollArea, QSpinBox, QVBoxLayout, QWidget)

from core.analysis import FrameProcessor
from core.detection import METHOD_DIRECT, METHOD_RING, TRACKPY_ERROR, DetectionParams
from core.models import Roi, TrimRange
from core.processing import OPERATIONS, Pipeline
from core.video_io import VideoInfo
from gui.frame_view import FrameView, RoiFrameView
from gui.player import PlayerWidget
from gui.state import ProjectState

PANEL_WIDTH = 300


def _side_panel() -> tuple[QWidget, QVBoxLayout]:
    panel = QWidget()
    panel.setFixedWidth(PANEL_WIDTH)
    lay = QVBoxLayout(panel)
    lay.setContentsMargins(6, 0, 0, 0)
    return panel, lay


_DURATION_CODE = re.compile(r"_(\d{1,4})$")  # project file code ..._XXYY_TT -> TT minutes


class OriginalTab(QWidget):
    """Video info + time scale (real capture rate of time-lapse videos)."""

    def __init__(self, state: ProjectState, parent=None):
        super().__init__(parent)
        self.state = state
        self.player = PlayerWidget(FrameView())
        self.info_lbl = QLabel("Abrí un video con Archivo → Abrir (Ctrl+O).")
        self.info_lbl.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)

        self.chk_lapse = QCheckBox("Video acelerado (time-lapse):")
        self.chk_lapse.setToolTip("Marcalo si el video se grabó a menos cuadros por segundo de los que "
                                  "reproduce. Todos los tiempos, velocidades y ω usan esta escala.")
        self.sp_fps = QDoubleSpinBox(decimals=3)
        self.sp_fps.setRange(0.001, 10000)
        self.sp_fps.setSingleStep(0.1)
        self.sp_fps.setSuffix(" cuadros = 1 s real")
        self.btn_from_duration = QPushButton("Calcular desde la duración real…")
        self.lbl_scale = QLabel()
        self.lbl_scale.setWordWrap(True)
        box = QGroupBox("Escala de tiempo")
        row = QHBoxLayout()
        row.addWidget(self.chk_lapse)
        row.addWidget(self.sp_fps)
        row.addWidget(self.btn_from_duration)
        row.addStretch(1)
        v = QVBoxLayout(box)
        v.addLayout(row)
        v.addWidget(self.lbl_scale)

        lay = QVBoxLayout(self)
        lay.addWidget(self.info_lbl)
        lay.addWidget(box)
        lay.addWidget(self.player, 1)

        self._sync_controls()
        self.chk_lapse.toggled.connect(self._on_controls)
        self.sp_fps.valueChanged.connect(self._on_controls)
        self.btn_from_duration.clicked.connect(self._from_duration)
        state.loaded.connect(self._on_loaded)
        state.timeScaleChanged.connect(lambda _: (self._sync_controls(), self._update_info()))

    def _sync_controls(self) -> None:
        lapse = self.state.real_fps is not None
        for w in (self.chk_lapse, self.sp_fps):
            w.blockSignals(True)
        self.chk_lapse.setChecked(lapse)
        if lapse:
            self.sp_fps.setValue(self.state.real_fps)
        self.sp_fps.setEnabled(lapse)
        self.btn_from_duration.setEnabled(lapse and self.state.info is not None)
        for w in (self.chk_lapse, self.sp_fps):
            w.blockSignals(False)

    def _on_controls(self) -> None:
        self.state.set_real_fps(self.sp_fps.value() if self.chk_lapse.isChecked() else None)
        self._sync_controls()
        self._update_info()

    def _from_duration(self) -> None:
        info = self.state.info
        if info is None:
            return
        m = _DURATION_CODE.search(os.path.splitext(os.path.basename(info.path))[0])
        # Prefill with the duration implied by the current scale: the _TT in the file name is the
        # nominal (planned) duration and can be off by >10 %, so it is only shown as a reference.
        guess = info.frame_count / self.state.time_fps / 60.0
        nominal = f"\nEl nombre del archivo indica {m.group(1)} min (valor nominal, no medido)." if m else ""
        minutes, ok = QInputDialog.getDouble(
            self, "Duración real del video",
            f"Duración real medida de la grabación [min]\n({info.frame_count} cuadros en el archivo)"
            + nominal, guess, 0.01, 100000.0, 2)
        if ok and minutes > 0:
            self.sp_fps.setValue(info.frame_count / (minutes * 60.0))  # triggers _on_controls

    def _update_info(self) -> None:
        info = self.state.info
        if info is None:
            self.lbl_scale.setText("")
            return
        real_s = info.frame_count / self.state.time_fps
        real_txt = f"{real_s / 60:.1f} min" if real_s >= 120 else f"{real_s:.2f} s"
        if self.state.real_fps is None:
            self.lbl_scale.setText(f"Tiempo real = tiempo del archivo ({info.fps:.3f} cuadros/s). "
                                   f"Duración real: {real_txt}.")
        else:
            self.lbl_scale.setText(
                f"1 cuadro = {1000.0 / self.state.time_fps:.1f} ms reales · el archivo se reproduce "
                f"<b>×{self.state.acceleration:.2f}</b> más rápido ({info.fps:.3f} fps) · "
                f"duración real: <b>{real_txt}</b> (archivo: {info.duration_s / 60:.1f} min).")

    def _on_loaded(self, info: VideoInfo) -> None:
        self.player.load(info.path)
        self.player.set_time_fps(self.state.time_fps)
        self.info_lbl.setText(
            f"<b>{info.path}</b><br>{info.width}×{info.height} px · {info.fps:.3f} fps del archivo · "
            f"{info.frame_count} cuadros · {info.duration_s:.3f} s de reproducción"
        )
        self._sync_controls()
        self._update_info()


class EditTab(QWidget):
    """Temporal trim (frame range) + spatial crop (ROI)."""

    saveRequested = Signal()

    def __init__(self, state: ProjectState, parent=None):
        super().__init__(parent)
        self.state = state
        self.view = RoiFrameView()
        self.player = PlayerWidget(self.view)

        # Temporal trim
        self.sp_start, self.sp_end = QSpinBox(), QSpinBox()
        self.lbl_start, self.lbl_end, self.lbl_dur = QLabel(), QLabel(), QLabel()
        btn_set_start = QPushButton("Inicio = cuadro actual")
        btn_set_end = QPushButton("Fin = cuadro actual")
        btn_go_start = QPushButton("Ir al inicio")
        btn_go_end = QPushButton("Ir al fin")
        trim_box = QGroupBox("Recorte temporal")
        f = QFormLayout(trim_box)
        f.addRow("Cuadro inicio", self.sp_start)
        f.addRow("", self.lbl_start)
        f.addRow("Cuadro fin", self.sp_end)
        f.addRow("", self.lbl_end)
        f.addRow("Duración", self.lbl_dur)
        row1, row2 = QHBoxLayout(), QHBoxLayout()
        row1.addWidget(btn_set_start); row1.addWidget(btn_set_end)
        row2.addWidget(btn_go_start); row2.addWidget(btn_go_end)
        f.addRow(row1)
        f.addRow(row2)

        # Spatial crop
        self.sp_x, self.sp_y, self.sp_w, self.sp_h = (QSpinBox() for _ in range(4))
        roi_box = QGroupBox("Región (rectángulo)")
        g = QFormLayout(roi_box)
        g.addRow(QLabel("Arrastrá con el mouse sobre el video\no ajustá los valores [px]."))
        for lbl, sp in (("x", self.sp_x), ("y", self.sp_y), ("Ancho", self.sp_w), ("Alto", self.sp_h)):
            g.addRow(lbl, sp)
        btn_reset = QPushButton("Cuadro completo")
        g.addRow(btn_reset)
        self.sp_side = QSpinBox()
        self.sp_side.setRange(8, 100000)
        self.sp_side.setValue(700)
        self.sp_side.setSuffix(" px")
        btn_square = QPushButton("Aplicar cuadrado")
        btn_square.setToolTip("Cuadrado del lado indicado, centrado en el recorte actual.")
        row_sq = QHBoxLayout()
        row_sq.addWidget(self.sp_side)
        row_sq.addWidget(btn_square)
        g.addRow("Lado", row_sq)
        self.chk_lock = QCheckBox("Bloquear tamaño (clic o arrastre = mover)")
        g.addRow(self.chk_lock)

        self.btn_save = QPushButton("Guardar recorte…")
        self.btn_save.setMinimumHeight(34)

        panel, pl = _side_panel()
        pl.addWidget(trim_box)
        pl.addWidget(roi_box)
        pl.addStretch(1)
        pl.addWidget(self.btn_save)

        lay = QHBoxLayout(self)
        lay.addWidget(self.player, 1)
        lay.addWidget(panel)

        # Wiring
        self.view.roiChanged.connect(state.set_roi)
        for sp in (self.sp_x, self.sp_y, self.sp_w, self.sp_h):
            sp.valueChanged.connect(self._roi_from_spins)
        self.sp_start.valueChanged.connect(self._trim_from_spins)
        self.sp_end.valueChanged.connect(self._trim_from_spins)
        btn_set_start.clicked.connect(lambda: self.sp_start.setValue(self.player.current_index))
        btn_set_end.clicked.connect(lambda: self.sp_end.setValue(self.player.current_index))
        btn_go_start.clicked.connect(lambda: self.player.seek(self.state.trim.start))
        btn_go_end.clicked.connect(lambda: self.player.seek(self.state.trim.end))
        btn_reset.clicked.connect(lambda: state.set_roi(Roi.full(state.info.width, state.info.height))
                                  if state.info else None)
        self.btn_save.clicked.connect(self.saveRequested)
        btn_square.clicked.connect(self._apply_square)
        self.chk_lock.toggled.connect(self._update_lock)

        state.loaded.connect(self._on_loaded)
        state.trimChanged.connect(self._on_trim)
        state.roiChanged.connect(self._on_roi)
        self.setEnabled(False)

    def _on_loaded(self, info: VideoInfo) -> None:
        self.setEnabled(True)
        self.player.load(info.path)
        last = info.frame_count - 1
        for sp in (self.sp_start, self.sp_end):
            sp.blockSignals(True); sp.setRange(0, last); sp.blockSignals(False)
        for sp, hi in ((self.sp_x, info.width - 1), (self.sp_y, info.height - 1),
                       (self.sp_w, info.width), (self.sp_h, info.height)):
            sp.blockSignals(True); sp.setRange(0 if sp in (self.sp_x, self.sp_y) else 2, hi); sp.blockSignals(False)

    def _apply_square(self) -> None:
        info, r = self.state.info, self.state.roi
        if info is None:
            return
        side = min(self.sp_side.value(), info.width, info.height)
        cx, cy = r.x + r.w // 2, r.y + r.h // 2
        x = min(max(0, cx - side // 2), info.width - side)
        y = min(max(0, cy - side // 2), info.height - side)
        self.state.set_roi(Roi(x, y, side, side))
        self.chk_lock.setChecked(True)

    def _update_lock(self) -> None:
        r = self.state.roi
        self.view.set_fixed_size((r.w, r.h) if self.chk_lock.isChecked() else None)
        for sp in (self.sp_w, self.sp_h):
            sp.setEnabled(not self.chk_lock.isChecked())

    def _trim_from_spins(self) -> None:
        s, e = self.sp_start.value(), self.sp_end.value()
        if self.sender() is self.sp_start and s > e:
            e = s
        elif self.sender() is self.sp_end and e < s:
            s = e
        self.state.set_trim(TrimRange(s, e))

    def _roi_from_spins(self) -> None:
        self.state.set_roi(Roi(self.sp_x.value(), self.sp_y.value(), self.sp_w.value(), self.sp_h.value()))

    def _on_trim(self, t: TrimRange) -> None:
        fps = self.state.info.fps
        for sp, v in ((self.sp_start, t.start), (self.sp_end, t.end)):
            sp.blockSignals(True); sp.setValue(v); sp.blockSignals(False)
        self.lbl_start.setText(f"t = {t.start / fps:.3f} s")
        self.lbl_end.setText(f"t = {t.end / fps:.3f} s")
        self.lbl_dur.setText(f"{t.length} cuadros · {t.length / fps:.3f} s")

    def _on_roi(self, r: Roi) -> None:
        for sp, v in ((self.sp_x, r.x), (self.sp_y, r.y), (self.sp_w, r.w), (self.sp_h, r.h)):
            sp.blockSignals(True); sp.setValue(v); sp.blockSignals(False)
        self.view.set_roi(r)
        if self.chk_lock.isChecked():
            self.view.set_fixed_size((r.w, r.h))


def _spin(minimum, maximum, value, step=1, decimals=0, suffix=""):
    sp = QDoubleSpinBox(decimals=decimals) if decimals > 0 else QSpinBox()
    sp.setRange(minimum, maximum)
    sp.setSingleStep(step)
    sp.setValue(value)
    if suffix:
        sp.setSuffix(suffix)
    return sp


class DetectionPanel(QGroupBox):
    """Controls for trackpy robot detection + trajectory linking."""

    changed = Signal()
    calibrateRequested = Signal()

    def __init__(self, parent=None):
        super().__init__("Detección de robots (Trackpy)", parent)
        self.setCheckable(True)
        self.setChecked(False)
        d = DetectionParams()

        self.cb_method = QComboBox()
        self.cb_method.addItem("Filtro de anillo (robots)", METHOD_RING)
        self.cb_method.addItem("Trackpy directo", METHOD_DIRECT)
        self.sp_rin = _spin(1, 2000, d.r_in, 1, 1, " px")
        self.sp_rout = _spin(2, 2500, d.r_out, 1, 1, " px")
        self.sp_scale = _spin(0.05, 1.0, d.scale, 0.05, 2)
        self.sp_ring_gray = _spin(1, 255, d.ring_gray_max, 5)
        self.sp_sep = _spin(1, 5000, d.separation, 1, 1, " px")
        self.sp_minmass = _spin(0, 1e7, d.minmass, 50)
        self.chk_invert = QCheckBox("Invertir (objetos oscuros)")
        self.chk_validate = QCheckBox("Validar anillo oscuro completo")
        self.chk_validate.setChecked(d.validate_ring)
        self.sp_cov = _spin(0.0, 1.0, d.min_coverage, 0.02, 2)
        self.sp_pix_dark = _spin(1, 255, d.ring_pixel_dark, 5)

        self.chk_link = QCheckBox("Vincular trayectorias (tp.link)")
        self.chk_link.setChecked(True)
        self.sp_search = _spin(1, 1000, 30, 1, 1, " px")
        self.sp_memory = _spin(0, 1000, 3, 1, 0, " cuadros")
        self.sp_min_len = _spin(1, 100000, 15, 1, 0, " cuadros")
        self.sp_min_len.setToolTip("Descarta trayectorias más cortas (tp.filter_stubs): "
                                   "elimina falsos positivos transitorios.")

        self.lbl_status = QLabel("—")
        self.lbl_status.setWordWrap(True)
        if TRACKPY_ERROR:
            self.lbl_status.setText(f"<span style='color:#c33'>{TRACKPY_ERROR}</span>")
        self.btn_csv = QPushButton("Exportar posiciones (CSV)…")
        self.btn_calibrate = QPushButton("Calibrar tamaño automáticamente")
        self.btn_calibrate.setToolTip("Mide el tamaño aparente de los robots en el recorte actual y ajusta "
                                      "radios, escala, separación y umbrales de gris.")
        self.lbl_calib = QLabel("Sin calibrar: valores para robots de ~96 px de diámetro.")
        self.lbl_calib.setWordWrap(True)

        f = QFormLayout(self)
        f.addRow(self.btn_calibrate)
        f.addRow(self.lbl_calib)
        f.addRow("Método", self.cb_method)
        f.addRow("Radio disco brillante", self.sp_rin)
        f.addRow("Radio exterior anillo", self.sp_rout)
        f.addRow("Gris máx. anillo (filtro)", self.sp_ring_gray)
        f.addRow("Escala de análisis", self.sp_scale)
        f.addRow("Separación mínima", self.sp_sep)
        f.addRow("Masa mínima", self.sp_minmass)
        f.addRow(self.chk_invert)
        f.addRow(self.chk_validate)
        f.addRow("Cobertura mínima", self.sp_cov)
        f.addRow("Gris máx. píxel anillo", self.sp_pix_dark)
        f.addRow(self.chk_link)
        f.addRow("Radio de búsqueda", self.sp_search)
        f.addRow("Memoria", self.sp_memory)
        f.addRow("Long. mín. trayectoria", self.sp_min_len)
        f.addRow(self.lbl_status)
        f.addRow(self.btn_csv)

        for w in (self.sp_rin, self.sp_rout, self.sp_scale, self.sp_ring_gray, self.sp_sep,
                  self.sp_minmass, self.sp_cov, self.sp_pix_dark):
            w.valueChanged.connect(self.changed)
        for w in (self.chk_invert, self.chk_validate):
            w.toggled.connect(self.changed)
        self.cb_method.currentIndexChanged.connect(self._update_enabled)
        self.chk_validate.toggled.connect(self._update_enabled)
        self.chk_link.toggled.connect(self._update_enabled)
        self.toggled.connect(self.changed)
        self.btn_calibrate.clicked.connect(self.calibrateRequested)
        self._update_enabled()

    def apply_params(self, p: DetectionParams) -> None:
        """Load size/intensity-dependent values (e.g. from calibration) without N refreshes."""
        pairs = ((self.sp_rin, p.r_in), (self.sp_rout, p.r_out), (self.sp_scale, p.scale),
                 (self.sp_ring_gray, p.ring_gray_max), (self.sp_sep, p.separation),
                 (self.sp_pix_dark, p.ring_pixel_dark))
        for sp, v in pairs:
            sp.blockSignals(True)
            sp.setValue(v)
            sp.blockSignals(False)
        self.changed.emit()

    def _update_enabled(self) -> None:
        ring = self.cb_method.currentData() == METHOD_RING
        self.sp_ring_gray.setEnabled(ring)
        self.chk_invert.setEnabled(not ring)
        for w in (self.sp_cov, self.sp_pix_dark):
            w.setEnabled(self.chk_validate.isChecked())
        for w in (self.sp_search, self.sp_memory, self.sp_min_len):
            w.setEnabled(self.chk_link.isChecked())
        self.changed.emit()

    def params(self) -> DetectionParams:
        return DetectionParams(
            enabled=self.isChecked() and TRACKPY_ERROR is None,
            method=self.cb_method.currentData(),
            r_in=self.sp_rin.value(), r_out=self.sp_rout.value(), scale=self.sp_scale.value(),
            ring_gray_max=self.sp_ring_gray.value(), separation=self.sp_sep.value(),
            minmass=self.sp_minmass.value(), invert=self.chk_invert.isChecked(),
            validate_ring=self.chk_validate.isChecked(), min_coverage=self.sp_cov.value(),
            ring_pixel_dark=self.sp_pix_dark.value(),
        )

    def link_params(self) -> Optional[tuple[float, int, int]]:
        if not self.chk_link.isChecked():
            return None
        return self.sp_search.value(), int(self.sp_memory.value()), int(self.sp_min_len.value())


class ProcessTab(QWidget):
    """Preview of trim+crop with a configurable processing pipeline and robot detection."""

    saveRequested = Signal()
    csvRequested = Signal()
    calibrateRequested = Signal()

    def __init__(self, state: ProjectState, parent=None):
        super().__init__(parent)
        self.state = state
        self.player = PlayerWidget(FrameView())
        self.player.set_transform(self._transform)
        self.lbl_out = QLabel()

        ops_widget = QWidget()
        ops_lay = QVBoxLayout(ops_widget)
        ops_lay.setContentsMargins(0, 0, 0, 0)
        ops_lay.addWidget(QLabel("<b>Operaciones</b> (se aplican en orden, antes de detectar)"))
        self._controls: list[tuple] = []
        for op in OPERATIONS:
            box = QGroupBox(op.label)
            box.setCheckable(True)
            box.setChecked(False)
            form = QFormLayout(box)
            spins = {}
            for ps in op.params:
                sp = _spin(ps.minimum, ps.maximum, ps.default, ps.step, ps.decimals)
                sp.valueChanged.connect(self.player.refresh)
                form.addRow(ps.label, sp)
                spins[ps.key] = sp
            if not op.params:
                form.addRow(QLabel("(sin parámetros)"))
            box.toggled.connect(self.player.refresh)
            ops_lay.addWidget(box)
            self._controls.append((op, box, spins))

        self.det_panel = DetectionPanel()
        self.det_panel.changed.connect(self.player.refresh)
        ops_lay.addWidget(self.det_panel)
        ops_lay.addStretch(1)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(ops_widget)

        self.btn_save = QPushButton("Guardar video procesado…")
        self.btn_save.setMinimumHeight(34)

        panel, pl = _side_panel()
        panel.setFixedWidth(PANEL_WIDTH + 40)
        pl.addWidget(scroll, 1)
        pl.addWidget(self.lbl_out)
        pl.addWidget(self.btn_save)

        lay = QHBoxLayout(self)
        lay.addWidget(self.player, 1)
        lay.addWidget(panel)

        self.btn_save.clicked.connect(self.saveRequested)
        self.det_panel.btn_csv.clicked.connect(self.csvRequested)
        self.det_panel.calibrateRequested.connect(self.calibrateRequested)
        state.loaded.connect(self._on_loaded)
        state.trimChanged.connect(lambda t: self.player.set_range(t.start, t.end))
        state.roiChanged.connect(self._on_roi)
        self.setEnabled(False)

    def build_pipeline(self) -> Pipeline:
        steps = [(op, {k: sp.value() for k, sp in spins.items()})
                 for op, box, spins in self._controls if box.isChecked()]
        return Pipeline(steps)

    def build_processor(self) -> FrameProcessor:
        return FrameProcessor(self.build_pipeline(), self.det_panel.params())

    def _transform(self, frame):
        proc = self.build_processor()
        t0 = time.perf_counter()
        try:
            out, found = proc.run(self.state.roi.apply(frame))
        except Exception as exc:
            self.det_panel.lbl_status.setText(f"<span style='color:#c33'>Error: {exc}</span>")
            raise
        if found is not None:
            dt = (time.perf_counter() - t0) * 1e3
            self.det_panel.lbl_status.setText(f"<b>{len(found)}</b> robots detectados · {dt:.0f} ms/cuadro")
        elif TRACKPY_ERROR is None:
            self.det_panel.lbl_status.setText("Detección desactivada")
        return out

    def _on_loaded(self, info: VideoInfo) -> None:
        self.setEnabled(True)
        self.player.load(info.path)

    def _on_roi(self, r: Roi) -> None:
        # Exporter drops one row/column on odd sizes (encoder requirement).
        self.lbl_out.setText(f"Salida: {r.w - r.w % 2}×{r.h - r.h % 2} px")
        self.player.refresh()
