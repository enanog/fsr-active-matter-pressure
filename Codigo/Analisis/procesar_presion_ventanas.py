"""
Post-processing pipeline for FSR pressure logs (Kilobots confined system).

Recursively scans the whole `Mediciones` folder (every dated/named
subfolder, at any depth -- except `Procesado`, which holds this script's own
output and is always skipped) and processes every log file whose name
matches the measurement code `AAAAMMDD_hhmm_XX_ll` (year, month, day, hour,
minute, robot count, recording minutes -- see CLAUDE.md), optionally
prefixed with `R_` (raw file) -- so a stray/unrelated file sitting in
`Mediciones/` is simply skipped instead of raising a false error. Matching
files may still be `.csv` or `.json` (several older logs are ".json" files
that actually hold plain CSV text). For each match it:
  1. Loads timestamp/ADC_RAW columns. Column names are matched
     case-insensitively (e.g. "ADC_RAW" and "adc_raw" both match), since
     different acquisition scripts/versions have used different headers.
  2. Recomputes G (conductance, uS) from ADC_RAW using the front-end calibration
     constants (V_REF, V_EXC, R_FEEDBACK, ADC_FS), matching fsr_single_read.ino.
  3. Resamples onto a uniform time grid (STEP_S) by linear interpolation, so that
     sliding windows are well defined even if the original sampling jittered.
  4. Computes deltaG for ONE fixed window size (DELTAG_FIXED_S, 2.5 s by
     default, easily changeable below): deltaG(t) = G(t) - G(t - DELTAG_FIXED_S),
     as a full-length time series column.
  5. Sweeps the window size deltaT from STEP_S (50 ms) up to DELTA_MAX_S (15 s)
     in steps of STEP_S. For each deltaT: deltaG(t) = G(t) - G(t - deltaT) over
     the whole run, then reduces that distribution to a single skewness value.
     This gives one (deltaT, skewness) pair per window size swept.
  6. Computes the empirical survival function of G itself:
     P(G >= g) -- x axis is G, y axis is that probability (matches the
     P(f>=F) reference plot).

All of the above is written into ONE output CSV per input file, named
`P_<codigo>.csv` (e.g. `P_20260824_1430_25_30.csv`), regardless of whether
the input had an `R_` prefix or none. The relative subfolder under
`MEDICIONES_ROOT` is mirrored inside `OUTPUT_DIR`, so results from different
dated folders never collide and stay easy to trace back to their source
(e.g. `Mediciones/08-24-2026/R_20260824_1430_25_30.csv` ->
`Mediciones/Procesado/08-24-2026/P_20260824_1430_25_30.csv`).
Columns have different natural lengths (tiempo/ADC_RAW/G/deltaG_fixed run
for the whole recording; deltaT/skewness sweep 300 window sizes; G_surv/
P_G_geq run for the whole recording too), so the shorter columns are
right-padded with NaN to keep the file rectangular.

No plots/images are generated -- CSV output only.

Run:  python procesar_presion_ventanas.py
"""

from __future__ import annotations

import os
import re

import numpy as np
import pandas as pd

# =============================================================================
# CONFIG -- edit these to match your setup
# =============================================================================

# Root folder to scan recursively (every subfolder at any depth is included,
# except EXCLUDE_DIRNAMES below).
MEDICIONES_ROOT = r"C:\Users\dylan\OneDrive\Desktop\Proyecto_PresionRecintoCircular\Mediciones"

# File extensions considered measurement logs (case-insensitive). Several
# older logs are ".json" files that actually hold plain CSV text.
INPUT_EXTS = {".csv", ".json"}

# Subfolder names to skip anywhere in the tree (its own output, plus the
# usual OS/VCS clutter).
EXCLUDE_DIRNAMES = {"Procesado", ".git", "$RECYCLE.BIN"}

# Output root. Each output file goes to
# OUTPUT_DIR/<same relative subfolder as the input>/P_<codigo>.csv.
OUTPUT_DIR = r"C:\Users\dylan\OneDrive\Desktop\Proyecto_PresionRecintoCircular\Mediciones\Procesado"

