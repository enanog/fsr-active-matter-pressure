"""Compare the filmed tests by motion mode (QR / QL / R): video kinematics + pressure sensor.

Usage (from the repository root):
    python software/analisis_video/comparar_modos.py
    python software/analisis_video/comparar_modos.py --ensayos 20263010_1100_22QL_60 20263010_1200_22R_60

Input
  datos/video/trayectorias/VP_<código>_robots.csv (+ _info.json)   one row per robot and frame
  datos/video/trayectorias/VP_<código>(n)_robots.csv               parts of a video cut while recording
  datos/video/cortes.json                                           gap between parts (medir_corte.py)
  datos/presion/crudos/R_<código>.csv                               FSR log (read with fsrscope.core.log_io)

Split tests: the parts are joined on one time axis with the measured gap filled with NaN
(status "sin video"). Robot identities of part (n+1) are matched to part n by minimum-cost
assignment of the last/first positions (mm, origin at the enclosure centre). theta of the later
part continues from the last value of the previous one (rotation inside the gap is unknown).

Time base: t_video = frame / f_r with f_r = 2.997 (DJI time-lapse, measured from the MP4 header);
sensor time = end of the LED pulse + t_video. Pressure statistics use the log between the start
and the end of the video (the gap included: the log is continuous).

Output: informes/ensayos/generado/modos/  PNG figures, CSV series and resumen_modos.csv.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import warnings
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.optimize import linear_sum_assignment

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(ROOT / "software" / "fsrscope"))
from core.log_io import load_log          # noqa: E402
from core.stats import moments_vs_deltaT  # noqa: E402

FR = 30000 / 1001 / 10                    # 2.997 frames per real second
OBSERVED = {"detectado", "detectado (umbral relajado)", "manual"}
FREEZE_P90_MM_S, FREEZE_SMOOTH_S, FREEZE_MIN_S = 0.52, 30.0, 20.0   # same as comparar_ensayos.py
SERIES_BIN_S = 30.0
G_CONTACT_US = 1.0                       # G above this: something presses the sensor
STEP_S = 0.05
DT_MAX_S = 15.0
CODE_RE = re.compile(r"(\d{8}_\d{4}_\d{2}([A-Za-z]{1,2})_\d{1,4})")
MODE_COLOR = {"QR": "#2a78d6", "QL": "#eb6834", "R": "#1baf7a"}     # validated categorical slots 1-3
MODE_NAME = {"QR": "QR", "QL": "QL", "R": "R (aleatorio)"}
LINESTYLES = ["-", "--", ":"]
INK, INK2, GRID = "#0b0b0b", "#52514e", "#e4e3df"


# --------------------------------------------------------------------------- helpers
def label(code: str) -> str:
    d, hm = code[:8], code[9:13]
    return f"{d[4:6]}/{d[6:8]} {hm[:2]}:{hm[2:]} {CODE_RE.search(code).group(2)}"


def runs(mask: np.ndarray, min_len: int) -> list[tuple[int, int]]:
    idx = np.flatnonzero(mask)
    if len(idx) == 0:
        return []
    groups = np.split(idx, np.flatnonzero(np.diff(idx) > 1) + 1)
    return [(int(g[0]), int(g[-1])) for g in groups if len(g) >= min_len]


def read_vp(path: Path) -> dict:
    cols = ["frame", "particle", "status", "x_mm", "y_mm", "vx_mm_s", "vy_mm_s", "speed_mm_s",
            "theta_deg", "omega_deg_s"]
    try:
        df = pd.read_csv(path, usecols=cols)
    except (OSError, ValueError) as exc:
        sys.exit(f"No se pudo leer {path.name}: {exc}")
    df = df.sort_values(["frame", "particle"])
    F, N = df["frame"].nunique(), df["particle"].nunique()
    if F * N != len(df):
        sys.exit(f"{path.name}: el CSV no es rectangular (cuadros x robots).")
    out = {c: pd.to_numeric(df[c], errors="coerce").to_numpy(float).reshape(F, N) for c in cols[3:]}
    out["status"] = df["status"].astype(str).to_numpy().reshape(F, N)
    return out


KEYS = ["x_mm", "y_mm", "vx_mm_s", "vy_mm_s", "speed_mm_s", "theta_deg", "omega_deg_s"]


def load_video(code: str, traj: Path, cuts: dict) -> dict:
    single = traj / f"VP_{code}_robots.csv"
    parts = sorted(traj.glob(f"VP_{code}(*)_robots.csv"))
    if single.exists():
        T = read_vp(single)
        F = len(T["x_mm"])
        T.update(t=np.arange(F) / FR, valid=np.ones(F, bool), parts=[(0, F)], match=[])
        return T
    if not parts:
        sys.exit(f"No hay trayectorias para {code}")
    if code not in cuts:
        sys.exit(f"{code} está partido en {len(parts)} y no figura en cortes.json: correr medir_corte.py")
    gaps = cuts[code]["hueco_s"]
    P = [read_vp(p) for p in parts]
    T = {k: [P[0][k]] for k in KEYS + ["status"]}
    t = [np.arange(len(P[0]["x_mm"])) / FR]
    valid, spans, match = [np.ones(len(t[0]), bool)], [(0, len(t[0]))], []
    prev = P[0]
    for Q, gap in zip(P[1:], gaps):
        N = prev["x_mm"].shape[1]
        a = np.column_stack([T["x_mm"][-1][-1], T["y_mm"][-1][-1]])
        b = np.column_stack([Q["x_mm"][0], Q["y_mm"][0]])
        C = np.linalg.norm(a[:, None] - b[None], axis=2)
        ri, perm = linear_sum_assignment(C)
        srt = np.sort(C, 1)
        match.append({"desplazamiento_mm": C[ri, perm], "ambiguedad": srt[:, 0] / srt[:, 1]})
        nmiss = max(int(round(gap * FR)) - 1, 0)
        last_t = t[-1][-1]
        for k in KEYS:
            q = Q[k][:, perm]
            if k == "theta_deg":
                q = q + T[k][-1][-1][None, :]
            T[k] += [np.full((nmiss, N), np.nan), q]
        T["status"] += [np.full((nmiss, N), "sin video", dtype=object), Q["status"][:, perm]]
        start = sum(len(v) for v in valid) + nmiss
        t += [last_t + np.arange(1, nmiss + 1) / FR, last_t + gap + np.arange(len(Q["x_mm"])) / FR]
        valid += [np.zeros(nmiss, bool), np.ones(len(Q["x_mm"]), bool)]
        spans.append((start, start + len(Q["x_mm"])))
        prev = Q
    out = {k: np.vstack(v) for k, v in T.items() if k != "status"}
    out["status"] = np.vstack([np.asarray(s, dtype=object) for s in T["status"]])
    out.update(t=np.concatenate(t), valid=np.concatenate(valid), parts=spans, match=match)
    return out


def load_sensor(path: Path) -> dict:
    r = load_log(path)
    if r.k_firmware is None:
        sys.exit(f"{path.name}: no se pudo deducir K del firmware.")
    G = r.adc * r.k_firmware
    sat = r.full_saturation()
    sat = (np.zeros(len(G), bool) if sat is None else sat) | (r.adc >= 1023 - 0.5)
    if not np.isfinite(r.led_off):
        sys.exit(f"{path.name}: sin pulso LED, no se puede sincronizar.")
    return {"t": r.t, "G": G, "sat": sat, "led_off": r.led_off, "K": r.k_firmware, "Gmax": 1023 * r.k_firmware}


# --------------------------------------------------------------------------- per test
def analyse(code: str, V: dict, S: dict) -> dict:
    mode = CODE_RE.search(code).group(2).upper()
    x, y, v, w = V["x_mm"], V["y_mm"], V["speed_mm_s"], V["omega_deg_s"]
    vx, vy, ok = V["vx_mm_s"], V["vy_mm_s"], V["valid"]
    F, N = x.shape
    obs = np.isin(V["status"], list(OBSERVED))
    r = np.hypot(x, y)
    Rc = float(np.nanpercentile(r[obs], 99.5))
    phi = np.degrees(np.arctan2(y, x)) % 360
    wall = r >= Rc - 33.0 / 2

    # collective stops (frames without video stay NaN and never count as stopped)
    p90 = np.full(F, np.nan)
    p90[ok] = np.nanpercentile(v[ok], 90, axis=1)
    p90s = pd.Series(p90).rolling(int(FREEZE_SMOOTH_S * FR), center=True, min_periods=1).median().to_numpy()
    frz = runs(np.nan_to_num(p90s, nan=np.inf) < FREEZE_P90_MM_S, int(FREEZE_MIN_S * FR))
    fmask = np.zeros(F, bool)
    for a, b in frz:
        fmask[a:b + 1] = True

    # collective rotation about the centre (CCW > 0)
    moving = (v > 1.0) & (r > 0.3 * Rc)
    sinang = (x * vy - y * vx) / np.maximum(r * np.hypot(vx, vy), 1e-12)
    Phi = np.nanmean(np.where(moving, sinang, np.nan), axis=1)

    # sensor on the video time base
    t_log = S["led_off"] + V["t"]
    G_f = np.interp(t_log, S["t"], S["G"], left=np.nan, right=np.nan)
    G_f[~ok] = np.nan
    in_vid = (S["t"] >= S["led_off"]) & (S["t"] <= t_log[-1])
    Gv, satv = S["G"][in_vid], S["sat"][in_vid]

    # pressure-mobility coupling: 30 s windows with video, p90 speed vs median G
    nb = int(round(SERIES_BIN_S * FR))
    wi = np.arange(F) // nb
    win = pd.DataFrame({"w": wi, "p90": p90, "G": G_f}).dropna().groupby("w").median()
    lg = np.log10(win["G"] + 0.01)
    rho = float(pd.Series(win["p90"]).corr(lg, method="spearman")) if len(win) > 10 else np.nan

    # deltaG skewness vs window on the uniform 50 ms grid, video interval
    tg = np.arange(S["led_off"], t_log[-1], STEP_S)
    g = np.interp(tg, S["t"], S["G"])
    dT, skew, kurt = moments_vs_deltaT(g, np.ones(len(g), bool), STEP_S, DT_MAX_S)

    wmean = np.nanmean(w, 0)
    turns = (V["theta_deg"][np.flatnonzero(ok)[-1]] - V["theta_deg"][0]) / 360.0
    vo = v[obs & np.isfinite(v)]
    wo = w[obs & np.isfinite(w)]
    res = {
        "codigo": code, "etiqueta": label(code), "modo": mode, "N": N,
        "dur_video_min": ok.sum() / FR / 60, "dur_total_min": V["t"][-1] / 60,
        "hueco_s": float(np.max(np.diff(V["t"][ok]))) if (~ok).any() else 0.0,
        "Rc_mm": Rc, "obs_pct": 100 * obs[ok].mean(),
        "v_med": float(np.median(vo)), "v_p95": float(np.percentile(vo, 95)),
        "v_med_activo": float(np.nanmedian(v[ok & ~fmask])),
        "w_abs_med": float(np.median(np.abs(wo))), "w_media": float(np.mean(wo)),
        "w_pos_pct": 100 * float((wo > 0).mean()),
        "robots_antihorario": int((wmean > 0.5).sum()), "robots_horario": int((wmean < -0.5).sum()),
        "Phi": float(np.nanmean(Phi)), "pared_pct": 100 * float(np.nanmean(wall[ok])),
        "atascos": len(frz), "atasco_min": fmask.sum() / FR / 60, "atasco_pct": 100 * fmask[ok].mean(),
        "atasco_max_s": max([(b - a + 1) / FR for a, b in frz], default=0.0),
        "K_uS": S["K"], "G_med": float(np.median(Gv)), "G_p90": float(np.percentile(Gv, 90)),
        "G_p99": float(np.percentile(Gv, 99)), "contacto_pct": 100 * float((Gv > G_CONTACT_US).mean()),
        "sat_pct": 100 * float(satv.mean()),
        "G_med_atasco": float(np.nanmedian(G_f[fmask])) if fmask.any() else np.nan,
        "G_med_libre": float(np.nanmedian(G_f[ok & ~fmask])),
        "rho_movilidad_G": rho,
        "skew_2p5s": float(np.interp(2.5, dT, skew)), "skew_max": float(np.nanmax(skew)),
    }
    ser = {"t": V["t"], "ok": ok, "p90": p90, "vmed": np.where(ok, np.nanmedian(v, 1), np.nan),
           "Phi": Phi, "fmask": fmask, "G_f": G_f, "wmean": wmean, "turns": turns,
           "x": x, "y": y, "r": r, "Rc": Rc, "dT": dT, "skew": skew, "Gv": Gv, "vo": vo, "wo": wo,
           "win": win, "frz": frz}
    return res, ser


# --------------------------------------------------------------------------- figures
def style(ax):
    ax.grid(True, color=GRID, lw=0.6)
    ax.set_axisbelow(True)
    for s in ("top", "right"):
        ax.spines[s].set_visible(False)
    for s in ("left", "bottom"):
        ax.spines[s].set_color(INK2)
    ax.tick_params(colors=INK2, labelsize=8)


def run_style(R: list[dict]) -> dict:
    seen, st = {}, {}
    for r in R:
        i = seen.get(r["modo"], 0)
        seen[r["modo"]] = i + 1
        st[r["codigo"]] = {"color": MODE_COLOR.get(r["modo"], INK2), "ls": LINESTYLES[i % 3]}
    return st


def binned(t, a, w):
    idx = (t // w).astype(int)
    s = pd.Series(a).groupby(idx).mean()
    return (s.index.to_numpy() + 0.5) * w, s.to_numpy()


def fig_series(R, SER, out, plt):
    n = len(R)
    fig, axs = plt.subplots(2 * n, 1, figsize=(7.5, 1.35 * 2 * n), sharex=True,
                            gridspec_kw={"height_ratios": [1, 1] * n, "hspace": 0.15})
    tmax = max(s["t"][-1] for s in SER) / 60
    for i, (r, s) in enumerate(zip(R, SER)):
        a1, a2 = axs[2 * i], axs[2 * i + 1]
        c = MODE_COLOR[r["modo"]]
        t = s["t"] / 60
        for a in (a1, a2):
            style(a)
            for p, q in s["frz"]:
                a.axvspan(t[p], t[q], color="#d9d8d3", lw=0)
            gap = ~s["ok"]
            if gap.any():
                gi = np.flatnonzero(gap)
                a.axvspan(t[gi[0]], t[gi[-1]], color="none", hatch="////", ec=INK2, lw=0)
        tb, vb = binned(s["t"], s["p90"], SERIES_BIN_S)
        a1.plot(tb / 60, vb, color=c, lw=1.4)
        a1.set_ylim(0, 6)
        a1.set_ylabel("$|v|_{90}$\n[mm/s]", fontsize=7, color=INK2)
        a1.text(0.005, 0.93, r["etiqueta"], transform=a1.transAxes, fontsize=8, color=INK, va="top",
                fontweight="bold")
        tb, gb = binned(s["t"], np.log10(s["G_f"] + 0.01), 10.0)
        a2.plot(tb / 60, gb, color=INK, lw=0.9)
        a2.set_ylim(-2.2, 3.7)
        a2.set_yticks([-2, 0, 2])
        a2.set_yticklabels(["0,01", "1", "100"])
        a2.set_ylabel("$G$\n[µS]", fontsize=7, color=INK2)
    axs[-1].set_xlim(0, tmax)
    axs[-1].set_xlabel("tiempo de video [min]", fontsize=8, color=INK2)
    fig.subplots_adjust(top=0.965, bottom=0.04)
    fig.suptitle("Movilidad (percentil 90 de la rapidez, 30 s) y conductancia del sensor (medianas de 10 s)\n"
                 "gris: atascos; corte blanco: sin video", fontsize=9, color=INK, y=0.995)
    fig.savefig(out / "series_tiempo.png", dpi=200, bbox_inches="tight")
    plt.close(fig)


def ccdf(a):
    a = np.sort(a[np.isfinite(a)])
    p = 1 - np.arange(len(a)) / len(a)
    k = np.unique(np.round(np.logspace(0, np.log10(len(a)), 600)).astype(int)) - 1
    return a[k], p[k]


def fig_distributions(R, SER, out, plt, st):
    fig, axs = plt.subplots(1, 3, figsize=(10.5, 3.3), constrained_layout=True)
    for r, s in zip(R, SER):
        kw = dict(color=st[r["codigo"]]["color"], ls=st[r["codigo"]]["ls"], lw=1.5, label=r["etiqueta"])
        xx, pp = ccdf(s["vo"])
        axs[0].plot(xx, pp, **kw)
        e = np.linspace(-40, 40, 81)
        h, _ = np.histogram(s["wo"], e)
        h = h / (len(s["wo"]) * np.diff(e))           # density over all points (tails beyond ±40 not drawn)
        axs[1].step(e[:-1], h, where="post", **kw)
        xx, pp = ccdf(s["Gv"])
        axs[2].plot(np.maximum(xx, 1e-2), pp, **kw)
    axs[0].set(xscale="log", yscale="log", xlim=(0.05, 15), ylim=(1e-5, 1.05),
               xlabel="$|v|$ [mm/s]", ylabel="$P(|v|\\geq x)$")
    axs[1].set(yscale="log", ylim=(1e-4, 0.5), xlabel="$\\omega$ [°/s]  (+ antihorario)", ylabel="densidad [s/°]")
    axs[2].set(xscale="log", yscale="log", xlim=(1e-2, 5e3), ylim=(1e-5, 1.05),
               xlabel="$G$ [µS]", ylabel="$P(G\\geq g)$")
    for a, ttl in zip(axs, ["Rapidez", "Velocidad angular", "Conductancia (supervivencia)"]):
        style(a)
        a.set_title(ttl, fontsize=9, color=INK)
        a.xaxis.label.set_size(8)
        a.yaxis.label.set_size(8)
    axs[0].legend(fontsize=7, frameon=False)
    fig.savefig(out / "distribuciones.png", dpi=200)
    plt.close(fig)


def fig_spin(R, SER, out, plt, st):
    fig, axs = plt.subplots(1, 2, figsize=(10, 3.4), constrained_layout=True)
    for r, s in zip(R, SER):
        kw = dict(color=st[r["codigo"]]["color"], ls=st[r["codigo"]]["ls"], lw=1.2, label=r["etiqueta"])
        axs[0].plot(np.sort(s["wmean"]), marker="o", ms=3, **kw)
        tb, pb = binned(s["t"], s["Phi"], 60.0)
        axs[1].plot(tb / 60, pb, **kw)
    axs[0].axhline(0, color=INK2, lw=0.8)
    axs[1].axhline(0, color=INK2, lw=0.8)
    axs[0].set(xlabel="robots ordenados", ylabel="$\\overline{\\omega}$ por robot [°/s]")
    axs[1].set(xlabel="tiempo de video [min]", ylabel="$\\Phi$ (medias de 1 min)", ylim=(-0.8, 0.8))
    axs[0].set_title("Giro propio medio de cada robot (+ antihorario)", fontsize=9, color=INK)
    axs[1].set_title("Circulación colectiva alrededor del centro (+ antihorario)", fontsize=9, color=INK)
    for a in axs:
        style(a)
        a.xaxis.label.set_size(8)
        a.yaxis.label.set_size(8)
    axs[0].legend(fontsize=7, frameon=False, ncol=2)
    fig.savefig(out / "giro_circulacion.png", dpi=200)
    plt.close(fig)


def fig_occupancy(R, SER, out, plt):
    n = len(R)
    fig, axs = plt.subplots(1, n, figsize=(2.2 * n, 2.6), constrained_layout=True)
    for a, r, s in zip(np.atleast_1d(axs), R, SER):
        x, y = s["x"][s["ok"]].ravel() / 10, s["y"][s["ok"]].ravel() / 10
        k = np.isfinite(x) & np.isfinite(y)
        h, _, _ = np.histogram2d(x[k], y[k], bins=80, range=[[-9.6, 9.6]] * 2, density=True)
        a.imshow(h.T, origin="lower", extent=[-9.6, 9.6, -9.6, 9.6], cmap="Greys",
                 vmax=np.percentile(h[h > 0], 99))
        a.add_patch(plt.Circle((0, 0), 9.25, fill=False, color=MODE_COLOR[r["modo"]], lw=1.2))
        a.set_title(r["etiqueta"], fontsize=8, color=INK)
        a.set_xticks([])
        a.set_yticks([])
        a.set_aspect("equal")
    fig.suptitle("Ocupación de los centros de los robots (vista del observador; círculo: pared interior)",
                 fontsize=8, color=INK)
    fig.savefig(out / "ocupacion.png", dpi=200)
    plt.close(fig)


def fig_sensor(R, SER, out, plt, st):
    fig, axs = plt.subplots(1, 2, figsize=(10, 3.3), constrained_layout=True)
    for r, s in zip(R, SER):
        kw = dict(color=st[r["codigo"]]["color"], ls=st[r["codigo"]]["ls"], lw=1.3, label=r["etiqueta"])
        w = s["win"]
        e = np.array([0, 0.4, 0.8, 1.2, 1.6, 2.0, 2.4, 2.8, 3.4, 6.0])
        ib = np.digitize(w["p90"], e) - 1
        g = pd.Series(np.log10(w["G"] + 0.01)).groupby(ib).median()
        n = pd.Series(ib).value_counts()
        keep = [i for i in g.index if 0 <= i < len(e) - 1 and n.get(i, 0) >= 5]
        xc = (e[:-1] + e[1:]) / 2
        axs[0].plot(xc[keep], g[keep].to_numpy(), marker="o", ms=3, **kw)
        axs[1].plot(s["dT"], s["skew"], **kw)
    axs[0].set(xlabel="$|v|_{90}$ en la ventana [mm/s]", ylabel="mediana de $G$ [µS]")
    axs[0].set_yticks([-2, -1, 0, 1, 2, 3])
    axs[0].set_yticklabels(["0,01", "0,1", "1", "10", "100", "1000"])
    axs[1].set(xlabel="$\\Delta T$ [s]", ylabel="asimetría de $\\Delta G$", xlim=(0, DT_MAX_S))
    axs[0].set_title("Presión vs. movilidad (ventanas de 30 s, ≥ 5 por punto)", fontsize=9, color=INK)
    axs[1].set_title("Asimetría de $\\Delta G = G(t)-G(t-\\Delta T)$", fontsize=9, color=INK)
    for a in axs:
        style(a)
        a.xaxis.label.set_size(8)
        a.yaxis.label.set_size(8)
    axs[0].legend(fontsize=7, frameon=False, ncol=2)
    fig.savefig(out / "sensor.png", dpi=200)
    plt.close(fig)


def fig_summary(R, out, plt):
    items = [("v_med", "$|v|$ mediana [mm/s]"), ("w_media", "$\\omega$ media [°/s]"), ("Phi", "circulación $\\Phi$"),
             ("pared_pct", "tiempo en la pared [%]"), ("atasco_pct", "tiempo en atasco [%]"),
             ("contacto_pct", "tiempo con $G>1$ µS [%]")]
    fig, axs = plt.subplots(2, 3, figsize=(10, 5.2), constrained_layout=True)
    xs = np.arange(len(R))
    for a, (k, ttl) in zip(axs.ravel(), items):
        vals = [r[k] for r in R]
        a.bar(xs, vals, color=[MODE_COLOR[r["modo"]] for r in R], width=0.7, ec="white", lw=2)
        a.axhline(0, color=INK2, lw=0.8)
        a.set_xticks(xs)
        a.set_xticklabels([r["etiqueta"].replace(" ", "\n") for r in R], fontsize=6.5)
        a.set_title(ttl, fontsize=9, color=INK)
        style(a)
        a.grid(axis="x", visible=False)
        for xi, v in zip(xs, vals):
            a.text(xi, v, f"{v:.0f}" if abs(v) >= 10 else f"{v:.2g}", ha="center", va="bottom" if v >= 0 else "top", fontsize=6.5, color=INK2)
    handles = [plt.Rectangle((0, 0), 1, 1, color=c) for c in MODE_COLOR.values()]
    fig.legend(handles, MODE_NAME.values(), loc="lower center", ncol=3, fontsize=8, frameon=False,
               bbox_to_anchor=(0.5, -0.04))
    fig.savefig(out / "resumen_modos.png", dpi=200, bbox_inches="tight")
    plt.close(fig)


def fig_cut(code, V, S, out, plt):
    """Reconstruction of a split test: parts on the sensor time axis and identity matching."""
    m = V["match"][0]
    t_log = S["led_off"] + V["t"]
    fig, axs = plt.subplots(1, 2, figsize=(10, 3.2), constrained_layout=True, gridspec_kw={"width_ratios": [2.2, 1]})
    a = axs[0]
    style(a)
    a.plot(S["t"] / 60, np.log10(S["G"] + 0.01), color=INK, lw=0.4)
    for i, (p, q) in enumerate(V["parts"]):
        a.axvspan(t_log[p] / 60, t_log[q - 1] / 60, color=MODE_COLOR["QL"], alpha=0.15, lw=0)
        a.text((t_log[p] + t_log[q - 1]) / 120, 3.55, f"parte ({i + 1})", ha="center", fontsize=8, color=INK)
    gi = np.flatnonzero(~V["valid"])
    a.axvspan(t_log[gi[0]] / 60, t_log[gi[-1]] / 60, color=INK, alpha=0.5, lw=0)
    a.set(xlabel="tiempo del registro del sensor [min]", ylabel="$\\log_{10} G$ [µS]", ylim=(-2.2, 3.9))
    a.set_title(f"{label(code)}: video reconstruido sobre el registro (hueco {np.max(np.diff(V["t"][V["valid"]])):.1f} s)",
                fontsize=9, color=INK)
    b = axs[1]
    style(b)
    d = np.sort(m["desplazamiento_mm"])
    b.bar(np.arange(len(d)), d, color=MODE_COLOR["QL"], width=0.7)
    b.set_yscale("log")
    b.set(xlabel="robots (ordenados)", ylabel="desplazamiento [mm]")
    b.set_title("Último cuadro (1) → primero (2)", fontsize=9, color=INK)
    for ax in axs:
        ax.xaxis.label.set_size(8)
        ax.yaxis.label.set_size(8)
    fig.savefig(out / f"corte_{code}.png", dpi=200)
    plt.close(fig)


# --------------------------------------------------------------------------- main
def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--ensayos", nargs="*", help="códigos a comparar (por defecto todos los que tienen VP_ y R_)")
    ap.add_argument("--salida", type=Path, default=ROOT / "informes" / "ensayos" / "generado" / "modos")
    a = ap.parse_args()
    warnings.filterwarnings("ignore", category=RuntimeWarning)
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    plt.rcParams.update({"font.size": 8, "axes.edgecolor": INK2, "text.color": INK, "axes.labelcolor": INK2})

    traj = ROOT / "datos" / "video" / "trayectorias"
    raw = ROOT / "datos" / "presion" / "crudos"
    cuts_p = ROOT / "datos" / "video" / "cortes.json"
    cuts = json.loads(cuts_p.read_text(encoding="utf-8")) if cuts_p.exists() else {}
    codes = a.ensayos or sorted({CODE_RE.search(p.name).group(1) for p in traj.glob("VP_*_robots.csv")})
    codes = [c for c in codes if (raw / f"R_{c}.csv").exists()]
    # sort by mode, then date/time
    order = {"QR": 0, "QL": 1, "R": 2}
    codes.sort(key=lambda c: (order.get(CODE_RE.search(c).group(2).upper(), 9), c[6:8] + c[4:6], c[9:13]))
    out = a.salida
    out.mkdir(parents=True, exist_ok=True)

    R, SER = [], []
    for code in codes:
        V = load_video(code, traj, cuts)
        S = load_sensor(raw / f"R_{code}.csv")
        res, ser = analyse(code, V, S)
        R.append(res)
        SER.append(ser)
        msg = f"{code}: {res['dur_video_min']:.1f} min de video"
        if V["match"]:
            d = V["match"][0]["desplazamiento_mm"]
            amb = V["match"][0]["ambiguedad"]
            msg += (f", {len(V['parts'])} partes, hueco {res['hueco_s']:.2f} s, identidad: desplazamiento "
                    f"mediana {np.median(d):.2f} mm (máx {d.max():.1f}), ambigüedad máx {amb.max():.2f}")
            fig_cut(code, V, S, out, plt)
        print(msg)
        pd.DataFrame({"t_min": ser["t"] / 60, "v_p90": ser["p90"], "Phi": ser["Phi"],
                      "atasco": ser["fmask"].astype(int), "G_uS": ser["G_f"]}).iloc[::3].to_csv(
            out / f"serie_{code}.csv", index=False, float_format="%.5g")

    st = run_style(R)
    pd.DataFrame(R).to_csv(out / "resumen_modos.csv", index=False, float_format="%.4g")
    fig_series(R, SER, out, plt)
    fig_distributions(R, SER, out, plt, st)
    fig_spin(R, SER, out, plt, st)
    fig_occupancy(R, SER, out, plt)
    fig_sensor(R, SER, out, plt, st)
    fig_summary(R, out, plt)
    print(f"Listo: {out}")


if __name__ == "__main__":
    main()
