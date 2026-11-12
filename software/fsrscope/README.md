# FSRScope

Aplicación de escritorio (PySide6 + pyqtgraph) para analizar los registros del sensor FSR del
recinto circular: calibración, recorte, ΔG, asimetría y curtosis vs ΔT, supervivencia e
histogramas, con el video del ensayo sincronizado y reproducción «en vivo». Reemplaza al script
`procesar_presion_ventanas.py` (antes en `software/analisis_presion/`).

```
pip install -r software/requirements.txt
python software/fsrscope/app.py                      # interfaz
python software/fsrscope/app.py 20260925_1500        # abre directamente ese ensayo
python software/herramientas/procesar_lote.py        # genera todos los P_<código>.csv sin interfaz
```

Ejecutable: `software/empaquetado/dist/FSRScope/FSRScope.exe` (ver `software/README.md`).
Las velocidades de los robots están en la app **Velocidades** (`software/velocidades/`) y la
superposición de varios ensayos en el **Comparador** (`software/comparador/`); las tres comparten
`software/comun/`.

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
  `SKEW()`/`KURT()` de Excel; ver `software/docs/Metodologia_calculo_presion.xlsx`).

## Archivos

- Configuración por ensayo: `datos/presion/config/<código>.json` (se guarda al exportar, al
  cambiar de ensayo o al cerrar si hubo cambios; la usa `herramientas/procesar_lote.py`).
- Salida: `datos/presion/procesados/P_<código>.csv`. Las series temporales se exportan dentro del
  recorte; las columnas más cortas (barrido, supervivencia, histogramas) se rellenan con vacío.

## Video partido

Si la cámara se cortó durante el ensayo y el video quedó en varios archivos
(`VC_<código>(1).mp4`, `VC_<código>(2).mp4`, …), FSRScope lo detecta solo y reproduce las partes en una
única línea de tiempo: cada parte empieza donde corresponde según el tiempo que no se grabó, en el
hueco muestra «Sin video», y los robots de VidFetch y la presión siguen sincronizados en todas las partes.

- **Hueco entre partes:** se toma de `datos/video/cortes.json`; si el ensayo no figura, se mide en el
  momento con los originales `VR_<código>(n)` (hora de inicio que graba la cámara en cada MP4, con 1 s de
  resolución, y cantidad de cuadros) y se guarda ahí para Velocidades, MATLAB y los informes.
- **Pestaña Video → «Video partido»:** muestra las partes, el hueco y avisos (parte recortada, cierre
  anormal de la cámara). Se puede desmarcar «Hueco automático» y escribir el hueco a mano (se guarda en la
  configuración del ensayo) o volver a medirlo con «Medir de nuevo en los originales».
- Lo mismo desde la línea de comandos: `python software/herramientas/medir_corte.py [código]`.

## Código

```
app.py             punto de entrada (python software/fsrscope/app.py o python -m fsrscope)
gui/               ventana, paneles, gráficos y video sincronizado
```

La lógica sin interfaz está en `software/comun/` (rutas y ensayos, configuración, lectura de
registros, señal, estadística, trayectorias, lote); la planilla con la metodología de cálculo, en
`software/docs/Metodologia_calculo_presion.xlsx`.
