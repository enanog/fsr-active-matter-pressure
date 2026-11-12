"""Publication figure of one Comparador tab, drawn with matplotlib and the shared style
(comun.estilo): same data and options as on screen, sized for a report column, page or poster."""

from __future__ import annotations

import numpy as np

from comun import estilo
from comparador import core


def _name(c: core.TrialCurves) -> str:
    return c.label.rsplit(" · ", 1)[0]


def figure(key: str, C: list[core.TrialCurves], o: core.Options, flags: dict, index: dict,
           width: str = "pagina"):
    import matplotlib
    matplotlib.use("Agg", force=False)
    import matplotlib.pyplot as plt
    from matplotlib.figure import Figure

    with matplotlib.rc_context(estilo.mpl_rc()):
        fig = Figure(figsize=estilo.figsize(width, 0.62), layout="constrained")
        ax = fig.add_subplot()
        sty = {c.code: estilo.series_style(index.get(c.code, 0)) for c in C}

        def line(c, x, y, **kw):
            col, ls = sty[c.code]
            kw.setdefault("ls", ls)
            return ax.plot(x, y, color=col, label=kw.pop("label", _name(c)), **kw)

        def shade(c):
            if flags.get("jams"):
                for a, b in c.jam_spans:
                    ax.axvspan(a, b, color=sty[c.code][0], alpha=0.12, lw=0)

        if key == "v":
            for c in C:
                if flags.get("raw"):
                    ax.plot(c.t_min, c.v, color=estilo.GRID, lw=0.5)
                shade(c)
                line(c, c.t_min, c.v_s)
            ax.axhline(o.threshold_mm_s, color=estilo.MUTED, lw=0.8, ls="--")
            ax.set(xlabel="$t$ video [min]", ylabel=r"$\bar V$ [mm/s]")
        elif key == "w":
            for c in C:
                if c.w_s is not None:
                    shade(c)
                    line(c, c.t_min, c.w_s)
            ax.set(xlabel="$t$ video [min]", ylabel=r"$\langle|\omega|\rangle$ [°/s]")
        elif key == "e":
            for c in C:
                if c.e_tr_s is None:
                    continue
                if flags.get("split"):
                    line(c, c.t_min, c.e_tr_s, ls="-")
                    line(c, c.t_min, c.e_rot_s, ls=":", label="_")
                else:
                    line(c, c.t_min, c.e_tr_s + c.e_rot_s)
            if flags.get("logy"):
                ax.set_yscale("log")
            unit = C[0].energy_unit if C else "µJ/kg"
            ax.set(xlabel="$t$ video [min]", ylabel="$E$ [nJ]" if unit == "nJ" else "$E/m$ [µJ/kg]")
        elif key in ("hist", "pdf", "ccdf"):
            edges = core.common_edges([c.samples for c in C], o.bins)
            for c in C:
                if not len(c.samples):
                    continue
                if key == "hist":
                    _, y = core.hist_fraction(c.samples, edges)
                    col, ls = sty[c.code]
                    ax.stairs(y, edges, color=col, ls=ls, label=_name(c), lw=1.2)
                elif key == "pdf":
                    x, y = core.pdf(c.samples, edges, log_bins=flags.get("logx", False))
                    ok = y > 0
                    line(c, x[ok], y[ok], marker="o", ms=2.5)
                else:
                    x, p = core.ccdf(c.samples, o.normalize_ccdf)
                    ok = x > 0 if flags.get("logx") else np.ones(len(x), bool)
                    line(c, x[ok], p[ok])
            if key == "hist":
                ax.set(xlabel="$v$ [mm/s]", ylabel="fracción de las muestras")
            elif key == "pdf":
                ax.set(xlabel="$v$ [mm/s]", ylabel="$P(v)$ [s/mm]")
            else:
                ax.set(xlabel=r"$v/\langle v\rangle$" if o.normalize_ccdf else "$v$ [mm/s]",
                       ylabel="$1-F$")
            if flags.get("logy"):
                ax.set_yscale("log")
            if flags.get("logx"):
                ax.set_xscale("log")
        elif key == "vg":
            ve = core.vg_edges(C, o.vg_bins)
            for c in C:
                x, med, q25, q75, _ = core.g_by_v(c, ve, o.vg_min_frames)
                if not len(x):
                    continue
                col, ls = sty[c.code]
                rho = core.correlation_vg(c)
                med = np.where(med > 0, med, np.nan) if flags.get("logy") else med
                ax.plot(x, med, color=col, ls=ls, marker="o", ms=3.5, mec="white", mew=0.6,
                        label=fr"{_name(c)} ($\rho$ = {rho:.2f})")
                if flags.get("iqr"):
                    ax.fill_between(x, q25, q75, color=col, alpha=0.15, lw=0)
            if flags.get("logy"):
                ax.set_yscale("log")
            ax.set(xlabel=r"$\bar V$ [mm/s]", ylabel=r"$G$ [µS]")
        else:
            raise ValueError(f"pestaña sin figura: {key}")
        if C:
            ax.legend(loc="best", ncols=1 if len(C) <= 4 else 2)
    return fig