# --- File naming convention ---
# Raw measurement files are named AAAAMMDD_hhmm_XX_ll (date, time, robot
# count, recording minutes), optionally prefixed "R_" -- both forms are
# recognized so files saved before the R_ prefix was adopted still work.
# Processed outputs are always written as "P_<codigo>.csv". Anything in
# Mediciones/ that doesn't match this code (stray files, differently named
# legacy logs) is silently skipped -- it is not "raw" until it's renamed.
CODE_RE = re.compile(r"^(?:[Rr]_)?(\d{8}_\d{4}_\d{2}_\d{2})$")
RAW_PREFIX = "R_"
PROC_PREFIX = "P_"

# --- Column mapping (source column names -> what the script expects) ---
# Matched case-insensitively against the file's header, so "ADC_RAW",
# "adc_raw", "Adc_Raw" etc. all resolve to the same column.
TIME_COL = "timestamp(ms)"   # column holding the time stamp
ADC_COL = "adc_raw"          # column holding the raw ADC counts
TIME_UNITS = "s"             # "s" or "ms" -- unit actually used by TIME_COL values
                              # (some logs are mislabeled "(ms)" but hold seconds)

# --- Front-end calibration (see Codigo/fsr_single_read/fsr_single_read.ino) ---
V_REF = 3.3        # [V] ADC reference voltage
V_EXC = 0.7534     # [V] excitation voltage
R_FEEDBACK = 12000.0  # [ohm] feedback resistor
ADC_FS = 1023.0    # full-scale ADC code (10-bit)
K_G_US = (V_REF * 1.0e6) / (ADC_FS * V_EXC * R_FEEDBACK)  # conductance factor [uS/count]

# --- Window sweep for the skewness-vs-deltaT curve ---
STEP_S = 0.05        # resampling step AND deltaT sweep step [s] (50 ms)
DELTA_MAX_S = 15.0    # largest window size swept [s]

# --- Fixed-window deltaG column (single time series, not swept) ---
DELTAG_FIXED_S = 2.5   # window size [s] used for the deltaG column -- change freely

# =============================================================================
# CORE FUNCTIONS
# =============================================================================


def _find_col(df: pd.DataFrame, name: str) -> str | None:
    """Case-insensitive lookup of `name` among df's columns (also tolerant of
    surrounding whitespace, already stripped by the caller). Returns the
    actual column label as found in df, or None if there's no match."""
    target = name.strip().lower()
    for c in df.columns:
        if c.strip().lower() == target:
            return c
    return None


def load_raw_log(path: str) -> pd.DataFrame:
    """Load a raw log file (CSV content, regardless of its extension) and return
    a clean DataFrame with 'tiempo_s' and 'ADC_RAW' columns.

    Defensive against malformed trailing rows (seen in real logs: partially
    filled lines at EOF) and non-numeric junk. Column names are matched
    case-insensitively against TIME_COL/ADC_COL (different logs use
    different casing, e.g. "ADC_RAW" vs "adc_raw").
    """
    df = pd.read_csv(path, engine="python", on_bad_lines="skip")
    df.columns = [c.strip() for c in df.columns]

    time_col = _find_col(df, TIME_COL)
    adc_col = _find_col(df, ADC_COL)
    if time_col is None or adc_col is None:
        raise ValueError(
            f"'{path}': expected columns '{TIME_COL}' and '{ADC_COL}' (case-insensitive), "
            f"found {list(df.columns)}. Fix TIME_COL/ADC_COL in the config."
        )

    out = pd.DataFrame()
    out["tiempo_s"] = pd.to_numeric(df[time_col], errors="coerce")
    out["ADC_RAW"] = pd.to_numeric(df[adc_col], errors="coerce")

    if TIME_UNITS == "ms":
        out["tiempo_s"] = out["tiempo_s"] / 1000.0
    elif TIME_UNITS != "s":
        raise ValueError(f"TIME_UNITS must be 's' or 'ms', got '{TIME_UNITS}'")

    out = out.dropna(subset=["tiempo_s", "ADC_RAW"])
    out = out.sort_values("tiempo_s").drop_duplicates(subset="tiempo_s")
    out["tiempo_s"] = out["tiempo_s"] - out["tiempo_s"].iloc[0]  # subtract t0

    if len(out) < 2:
        raise ValueError(f"'{path}': not enough valid rows after cleaning ({len(out)}).")

    return out.reset_index(drop=True)


