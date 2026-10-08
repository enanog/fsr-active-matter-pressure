"""Parameter panels (left dock). Each panel loads values from TrialSettings with signals blocked
(`load`) and writes them back on user edits (`store`), then emits `changed`."""

from __future__ import annotations

from typing import Optional

import numpy as np
from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtWidgets import (QAbstractItemView, QCheckBox, QComboBox, QDoubleSpinBox, QFormLayout,
                               QGroupBox, QHBoxLayout, QHeaderView, QLabel, QListWidget,
                               QListWidgetItem, QPushButton, QSpinBox, QTableWidget,
                               QTableWidgetItem, QVBoxLayout, QWidget)

from core import paths
from core.export import COLUMNS, header
from core.session import TrialData
from core.settings import TrialSettings
from gui.plots import RAW_COLUMNS, SPEC_BY_ID

NONE_SENTINEL = -1.0


def dspin(lo: float, hi: float, dec: int, step: float, suffix: str = "", tip: str = "") -> QDoubleSpinBox:
    w = QDoubleSpinBox()
    w.setRange(lo, hi)
    w.setDecimals(dec)
    w.setSingleStep(step)
    w.setKeyboardTracking(False)        # emit on Enter / focus-out / arrows, not every keystroke
    if suffix:
        w.setSuffix(" " + suffix)
    if tip:
        w.setToolTip(tip)
    return w


def note(text: str = "") -> QLabel:
    lab = QLabel(text)
    lab.setWordWrap(True)
    lab.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
    lab.setStyleSheet("color:#444;")
    return lab


class _Panel(QWidget):
    changed = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._loading = False

    def _emit(self, *_):
        if not self._loading:
            self.changed.emit()

    def _watch(self, *widgets):
        for w in widgets:
            if isinstance(w, (QDoubleSpinBox, QSpinBox)):
                w.valueChanged.connect(self._emit)
            elif isinstance(w, QCheckBox):
                w.toggled.connect(self._emit)
            elif isinstance(w, QComboBox):
                w.currentIndexChanged.connect(self._emit)


# =============================================================================================
class TrialPanel(QWidget):
    trialSelected = Signal(object)        # paths.Trial
    openLogRequested = Signal()
    openVideoRequested = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.list = QListWidget()
        self.list.itemActivated.connect(self._pick)
        self.list.itemClicked.connect(self._pick)
        b_reload = QPushButton("Actualizar lista")
        b_reload.clicked.connect(self.refresh)
        b_open = QPushButton("Abrir registro…")
        b_open.clicked.connect(self.openLogRequested)
        b_video = QPushButton("Abrir video…")
        b_video.clicked.connect(self.openVideoRequested)
        self.info = note()
        row = QHBoxLayout()
        for b in (b_reload, b_open, b_video):
            row.addWidget(b)
        lay = QVBoxLayout(self)
        lay.addWidget(QLabel(f"Registros en {paths.RAW_DIR.relative_to(paths.REPO_ROOT).as_posix()}/"))
        lay.addWidget(self.list, 2)
        lay.addLayout(row)
        lay.addWidget(self.info, 1)
        self._trials: list[paths.Trial] = []
        self.refresh()

    def refresh(self) -> None:
        cur = self.current_code()
        self.list.clear()
        self._trials = paths.discover_trials()
        for tr in self._trials:
            tags = []
            if tr.video_path is not None:
                tags.append("video")
            if tr.traj_path is not None:
                tags.append("trayectorias")
            if paths.config_path(tr).is_file():
                tags.append("config")
            it = QListWidgetItem(tr.label + (f"   [{', '.join(tags)}]" if tags else ""))
            it.setData(Qt.ItemDataRole.UserRole, tr)
            it.setToolTip(str(tr.raw_path))
            self.list.addItem(it)
            if tr.code == cur:
                self.list.setCurrentItem(it)

    def current_code(self) -> Optional[str]:
        it = self.list.currentItem()
        return it.data(Qt.ItemDataRole.UserRole).code if it is not None else None

    def select_code(self, code: str) -> None:
        for i in range(self.list.count()):
            it = self.list.item(i)
            if it.data(Qt.ItemDataRole.UserRole).code == code:
                self.list.setCurrentItem(it)
                return

    def _pick(self, it: QListWidgetItem) -> None:
        self.trialSelected.emit(it.data(Qt.ItemDataRole.UserRole))

    def show_info(self, td: Optional[TrialData], video_path, video_msg: str = "") -> None:
        if td is None:
            self.info.setText("")
            return
        r, s = td.raw, td.series
        led = (f"{r.led_on:.2f} → {r.led_off:.2f} s" if np.isfinite(r.led_off) else "no registrado")
        lines = [
            f"<b>{td.trial.code}</b>",
            f"Registro: {r.path.name} · {len(r.data)} filas · {r.duration_s / 60:.1f} min reales",
            f"Pulso LED de sincronía: {led}",
            "Factor del firmware: " + (f"{r.k_firmware:.4f} µS/cuenta (≈ R_FB {td.settings.calibration.r_feedback_from_k(r.k_firmware):.0f} Ω)"
                                        if r.k_firmware else "no disponible"),
            f"Saturación: {100 * s.sat.mean():.2f} % de las muestras",
            f"Video: {video_path.name if video_path else 'no encontrado'}" + (f" ({video_msg})" if video_msg else ""),
            f"Trayectorias: {td.trial.traj_path.name if td.robots is not None else 'no'}"
            + (f" ({td.robots_error})" if td.robots_error else ""),
        ]
        lines += [f"<span style='color:#b00'>Aviso: {w}</span>" for w in r.warnings]
        self.info.setText("<br>".join(lines))


