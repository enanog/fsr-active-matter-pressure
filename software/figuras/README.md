# Figuras

Scripts que generan figuras y secciones de los informes. Cada uno se corre desde la raíz del
repositorio (`python software/figuras/<script>.py --help`); `python software/figuras` los lista.

| Script | Qué genera |
|---|---|
| `plantilla.py` | **punto de partida para una figura nueva** (ejemplo: V̄(t) y G(t) en dos paneles) |
| `generar_informe.py` | datos y sección LaTeX de un ensayo (`informes/ensayos/generado/<código>/`) |
| `comparar_ensayos.py` | parte comparativa del informe de ensayos (`informes/ensayos/generado/comparacion/`) |
| `comparar_modos.py` | comparación por modo AH / HO / AL (`informes/ensayos/generado/modos/`) |
| `figuras_metodo.py` | figuras de método del informe de la aplicación (`informes/aplicacion/figuras/metodo/`) |

## Agregar una figura

1. Copiar `plantilla.py` con un nombre descriptivo (por ejemplo `presion_vs_densidad.py`).
2. Editar `dibujar(...)`: recibe un `MobilityData` por ensayo (trayectorias, presión sincronizada,
   atascos, energía) y devuelve una figura de matplotlib.
3. Correrlo: `python software/figuras/presion_vs_densidad.py 20261030 --ancho columna`. Por defecto
   guarda `informes/figuras/<nombre>.pdf` y `.png`.

Para figuras rápidas de varios ensayos superpuestos, el **Comparador** ya exporta cada pestaña con el
mismo estilo. En MATLAB: `software/matlab/figuras/` (un script por figura, mismos colores).

## Estilo común (`software/comun/estilo.py`)

- `estilo.mpl_rc()` / `apply_mpl()`: tipografía tipo Computer Modern (sin instalar LaTeX), tamaños de 9 pt,
  grilla tenue, sin bordes superior/derecho, PDF con fuentes embebidas.
- `estilo.figsize("columna" | "pagina" | "poster" | cm, aspecto)`.
- `estilo.series_style(i)`: color y trazo del i-ésimo ensayo (orden fijo; el color sigue al ensayo).
  `estilo.MODE_COLOR`: AH (antihorario) azul, HO (horario) naranja, AL (aleatorio) aqua.
- `estilo.save(fig, ruta, ("pdf", "png"))`.
- Sin doble eje Y: dos magnitudes de escala distinta van en dos paneles con el eje X compartido.
