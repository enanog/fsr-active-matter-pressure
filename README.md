# Presión en un recinto circular con robots autopropulsados

Proyecto ITBA (Dylan Frigerio): medición de la presión que ejerce un sistema de robots
autopropulsados (tipo Kilobot) confinados en una arena circular, con sensores FSR y
seguimiento de los robots por video.

## Estructura

```
.
├── README.md                 este archivo
├── CLAUDE.md                 registro técnico de decisiones (contexto para sesiones con Claude)
├── hardware/
│   ├── pcb/                  placa de adquisición FSR (Altium)
│   ├── firmware/             sketches de Arduino (lectura de uno o varios FSR)
│   └── simulacion/           simulaciones LTspice del front-end
├── software/                 ver software/README.md
│   ├── comun/                biblioteca compartida de las apps (presión, trayectorias, cortes de video)
│   ├── vidfetch/             app: recorte de video y seguimiento de robots
│   ├── fsrscope/             app: presión (G, ΔG, asimetría, supervivencia) con video sincronizado
│   ├── matlab_figuras/       figuras de comparación en MATLAB (figuras.m + cargar_datos.m)
│   ├── herramientas/         línea de comandos (lote de presión, reexportar, verificaciones)
│   └── empaquetado/          construcción de los .exe de las dos apps
├── datos/
│   ├── presion/
│   │   ├── crudos/           R_<código>.csv  todos los registros del sensor (20 Hz), también agosto y arena vacía
│   │   ├── config/           <código>.json   parámetros de FSRScope por ensayo
│   │   └── calibracion.csv   R_FEEDBACK de cada registro (la usa MATLAB)
│   └── video/                videos no versionados (pendrive); sesiones y CSV sí
│       ├── cortes.json       hueco entre partes de videos partidos
│       ├── originales/       VR_<código>.MP4  video original de la cámara, 4K
│       ├── recortados/       VC_<código>.MP4  recorte a la arena (lo que se analiza)
│       ├── seguimiento/      VS_<código>_seguimiento.mp4  video con los robots marcados
│       ├── sesiones/         VA_<código>_analisis.npz  sesiones de VidFetch
│       └── trayectorias/     VP_<código>_robots.csv    posiciones, velocidades y giros exportados
├── informes/
│   ├── preambulo.tex, config.tex   LaTeX compartido por los dos informes
│   ├── figuras/matlab_figuras/     salida de software/matlab_figuras
│   ├── aplicacion/           informe de la app VidFetch (uso, librerías, código)
│   └── ensayos/              informe de resultados de los ensayos filmados
└── difusion/
    └── poster_rafa2026/      póster y resumen de la RAFA 2026
```

## Código de ensayo

Todos los archivos de un mismo ensayo comparten el código `AAAAMMDD_HHMM_XXYY_TT` (ordena cronológicamente: el más nuevo queda último):

| Campo | Ejemplo | Significado |
|---|---|---|
| fecha | `20260924` | año, mes, día (24/09/2026) |
| hora | `1600` | hora de inicio |
| robots y modo | `22AH` | 22 robots; modo `AH` (todos giran **antihorario**: solo el motor izquierdo), `HO` (todos giran **horario**: solo el motor derecho), `AL` (**aleatorio**) |
| duración | `60` | duración **nominal** en minutos (la real puede diferir) |

El prefijo indica el tipo de archivo: `R_` registro crudo del sensor, `P_` registro procesado,
`VR_` video original, `VC_` video recortado, `VA_` sesión de análisis, `VP_` trayectorias.

## Flujo de trabajo

1. **Presión**: copiar `R_<código>.csv` a `datos/presion/crudos/` y abrirlo con
   `python software/fsrscope/app.py` (calibración, recorte, gráficos y video sincronizado;
   *Exportar* → `datos/presion/procesados/P_<código>.csv`, se crea al exportar). Sin interfaz:
   `python software/herramientas/procesar_lote.py` procesa todos con la configuración guardada.
2. **Video**: copiar el video a `datos/video/originales/`, recortarlo con VidFetch
   (`python software/vidfetch/app.py`) a `datos/video/recortados/`, analizarlo (escala de tiempo
   3 cuadros/s, **orientación de la escena: rotada 180°**, robot 33 mm, recinto Ø 185/195 mm, escala desde el
   recinto) y guardar la sesión en `sesiones/` y el CSV en `trayectorias/`. Las posiciones salen con
   origen en el centro del recinto (detectado en cada cuadro o marcado a mano), x a la derecha e y hacia
   arriba en la vista del observador. Con una sesión ya guardada, `software/herramientas/reexportar.py` regenera el CSV sin interfaz.
3. **Figuras**: abrir `software/matlab_figuras/figuras.m` en MATLAB (R2020b+, Statistics Toolbox),
   elegir los ensayos en *Ajustes* y correr (F5 todas, Ctrl+Enter una sección). Lee directamente
   `VP_*_robots.csv`, `R_*.csv`, `datos/presion/calibracion.csv` y `datos/video/cortes.json`.
4. **Informes**: compilar `informes/ensayos/informe_ensayos.tex` e `informes/aplicacion/informe_aplicacion.tex`
   (dos pasadas de `pdflatex` o `latexmk -pdf`). Los scripts Python que generaban `informes/*/generado/` y
   las figuras de método se eliminaron el 16/11/2026 (recuperables desde git, commit anterior).

Las dos apps también se pueden usar como `.exe` sin Python: `software/empaquetado/construir.bat`
(detalle en `software/README.md`).

## Notas

- Los videos se graban con una cámara DJI fija sobre la arena, en *time-lapse* (≈3 cuadros por segundo
  real, reproducidos a 29,97 fps). **No están espejados.** El observador mira la arena desde el borde
  superior del video (y = 0 px), así que VidFetch, los informes y FSRScope muestran la imagen **rotada
  180°** (opción *Orientación de la escena: rotada 180°*): x a la derecha del observador, y hacia la pared
  de enfrente, ángulos antihorarios positivos. En el modo `AH` los robots giran en sentido antihorario.
- El registrador del sensor enciende un LED 5 s al comenzar; el video recortado empieza al terminar
  ese pulso, lo que permite sincronizar video y presión.
- El recinto se desliza unos mm sobre la placa durante la primera media hora y la cámara cambia
  levemente de aumento: VidFetch mide el recinto a lo largo del video y usa el centro y la escala de
  cada cuadro.
- Requisitos de Python: `software/vidfetch/requirements.txt` y `software/requirements.txt`.
