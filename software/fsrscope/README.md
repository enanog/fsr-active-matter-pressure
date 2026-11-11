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

Las **velocidades de los robots** se analizan en una aplicación aparte que comparte `core/`:

```
python software/fsrscope/velocidades.py                  # interfaz
python software/fsrscope/velocidades.py 20263010_1600    # abre directamente ese ensayo
python software/fsrscope/velocidades.py --resumen        # datos/resumen_ensayos.csv sin interfaz
```

Una pestaña por gráfico, con sus opciones arriba y un botón **Ventana aparte** (al cerrar la ventana
vuelve a su pestaña): V̄(t) (media de |v| entre robots por cuadro), ⟨|ω|⟩(t), energía cinética del
conjunto (Σ½mv² + Σ½Iω², I = k·m·R², por unidad de masa [µJ/kg] o en nJ si se carga la masa), V̄ y G
con doble eje, umbral de atasco (línea arrastrable, atascos sombreados), histograma de velocidades
medias, P(v), 1 − F(v), mapa de ocupación (robots/cm², todo / atasco / flujo) y **Resumen de
ensayos** (una fila por ensayo con los valores medios, también en `datos/resumen_ensayos.csv`).
Todos los gráficos de tiempo llevan la misma media móvil (30 s por defecto, pestaña lateral
«Visualización») con la serie cruda en gris de fondo. Las distribuciones se calculan con los datos
sin suavizar; la casilla «Distribuciones de V̄ suavizada» existe solo para comparar (con 30 s el
desvío de V̄ baja de 0,39 a 0,18 mm/s y P(V̄ < 0,35) de 4 % a 0,03 % en 30/10 12:00).
Atasco: el estadístico elegido (media por defecto), con mediana móvil de 30 s, por debajo del umbral
(0,35 mm/s por defecto) durante ≥ 20 s; coincide con el criterio de los informes (p90 < 0,52 mm/s)
en el ≥ 98,5 % de los cuadros de los 7 ensayos. Su configuración (umbral, ventana en minutos de
video, opciones de los gráficos) va en `datos/video/config/<código>.json`; de FSRScope solo lee la
sincronía, la calibración, el recorte y las exclusiones (para G), sin escribir su configuración.

## Qué hace cada pestaña

| Pestaña | Contenido |
|---|---|
| Ensayo | registros de `datos/presion/crudos/` (marca si hay video, trayectorias o configuración guardada), datos del registro: pulso LED, factor del firmware, saturación |
| Calibración | `V_REF`, `V_EXC`, `R_FEEDBACK`, `ADC_FS`. Modo automático: usa el factor G/ADC que registró el propio firmware (sigue los cambios de `R_FEEDBACK` entre ensayos). Muestra el piso de saturación |
| Análisis | paso de remuestreo, ΔT fija de la serie ΔG(t), ΔT máxima del barrido, clases de histograma; recorte temporal y tramos excluidos (con la selección amarilla arrastrable sobre los gráficos) |
| Video | escala del time-lapse (cuadros por segundo real), desfase video↔sensor (automático = fin del pulso LED), vista rotada 180° (como la ve el observador), superposición de los robots de VidFetch coloreados por \|v\| |
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
main.py            interfaz (presión + video)
velocidades.py     interfaz de velocidades de los robots
procesar_lote.py   procesamiento por lotes (misma lógica que la interfaz)
core/              lógica sin interfaz
  paths.py         estructura del repo y búsqueda de ensayos (R_/VC_/VR_/VP_)
  settings.py      parámetros y JSON por ensayo
  log_io.py        lectura robusta de todos los formatos de registro
  signal.py        calibración, remuestreo, saturación, máscara de análisis, ΔG
  stats.py         asimetría/curtosis vs ΔT, supervivencia, histogramas
  robots.py        trayectorias de VidFetch (une videos partidos con datos/video/cortes.json)
  mobility.py      velocidades.py: V̄, atascos por umbral, distribuciones, mapa de ocupación
  summary.py       velocidades.py: resumen por ensayo
  video.py         lectura de cuadros para reproducción
  export.py        columnas y escritura del CSV procesado
  session.py       todo lo cargado de un ensayo (lo comparten la GUI y el lote)
gui/               interfaz (ventana, paneles, gráficos, video, trabajos en segundo plano;
                   vel_window.py y vel_plots.py son los de velocidades.py)
docs/              planilla con la metodología de cálculo
```
