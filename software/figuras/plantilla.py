"""Plantilla para una figura nueva (copiar este archivo, renombrarlo y editar `dibujar`).

Ejemplo que ya funciona: V̄(t) arriba y G(t) abajo (ambas con media móvil de 30 s), con el mismo eje de tiempo (dos paneles en
lugar de doble eje), para los ensayos pedidos, con el estilo común del proyecto (comun/estilo.py)
y los mismos datos y sincronía que usan Velocidades y FSRScope.

    python software/figuras/plantilla.py 20261030_1200 20261030_1600
    python software/figuras/plantilla.py 20260924 --ancho columna --salida informes/figuras/vg_tiempo

Salida: <salida>.pdf y .png (por defecto informes/figuras/<nombre del script>.*).
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))   # software/: comun, vidfetch, ...
import numpy as np  # noqa: E402

from comun import estilo, paths  # noqa: E402
from comun.mobility import MobilityData, rolling_mean  # noqa: E402
from comun.summary import trials_with_trajectories  # noqa: E402

NAME = Path(__file__).stem


def load(filters: list[str]) -> list[MobilityData]:
    """Trials (with trajectories) whose code contains any of the filters, oldest first."""
    trials = [t for t in trials_with_trajectories() if not filters or any(f in t.code for f in filters)]
    if not trials:
        sys.exit(f"Ningún ensayo con trayectorias coincide con {filters}.")
    return [MobilityData.open(t) for t in trials]


def dibujar(mds: list[MobilityData], ancho: str):
    """Edit here. One MobilityData per trial: .robots (positions, |v|, ω), .td (pressure:
    .td.series.t / .G, FSRScope sync), .frame_minutes, .smooth(x), .jams, .energy()."""
    from matplotlib.figure import Figure
    all_codes = [t.code for t in trials_with_trajectories()]
    fig = Figure(figsize=estilo.figsize(ancho, 0.75), layout="constrained")
    ax_v, ax_g = fig.subplots(2, 1, sharex=True)
    for md in mds:
        color, ls = estilo.series_style(all_codes.index(md.trial.code))   # colour follows the trial
        label = paths.code_label(md.trial.code).rsplit(" · ", 1)[0]
        ax_v.plot(md.frame_minutes, md.smooth(md.robots.v_mean, 30), color=color, ls=ls, label=label)
        if md.td is not None:
            s = md.td.series
            t_min = md.sensor_to_minutes(s.t)
            ok = (t_min >= 0) & (t_min <= md.duration_min)
            g = rolling_mean(s.G, int(round(30 / s.step_s)))   # 30 s moving average, as V̄
            ax_g.plot(t_min[ok], np.where(g[ok] > 1e-3, g[ok], np.nan), color=color, ls=ls, lw=0.8)
    ax_v.set(ylabel=r"$\bar V$ [mm/s]")
    ax_g.set(xlabel="$t$ video [min]", ylabel="$G$ [µS]", yscale="log")
    ax_v.legend(loc="upper right", ncols=min(3, len(mds)))
    return fig


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("ensayos", nargs="*", help="códigos (o parte) de los ensayos; vacío = todos")
    ap.add_argument("--ancho", default="pagina", help="columna | pagina | poster | ancho en cm")
    ap.add_argument("--salida", type=Path, default=paths.REPO_ROOT / "informes" / "figuras" / NAME)
    ap.add_argument("--formatos", nargs="+", default=["pdf", "png"])
    a = ap.parse_args(argv)
    ancho = a.ancho if a.ancho in estilo.WIDTH_CM else float(a.ancho)
    import matplotlib
    with matplotlib.rc_context(estilo.mpl_rc()):
        fig = dibujar(load(a.ensayos), ancho)
        for p in estilo.save(fig, a.salida, a.formatos):
            print(p)
    return 0


if __name__ == "__main__":
    sys.exit(main())
