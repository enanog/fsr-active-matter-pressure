"""Everything loaded for one trial, shared by the GUI and the batch processor."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

import numpy as np

from core import paths
from core.export import build_table, default_columns, normalized_columns, write_table
from core.log_io import RawLog, load_log
from core.robots import Robots, load_robots
from core.settings import TrialSettings, load_settings
from core.signal import Series, build_series
from core.stats import Stats, compute_stats


@dataclass
class TrialData:
    trial: paths.Trial
    raw: RawLog
    settings: TrialSettings
    series: Optional[Series] = None
    robots: Optional[Robots] = None
    robots_error: str = ""

    @classmethod
    def open(cls, trial: paths.Trial, load_trajectories: bool = True) -> "TrialData":
        raw = load_log(trial.raw_path)
        settings = load_settings(paths.config_path(trial)) or TrialSettings()
        settings.export_columns = normalized_columns(settings.export_columns or default_columns())
        td = cls(trial, raw, settings)
        if load_trajectories and trial.traj_path is not None:
            try:
                td.robots = load_robots(trial.traj_path)
            except Exception as exc:  # trajectories are optional: report and go on
                td.robots_error = str(exc)
        td.rebuild()
        return td

    def rebuild(self) -> None:
        self.series = build_series(self.raw, self.settings.calibration, self.settings.analysis.step_s)

    # --- video synchronisation -------------------------------------------------------------
    @property
    def led_offset(self) -> Optional[float]:
        return None if np.isnan(self.raw.led_off) else float(self.raw.led_off)

    @property
    def offset_s(self) -> float:
        """Sensor time of video frame 0."""
        sy = self.settings.sync
        if sy.offset_auto and self.led_offset is not None:
            return self.led_offset
        return sy.offset_s

    def frame_at(self, t_sensor: float) -> int:
        return int(np.floor((t_sensor - self.offset_s) * self.settings.sync.frames_per_s + 1e-9))

    def time_of_frame(self, frame) -> np.ndarray:
        return self.offset_s + np.asarray(frame, dtype=float) / self.settings.sync.frames_per_s

    def robot_speed_on(self, t_sensor: np.ndarray):
        if self.robots is None:
            return None
        tf = self.time_of_frame(self.robots.frames)
        out = []
        for v in (self.robots.v_median, self.robots.v_p90):
            y = np.interp(t_sensor, tf, v, left=np.nan, right=np.nan)
            out.append(y)
        return tuple(out)

    # --- processing --------------------------------------------------------------------------
    def stats(self, t_now: Optional[float] = None, sweep: bool = True) -> Stats:
        return compute_stats(self.series, self.settings.analysis, t_now, sweep)

    def export(self, path=None, stats: Optional[Stats] = None):
        path = path or paths.processed_path(self.trial)
        st = stats if stats is not None and stats.t_now is None else self.stats()
        rs = self.robot_speed_on if self.robots is not None else None
        df = build_table(self.series, st, self.settings, self.offset_s, rs)
        write_table(df, path)
        return path, df
