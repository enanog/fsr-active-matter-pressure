"""Compare several tracked tests and generate the comparative part of informe_ensayos.tex.

Usage (from the repository root):
    python software/analisis_video/comparar_ensayos.py "datos/video/trayectorias/VP_*_robots.csv" \
        [--mediciones datos/presion/crudos] [--cuadros-por-segundo 3]

Input: the "una fila por robot y cuadro" CSVs exported by the app (one per test). The test code
(AAAADDMM_HHMM_XXYY_TT) is taken from each file name. With --mediciones, the pressure log
R_<code>.csv of each test is aligned with the video by cross-correlation (exploratory).

Output: informes/ensayos/generado/comparacion/ with comparacion.tex (tables + PGFPlots figures), the CSV
series it plots, datos.tex (one macro per number, used by the hand-written discussion) and
ocupacion.png. Then compile informes/ensayos/informe_ensayos.tex (twice).
"""
from __future__ import annotations

import argparse
import warnings
import re
import sys
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]                                  # repository root (software/analisis_video/..)
DEFAULT_REPORT = ROOT / "informes" / "ensayos"
DEFAULT_PRESSURE = ROOT / "datos" / "presion" / "crudos"
CODE_RE = re.compile(r"(\d{8}_\d{4}_\d{2}[A-Za-z]{1,2}_\d{1,4})")
LETTERS = "ABCDEFGH"
OBSERVED = {"detectado", "detectado (umbral relajado)", "manual"}

# Collective stop ("atasco"): 90th percentile of the robots' speed, median-filtered over 30 s,
# below this threshold for at least FREEZE_MIN_S.
FREEZE_P90_MM_S = 0.6
FREEZE_SMOOTH_S = 30.0
FREEZE_MIN_S = 20.0
SERIES_BIN_S = 30.0
SENSOR_BIN_S = 10.0
MAX_LAG_S = (-60.0, 120.0)


# --------------------------------------------------------------------------- helpers
def num(v: float, digits: int = 3) -> str:
    if v is None or not np.isfinite(v):
        return "nan"
    return f"{v:.{digits}g}" if abs(v) < 1e4 else f"{v:.0f}"


def label_from_code(code: str) -> str:
    """'20262409_1600_22QR_60' -> '24/09 16:00' (date stored as year, day, month)."""
    d, hm = code[:8], code[9:13]
    a, b = int(d[4:6]), int(d[6:8])
    # The project's files store year-day-month (20262409 = 24 Sep); fall back if that is impossible.
    day, month = (b, a) if (b > 12 and a <= 12) else (a, b)
    return f"{day:02d}/{month:02d} {hm[:2]}:{hm[2:]}"


def runs(mask: np.ndarray, min_len: int) -> list[tuple[int, int]]:
    idx = np.flatnonzero(mask)
    if len(idx) == 0:
        return []
    groups = np.split(idx, np.flatnonzero(np.diff(idx) > 1) + 1)
    return [(int(g[0]), int(g[-1])) for g in groups if len(g) >= min_len]


def load(path: Path, fps_override: float | None) -> dict:
    try:
        df = pd.read_csv(path)
    except Exception as exc:
        sys.exit(f"No se pudo leer {path}: {exc}")
    need = {"frame", "t_s", "particle", "x_px", "y_px", "status", "speed_px_s", "omega_deg_s", "theta_deg"}
    if need - set(df.columns):
        sys.exit(f"{path.name}: faltan columnas {sorted(need - set(df.columns))}")
    df = df.sort_values(["frame", "particle"]).reset_index(drop=True)
    F, N = df["frame"].nunique(), df["particle"].nunique()
    if F * N != len(df):
        sys.exit(f"{path.name}: el CSV no es rectangular (cuadros x robots).")
    d1 = df.drop_duplicates("frame")
    r = (d1["frame"] / d1["t_s"]).replace([np.inf, -np.inf], np.nan).dropna()
    fps_csv = float(r.median()) if len(r) else float("nan")
    fps = fps_override or fps_csv
    k_rate = fps / fps_csv if np.isfinite(fps_csv) else 1.0
    if "x_m" in df.columns and df["x_m"].notna().any():
        s_mm = float(np.nanmedian(df["x_m"] / df["x_px"].where(df["x_px"] > 1))) * 1000.0
    else:
        sys.exit(f"{path.name}: el CSV no trae escala (x_m); exportalo con el diámetro real cargado.")
    A = lambda c: pd.to_numeric(df[c], errors="coerce").to_numpy().reshape(F, N)
    m = CODE_RE.search(path.stem)
    code = m.group(1) if m else path.stem
    return {"code": code, "label": label_from_code(code) if m else code, "F": F, "N": N, "fps": fps,
            "s": s_mm, "x": A("x_px"), "y": A("y_px"), "status": df["status"].to_numpy().reshape(F, N),
            "v": A("speed_px_s") * s_mm * k_rate, "vx": A("vx_px_s") * s_mm * k_rate,
            "vy": A("vy_px_s") * s_mm * k_rate, "w": A("omega_deg_s") * k_rate, "th": A("theta_deg")}


