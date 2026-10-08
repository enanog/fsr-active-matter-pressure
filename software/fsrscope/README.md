# FSRScope

Aplicación de escritorio (PySide6 + pyqtgraph) para analizar los registros del sensor FSR del
recinto circular: calibración, recorte, ΔG, asimetría y curtosis vs ΔT, supervivencia e
histogramas, con el video del ensayo sincronizado y reproducción «en vivo». Reemplaza al script
`procesar_presion_ventanas.py` (antes en `software/analisis_presion/`).

```
pip install -r software/fsrscope/requirements.txt
python software/fsrscope/main.py                  # interfaz
python software/fsrscope/main.py 20262509_1500    # abre directamente ese ensayo
python software/fsrscope/procesar_lote.py         # genera todos los P_<código>.csv sin interfaz
```

## Qué hace cada pestaña

| Pestaña | Contenido |
|---|---|
| Ensayo | registros de `datos/presion/crudos/` (marca si hay video, trayectorias o configuración guardada), datos del registro: pulso LED, factor del firmware, saturación |
| Calibración | `V_REF`, `V_EXC`, `R_FEEDBACK`, `ADC_FS`. Modo automático: usa el factor G/ADC que registró el propio firmware (sigue los cambios de `R_FEEDBACK` entre ensayos). Muestra el piso de saturación |
| Análisis | paso de remuestreo, ΔT fija de la serie ΔG(t), ΔT máxima del barrido, clases de histograma; recorte temporal y tramos excluidos (con la selección amarilla arrastrable sobre los gráficos) |
| Video | escala del time-lapse (cuadros por segundo real), desfase video↔sensor (automático = fin del pulso LED), espejado, superposición de los robots de VidFetch coloreados por \|v\| |
| Gráficos | qué gráficos mostrar, en qué orden (arrastrar) y sus opciones (escalas log, líneas de saturación, columna cruda a graficar…) |
| Exportar | columnas del CSV procesado y su orden (por defecto, el formato histórico), exportación, guardado de configuración y procesamiento por lotes |

Barra inferior: reproducir/pausar (Espacio), cuadro anterior/siguiente (←/→, Mayús = ±10 s),
velocidad en segundos de ensayo por segundo (×10 = velocidad del time-lapse), **En vivo** (los
gráficos de tiempo muestran solo hasta el cursor con una ventana móvil y la estadística se acumula
hasta ese instante; en gris, la del ensayo completo) y **Seguir cursor**. Doble clic o arrastrar el
cursor rojo en un gráfico de tiempo salta a ese instante. Clic derecho sobre un gráfico: escalas y
*Export…* (PNG, SVG, CSV).

## Convenciones

- Tiempo del sensor: segundos desde la primera fila del registro (misma referencia que el pulso
  LED). `t_sensor = desfase + cuadro / f_r`, con `f_r` = 3 cuadros por segundo real.
- G en µS, sin filtrado ni corrección de línea de base (el firmware ya filtra; una línea de base
  adaptativa borraría los atascos).
- ΔG(t) = G(t) − G(t − ΔT) se anula (NaN) cuando cualquiera de los dos extremos cae fuera del
  recorte o en un tramo excluido; la estadística usa solo esas diferencias válidas.
- Asimetría y curtosis: estimadores insesgados de Fisher–Pearson (iguales a `pandas` y a
  `SKEW()`/`KURT()` de Excel; ver `docs/Metodologia_calculo_presion.xlsx`).

## Archivos

- Configuración por ensayo: `datos/presion/config/<código>.json` (se guarda al exportar, al
  cambiar de ensayo o al cerrar si hubo cambios; la usa `procesar_lote.py`).
- Salida: `datos/presion/procesados/P_<código>.csv`. Las series temporales se exportan dentro del
  recorte; las columnas más cortas (barrido, supervivencia, histogramas) se rellenan con vacío.

## Código

```
main.py            interfaz
procesar_lote.py   procesamiento por lotes (misma lógica que la interfaz)
core/              lógica sin interfaz
  paths.py         estructura del repo y búsqueda de ensayos (R_/VC_/VR_/VP_)
  settings.py      parámetros y JSON por ensayo
  log_io.py        lectura robusta de todos los formatos de registro
  signal.py        calibración, remuestreo, saturación, máscara de análisis, ΔG
  stats.py         asimetría/curtosis vs ΔT, supervivencia, histogramas
  robots.py        trayectorias de VidFetch
  video.py         lectura de cuadros para reproducción
  export.py        columnas y escritura del CSV procesado
  session.py       todo lo cargado de un ensayo (lo comparten la GUI y el lote)
gui/               interfaz (ventana, paneles, gráficos, video, trabajos en segundo plano)
docs/              planilla con la metodología de cálculo
```