# =============================================================================================
class CalibrationPanel(_Panel):
    copyDetected = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.mode = QComboBox()
        self.mode.addItem("Automática (factor que registró el firmware)", "auto")
        self.mode.addItem("Manual (parámetros del front-end)", "manual")
        self.v_ref = dspin(0.1, 10, 4, 0.1, "V", "Tensión de referencia del ADC")
        self.v_exc = dspin(0.0001, 10, 4, 0.01, "V", "Tensión de excitación del FSR")
        self.r_fb = dspin(1, 1e7, 1, 100, "Ω", "Resistencia de realimentación del transimpedancia")
        self.adc_fs = dspin(1, 1e6, 0, 1, "cuentas", "Código de fondo de escala (10 bits = 1023)")
        form = QFormLayout()
        form.addRow("Modo", self.mode)
        form.addRow("V_REF", self.v_ref)
        form.addRow("V_EXC", self.v_exc)
        form.addRow("R_FEEDBACK", self.r_fb)
        form.addRow("ADC fondo de escala", self.adc_fs)
        self.b_copy = QPushButton("Usar el R_FEEDBACK detectado en modo manual")
        self.b_copy.clicked.connect(self.copyDetected)
        self.summary = note()
        lay = QVBoxLayout(self)
        lay.addWidget(note("Modelo: V_out = V_EXC·R_FEEDBACK/R_FSR, G = 1/R_FSR = ADC·K, "
                           "K = V_REF·10⁶/(ADC_FS·V_EXC·R_FEEDBACK) [µS/cuenta]."))
        lay.addLayout(form)
        lay.addWidget(self.b_copy)
        lay.addWidget(self.summary)
        lay.addStretch(1)
        self._watch(self.mode, self.v_ref, self.v_exc, self.r_fb, self.adc_fs)

    def load(self, s: TrialSettings, td: Optional[TrialData]) -> None:
        self._loading = True
        c = s.calibration
        self.mode.setCurrentIndex(max(0, self.mode.findData(c.mode)))
        self.v_ref.setValue(c.v_ref)
        self.v_exc.setValue(c.v_exc)
        self.r_fb.setValue(c.r_feedback)
        self.adc_fs.setValue(c.adc_fs)
        self._loading = False
        self.update_summary(td)

    def store(self, s: TrialSettings) -> None:
        c = s.calibration
        c.mode = self.mode.currentData()
        c.v_ref, c.v_exc = self.v_ref.value(), self.v_exc.value()
        c.r_feedback, c.adc_fs = self.r_fb.value(), self.adc_fs.value()

    def update_summary(self, td: Optional[TrialData]) -> None:
        manual = self.mode.currentData() == "manual"
        # In auto mode R_FEEDBACK only matters when the log has no firmware factor.
        self.r_fb.setEnabled(manual or td is None or td.raw.k_firmware is None)
        self.b_copy.setEnabled(td is not None and td.raw.k_firmware is not None)
        if td is None or td.series is None:
            self.summary.setText("")
            return
        s = td.series
        warn = ""
        if self.mode.currentData() == "auto" and td.raw.k_firmware is None:
            warn = "<br><span style='color:#b00'>El registro no trae G ni R: se usan los parámetros.</span>"
        if manual and td.raw.k_firmware:
            ratio = s.k_us / td.raw.k_firmware
            if abs(ratio - 1) > 0.02:
                warn += (f"<br><span style='color:#b00'>K manual = {ratio:.3g} × el del firmware: "
                         f"revisar R_FEEDBACK.</span>")
        self.summary.setText(
            f"K en uso: <b>{s.k_us:.5f} µS/cuenta</b> ({s.k_source})<br>"
            f"R_FEEDBACK equivalente: {s.r_feedback_eff:.1f} Ω<br>"
            f"Saturación: G máx = {s.g_max:.1f} µS ⇔ R_FSR mín = {s.r_floor:.1f} Ω<br>"
            f"Muestras saturadas: {100 * s.sat.mean():.2f} %{warn}")