def arena(x: np.ndarray, y: np.ndarray) -> tuple[float, float, float]:
    """Centre and radius of the circle reachable by robot centres (robust enclosing circle)."""
    from scipy.optimize import minimize
    pts = np.column_stack([x.ravel(), y.ravel()])
    pts = pts[np.isfinite(pts).all(1)][:: max(1, len(pts) // 200000)]
    c0 = (np.percentile(pts, 0.1, 0) + np.percentile(pts, 99.9, 0)) / 2
    f = lambda c: np.percentile(np.hypot(*(pts - c).T), 99.9)
    c = minimize(f, c0, method="Nelder-Mead", options={"xatol": 0.05, "fatol": 0.01}).x
    return float(c[0]), float(c[1]), float(f(c))


def msd(x: np.ndarray, y: np.ndarray, fps: float, s: float) -> pd.DataFrame:
    F = len(x)
    lags = np.unique(np.round(np.logspace(0, np.log10(min(F // 4, int(1200 * fps))), 40)).astype(int))
    out = []
    for L in lags:
        dx, dy = x[L:] - x[:-L], y[L:] - y[:-L]
        out.append((L / fps, float(np.nanmean(dx ** 2 + dy ** 2)) * s * s))
    return pd.DataFrame(out, columns=["tau", "msd"])


# --------------------------------------------------------------------------- pressure log
def sensor(path: Path) -> dict | None:
    try:
        d = pd.read_csv(path)
    except Exception as exc:
        print(f"Aviso: no se pudo leer {path.name}: {exc}")
        return None
    d = d.loc[:, ~d.columns.str.startswith("Unnamed")]
    if "R" not in d.columns:
        print(f"Aviso: {path.name} no tiene columna R.")
        return None
    t_all = pd.to_numeric(d.iloc[:, 0], errors="coerce").to_numpy()
    led_on = led_off = np.nan
    if "LED" in d.columns:
        on = np.flatnonzero(pd.to_numeric(d["LED"], errors="coerce").to_numpy() == 1)
        if len(on):
            first = on[: np.flatnonzero(np.diff(on) > 1)[0] + 1] if np.any(np.diff(on) > 1) else on
            led_on, led_off = t_all[first[0]] - t_all[0], t_all[first[-1]] - t_all[0]
    if "SYNC" in d.columns:
        d = d[d["SYNC"].isna()]
    t = pd.to_numeric(d.iloc[:, 0], errors="coerce").to_numpy()
    R = pd.to_numeric(d["R"], errors="coerce").to_numpy()
    ok = np.isfinite(t) & np.isfinite(R) & (R > 0)
    t0 = t_all[np.isfinite(t_all)][0]
    sat = ((d["CLIPSAT"] == d["N"]).to_numpy() if {"CLIPSAT", "N"} <= set(d.columns)
           else np.zeros(len(d), bool))
    return {"t": t[ok] - t0, "G": 1e6 / R[ok], "sat": sat[ok], "led_on": led_on, "led_off": led_off}


def align(mob: np.ndarray, fps: float, sen: dict) -> tuple[float, float]:
    """Lag [s] (sensor time = video time + lag) maximising corr(-log mobility, log G)."""
    tb = np.arange(0, sen["t"][-1], 1.0 / fps)
    lg = np.interp(tb, sen["t"], np.log10(np.clip(sen["G"], 1e-6, None)))
    lm = -np.log10(pd.Series(mob).rolling(9, center=True, min_periods=1).median().to_numpy() + 0.05)
    best = (0.0, -np.inf)
    for lag in range(int(MAX_LAG_S[0] * fps), int(MAX_LAG_S[1] * fps) + 1):
        a0, a1 = max(0, -lag), min(len(lm), len(tb) - lag)
        if a1 - a0 < 600:
            continue
        r = np.corrcoef(lm[a0:a1], lg[a0 + lag:a1 + lag])[0, 1]
        if r > best[1]:
            best = (lag / fps, float(r))
    return best


# --------------------------------------------------------------------------- per test
def analyse(T: dict, out: Path, k: str, sen: dict | None) -> dict:
    F, N, fps, s = T["F"], T["N"], T["fps"], T["s"]
    v, w, th, st = T["v"], T["w"], T["th"], T["status"]
    obs = np.isin(st, list(OBSERVED))
    dur = F / fps
    cx, cy, Rc = arena(T["x"], T["y"])
    R_arena_mm = (Rc + 0.5 * 35.0 / s) * s  # centre circle + robot radius (35 mm robots)
    D_mm = 35.0
    phi = N * (D_mm / 2) ** 2 / R_arena_mm ** 2

    # collective stops
    p90 = np.nanpercentile(v, 90, axis=1)
    p90s = pd.Series(p90).rolling(int(FREEZE_SMOOTH_S * fps), center=True, min_periods=1).median().to_numpy()
    frz = runs(p90s < FREEZE_P90_MM_S, int(FREEZE_MIN_S * fps))
    fmask = np.zeros(F, bool)
    for a, b in frz:
        fmask[a:b + 1] = True
    pd.DataFrame([{"ini_min": a / fps / 60, "fin_min": b / fps / 60, "dur_s": (b - a + 1) / fps,
                   "v_med": float(np.nanmedian(v[a:b + 1])), "w_med": float(np.nanmedian(np.abs(w[a:b + 1])))}
                  for a, b in frz]).to_csv(out / f"atascos_{k}.csv", index=False, float_format="%.4g")

    # time series (30 s bins)
    nb = int(round(SERIES_BIN_S * fps))
    idx = np.arange(F) // nb
    ser = pd.DataFrame({"t": pd.Series(np.arange(F) / fps / 60).groupby(idx).mean(),
                        "v_med": pd.Series(np.nanmedian(v, 1)).groupby(idx).mean(),
                        "v_p90": pd.Series(p90).groupby(idx).mean(),
                        "w_med": pd.Series(np.nanmedian(np.abs(w), 1)).groupby(idx).mean(),
                        "atasco": pd.Series(fmask.astype(float)).groupby(idx).mean()})
    ser.to_csv(out / f"serie_{k}.csv", index=False, float_format="%.4g")

    # distributions (observed points)
    vo, wo = v[obs], w[obs]
    vo, wo = vo[np.isfinite(vo)], wo[np.isfinite(wo)]
    e = np.linspace(0, 8, 41)
    h, _ = np.histogram(np.clip(vo, 0, 8 - 1e-9), e, density=True)
    pd.DataFrame({"v": e, "p": np.append(h, h[-1])}).to_csv(out / f"hist_v_{k}.csv", index=False, float_format="%.5g")
    e = np.linspace(-60, 60, 61)
    h, _ = np.histogram(np.clip(wo, -60, 60 - 1e-9), e, density=True)
    pd.DataFrame({"w": e, "p": np.append(h, h[-1])}).to_csv(out / f"hist_w_{k}.csv", index=False, float_format="%.5g")

    # per-robot spin and turns
    turns = th[-1] / 360.0
    wmean = np.nanmean(w, 0)
    order = np.argsort(wmean)
    pd.DataFrame({"rank": np.arange(N), "id": order, "w": wmean[order], "vueltas": turns[order]}).to_csv(
        out / f"giro_{k}.csv", index=False, float_format="%.4g")

    # collective rotation about the arena centre (CCW on screen positive: y axis flipped)
    rx, ry = (T["x"] - cx) * s, -(T["y"] - cy) * s      # mm, y up
    vx, vy = T["vx"], -T["vy"]                          # mm/s, y up
    r = np.hypot(rx, ry)
    moving = (v > 1.0) & (r > 0.3 * Rc * s)
    sinang = (rx * vy - ry * vx) / np.maximum(r * np.hypot(vx, vy), 1e-12)
    phi_rot = np.nanmean(np.where(moving, sinang, np.nan), axis=1)
    Omega = np.degrees(np.nansum(rx * vy - ry * vx, 1) / np.nansum(r * r, 1))   # deg/s

    # mean square displacement (all frames) and radial density
    m = msd(T["x"], T["y"], fps, s)
    m.to_csv(out / f"msd_{k}.csv", index=False, float_format="%.5g")
    fit = m[(m["tau"] >= 1) & (m["tau"] <= 20)]
    alpha = float(np.polyfit(np.log(fit["tau"]), np.log(fit["msd"]), 1)[0]) if len(fit) > 2 else np.nan
    e = np.linspace(0, 1, 26)
    h, _ = np.histogram((r / (Rc * s)).ravel()[np.isfinite(r.ravel())].clip(0, 1 - 1e-9), e)
    area = np.pi * (e[1:] ** 2 - e[:-1] ** 2)
    dens = h / area / (h.sum() / np.pi)
    pd.DataFrame({"r": (e[:-1] + e[1:]) / 2, "n": dens}).to_csv(out / f"radial_{k}.csv", index=False, float_format="%.4g")

    res = {
        "Cod": T["code"].replace("_", r"\_"), "Lab": T["label"], "N": N, "F": F, "Fps": fps, "Dur": dur / 60,
        "Esc": s, "Rar": R_arena_mm / 10, "Phi": phi,
        "Obs": 100 * obs.mean(), "Rel": int((st == "detectado (umbral relajado)").sum()),
        "Int": int((st == "interpolado").sum()), "Man": int((st == "manual").sum()),
        "Pre": int(np.isin(st, ["predicho (revisar)", "perdido"]).sum()),
        "Vmed": float(np.median(vo)), "Vmean": float(np.mean(vo)), "Vp95": float(np.percentile(vo, 95)),
        "VmedAct": float(np.nanmedian(v[~fmask])), "Wmed": float(np.median(np.abs(wo))),
        "Wmean": float(np.mean(wo)), "Wpos": 100 * float((wo > 0).mean()),
        "Nccw": int((turns > 1).sum()), "Ncw": int((turns < -1).sum()),
        "Vmax": float(np.nanmax(np.abs(turns))), "Vnet": float(np.nansum(turns)),
        "Spin": float(np.nanmax(np.abs(wmean))),
        "NAt": len(frz), "TAt": float(fmask.sum() / fps / 60), "PAt": 100 * float(fmask.mean()),
        "AtMax": max([(b - a + 1) / fps for a, b in frz], default=0.0),
        "Prot": float(np.nanmean(phi_rot)), "Om": float(np.nanmean(Omega)),
        "Alfa": alpha, "Msd": float(m["msd"].iloc[-1]), "TauMax": float(m["tau"].iloc[-1] / 60),
    }

    # exploratory link with the pressure log
    if sen is not None:
        lag_xc, rr = align(p90, fps, sen)
        # The cropped video starts when the 5 s sync LED pulse of the logger ends; the
        # cross-correlation only confirms it. Without LED, the cross-correlation lag is used.
        lag = sen["led_off"] if np.isfinite(sen["led_off"]) else lag_xc
        tv = sen["t"] - lag                          # sensor sample -> video time
        bins = np.arange(0, dur + SENSOR_BIN_S, SENSOR_BIN_S)
        ib = np.digitize(tv, bins) - 1
        okb = (ib >= 0) & (ib < len(bins) - 1)
        g = pd.Series(np.log10(sen["G"][okb])).groupby(ib[okb]).median()
        sb = pd.Series(sen["sat"][okb].astype(float)).groupby(ib[okb]).mean()
        vb = pd.Series(p90).groupby((np.arange(F) / fps // SENSOR_BIN_S).astype(int)).mean()
        fb = pd.Series(fmask.astype(float)).groupby((np.arange(F) / fps // SENSOR_BIN_S).astype(int)).mean()
        dfp = pd.DataFrame({"v_p90": vb, "atasco": fb}).join(pd.DataFrame({"logG": g, "sat": sb}), how="inner")
        dfp.insert(0, "t", (dfp.index + 0.5) * SENSOR_BIN_S / 60)
        dfp.to_csv(out / f"presion_{k}.csv", index=False, float_format="%.4g")
        f_in = np.zeros(len(tv), bool)
        fi = np.round(tv * fps).astype(int)
        val = (fi >= 0) & (fi < F)
        f_in[val] = fmask[fi[val]]
        Gin, Gout = np.median(sen["G"][f_in]) if f_in.any() else np.nan, np.median(sen["G"][val & ~f_in])
        res.update({"Lag": lag_xc, "Rxc": rr, "Led": sen["led_on"], "LedFin": sen["led_off"],
                    "LagLed": lag_xc - sen["led_off"], "Desf": lag,
                    "Gin": Gin, "Gout": Gout, "Grat": Gin / Gout if Gout > 0 else np.nan,
                    "SatIn": 100 * float(sen["sat"][f_in].mean()) if f_in.any() else np.nan,
                    "SatAll": 100 * float(sen["sat"][val].mean()),
                    "HasSen": 1})
    else:
        res["HasSen"] = 0
    T["arena"] = (cx, cy, Rc)
    return res


def occupancy_png(tests: list[dict], out: Path) -> None:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    fig, axs = plt.subplots(1, len(tests), figsize=(3.3 * len(tests), 3.4), constrained_layout=True)
    axs = np.atleast_1d(axs)
    for ax, T in zip(axs, tests):
        cx, cy, Rc = T["arena"]
        s = T["s"] / 10.0  # cm/px
        x, y = (T["x"] - cx).ravel() * s, (T["y"] - cy).ravel() * s
        ok = np.isfinite(x) & np.isfinite(y)
        lim = Rc * s * 1.05
        h, xe, ye = np.histogram2d(x[ok], y[ok], bins=90, range=[[-lim, lim], [-lim, lim]], density=True)
        im = ax.imshow(h.T, origin="upper", extent=[-lim, lim, lim, -lim], cmap="viridis",
                       vmax=np.percentile(h[h > 0], 99))
        ax.add_patch(plt.Circle((0, 0), Rc * s, fill=False, color="w", lw=0.8, ls="--"))
        ax.set_title(T["label"], fontsize=10)
        ax.set_xlabel("x [cm]", fontsize=9)
        ax.tick_params(labelsize=8)
    axs[0].set_ylabel("y [cm]", fontsize=9)
    cb = fig.colorbar(im, ax=axs, shrink=0.85)
    cb.set_label("densidad de ocupación [1/cm²]", fontsize=9)
    cb.ax.tick_params(labelsize=8)
    fig.savefig(out / "ocupacion.png", dpi=200)
    plt.close(fig)


# --------------------------------------------------------------------------- LaTeX
COLORS = ["azul", "rojo", "verde", "naranja", "violet", "teal", "brown", "magenta"]


def write_tex(tests: list[dict], R: list[dict], out: Path, rel: str) -> None:
    ks = LETTERS[:len(tests)]
    lines = ["% Generated by comparar_ensayos.py -- do not edit; re-run the script instead."]
    for k, r in zip(ks, R):
        for key, val in r.items():
            if isinstance(val, str):
                txt = val
            elif isinstance(val, (int, np.integer)):
                txt = str(int(val))
            else:
                txt = num(float(val), 3)
            lines.append(f"\\expandafter\\def\\csname Cmp{key}{k}\\endcsname{{{txt}}}")
    lines.append(f"\\def\\CmpNumEnsayos{{{len(tests)}}}")
    lines.append(f"\\def\\CmpUmbralAtasco{{{num(FREEZE_P90_MM_S)}}}")
    lines.append(f"\\def\\CmpVentanaAtasco{{{num(FREEZE_SMOOTH_S)}}}")
    lines.append(f"\\def\\CmpMinAtasco{{{num(FREEZE_MIN_S)}}}")
    lines.append("\\newcommand{\\Cmp}[2]{\\csname Cmp#1#2\\endcsname}")
    (out / "datos.tex").write_text("\n".join(lines) + "\n", encoding="utf-8")

    def row(name: str, key: str, unit: str = "", fmt: str = "num") -> str:
        cells = []
        for k in ks:
            v = f"\\Cmp{{{key}}}{{{k}}}"
            cells.append(f"\\num{{{v}}}" if fmt == "num" else v)
        u = f" [\\si{{{unit}}}]" if unit else ""
        return f"    {name}{u} & " + " & ".join(cells) + r" \\"

    head = " & ".join(f"\\Cmp{{Lab}}{{{k}}}" for k in ks)
    colspec = "l" + "r" * len(ks)
    T1 = [r"\begin{table}[H]", r"  \centering",
          r"  \caption{Comparación de los ensayos: datos, calidad del seguimiento, movimiento y rotación.}",
          r"  \label{tab:comparacion}", r"  \small", f"  \\begin{{tabular}}{{@{{}}{colspec}@{{}}}}",
          r"    \toprule", f"    & {head} \\\\", r"    \midrule",
          f"    \\multicolumn{{{len(ks) + 1}}}{{@{{}}l}}{{\\textit{{Ensayo}}}} \\\\",
          row("Robots $N$", "N"), row("Cuadros", "F"), row("Duración real", "Dur", r"\minute"),
          row("Escala $s$", "Esc", r"\milli\metre\per px"), row("Radio útil de la arena", "Rar", r"\centi\metre"),
          row("Fracción de área $\\phi$", "Phi"),
          r"    \midrule", f"    \\multicolumn{{{len(ks) + 1}}}{{@{{}}l}}{{\\textit{{Seguimiento}}}} \\\\",
          row("Posiciones observadas", "Obs", r"\percent"), row("Puntos con umbral relajado", "Rel"),
          row("Puntos interpolados", "Int"), row("Anclas manuales", "Man"), row("Puntos predichos o perdidos", "Pre"),
          r"    \midrule", f"    \\multicolumn{{{len(ks) + 1}}}{{@{{}}l}}{{\\textit{{Traslación}}}} \\\\",
          row("$|\\vec v|$ mediana", "Vmed", r"\milli\metre\per\second"),
          row("$|\\vec v|$ media", "Vmean", r"\milli\metre\per\second"),
          row("$|\\vec v|$ percentil 95", "Vp95", r"\milli\metre\per\second"),
          row("$|\\vec v|$ mediana fuera de atascos", "VmedAct", r"\milli\metre\per\second"),
          row("Exponente MSD $\\alpha$ (1--20 s)", "Alfa"),
          r"    \midrule", f"    \\multicolumn{{{len(ks) + 1}}}{{@{{}}l}}{{\\textit{{Rotación}}}} \\\\",
          row("$|\\omega|$ mediana", "Wmed", r"\degree\per\second"),
          row("$\\omega$ media (con signo)", "Wmean", r"\degree\per\second"),
          row("Puntos con $\\omega>0$ (antihorario)", "Wpos", r"\percent"),
          row("Robots con giro neto $>+1$ vuelta", "Nccw"), row("Robots con giro neto $<-1$ vuelta", "Ncw"),
          row("Mayor giro neto de un robot", "Vmax", "vueltas"),
          row("Rotación colectiva $\\overline{\\Phi}$", "Prot"),
          r"    \midrule", f"    \\multicolumn{{{len(ks) + 1}}}{{@{{}}l}}{{\\textit{{Atascos}}}} \\\\",
          row("Episodios", "NAt"), row("Tiempo total", "TAt", r"\minute"),
          row("Fracción del ensayo", "PAt", r"\percent"), row("Episodio más largo", "AtMax", r"\second"),
          r"    \bottomrule", r"  \end{tabular}", r"\end{table}"]

    def plot(file: str, x: str, y: str, k: str, i: int, extra: str = "", legend: bool = True) -> str:
        s = (f"      \\addplot [{COLORS[i % len(COLORS)]}, thick{extra}] table [x={x}, y={y}, col sep=comma] "
             f"{{{rel}/{file}_{k}.csv}};")
        return s + (f"\n      \\addlegendentry{{\\Cmp{{Lab}}{{{k}}}}}" if legend else "")

    def axis(opts: str, body: list[str]) -> list[str]:
        return [r"  \begin{tikzpicture}", f"    \\begin{{axis}}[{opts}]", *body, r"    \end{axis}",
                r"  \end{tikzpicture}"]

    common = "grid=major, grid style={gray!20}, legend style={font=\\footnotesize}, tick label style={font=\\footnotesize}"
    F_ser = [r"\begin{figure}[H]", r"  \centering"]
    for i, k in enumerate(ks):
        F_ser += axis(f"width=0.96\\linewidth, height=3.6cm, ymin=0, ymax=8, enlarge x limits=false, xmin=0, "
                      f"ylabel={{$|\\vec v|$ [\\si{{\\milli\\metre\\per\\second}}]}}, {common}, "
                      f"title={{\\Cmp{{Lab}}{{{k}}}}}, title style={{font=\\small, yshift=-1ex}}"
                      + (", xlabel={$t$ [\\si{\\minute}]}" if i == len(ks) - 1 else ""),
                      [f"      \\addplot [ybar interval, fill=gray!30, draw=none, forget plot] table [x=t, "
                       f"y expr=8*\\thisrow{{atasco}}, col sep=comma] {{{rel}/serie_{k}.csv}};",
                       plot("serie", "t", "v_p90", k, i, legend=False),
                       f"      \\addplot [black, thin] table [x=t, y=v_med, col sep=comma] {{{rel}/serie_{k}.csv}};"])
        F_ser.append("")
    F_ser += [r"  \caption{Evolución de la rapidez en ventanas de \SI{30}{\second}: percentil 90 entre robots (color) y "
              r"mediana (negro). Sombreado: atascos (percentil 90 suavizado $<\SI{\CmpUmbralAtasco}{\milli\metre\per\second}$ "
              r"durante al menos \SI{\CmpMinAtasco}{\second}).}", r"  \label{fig:cmp_serie}", r"\end{figure}"]

    F_hist = [r"\begin{figure}[H]", r"  \centering"]
    F_hist += axis(f"width=0.49\\linewidth, height=5.2cm, ymode=log, xmin=0, xmax=8, ymin=1e-4, "
                   f"xlabel={{$|\\vec v|$ [\\si{{\\milli\\metre\\per\\second}}]}}, "
                   f"ylabel={{densidad [\\si{{\\second\\per\\milli\\metre}}]}}, {common}, legend pos=north east",
                   [plot("hist_v", "v", "p", k, i, ", const plot mark left") for i, k in enumerate(ks)])
    F_hist.append(r"  \hfill")
    F_hist += axis(f"width=0.49\\linewidth, height=5.2cm, ymode=log, xmin=-60, xmax=60, ymin=1e-4, "
                   f"xlabel={{$\\omega$ [\\si{{\\degree\\per\\second}}]}}, "
                   f"ylabel={{densidad [\\si{{\\second\\per\\degree}}]}}, {common}, legend pos=north east",
                   [plot("hist_w", "w", "p", k, i, ", const plot mark left", legend=False) for i, k in enumerate(ks)])
    F_hist += [r"  \caption{Distribuciones de la rapidez (izq.) y de la velocidad angular (der., positivo = "
               r"antihorario) de todos los robots y cuadros con posición observada. Escala logarítmica.}",
               r"  \label{fig:cmp_hist}", r"\end{figure}"]

    F_giro = [r"\begin{figure}[H]", r"  \centering"]
    F_giro += axis(f"width=0.49\\linewidth, height=5.2cm, xlabel={{robots ordenados por $\\overline{{\\omega}}$}}, "
                   f"ylabel={{$\\overline{{\\omega}}$ por robot [\\si{{\\degree\\per\\second}}]}}, {common}, "
                   f"legend pos=south east, xmin=-0.5, xmax={max(T['N'] for T in tests) - 0.5}",
                   [plot("giro", "rank", "w", k, i, ", mark=*, mark size=1.2pt") for i, k in enumerate(ks)]
                   + [r"      \addplot [black, thin, forget plot] coordinates {(-1,0) (40,0)};"])
    F_giro.append(r"  \hfill")
    F_giro += axis(f"width=0.49\\linewidth, height=5.2cm, xmode=log, ymode=log, "
                   f"xlabel={{$\\tau$ [\\si{{\\second}}]}}, ylabel={{MSD [\\si{{\\milli\\metre\\squared}}]}}, "
                   f"{common}, legend pos=south east",
                   [plot("msd", "tau", "msd", k, i, legend=False) for i, k in enumerate(ks)]
                   + [r"      \addplot [black, dashed, domain=1:20, forget plot] {3*x^2};",
                      r"      \node[font=\scriptsize, anchor=west] at (axis cs:22,1200) {$\propto\tau^2$};"])
    F_giro += [r"  \caption{Izq.: velocidad angular media de cada robot, ordenada (cada punto es un robot). "
               r"Der.: desplazamiento cuadrático medio $\mathrm{MSD}(\tau)=\langle|\vec r(t+\tau)-\vec r(t)|^2\rangle$; "
               r"la recta de referencia indica movimiento balístico.}", r"  \label{fig:cmp_giro}", r"\end{figure}"]

    F_rad = [r"\begin{figure}[H]", r"  \centering",
             r"  \includegraphics[width=\linewidth]{" + rel + r"/ocupacion.png}",
             r"  \caption{Densidad de ocupación de los centros de los robots durante todo cada ensayo. Línea "
             r"punteada: círculo que pueden alcanzar los centros (radio útil menos el radio del robot).}",
             r"  \label{fig:cmp_ocupacion}", r"\end{figure}", r"\begin{figure}[H]", r"  \centering"]
    F_rad += axis(f"width=0.62\\linewidth, height=5cm, xmin=0, xmax=1, ymin=0, "
                  f"xlabel={{$r/R_{{\\mathrm{{c}}}}$}}, ylabel={{densidad relativa}}, {common}, legend pos=north west",
                  [plot("radial", "r", "n", k, i, ", mark=*, mark size=1pt") for i, k in enumerate(ks)]
                  + [r"      \addplot [black, dashed, forget plot] coordinates {(0,1) (1,1)};"])
    F_rad += [r"  \caption{Densidad radial de los centros normalizada por área ($1$ = distribución uniforme); "
              r"$R_{\mathrm{c}}$ es el radio máximo que alcanzan los centros.}", r"  \label{fig:cmp_radial}",
              r"\end{figure}"]

    has_sen = all(r.get("HasSen") for r in R)
    F_p = []
    if has_sen:
        F_p = [r"\begin{figure}[H]", r"  \centering"]
        for i, k in enumerate(ks):
            F_p += [r"  \begin{tikzpicture}",
                    f"    \\begin{{axis}}[width=0.93\\linewidth, height=3.6cm, axis y line*=left, ymin=0, ymax=8, xmin=0, "
                    f"enlarge x limits=false, ylabel={{$|\\vec v|_{{90}}$ [\\si{{\\milli\\metre\\per\\second}}]}}, "
                    f"{common}, title={{\\Cmp{{Lab}}{{{k}}}}}, title style={{font=\\small, yshift=-1ex}}"
                    + (", xlabel={$t$ de video [\\si{\\minute}]}" if i == len(ks) - 1 else "") + "]",
                    f"      \\addplot [ybar interval, fill=gray!30, draw=none] table [x=t, y expr=8*\\thisrow{{atasco}}, "
                    f"col sep=comma] {{{rel}/presion_{k}.csv}};",
                    f"      \\addplot [azul, thin] table [x=t, y=v_p90, col sep=comma] {{{rel}/presion_{k}.csv}};",
                    r"    \end{axis}",
                    f"    \\begin{{axis}}[width=0.93\\linewidth, height=3.6cm, axis y line*=right, axis x line=none, xmin=0, "
                    f"enlarge x limits=false, ylabel={{$\\log_{{10}} G$ [\\si{{\\micro\\siemens}}]}}, "
                    "ylabel style={rojo}, tick label style={font=\\footnotesize}]",
                    f"      \\addplot [rojo, thin] table [x=t, y=logG, col sep=comma] {{{rel}/presion_{k}.csv}};",
                    r"    \end{axis}", r"  \end{tikzpicture}", ""]
        F_p += [r"  \caption{Movilidad de los robots (percentil 90 de la rapidez, azul; atascos sombreados) y "
                r"conductancia del sensor de presión $G=1/R$ (rojo, escala logarítmica, medianas de \SI{10}{\second}), "
                r"con el registro alineado al fin del pulso LED de sincronización (\cref{tab:presion}).}",
                r"  \label{fig:cmp_presion}", r"\end{figure}"]
        T2 = [r"\begin{table}[H]", r"  \centering",
              r"  \caption{Alineación del registro de presión con el video y conductancia dentro y fuera de los atascos.}",
              r"  \label{tab:presion}", r"  \small", f"  \\begin{{tabular}}{{@{{}}{colspec}@{{}}}}", r"    \toprule",
              f"    & {head} \\\\", r"    \midrule",
              row("Pulso LED: inicio", "Led", r"\second"), row("Pulso LED: fin ($=$ inicio del video)", "LedFin", r"\second"),
              row("Retardo por correlación cruzada", "Lag", r"\second"), row("Coeficiente de correlación $r$", "Rxc"),
              row("Correlación cruzada $-$ fin del pulso", "LagLed", r"\second"),
              row("$G$ mediana en atascos", "Gin", r"\micro\siemens"),
              row("$G$ mediana fuera de atascos", "Gout", r"\micro\siemens"),
              row("Cociente", "Grat"),
              row("Muestras saturadas en atascos", "SatIn", r"\percent"),
              row("Muestras saturadas en total", "SatAll", r"\percent"),
              r"    \bottomrule", r"  \end{tabular}", r"\end{table}"]
        F_p = T2 + F_p

    body = ["% Generated by comparar_ensayos.py -- do not edit; re-run the script instead.",
            r"\subsection{Tabla comparativa}", *T1,
            r"\subsection{Rapidez en el tiempo y atascos}\label{sec:cmp_atascos}", *F_ser,
            r"\subsection{Distribuciones}", *F_hist,
            r"\subsection{Rotación individual y desplazamiento}", *F_giro,
            r"\subsection{Ocupación de la arena}", *F_rad]
    (out / "comparacion.tex").write_text("\n".join(body) + "\n", encoding="utf-8")
    (out / "presion.tex").write_text("% Generated by comparar_ensayos.py\n" + "\n".join(F_p) + "\n", encoding="utf-8")


# --------------------------------------------------------------------------- main
def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("csv", type=Path, nargs="+", help="CSV 'una fila por robot y cuadro' de cada ensayo")
    ap.add_argument("--mediciones", type=Path, default=DEFAULT_PRESSURE if DEFAULT_PRESSURE.is_dir() else None,
                    help="carpeta con R_<código>.csv del sensor (por defecto datos/presion/crudos)")
    ap.add_argument("--cuadros-por-segundo", type=float, help="reexpresar todos los CSV con esta escala de tiempo")
    ap.add_argument("--informe-dir", type=Path, default=DEFAULT_REPORT)
    a = ap.parse_args()
    warnings.filterwarnings("ignore", category=RuntimeWarning)   # empty slices in all-stopped frames
    # Windows shells do not expand wildcards: expand them here, sorted by name (= by date/time).
    paths: list[Path] = []
    for c in a.csv:
        paths += sorted(Path(c.parent).glob(c.name)) if any(ch in c.name for ch in "*?[") else [c]
    a.csv = paths
    if not a.csv:
        sys.exit("No se encontró ningún CSV.")
    if len(a.csv) > len(LETTERS):
        sys.exit(f"Máximo {len(LETTERS)} ensayos.")
    out = a.informe_dir / "generado" / "comparacion"
    out.mkdir(parents=True, exist_ok=True)
    tests, results = [], []
    for k, path in zip(LETTERS, a.csv):
        T = load(path, a.cuadros_por_segundo)
        sen = None
        if a.mediciones:
            sp = a.mediciones / f"R_{T['code']}.csv"
            sen = sensor(sp) if sp.exists() else None
            if sen is None:
                print(f"Aviso: sin registro de presión para {T['code']} ({sp}).")
        print(f"[{k}] {T['code']}: {T['F']} cuadros, {T['N']} robots, {T['fps']:g} cuadros/s")
        results.append(analyse(T, out, k, sen))
        tests.append(T)
    occupancy_png(tests, out)
    write_tex(tests, results, out, "generado/comparacion")
    print(f"Listo: {out}. Compilá informe_ensayos.tex dos veces.")


if __name__ == "__main__":
    main()
