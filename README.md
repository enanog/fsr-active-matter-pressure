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
├── software/
│   ├── vidfetch/             app de escritorio: recorte de video y seguimiento de robots
│   ├── analisis_video/       scripts que generan el informe de ensayos a partir de los CSV de VidFetch
│   └── fsrscope/             app de análisis de presión (G, ΔG, asimetría, supervivencia) con video sincronizado
├── datos/
│   ├── presion/
│   │   ├── crudos/           R_<código>.csv  registros del sensor (20 Hz)
│   │   ├── procesados/       P_<código>.csv  salida de FSRScope
│   │   ├── config/           <código>.json   parámetros de FSRScope por ensayo
│   │   └── referencia/       mediciones sin robots / de calibración
│   └── video/                videos no versionados (pendrive); sesiones y CSV sí
│       ├── originales/       VR_<código>.MP4  video original de la cámara, 4K
│       ├── recortados/       VC_<código>.MP4  recorte a la arena (lo que se analiza)
│       ├── seguimiento/      VS_<código>_seguimiento.mp4  video con los robots marcados
│       ├── sesiones/         VA_<código>_analisis.npz  sesiones de VidFetch
│       └── trayectorias/     VP_<código>_robots.csv    posiciones, velocidades y giros exportados
├── informes/
│   ├── comun/                preámbulo y configuración LaTeX compartidos
│   ├── aplicacion/           informe de la app VidFetch (uso, librerías, código)
│   └── ensayos/              informe de resultados de los ensayos filmados
└── difusion/
    └── poster_rafa2026/      póster y resumen de la RAFA 2026
```

## Código de ensayo

Todos los archivos de un mismo ensayo comparten el código `AAAADDMM_HHMM_XXYY_TT`:

| Campo | Ejemplo | Significado |
|---|---|---|
| fecha | `20262409` | año, día, mes (24/09/2026) |
| hora | `1600` | hora de inicio |
| robots y modo | `22QR` | 22 robots; modo `R` (aleatorio), `QR` (todos giran a la derecha), `QZ` (a la izquierda) |
| duración | `60` | duración **nominal** en minutos (la real puede diferir) |

El prefijo indica el tipo de archivo: `R_` registro crudo del sensor, `P_` registro procesado,
`VR_` video original, `VC_` video recortado, `VA_` sesión de análisis, `VP_` trayectorias.

## Flujo de trabajo

1. **Presión**: copiar `R_<código>.csv` a `datos/presion/crudos/` y abrirlo con
   `python software/fsrscope/main.py` (calibración, recorte, gráficos y video sincronizado;
   *Exportar* → `datos/presion/procesados/P_<código>.csv`). Sin interfaz:
   `python software/fsrscope/procesar_lote.py` procesa todos con la configuración guardada.
2. **Video**: copiar el video a `datos/video/originales/`, recortarlo con VidFetch
   (`python software/vidfetch/main.py`) a `datos/video/recortados/`, analizarlo (escala de tiempo
   3 cuadros/s, **video espejado: horizontal**, robot 33 mm, recinto Ø 185/195 mm, escala desde el
   recinto) y guardar la sesión en `sesiones/` y el CSV en `trayectorias/`. Las posiciones salen con
   origen en el centro del recinto (detectado en cada cuadro o marcado a mano), x a la derecha e y hacia
   arriba. Con una sesión ya guardada, `software/vidfetch/tools/reexportar.py` regenera el CSV sin interfaz.
3. **Informes**: desde la raíz,
   ```
   python software/analisis_video/generar_informe.py datos/video/trayectorias/VP_<código>_robots.csv --video datos/video/recortados/VC_<código>.MP4 --nombre <código>
   python software/analisis_video/comparar_ensayos.py "datos/video/trayectorias/VP_*_robots.csv"
   ```
   y compilar `informes/ensayos/informe_ensayos.tex` e `informes/aplicacion/informe_aplicacion.tex`
   (dos pasadas de `pdflatex` o `latexmk -pdf`).

## Notas

- Los videos se graban con una cámara DJI fija sobre la arena, en *time-lapse* (≈3 cuadros por segundo real, reproducidos a 29,97 fps) y
  están **espejados** respecto del eje vertical: hay que indicarlo en VidFetch para que los giros
  salgan con el sentido real.
- El registrador del sensor enciende un LED 5 s al comenzar; el video recortado empieza al terminar
  ese pulso, lo que permite sincronizar video y presión.
- El recinto se desliza unos mm sobre la placa durante la primera media hora y la cámara cambia
  levemente de aumento: VidFetch mide el recinto a lo largo del video y usa el centro y la escala de
  cada cuadro.
- Requisitos de Python: `software/vidfetch/requirements.txt` y `software/fsrscope/requirements.txt`.