def compute_G(adc_raw: pd.Series) -> pd.Series:
    """Conductance [uS] from raw ADC counts, per the FSR front-end model."""
    return adc_raw * K_G_US


def resample_uniform(df: pd.DataFrame, step_s: float) -> pd.DataFrame:
    """Interpolate ADC_RAW/G onto a uniform time grid with spacing step_s."""
    t0, t1 = df["tiempo_s"].iloc[0], df["tiempo_s"].iloc[-1]
    n_steps = int(np.floor((t1 - t0) / step_s)) + 1
    grid_t = t0 + np.arange(n_steps) * step_s

    grid = pd.DataFrame({"tiempo": grid_t})
    grid["ADC_RAW"] = np.interp(grid_t, df["tiempo_s"], df["ADC_RAW"])
    grid["G"] = compute_G(grid["ADC_RAW"])
    return grid


def sliding_deltaG(g: np.ndarray, lag: int) -> np.ndarray:
    """deltaG(t) = G(t) - G(t - lag*STEP_S), as a full-length array (NaN where
    no full window is available yet)."""
    delta = np.full_like(g, np.nan, dtype=float)
    if 0 < lag < len(g):
        delta[lag:] = g[lag:] - g[:-lag]
    return delta


def sample_skewness(x: np.ndarray) -> float:
    """Fisher-Pearson adjusted sample skewness, NaN-safe, no scipy dependency."""
    x = x[~np.isnan(x)]
    n = len(x)
    if n < 3:
        return np.nan
    mean = x.mean()
    std = x.std(ddof=1)
    if std == 0:
        return np.nan
    m3 = np.mean((x - mean) ** 3)
    g1 = m3 / std**3
    # bias correction (same convention as pandas.Series.skew)
    return (np.sqrt(n * (n - 1)) / (n - 2)) * g1


def skewness_vs_deltaT(g: np.ndarray, step_s: float, delta_max_s: float) -> tuple[np.ndarray, np.ndarray]:
    """Sweep window size deltaT from step_s to delta_max_s (in steps of step_s);
    for each deltaT, compute the total skewness of the deltaG(t) = G(t)-G(t-deltaT)
    distribution over the whole run. Returns (delta_t_values, skewness_values).
    """
    n_deltas = int(round(delta_max_s / step_s))
    delta_t_values = (np.arange(1, n_deltas + 1)) * step_s
    skew_values = np.empty(n_deltas)
    for i, lag in enumerate(range(1, n_deltas + 1)):
        d = sliding_deltaG(g, lag)
        skew_values[i] = sample_skewness(d)
    return delta_t_values, skew_values


