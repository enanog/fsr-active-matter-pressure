"""All user-tunable parameters, grouped by concern, with JSON (de)serialization.

One JSON per trial (datos/presion/config/<code>.json) stores what was tuned in the GUI so that the
batch processor reproduces it exactly.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field, fields
from pathlib import Path
from typing import Any, Optional


@dataclass
class Calibration:
    """Front-end (transimpedance) model: V_out = V_EXC * R_FEEDBACK / R_FSR, G = 1/R_FSR.

    mode = "auto": use the conductance factor the firmware itself logged (median G/ADC of the
    file) when available -- this tracks hardware changes of R_FEEDBACK between trials; falls
    back to the parameters below for logs without a G column.
    mode = "manual": always use the parameters below.
    """
    mode: str = "auto"
    v_ref: float = 3.3          # [V] ADC reference
    v_exc: float = 0.7534       # [V] excitation
    r_feedback: float = 1000.0  # [ohm] feedback resistor
    adc_fs: float = 1023.0      # full-scale code (10 bit)

    def k_params(self) -> float:
        """Conductance per ADC count [uS/count] from the circuit parameters."""
        return self.v_ref * 1e6 / (self.adc_fs * self.v_exc * self.r_feedback)

    def r_feedback_from_k(self, k_us: float) -> float:
        """R_FEEDBACK that yields conductance factor k_us with the current V_REF/V_EXC/ADC_FS."""
        return self.v_ref * 1e6 / (self.adc_fs * self.v_exc * k_us)


@dataclass
class Analysis:
    step_s: float = 0.05            # uniform resampling step = deltaT sweep step [s]
    deltaT_fixed_s: float = 2.5     # window of the deltaG(t) time series [s]
    deltaT_max_s: float = 15.0      # largest window of the skewness/kurtosis sweep [s]
    t_start: Optional[float] = None  # crop, sensor time [s] (None = start of log)
    t_end: Optional[float] = None    # crop, sensor time [s] (None = end of log)
    exclusions: list = field(default_factory=list)  # [[t0, t1], ...] sensor time [s]
    exclude_saturated: bool = False
    hist_bins: int = 120


@dataclass
class Sync:
    """Video <-> sensor time: t_sensor = offset_s + frame / frames_per_s."""
    offset_auto: bool = True        # offset = end of the LED sync pulse
    offset_s: float = 0.0
    frames_per_s: float = 3.0       # time-lapse: video frames per REAL second
    view: str = "rot180"            # how the video is shown: "rot180" = camera image rotated 180 deg, as
                                    # seen by the experimenter (top edge of the video); "no" = as recorded
    show_robots: bool = False       # overlay VidFetch trajectories on the video
    robot_radius_px: float = 47.0
    video_path: str = ""            # manual choice; empty = VC_/VR_<code> found in datos/video


@dataclass
class Playback:
    speed: float = 10.0             # sensor seconds per wall second
    live: bool = False              # "as if measuring": hide future data, cumulative stats
    live_window_s: float = 120.0    # visible span of time plots in live mode (0 = from start)
    stats_period_s: float = 1.0     # stats refresh period while playing [wall s]


@dataclass
class TrialSettings:
    calibration: Calibration = field(default_factory=Calibration)
    analysis: Analysis = field(default_factory=Analysis)
    sync: Sync = field(default_factory=Sync)
    playback: Playback = field(default_factory=Playback)
    plots: list = field(default_factory=list)          # [{"id":..., "visible":..., "options":{}}]
    export_columns: list = field(default_factory=list)  # [[name, checked], ...]

    def to_json(self) -> str:
        return json.dumps(asdict(self), indent=2, ensure_ascii=False)

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "TrialSettings":
        def build(dc, sub):
            names = {f.name for f in fields(dc)}
            return dc(**{k: v for k, v in (sub or {}).items() if k in names})
        return cls(
            calibration=build(Calibration, d.get("calibration")),
            analysis=build(Analysis, d.get("analysis")),
            sync=build(Sync, d.get("sync")),
            playback=build(Playback, d.get("playback")),
            plots=list(d.get("plots") or []),
            export_columns=[list(x) for x in (d.get("export_columns") or [])],
        )


def load_settings(path: Path) -> Optional[TrialSettings]:
    """Settings saved for a trial, or None if absent/unreadable (never raises)."""
    try:
        if path.is_file():
            return TrialSettings.from_dict(json.loads(path.read_text(encoding="utf-8")))
    except (OSError, ValueError, TypeError) as exc:
        print(f"Aviso: configuración ilegible '{path}': {exc}")
    return None


def save_settings(path: Path, s: TrialSettings) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(s.to_json(), encoding="utf-8")