# =============================================================================================
class AnalysisPanel(_Panel):
    cropFromLed = Signal()
    cropToView = Signal()
    cropAll = Signal()
    cropToSelection = Signal()
    excludeSelection = Signal()
    selectionToggled = Signal(bool)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.step = dspin(0.005, 5, 3, 0.05, "s", "Paso de remuestreo uniforme y del barrido de ΔT")
        self.dT_fixed = dspin(0.005, 600, 3, 0.5, "s", "Ventana de la serie ΔG(t) = G(t) − G(t − ΔT)")
        self.dT_max = dspin(0.01, 600, 2, 1, "s", "Ventana más grande del barrido de asimetría/curtosis")
        self.bins = QSpinBox()
        self.bins.setRange(5, 2000)
        self.bins.setKeyboardTracking(False)
        f1 = QFormLayout()
        f1.addRow("Paso de remuestreo", self.step)
        f1.addRow("ΔT de la serie ΔG(t)", self.dT_fixed)
        f1.addRow("ΔT máx. del barrido", self.dT_max)
        f1.addRow("Clases de histograma", self.bins)
        g1 = QGroupBox("Ventanas")
        g1.setLayout(f1)

        self.t0 = dspin(NONE_SENTINEL, 1e6, 2, 1, "s")
        self.t1 = dspin(NONE_SENTINEL, 1e6, 2, 1, "s")
        self.t0.setSpecialValueText("inicio del registro")
        self.t1.setSpecialValueText("fin del registro")
        f2 = QFormLayout()
        f2.addRow("Desde", self.t0)
        f2.addRow("Hasta", self.t1)
        b_led, b_view, b_all = (QPushButton("Desde fin del LED"), QPushButton("Vista actual"),
                                QPushButton("Todo"))
        b_led.clicked.connect(self.cropFromLed)
        b_view.clicked.connect(self.cropToView)
        b_all.clicked.connect(self.cropAll)
        r = QHBoxLayout()
        for b in (b_led, b_view, b_all):
            r.addWidget(b)
        f2.addRow(r)
        g2 = QGroupBox("Recorte (tiempo del sensor)")
        g2.setLayout(f2)

        self.sel = QCheckBox("Mostrar selección (región amarilla arrastrable)")
        self.sel.toggled.connect(self.selectionToggled)
        b_csel, b_xsel = QPushButton("Recortar a la selección"), QPushButton("Excluir selección")
        b_csel.clicked.connect(self.cropToSelection)
        b_xsel.clicked.connect(self.excludeSelection)
        self.table = QTableWidget(0, 2)
        self.table.setHorizontalHeaderLabels(["desde [s]", "hasta [s]"])
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.table.setMaximumHeight(130)
        self.table.itemChanged.connect(self._emit)
        b_del = QPushButton("Quitar exclusión")
        b_del.clicked.connect(self._remove_row)
        self.excl_sat = QCheckBox("Excluir muestras saturadas de la estadística")
        g3 = QGroupBox("Selección y tramos excluidos")
        v3 = QVBoxLayout(g3)
        v3.addWidget(self.sel)
        r3 = QHBoxLayout()
        r3.addWidget(b_csel)
        r3.addWidget(b_xsel)
        v3.addLayout(r3)
        v3.addWidget(self.table)
        v3.addWidget(b_del)
        v3.addWidget(self.excl_sat)

        self.summary = note()
        lay = QVBoxLayout(self)
        lay.addWidget(g1)
        lay.addWidget(g2)
        lay.addWidget(g3)
        lay.addWidget(self.summary)
        lay.addStretch(1)
        self._watch(self.step, self.dT_fixed, self.dT_max, self.bins, self.t0, self.t1, self.excl_sat)

    def _remove_row(self) -> None:
        rows = sorted({i.row() for i in self.table.selectedIndexes()}, reverse=True)
        if not rows and self.table.rowCount():
            rows = [self.table.rowCount() - 1]
        for r in rows:
            self.table.removeRow(r)
        self._emit()

    def load(self, s: TrialSettings, td: Optional[TrialData]) -> None:
        self._loading = True
        a = s.analysis
        self.step.setValue(a.step_s)
        self.dT_fixed.setValue(a.deltaT_fixed_s)
        self.dT_max.setValue(a.deltaT_max_s)
        self.bins.setValue(a.hist_bins)
        dur = td.raw.duration_s if td is not None else 1e6
        for w in (self.t0, self.t1):
            w.setMaximum(dur)
        self.t0.setValue(NONE_SENTINEL if a.t_start is None else a.t_start)
        self.t1.setValue(NONE_SENTINEL if a.t_end is None else a.t_end)
        self.table.blockSignals(True)
        self.table.setRowCount(0)
        for seg in a.exclusions:
            r = self.table.rowCount()
            self.table.insertRow(r)
            for c in range(2):
                self.table.setItem(r, c, QTableWidgetItem(f"{float(seg[c]):.2f}"))
        self.table.blockSignals(False)
        self.excl_sat.setChecked(a.exclude_saturated)
        self._loading = False

    def store(self, s: TrialSettings) -> None:
        a = s.analysis
        a.step_s, a.deltaT_fixed_s = self.step.value(), self.dT_fixed.value()
        a.deltaT_max_s, a.hist_bins = self.dT_max.value(), self.bins.value()
        a.t_start = None if self.t0.value() <= NONE_SENTINEL else self.t0.value()
        a.t_end = None if self.t1.value() <= NONE_SENTINEL else self.t1.value()
        excl = []
        for r in range(self.table.rowCount()):
            try:
                excl.append(sorted([float(self.table.item(r, c).text().replace(",", ".")) for c in range(2)]))
            except (AttributeError, ValueError):
                continue
        a.exclusions = excl
        a.exclude_saturated = self.excl_sat.isChecked()

    def show_summary(self, n_used: int, n_total: int, step: float, extra: str = "") -> None:
        self.summary.setText(f"En la estadística: {n_used} de {n_total} muestras "
                             f"({n_used * step / 60:.1f} min){extra}")