def empirical_survival_ge(x: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Empirical survival function S(x_i) = P(X >= x_i) from samples in x,
    sorted ascending by x (matches the P(f>=F) convention of the reference plot:
    the smallest value has S=1, the largest has S=1/n).
    """
    x = x[~np.isnan(x)]
    n = len(x)
    if n == 0:
        return np.array([]), np.array([])
    x_sorted = np.sort(x)
    rank = np.arange(1, n + 1)  # 1-based rank, ascending
    survival = (n - rank + 1) / n  # P(X >= x_sorted[i])
    return x_sorted, survival


def pad_to_length(arr: np.ndarray, length: int) -> np.ndarray:
    """Right-pad a 1D array with NaN up to `length`."""
    out = np.full(length, np.nan, dtype=float)
    out[: len(arr)] = arr[:length]
    return out


def extract_code(basename_no_ext: str) -> str | None:
    """Return the AAAAMMDD_hhmm_XX_ll code if `basename_no_ext` matches the
    naming convention (with or without an 'R_' prefix), else None."""
    m = CODE_RE.match(basename_no_ext.strip())
    return m.group(1) if m else None


def discover_files(root: str, exts: set[str], exclude_dirnames: set[str]) -> list[tuple[str, str]]:
    """Recursively walk `root`, skipping any subfolder whose name is in
    `exclude_dirnames` (checked case-insensitively), and return
    (path, codigo) pairs for every file whose extension (case-insensitive)
    is in `exts` AND whose base name matches the AAAAMMDD_hhmm_XX_ll code
    (see CODE_RE) -- anything else in the folder is ignored. Sorted for a
    deterministic, reproducible run order."""
    exclude_lower = {d.lower() for d in exclude_dirnames}
    exts_lower = {e.lower() for e in exts}
    found: list[tuple[str, str]] = []
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d.lower() not in exclude_lower]
        for fn in filenames:
            base, ext = os.path.splitext(fn)
            if ext.lower() not in exts_lower:
                continue
            codigo = extract_code(base)
            if codigo is not None:
                found.append((os.path.join(dirpath, fn), codigo))
    return sorted(found)


def out_csv_path(out_dir: str, root: str, in_path: str, codigo: str) -> str:
    """Output path mirroring in_path's subfolder (relative to `root`) inside
    out_dir, named "P_<codigo>.csv"."""
    rel_dir = os.path.relpath(os.path.dirname(in_path), root)
    dest_dir = out_dir if rel_dir in (".", "") else os.path.join(out_dir, rel_dir)
    return os.path.join(dest_dir, f"{PROC_PREFIX}{codigo}.csv")


def process_file(in_path: str, out_path: str) -> None:
    raw = load_raw_log(in_path)
    grid = resample_uniform(raw, STEP_S)
    n = len(grid)
    g = grid["G"].to_numpy()

    # fixed-window deltaG column (full time series, e.g. deltaG_2.5s)
    fixed_lag = int(round(DELTAG_FIXED_S / STEP_S))
    deltaG_fixed = sliding_deltaG(g, fixed_lag)
    deltaG_col_name = f"deltaG_{DELTAG_FIXED_S:g}s"

    delta_t, skew = skewness_vs_deltaT(g, STEP_S, DELTA_MAX_S)
    surv_G, surv_S = empirical_survival_ge(g)

    result = pd.DataFrame(
        {
            "tiempo": grid["tiempo"],
            "ADC_RAW": grid["ADC_RAW"],
            "G": grid["G"],
            deltaG_col_name: deltaG_fixed,
            "deltaT": pad_to_length(delta_t, n),
            "skewness": pad_to_length(skew, n),
            "G_surv": pad_to_length(surv_G, n),
            "P_G_geq": pad_to_length(surv_S, n),
        }
    )

    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    result.to_csv(out_path, index=False)


def main() -> None:
    files = discover_files(MEDICIONES_ROOT, INPUT_EXTS, EXCLUDE_DIRNAMES)

    if not files:
        raise FileNotFoundError(
            f"No se encontraron archivos con el codigo AAAAMMDD_hhmm_XX_ll "
            f"(con o sin prefijo '{RAW_PREFIX}') bajo '{MEDICIONES_ROOT}' "
            f"(excluyendo {sorted(EXCLUDE_DIRNAMES)})."
        )

    print(f"Encontrados {len(files)} archivo(s) con codigo valido bajo '{MEDICIONES_ROOT}'.\n")

    ok, fail = 0, 0
    for f, codigo in files:
        rel = os.path.relpath(f, MEDICIONES_ROOT)
        out_path = out_csv_path(OUTPUT_DIR, MEDICIONES_ROOT, f, codigo)
        try:
            process_file(f, out_path)
            print(f"OK   {rel} -> {os.path.relpath(out_path, MEDICIONES_ROOT)}")
            ok += 1
        except Exception as exc:  # defensive: keep processing remaining files
            print(f"FAIL {rel}: {exc}")
            fail += 1

    print(f"\n{ok} OK, {fail} FAIL, de {len(files)} archivo(s) total.")


if __name__ == "__main__":
    main()