# =============================================================================================
class SyncPanel(_Panel):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.fr = dspin(0.01, 1000, 4, 0.01, "cuadros/s",
                        "Cuadros de video por segundo REAL (time-lapse ×10: 3 cuadros = 1 s)")
        self.auto = QCheckBox("Desfase = fin del pulso LED (automático)")
        self.offset = dspin(-1e5, 1e5, 2, 0.1, "s", "Tiempo del sensor que corresponde al cuadro 0")
        self.mirror = QCheckBox("Video espejado (mostrar volteado horizontalmente)")
        self.robots = QCheckBox("Superponer robots de VidFetch (color = |v|)")
        self.radius = dspin(2, 500, 1, 1, "px", "Radio dibujado de cada robot")
        form = QFormLayout()
        form.addRow("Escala de tiempo", self.fr)
        form.addRow(self.auto)
        form.addRow("Desfase (t sensor del cuadro 0)", self.offset)
        form.addRow(self.mirror)
        form.addRow(self.robots)
        form.addRow("Radio del robot", self.radius)
        self.summary = note()
        lay = QVBoxLayout(self)
        lay.addWidget(note("t_sensor = desfase + cuadro / (cuadros por segundo real). El video "
                           "recortado empieza al terminar el pulso LED de 5 s del registrador."))
        lay.addLayout(form)
        lay.addWidget(self.summary)
        lay.addStretch(1)
        self.auto.toggled.connect(lambda on: self.offset.setEnabled(not on))
        self._watch(self.fr, self.auto, self.offset, self.mirror, self.robots, self.radius)

    def load(self, s: TrialSettings, td: Optional[TrialData]) -> None:
        self._loading = True
        sy = s.sync
        self.fr.setValue(sy.frames_per_s)
        self.auto.setChecked(sy.offset_auto)
        self.offset.setValue(td.offset_s if td is not None else sy.offset_s)
        self.offset.setEnabled(not sy.offset_auto)
        self.mirror.setChecked(sy.mirror)
        self.robots.setChecked(sy.show_robots)
        self.radius.setValue(sy.robot_radius_px)
        self.robots.setEnabled(td is not None and td.robots is not None)
        self._loading = False
        self.update_summary(td, None)

    def store(self, s: TrialSettings) -> None:
        sy = s.sync
        sy.frames_per_s = self.fr.value()
        sy.offset_auto = self.auto.isChecked()
        sy.offset_s = self.offset.value()
        sy.mirror = self.mirror.isChecked()
        sy.show_robots = self.robots.isChecked()
        sy.robot_radius_px = self.radius.value()

    def update_summary(self, td: Optional[TrialData], n_frames: Optional[int]) -> None:
        if td is None:
            self.summary.setText("")
            return
        led = td.led_offset
        self._loading = True
        self.offset.setValue(td.offset_s)
        self._loading = False
        txt = [f"Desfase en uso: <b>{td.offset_s:.2f} s</b>"
               + (" (fin del LED)" if td.settings.sync.offset_auto and led is not None else "")]
        if td.settings.sync.offset_auto and led is None:
            txt.append("<span style='color:#b00'>El registro no tiene pulso LED: se usa el valor manual.</span>")
        if n_frames:
            dur_v = n_frames / td.settings.sync.frames_per_s
            dur_s = td.raw.duration_s - td.offset_s
            txt.append(f"Video: {n_frames} cuadros = {dur_v:.1f} s reales; registro después del "
                       f"desfase: {dur_s:.1f} s (diferencia {dur_v - dur_s:+.1f} s)")
            txt.append(f"Escala que haría coincidir las duraciones: {n_frames / max(dur_s, 1e-9):.4f} cuadros/s")
        self.summary.setText("<br>".join(txt))


# =============================================================================================
class PlotsPanel(QWidget):
    statesChanged = Signal()
    optionChanged = Signal(str, dict)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.list = QListWidget()
        self.list.setDragDropMode(QAbstractItemView.DragDropMode.InternalMove)
        # Deferred so a drag (remove + insert, or move) is reported once, after it completes.
        self._notify = QTimer(self, singleShot=True, interval=0)
        self._notify.timeout.connect(self.statesChanged)
        m = self.list.model()
        for sig in (m.rowsMoved, m.rowsInserted, m.rowsRemoved):
            sig.connect(lambda *a: self._notify.start())
        self.list.itemChanged.connect(lambda *a: self._notify.start())
        self.list.currentItemChanged.connect(self._show_options)
        self.box = QGroupBox("Opciones del gráfico")
        self.form = QFormLayout(self.box)
        lay = QVBoxLayout(self)
        lay.addWidget(note("Tildá los gráficos a mostrar y arrastralos para ordenarlos. Los de "
                           "tiempo van a la columna izquierda; los estadísticos, a la derecha. "
                           "Clic derecho sobre un gráfico: escala, exportar imagen o datos."))
        lay.addWidget(self.list, 1)
        lay.addWidget(self.box)
        self._opts: dict[str, dict] = {}
        self._raw_columns: list[str] = []

    def load(self, states: list[dict], has_robots: bool, raw_columns: list[str]) -> None:
        self._raw_columns = raw_columns
        self.list.blockSignals(True)
        self.list.model().blockSignals(True)
        self.list.clear()
        for st in states:
            spec = SPEC_BY_ID[st["id"]]
            it = QListWidgetItem(("◷ " if spec.kind == "time" else "∑ ") + spec.title
                                 + ("  (sin trayectorias)" if spec.needs_robots and not has_robots else ""))
            it.setData(Qt.ItemDataRole.UserRole, spec.id)
            it.setFlags(it.flags() | Qt.ItemFlag.ItemIsUserCheckable | Qt.ItemFlag.ItemIsDragEnabled)
            it.setFlags(it.flags() & ~Qt.ItemFlag.ItemIsDropEnabled)
            it.setCheckState(Qt.CheckState.Checked if st["visible"] else Qt.CheckState.Unchecked)
            self.list.addItem(it)
            self._opts[spec.id] = dict(st["options"])
        self.list.model().blockSignals(False)
        self.list.blockSignals(False)
        self.list.reset()
        self._show_options(self.list.currentItem())

    def states(self) -> list[dict]:
        out = []
        for i in range(self.list.count()):
            it = self.list.item(i)
            pid = it.data(Qt.ItemDataRole.UserRole)
            out.append({"id": pid, "visible": it.checkState() == Qt.CheckState.Checked,
                        "options": dict(self._opts.get(pid, {}))})
        return out

    def _show_options(self, it: Optional[QListWidgetItem], *_):
        while self.form.rowCount():
            self.form.removeRow(0)
        if it is None:
            self.box.setTitle("Opciones del gráfico (elegí uno de la lista)")
            return
        pid = it.data(Qt.ItemDataRole.UserRole)
        spec = SPEC_BY_ID[pid]
        self.box.setTitle(f"Opciones: {spec.title}")
        opts = self._opts.setdefault(pid, {o.key: o.default for o in spec.options})
        for o in spec.options:
            val = opts.get(o.key, o.default)
            if o.choices is not None:
                w = QComboBox()
                choices = self._raw_columns if o.choices == RAW_COLUMNS else list(o.choices)
                w.addItems([str(c) for c in choices])
                if str(val) in choices:
                    w.setCurrentText(str(val))
                w.currentTextChanged.connect(lambda v, k=o.key, p=pid: self._set(p, k, v))
            elif isinstance(o.default, bool):
                w = QCheckBox()
                w.setChecked(bool(val))
                w.toggled.connect(lambda v, k=o.key, p=pid: self._set(p, k, bool(v)))
            elif isinstance(o.default, int):
                w = QSpinBox()
                w.setRange(int(o.minimum), int(o.maximum))
                w.setValue(int(val))
                w.valueChanged.connect(lambda v, k=o.key, p=pid: self._set(p, k, int(v)))
            else:
                w = dspin(o.minimum, o.maximum, 2, 1)
                w.setValue(float(val))
                w.valueChanged.connect(lambda v, k=o.key, p=pid: self._set(p, k, float(v)))
            self.form.addRow(o.label, w)
        if not spec.options:
            self.form.addRow(QLabel("Sin opciones."))

    def _set(self, pid: str, key: str, value) -> None:
        self._opts.setdefault(pid, {})[key] = value
        self.optionChanged.emit(pid, {key: value})


# =============================================================================================
class ExportPanel(QWidget):
    exportRequested = Signal()
    exportAsRequested = Signal()
    saveConfigRequested = Signal()
    resetRequested = Signal()
    batchRequested = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.list = QListWidget()
        self.list.setDragDropMode(QAbstractItemView.DragDropMode.InternalMove)
        self.target = note()
        b_exp = QPushButton("Exportar P_<código>.csv")
        b_exp.setStyleSheet("font-weight:600;")
        b_as = QPushButton("Exportar como…")
        b_cfg = QPushButton("Guardar configuración del ensayo")
        b_reset = QPushButton("Restablecer parámetros por defecto")
        b_batch = QPushButton("Procesar todos los registros (lote)")
        b_exp.clicked.connect(self.exportRequested)
        b_as.clicked.connect(self.exportAsRequested)
        b_cfg.clicked.connect(self.saveConfigRequested)
        b_reset.clicked.connect(self.resetRequested)
        b_batch.clicked.connect(self.batchRequested)
        lay = QVBoxLayout(self)
        lay.addWidget(note("Columnas del CSV procesado: tildá las que querés y arrastralas para "
                           "ordenarlas. Por defecto, el formato histórico (compatible con los "
                           "gráficos de LabPlotter). Las series temporales se exportan solo dentro "
                           "del recorte."))
        lay.addWidget(self.list, 1)
        lay.addWidget(self.target)
        r1 = QHBoxLayout()
        r1.addWidget(b_exp)
        r1.addWidget(b_as)
        lay.addLayout(r1)
        lay.addWidget(b_cfg)
        lay.addWidget(b_reset)
        lay.addWidget(b_batch)
        lay.addWidget(note(f"La configuración se guarda en "
                           f"{paths.CONFIG_DIR.relative_to(paths.REPO_ROOT).as_posix()}/<código>.json "
                           f"(también al cambiar de ensayo o cerrar) y la usa el procesamiento por lotes."))

    def load(self, s: TrialSettings, td: Optional[TrialData]) -> None:
        self.list.clear()
        for key, on in s.export_columns:
            it = QListWidgetItem(f"{header(key, s)} — {COLUMNS[key]}")
            it.setData(Qt.ItemDataRole.UserRole, key)
            it.setFlags(it.flags() | Qt.ItemFlag.ItemIsUserCheckable | Qt.ItemFlag.ItemIsDragEnabled)
            it.setFlags(it.flags() & ~Qt.ItemFlag.ItemIsDropEnabled)
            it.setCheckState(Qt.CheckState.Checked if on else Qt.CheckState.Unchecked)
            self.list.addItem(it)
        if td is not None:
            self.target.setText(f"Destino: {paths.processed_path(td.trial).relative_to(paths.REPO_ROOT).as_posix()}"
                                if paths.processed_path(td.trial).is_relative_to(paths.REPO_ROOT) else "")

    def store(self, s: TrialSettings) -> None:
        s.export_columns = [[self.list.item(i).data(Qt.ItemDataRole.UserRole),
                             self.list.item(i).checkState() == Qt.CheckState.Checked]
                            for i in range(self.list.count())]
