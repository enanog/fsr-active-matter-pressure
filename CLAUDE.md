# CLAUDE.md — Contexto de sesiones con Claude

Este archivo documenta las adiciones hechas por Claude al repo, para poder
retomar el contexto en conversaciones futuras (chat, Claude Code, etc.).

## Convención de nombres (vigente)

- `deltaT` — tamaño de ventana temporal, en segundos.
- `deltaG` — diferencia de conductancia `G(t) - G(t - deltaT)` (lo que antes
  se llamaba, incorrectamente, `deltaT`; se corrigió porque lo que se resta
  son valores de `G`, no de tiempo).

## 2026-10-08 (noche) — Recinto: origen en el centro, escala, exportación por robot

**Pedido:** (0,0) en el centro del recinto (Ø int 18,5 cm / ext 19,5 cm — el usuario escribió "r"; son
**diámetros**: con radios el anillo no entra en el VC de 610 px), detección automática con alternativa
manual, exportar todos los datos de un solo robot, informes completos con cómo re-ejecutar todo.

- **`core/arena.py` (nuevo):** máscara HSV del anillo (tono dominante saturado ±12; LEDs/pilas fuera),
  720 rayos con borde subpíxel en S, ajuste de **2 círculos concéntricos** (Kåsa + MAD), `detect_one`
  (~0,12 s/cuadro), `ArenaTrack` (muestras cada `DEFAULT_STEP`=15 cuadros, mediana móvil 5, interp.),
  manual por ≥3 clics (`fit_points`) con opción de seguir el movimiento detectado, `track_video` (grab +
  retrieve), `draw`. Guardado en la sesión `.npz` (`arena` array + meta, versión 3).
- **Hallazgos en los 3 VC:** (1) el anillo **se desliza sobre la placa** 1,5–2,6 × 3,3–4,1 mm (mismo patrón
  los 3 días: baja ~2 mm los primeros 15 min y vuelve entre 15–30 min); la placa no se mueve (correlación de
  fase < 1 px). (2) **La cámara cambia de aumento** en saltos de +0,5 % (24/09 min 18, 25/09 15:00 min 13): la
  placa también se agranda 0,47 % → reenfoque. ⇒ centro y escala por cuadro.
- **Escala:** recinto 0,3233/0,3241/0,3230 mm/px. r_ext/r_int = 1,0545–1,0547 vs 195/185 = 1,0541. Cuerpo del
  robot 101 px (4870 rayos libres) = 32,7 mm. Capas a 75,2 y 42,8 mm → separación 32,5 mm = D. La escala
  vieja (35 mm / 2·47 px = 0,372) estaba **15 % alta** (r_ext del detector = anillo oscuro, no el cuerpo
  ~51 px) ⇒ longitudes y velocidades **−13 %** respecto de los informes anteriores. Diámetro robot por
  defecto: **33 mm**.
- **Perspectiva:** R_c = q99,5(r) = 77,8–78,2 mm vs R_int − D/2 = 76 mm ⇒ κ = 0,972–0,978 (2,5 %). Se reporta,
  no se aplica por defecto (opción `scale_source="perspectiva"`).
- **Export (`kinematics.table`, 34 col.):** x_mm, y_mm (origen centro del recinto del cuadro, y arriba,
  espejo corregido), r_mm, phi_deg, wall_dist_mm (= R_int − r), v{x,y}_mm_s (SG de las posiciones en mm →
  relativas al recinto, incluyen la escala por cuadro), speed, vel_dir, v_rad, v_tan (>0 antihorario),
  θ/ω, px centrados, mm_per_px, xc/yc_video_px, x/y_video_px, mass, ring_cov, status_code, espejo.
  **Cambian nombres**: x_m/speed_m_s → *_mm*. `_info.json` junto a cada CSV. `robot_table`, resumen con
  mean_r, pct_wall_layer (r ≥ R_c − D/2), mean_v_tan, pct_omega_cw, turns.
- **GUI:** grupo "Recinto: origen (0,0) y escala" (detectar, marcar a mano, ajustar, seguir movimiento,
  descartar manual, diámetros, mostrar), combo "Escala desde", "Exportar un robot", "Exportar cada robot".
  Detecta el recinto durante "Analizar video"; sesiones viejas lo miden al cargarse. Overlay en video exportado.
- **`tools/reexportar.py` (nuevo):** sesión → CSV/JSON/resumen/por robot, `--redetectar`, `--guardar-sesion`.
- **`tools/verificar_cinematica.py` (nuevo, solo cv2/numpy/pandas):** panel A = cuadro des-espejado con robots
  redibujados solo desde x_mm/y_mm + recinto + ejes; panel B = ∫v dt en Δ (def. 5 s) vs posición en t+Δ;
  .txt con 4 controles. Resultado en los 3 ensayos: transformación 0,0005 mm; ∫v vs Δpos 10 s mediana
  0,13 mm (2,5–2,8 %); v vs diferencia finita cruda r = 0,96, pendiente 1,05. Pendiente: pruebas físicas
  (regla, flecha/letra para el espejado, velocidad cronometrada).
- **Scripts:** `generar_informe.py` y `comparar_ensayos.py` leen el formato nuevo (y el viejo). Umbral de
  atasco **0,52 mm/s** (= 0,6 × 0,869: mismos episodios). FSRScope `robots.py` acepta speed_mm_s.
- **Datos regenerados (08/10):** 3 sesiones con recinto (medido cada 30 cuadros sobre JPEG q2 extraídos con
  ffmpeg en la PC; `--redetectar` usa el video, paso 15) y 3 VP_ (espejo horizontal, ventana 5, D 33 mm).
  Calidad recalculada: estrictos 265302/217149/241944; episodios 46/33/15.
- **Resultados nuevos:** φ = 0,70 (antes 0,58); capas 75,2/42,8/~11 mm con 12,5/7,3/2,2 robots (87–90 %
  llenas); |v| mediana 0,50/0,56/0,61 mm/s; contrarrotantes en la pared: A 65 vs 52 %, C 75 vs 45 %, **B 57 vs
  58 % (no se cumple)** → hipótesis de rodadura abierta.
- **Pendientes:** medir alturas de pared y robots (κ geométrico); fijar anillo y foco de la cámara; ubicar
  el FSR en φ; el usuario debe revisar que las sesiones 24/09 tenían espejo `no`/ventana 3 (se regeneraron
  con horizontal/5, como los otros dos). Cambios no commiteados (el usuario decide el commit).

## 2026-10-08 — Deriva del giro acumulado θ: diagnóstico y corrección

**Problema (reportado por el usuario: la desrotación del informe no queda quieta):** θ se resolvía solo con
enlaces de 1, 2, 4, 8 y 16 cuadros. Cada paso subestima levemente el giro (~0,8 % en 32 cuadros; el
gradiente de iluminación no gira con el robot) y el error se acumula. Contra la comparación directa de la
huella entre cuadros separados (q ≥ 0,8), θ erraba en mediana 30 / 44 / 30° a 10 min (p90 107–138°) en
24/09, 25/09 12:30 y 25/09 15:00.
- Las comparaciones directas de largo alcance son confiables: cierre en triángulo a 5+5 min p90 < 1°.
- **Corrección (`core/rotation.py`):** `solve_angles` agrega enlaces de 32, 64, 128… muestras hasta todo el
  registro (uno cada L/128 muestras, q ≥ 0,80), rama 2π elegida con la solución del nivel anterior
  (tolerancia 90°), 3 pasadas, pasada robusta (descarta residuos > 15°, conserva lag 1). Sistemas con
  enlaces largos: CG con Jacobi arrancado en la solución previa (10× más rápido que spsolve).
  `solve_angles(sig, long_range=False)` reproduce el método anterior exacto (dif. 3e-12°).
- **Validación con bloques retenidos (77 muestras, enlaces largos solo entre bloques pares, evaluación en
  impares):** a 10 min mediana 0,9 / 0,9 / 0,9°, p90 2,8 / 3,3 / 2,8° (antes 32 / 44 / 29°, p90 112 / 139 / 108°).
- Costo: ~3 s por robot (~1–2 min por video). `kinematics._rotation` cachea θ en el `TrackingResult`
  (cambiar escala de tiempo o ventana no lo recalcula).
- Impacto: ω̄ por robot cambia ≤ 0,6 °/s (~3 %); ningún cambio de signo; siguen 14 de 22 horarios en los 3
  ensayos. θ final cambia en mediana 190–360° (hasta ~6 vueltas en los que más giran).
- Caso conocido: 25/09 12:30 robots 20 y 21 tienen los primeros ~7 s con pasos de baja calidad (q 0,3–0,5,
  saltos de ~95°) sin enlace largo posible: todo su θ queda con desfase constante (ω no se afecta salvo ahí).
- Herramienta `software/vidfetch/tools/verificar_giro.py`: recortes del VC cada 2,5 min, grabado / desgirado
  con θ anterior / con θ nuevo (probada con video sintético de giro conocido; signo: desgirar = rotar −θ).
- Figura `informes/ensayos/figuras/rotacion_deriva.png` (error vs tiempo y vs separación, antes/ahora).
- Sesiones recargadas por el usuario el 08/10: diámetro 33 mm en las 3; **24/09 con espejo `no` y ventana 3**
  (las otras: horizontal, 5) → pendiente confirmar.

## 2026-10-08 — Versionado de sesiones y trayectorias de video
- `.gitignore`: se ignoran solo los videos (`originales/`, `recortados/`, `seguimiento/`, `*.mp4`) y `Videos/`; `.gitkeep` conserva esas carpetas.
- Se versionan `datos/video/sesiones/*.npz` (54–64 MB) y `trayectorias/*.csv` (≤ 56 MB): < 100 MB (límite duro de GitHub); > 50 MB da solo advertencia. Sin Git LFS (no instalado).
- `VP_20262409_1600_22QR_60_robots.csv` había sido sobrescrito con el resumen por robot (22 filas): renombrado a `_resumen.csv` y trayectoria completa regenerada desde `VA_…npz` con `TrackingSession.load → run → to_dataframe` (265 518 filas × 25 col.); giro total y rapidez media coinciden con el resumen (|Δv| < 1e-5 px/s).

## 2026-10-08 — Material didáctico: detección + v + ω

- `informes/aplicacion/deteccion_cinematica.xlsx`: rehace con fórmulas (43k, 0 errores en LibreOffice) la detección, v y ω
  del robot 3, ensayo `20262409_1600`, cuadros 6034/6035 (5998–6092 para v y ω). Hojas: Parametros (nombres definidos),
  Img_analisis (gris ×0,511), Filtro_anillo (máscaras 51×51, R en un punto), Mapa_R (μ, R y centroide iterado ≈ trackpy),
  Img_completa/Img_6035, Cobertura (360 rayos × r 37–44, vecino más cercano = cv2.warpPolar flag 0), Firma_6034/6035,
  Giro (c(Δ) cada 0,1°, selector firmas calculadas/app), Velocidad, Rotacion. Builder: no versionado (scratch de la sesión).
- Verificado: R = 24 robot / 14 hueco; cobertura 0,856 / 0,672 (= Python sobre el mismo cuadro); vx y ω SG = app
  (dif < 1e-3 px/s, < 0,01 °/s); giro con firmas de la app = rel_angle −4,07° exacto.
- Los cuadros redecodificados (OpenCV Linux) difieren levemente de los que vio la app en Windows: CSV ring_cov 0,847 vs
  0,856, firmas ±0,09, giro 3,9° vs 4,07°. No es error de método.
- Centroide simple sobre R converge a ~1,4 px del de trackpy (trackpy filtra pasa-banda antes).
- Doc Claude «Detección de robots y cálculo de velocidad y velocidad angular» (artifact 16388c95…) explica lo mismo con
  figuras `informes/aplicacion/figuras/metodo/f1–f8` y un diagrama del recorrido.

## 2026-10-08 — FSRScope: app de análisis de presión con video sincronizado

**Reemplaza** `software/analisis_presion/procesar_presion_ventanas.py` (borrado; la planilla pasó a
`software/fsrscope/docs/`). Ubicación `software/fsrscope/` (`main.py` GUI, `procesar_lote.py` CLI,
`core/` sin GUI, `gui/` PySide6 + **pyqtgraph** — elegido sobre matplotlib por redibujar series de
80k puntos a ~30 Hz con cursor/ventana móvil; export PNG/SVG/CSV por clic derecho).

- `core/`: `paths` (repo, códigos, R_/VC_/VR_/VP_), `settings` (dataclasses + JSON por ensayo en
  `datos/presion/config/<código>.json`), `log_io` (todos los formatos de log; unidades de tiempo
  auto; filas basura con tiempo absurdo descartadas por mediana móvil; filas SYNC fuera; t0 = primera
  fila con tiempo, misma referencia que el LED), `signal` (K, remuestreo, saturación ADC≥FS o
  CLIPSAT==N, máscara recorte/exclusiones/saturadas/t_now), `stats` (asimetría y curtosis insesgadas
  vs ΔT, supervivencia, histogramas), `robots` (VP_ → mediana/p90 |v|, posiciones), `video`
  (grab para saltos ≤24 cuadros, seek si no; verificado exacto contra lectura secuencial en VC real),
  `export` (columnas elegibles/ordenables; default = formato histórico), `session` (TrialData).
- **Calibración automática por archivo:** K = mediana(G/ADC) que logueó el firmware → R_FB equivalente.
  Detectado: 24/08 = 12 kΩ, 27/08 = K 0.6299 (≈6.8 kΩ con V_EXC actual, raro), 24/09 = 5 kΩ,
  25/09 = 1 kΩ. Modo manual disponible.
- ΔG con máscara: NaN si algún extremo cae fuera del recorte o en tramo excluido.
- Sincronía: t_sensor = desfase + cuadro/f_r; desfase auto = fin del LED (20.70 / 48.15 / 14.40 s),
  f_r = 3. VC dura 11–27 s menos que el registro tras el desfase (normal: el registro sigue).
- En vivo: gráficos de tiempo hasta el cursor con ventana móvil; estadística acumulada hasta t
  (hilo aparte, 1 Hz al reproducir) sobre la del ensayo completo en gris.
- Config se autoguarda solo si cambió (al cambiar de ensayo/cerrar) y siempre al exportar.
- Verificado: P_ nuevos = P_ existentes para 24/09 y 25/09 (G dif < 1.3e-4 µS, asimetría < 2e-5).

**Hallazgo:** los `P_` de **agosto** (24/08 ×3, 27/08) en `datos/presion/procesados/` se generaron con
R_FB = 5 kΩ (K 0.8563) pero el firmware de esas corridas usaba 12 kΩ (K 0.3568) → **G ×2.4 alta**
(×1.36 en 27/08). Asimetría/curtosis no cambian (invariantes de escala); sí cambian ejes de G,
histogramas y supervivencia (figuras del póster). No se regeneraron.

**Pendientes:**
- Decidir si regenerar los P_ de agosto (`procesar_lote.py 202608`) y rehacer figuras de LabPlotter.
- Instalar `pyqtgraph` en la PC (`pip install -r software/fsrscope/requirements.txt`) y probar la GUI
  con los VC reales (solo se probó offscreen con video sintético).
- R_20260824_1400_00_07 (0 robots, sin modo) no entra en la lista: abrir con «Abrir registro…».

## 2026-10-08 — Reorganización del repositorio (estructura vigente)

Estructura por tipo de dato (ver `README.md` de la raíz). Rutas viejas → nuevas (las secciones
más abajo usan las viejas):

| Antes | Ahora |
|---|---|
| `Placa/` | `hardware/pcb/` |
| `Codigo/fsr_*/` (Arduino) | `hardware/firmware/fsr_*/` |
| `Simulacion/` | `hardware/simulacion/` |
| `Codigo/VidFetch/` (app) | `software/vidfetch/` |
| `Codigo/VidFetch/informe/*.py` | `software/analisis_video/` (`generar_informe.py`, `comparar_ensayos.py`) |
| `Codigo/Analisis/` | `software/analisis_presion/` → reemplazado por `software/fsrscope/` |
| `Mediciones/R_*.csv` | `datos/presion/crudos/` |
| `Mediciones/Procesado/P_*.csv` | `datos/presion/procesados/` |
| `Mediciones/` vacío / sala vacía / `Procesado/20260827_1534_26_30.csv` | `datos/presion/referencia/` |
| `Videos/VR_*`, `VC_*` | `datos/video/originales/`, `datos/video/recortados/` |
| `Videos/Datos/VA_*`, `VP_*` | `datos/video/sesiones/`, `datos/video/trayectorias/` |
| `Codigo/VidFetch/informe/` (LaTeX) | `informes/{comun,aplicacion,ensayos}/` |
| `Poster/` | `difusion/poster_rafa2026/` (sin .aux/.log/.synctex) |

- `.gitignore`: `datos/video/**` (salvo README), intermedios de LaTeX, `__pycache__`, `*.raw`.
- Informe de ensayos: texto a mano en `informes/ensayos/secciones/`, generado en
  `informes/ensayos/generado/` (`<código>/`, `comparacion/`, `lista_ensayos.tex`). Scripts con
  rutas por defecto relativas al repo (`--informe-dir` = `informes/ensayos`, `--mediciones` =
  `datos/presion/crudos`). Correr desde la raíz.
- LabPlotter (`difusion/poster_rafa2026/figures/*.json`): solo se actualizó la ruta de
  `Medicion Vacio.csv`; las referencias a `Medicion 25/26/27 Robots 30 Min.csv` ya estaban rotas
  antes (esos archivos se renombraron a `P_…` en septiembre).

## 2026-10-08 — Video espejado y análisis de los 3 ensayos

**Video espejado:** los videos de la cámara fija (DJI, cenital) están espejados respecto del eje vertical (confirmado por el
usuario: en modo `QR` todos los robots están programados para girar a la derecha). Nueva opción de
VidFetch `KinematicsParams.mirror` = `no` | `horizontal` | `vertical` (combo *Video espejado* en
*Seguimiento*, se guarda en la sesión). El análisis sigue en coordenadas de imagen (superposición
correcta); solo las exportaciones se pasan a la escena real: `x → W − x`, `vx → −vx`, `θ, ω → −θ, −ω`,
dirección recalculada; columna `espejo` en el CSV; `x_video_px`/`y_video_px` quedan en imagen.
`generar_informe.py` des-espeja para dibujar la captura. **Para estos videos: horizontal.**

**Datos:** las 3 sesiones `VA_*.npz` se recargaron, el seguimiento reprodujo exactamente los CSV del
usuario (dif. relativa < 1e-4, estados idénticos) y se re-exportaron con espejado horizontal
(`datos/video/trayectorias/VP_*_robots.csv`); las sesiones guardan `mirror` y la nueva ruta del video.
Anclas manuales 0/2/1 (al final); advertencias < 0,13 % de puntos (un obstáculo cruza la escena).
Ventana Savitzky–Golay 5 cuadros; r_ext = 47 px → s = 0,372 mm/px.

**Resultados clave (verificados con un cálculo independiente):**
- Reproducible: |v| mediana 0,58/0,64/0,70 mm/s, p95 ≈ 3,5–3,6; |ω| mediana 3,0–3,8 °/s; MSD α ≈ 1,3;
  φ ≈ 0,58; tres capas concéntricas en r/R_c ≈ 0,14 / 0,55 / 0,95.
- Giro (corregido): 14 de 22 robots giran neto a la derecha (horario, como programado) en los 3
  ensayos; ω media con signo −2,5 a −3,3 °/s; circulación colectiva horaria débil (Φ ≈ −0,2).
- Los 8 que contrarrotan: |ω̄| ≈ 2 °/s (vs 5–6), giran a la derecha 40–47 % del tiempo y pasan
  58–68 % del tiempo contra la pared (vs 47–52 %) → hipótesis: ruedan por el interior de la pared
  (orbitar horario apoyado en la pared ⇒ giro propio antihorario).
- Atascos (p90 |v| suavizado 30 s < 0,6 mm/s ≥ 20 s): 24/09 3 (17 %, uno de 382 s en min 45–51);
  25/09 12:30 1 (106 s); 25/09 15:00 4 (3,8 min).
- Sincronía: el VC empieza al FIN del pulso LED de 5 s del registrador; t_video = t_sensor −
  t_LED,fin (20,7 / 48,15 / 14,4 s); correlación cruzada lo confirma (±0,5 s) y da f_r = 3,000 ± 0,003.
- Sensor: 24/09 G mediana 876 µS en atascos vs 0,011 fuera; la saturación de 382 s coincide con el
  atasco de min 45–51 (empieza ~13 s después). 25/09 15:00 ×23; 25/09 12:30 sin relación.

**Pendientes:**
- Identificar robots entre videos (marcas) para confirmar si los que contrarrotan son siempre los
  mismos o los de la pared.
- Ubicación del FSR en la arena.
- `D:\Documentos\Personal\video_editor` quedó desactualizado (la copia vigente es `software/vidfetch`).

## 2026-10-07 — VidFetch (seguimiento de robots en video) y escala de tiempo de los time-lapse

**Ubicación:** `Codigo/VidFetch/` (app PySide6: `main.py`, `core/` lógica, `gui/` interfaz;
copia espejo en `D:\Documentos\Personal\video_editor`). Informe LaTeX genérico en
`Codigo/VidFetch/informe/`.

**Qué hace la app:** abre un video, recorta tiempo/rectángulo, detecta los robots (filtro de anillo
+ `trackpy.locate` + validación por cobertura del anillo), sigue `N` robots fijos (asignación
húngara + predicción, anclas manuales, interpolación de huecos), y calcula por robot `v` (módulo y
dirección), orientación acumulada `θ` (firmas polares de Fourier, θ=0 en el primer cuadro del
tramo) y `ω`. Exporta un único CSV con todos los robots (formato largo o ancho), un resumen por
robot, video anotado y la sesión `.npz`. Diámetro real del robot: **35 mm** (escala px→m).

**Videos (`Videos/`):** `VR_<código>.MP4` = original DJI 4K; `VC_<código>.MP4` = recorte a la
arena (~610×610 px) que es lo que se analiza. `<código>` = el mismo de `Mediciones/R_<código>.csv`.

**Escala de tiempo (time-lapse):** los videos se graban a `f_r` ≈ 3 cuadros por segundo real y se
reproducen a `f_a` = 29.97 fps (×10). Todo el análisis trabaja en cuadros; `t = n/f_r`,
`v ∝ f_r`, `ω ∝ f_r`. Posiciones y `θ` no dependen de `f_r`.
- App: pestaña Original → grupo "Escala de tiempo" (casilla time-lapse + "N cuadros = 1 s real",
  default 3; botón "Calcular desde la duración real…"). Cambiarla recalcula solo la cinemática.
- Informe: `\CuadrosPorSegundo{3}` en `informe/config.tex`; `generar_informe.py --cuadros-por-segundo F`
  reescala un CSV exportado con otra escala sin re-analizar.
- **Verificación de `f_r` con el registro del sensor** (duración `R_<código>.csv` vs cuadros `VR`):
  `20262409_1600`: 12105 cuadros / 4055.1 s = 2.985; `20262509_1230`: 9907 / 3368.4 s = 2.941;
  `20262509_1500`: 11038 / 3699.5 s = 2.984 → consistente con time-lapse ×10 (`f_r` = 2.997).
- **El `_60` del nombre es nominal:** duraciones reales ≈ 67.3 / 55.1 / 61.4 min. Usar 60 min daría
  `f_r` = 3.36 / 2.75 / 3.07 (errores de −8 % a +12 % en v y ω). No usarlo para calibrar.

**Informe LaTeX:** `main.tex` incluye `secciones/videos.tex` (videos, base de tiempo, tablas de
`f_r`), `secciones/metodologia.tex`, `secciones/procedimiento.tex` (paso a paso + columnas del CSV)
y `videos/lista_videos.tex` (generado). Para agregar un ensayo:
`python informe/generar_informe.py <export.csv> --video <VC_...MP4> --nombre <código>` y compilar
`main.tex` dos veces. (Reemplazado el 2026-10-08 por dos informes en `informes/`.)

**Pendientes / conocidos:**
- Correr los análisis de los 3 `VC_` con `f_r` = 3 (o 2.997) y generar sus secciones.
- CSV o `.npz` exportados antes de 2026-10-07 tienen tiempos a 29.97 fps (v y ω ×10): reescalar con
  `--cuadros-por-segundo 3` o volver a exportar.
- Tracker: tras un hueco largo, un candidato con umbral relajado puede ser falso positivo cerca de
  una predicción errónea (visto en un robot, ~90 px de error en 8 puntos). Para estadística, filtrar
  `status == detectado`.
- `Videos/README.md` está desactualizado (lista `DJI_0196…`).
- El código de fecha de los archivos es año-día-mes (`20262409` = 24/09), no `AAAAMMDD`.

## 2026-09-24 — Saturación del ADC en `R_20262409_1600_23QR_60.csv` y ajuste de `R_FEEDBACK`

**Modelo del front-end (transimpedancia):** `V_out = V_EXC * R_FEEDBACK / R_FSR`
(la FSR entrega una corriente `I = V_EXC/R_FSR` que el feedback convierte en
tensión). El ADC (10 bits, `V_REF = 3.3 V`) satura en `V_out = V_REF`, o sea
cuando la resistencia de la FSR cae por debajo de:

```
R_floor = V_EXC * R_FEEDBACK / V_REF
```

**Hallazgo:** en este archivo, la columna `R` (que el firmware ya calcula a
partir del ADC) tiene un piso duro en **1141.5 Ω** durante 7367 filas — el
firmware loguea directamente contadores de clipping (`CLIP0`, `CLIPSAT` sobre
`N` muestras promediadas por fila). Ese piso coincide *exacto* con
`R_floor` para `R_FEEDBACK = 5000 Ω` (dos resistencias de 10 kΩ en paralelo,
la config actual de hardware según el usuario) — **no con los 12000 Ω** que
tenía hardcodeados `procesar_presion_ventanas.py` hasta ahora. **Corregido:**
`R_FEEDBACK = 5000.0` en el script (commit 2026-09-24), verificado contra
este dato. Si el hardware vuelve a cambiar, hay que re-verificar del mismo
modo (el piso de saturación en los datos es la forma más confiable de
calibrar `R_FEEDBACK` a posteriori, más confiable que fiarse de lo que se
recuerda haber armado en la placa).

**Extensión de la saturación en esta medición:** 4 episodios de saturación
plena (`CLIPSAT == N`), el más largo de **~382 s (6.4 min) sostenidos sin
ninguna variación** en `R` (siempre clavado en 1141.5 Ω, ni un conteo de
ruido de por medio) entre t≈3015 s y t≈3397 s, sobre un total de 67.6 min
grabados (~6.3 min del total, 9.3%, con algo de saturación). Que el valor
sea *constante* durante 6+ minutos (no oscilando cerca del umbral) indica
que la señal real estuvo bien adentro de la zona de saturación, no apenas
por encima del piso — la verdadera R durante el atasco pudo haber sido
sensiblemente menor a 1141.5 Ω; los datos clippeados no permiten saber
cuánto.

**Recomendación sobre bajar `R_FEEDBACK`:** como `R_floor` escala
linealmente con `R_FEEDBACK`, para candidatos:

| `R_FEEDBACK` | `R_floor` | Reducción vs. actual (5 kΩ) |
|---|---|---|
| 10 kΩ | 2283 Ω | ×0.5 (peor) |
| 5 kΩ (actual) | 1141.5 Ω | — |
| 3k3 | 753 Ω | ×1.52 |
| **2k2** | **502 Ω** | **×2.27** |
| 1 kΩ | 228 Ω | ×5 |
| 680 Ω | 155 Ω | ×7.35 |

2k2 baja el piso a ~502 Ω (más del doble de margen). Dado que la
saturación fue profunda y sostenida (no marginal), **2k2 reduce el riesgo
pero no lo garantiza** — si el atasco real llevó la FSR bien por debajo de
502 Ω, va a volver a saturar, aunque con menor duración/frecuencia que
ahora. No hay forma de calcular el `R_FEEDBACK` óptimo sin un dato no
censurado del peor caso (banco de pruebas con carga máxima conocida, o
repetir la medición con 2k2 y revisar `CLIPSAT` de nuevo). Contrapartida de
bajar mucho `R_FEEDBACK`: menor ganancia en el otro extremo (fuerza
baja/basal). Simulando el efecto de bajar a 1k sobre este mismo archivo:
hoy (5k) el 47% de las filas ya lee ≥1 cuenta de ADC en promedio
(resoluble sin depender del oversampling); con 1k, de ese 47% un 11.5%
(~5.4% del total) caería por debajo de 1 cuenta. Esa franja degradada
corresponde a `R_FSR` ≈ 230 kΩ–1.2 MΩ (contacto muy leve, casi sin
fuerza) — **no** al rango donde ocurre el atasco (unos pocos kΩ o menos),
que se mantiene bien resuelto. El circuito no comprime logarítmicamente
(es transimpedancia lineal, `V_out = V_EXC·R_FEEDBACK/R_FSR`), así que
bajar `R_FEEDBACK` sí compromete la resolución en el extremo de fuerza
baja en la misma proporción que gana margen arriba — la relación
logarítmica R_FSR-vs-fuerza no da protección extra ahí.

**Decisión final (2026-09-24):** el usuario cambió la resistencia física a
**1 kΩ** (`R_FEEDBACK = 1000.0`, ya actualizado en el script). Validado
empíricamente: presionando el sensor a mano al máximo, con 1k **no
satura**; con 2k2 **sí satura**. Esto acota la `R_FSR` máxima alcanzable a
mano en algún punto entre 228 Ω (piso con 1k) y 502 Ω (piso con 2k2) —
consistente con el modelo. Con 1k, la franja de baja resolución queda en
contacto casi nulo (ver párrafo anterior), fuera del rango de interés para
la dinámica de atascos.

## 2026-09-24 — Convención de nombres de archivos de medición

Los archivos de medición se guardan directamente en `Mediciones/` (sin
subcarpetas por fecha — el usuario aplanó esa estructura), con el código
**`AAAAMMDD_HHMM_XXYY_TT.csv`**: año, mes, día, hora, minuto, cantidad de
robots (`XX`, 2 dígitos) + modo de movimiento (`YY`, 1-2 letras: `R` =
random, `QR` = todos girando a la derecha, `QZ` = todos girando a la
izquierda — **interpretación de Claude a partir del ejemplo dado, a
confirmar**), y minutos de medición (`TT`). Ejemplos dados por el usuario:
`23QR`, `23QZ`, `23R` (23 robots, cada uno de los 3 modos).

Los crudos llevan `R_` adelante del código (`R_AAAAMMDD_HHMM_XXYY_TT.csv`)
y los procesados `P_` (`P_AAAAMMDD_HHMM_XXYY_TT.csv`), generados siempre en
`Mediciones/Procesado/`. El script acepta el código con o sin `R_` (para no
romper si algún crudo se guarda sin el prefijo), pero el DAQ debería
guardarlos ya con `R_`.

**Importante — cambio de formato:** el código anterior no tenía el campo de
modo (`AAAAMMDD_hhmm_XX_ll`, sin letras después de los robots). El script
ahora **exige** el modo (`XXYY`, con letra) para reconocer un archivo como
válido — los 5 crudos ya existentes (`R_20260824_1400_00_07.csv`,
`R_20260824_1430_25_30.csv`, `R_20260824_1530_26_30.csv`,
`R_20260824_1600_27_30.csv`, `R_20260827_1534_26_30.csv`) usan el formato
viejo, **no tienen el modo registrado** y por lo tanto el script ya **no
los detecta** hasta que se rebauticen con el modo correspondiente (ej.
`R_20260824_1430_25QR_30.csv` si esa corrida fue "todos a la derecha").
Falta que el usuario confirme el modo de cada uno para poder renombrarlos.

## 2026-08-31 — Script de post-procesamiento

**Ubicación:** `Codigo/Analisis/procesar_presion_ventanas.py`

**Qué hace (actualizado 2026-09-24):** recorre **recursivamente** toda la
carpeta `Mediciones/` (cualquier subcarpeta, salvo `Procesado`, que es la
salida y siempre se excluye) y procesa **solo** los archivos cuyo nombre
matchea el código `AAAAMMDD_HHMM_XXYY_TT` (con o sin prefijo `R_`) —
cualquier otro archivo suelto, o uno con el formato viejo sin modo de
movimiento, se ignora en silencio en vez de tirar error. Acepta
`.csv` y `.json` (varios logs viejos son ".json" con contenido CSV plano).
El matching de columnas (`TIME_COL`, `ADC_COL`) es **insensible a
mayúsculas/minúsculas**, porque distintas versiones de log usan headers
distintos (`adc_raw` vs `ADC_RAW`). Para cada archivo detectado genera **un
único CSV** llamado `P_<codigo>.csv` en `Mediciones/Procesado/<misma
subcarpeta relativa>/` (así los resultados de distintas carpetas nunca se
pisan y quedan trazables al origen). No genera ninguna imagen/PNG — solo
CSV. La serie se remuestrea antes a una grilla uniforme de 50 ms
(`STEP_S`) por interpolación lineal.

Columnas del CSV de salida (longitudes distintas → las más cortas se
rellenan con NaN al final para mantener el archivo rectangular):

- `tiempo` — tiempo remuestreado, con el t0 original restado (arranca en 0).
- `ADC_RAW` — ADC crudo interpolado a la grilla uniforme.
- `G` — conductancia [uS] recalculada desde `ADC_RAW` con la calibración del
  front-end (`V_REF`, `V_EXC`, `R_FEEDBACK`, `ADC_FS`, igual que en
  `Codigo/fsr_single_read/fsr_single_read.ino`; no se usa el `G_uS` que ya
  trae el log, para poder recalibrar reprocesando).
- `deltaG_2.5s` (nombre dinámico según `DELTAG_FIXED_S`) — serie completa
  `deltaG(t) = G(t) - G(t - DELTAG_FIXED_S)` para UN tamaño de ventana fijo,
  fácilmente cambiable (`DELTAG_FIXED_S = 2.5` por defecto). Misma longitud
  que `tiempo`/`ADC_RAW`/`G`.
- `deltaT`, `skewness` — barrido del tamaño de ventana desde 50 ms hasta 15 s
  en pasos de 50 ms (300 valores por defecto, controlado por `STEP_S` y
  `DELTA_MAX_S`). Para cada `deltaT`, se arma la serie
  `deltaG(t) = G(t) - G(t-deltaT)` sobre toda la corrida y `skewness` es su
  asimetría muestral total (Fisher-Pearson, sin sesgo, sin dependencia de
  scipy) — un valor por fila de `deltaT` (columna más corta que `tiempo`,
  rellena con NaN).
- `G_surv`, `P_G_geq` — función de supervivencia empírica de `G` (no de
  deltaG): `G_surv` ordenado ascendente, `P_G_geq(g) = P(G >= g)`. Pensada
  para graficar como en la figura de referencia (eje X = G, eje Y =
  probabilidad, escala log).

**Config editable al inicio del script:** `MEDICIONES_ROOT` (carpeta raíz a
recorrer recursivamente), `INPUT_EXTS`, `EXCLUDE_DIRNAMES`, `CODE_RE` /
`RAW_PREFIX` / `PROC_PREFIX` (convención de nombres), `OUTPUT_DIR`,
`TIME_COL`/`ADC_COL`/`TIME_UNITS` (mapeo de columnas de entrada, matching
case-insensitive), constantes de calibración, `STEP_S`, `DELTA_MAX_S`,
`DELTAG_FIXED_S`.

**Validado con:** árbol sintético con el formato nuevo (`23QR`, `23QZ`,
`23R`, con y sin prefijo `R_`, headers en mayúscula/minúscula mezclados) y
confirmando que un archivo con el formato viejo (sin modo) ya no matchea.
Ejecutado también contra los 5 crudos reales antes de este cambio de
formato (ver historial arriba) — sigue corriendo sin errores end-to-end,
solo cambia qué nombres reconoce.

**Pendiente / a decidir en el futuro:** si conviene superponer las curvas
de supervivencia de distintos archivos (distinta cantidad de robots) en un
único gráfico comparativo, como en la figura de referencia (que muestra
varias curvas para distintos `N_tot`).

## 2026-08-31 — Hoja de cálculo con la metodología (G / deltaG / skewness / kurtosis / supervivencia)

**Ubicación:** `Codigo/Analisis/Metodologia_calculo_presion.xlsx`

**Qué es:** un workbook pedagógico para mostrar, con **fórmulas de Excel en
vivo** (no valores pegados), cómo se calcula cada magnitud del pipeline de
Python. Usa una muestra real de 1500 filas (~75 s) de
`Mediciones/24-08-2026/Medicion 25 Robots 30 Min.json`, incluida dentro del
propio archivo (hoja `Datos`), no como referencia externa.

Hojas (en este orden):
- **Notas** — explicación completa de la metodología (para leer primero).
- **Config** — constantes de calibración (`V_REF`, `V_EXC`, `R_FEEDBACK`,
  `ADC_FS`, `K_G_US`, `STEP_S`, `DELTA_MAX_S`, `N_MUESTRAS`, `N_VENTANA`).
- **Datos** — `timestamp_original_s` y `ADC_RAW` (input crudo) + `tiempo`
  (con t0 restado) y `G` (`=ADC_RAW*K_G_US`), como fórmulas.
- **Ejemplo_ventana** — un `deltaT` editable (celda amarilla, default 2.5 s)
  y, para ese valor, la columna completa `deltaG(t) = G(t) - G(t-deltaT)`
  fila por fila, más `SKEW()`/`KURT()` de Excel calculadas en vivo sobre esa
  columna.
- **Barrido_deltaT** — 300 filas (una por cada `deltaT` de 50 ms a 15 s),
  con `skewness` y `kurtosis` calculadas cada una con una fórmula matricial
  que arma `deltaG` al vuelo vía `OFFSET` (sin 300 columnas auxiliares) +
  gráfico de ambas curvas vs. `deltaT`.
- **Supervivencia** — `G_ordenado = SMALL(G, k)` y `P_G_geq = (N-k+1)/N`,
  con gráfico (eje X = G, eje Y = P(G≥g) en escala log), igual formato que
  la figura de referencia que pasó el usuario.

**Verificación:** los valores de skewness/kurtosis de `Barrido_deltaT` y
`Ejemplo_ventana` se contrastaron contra el mismo cálculo hecho en Python
(numpy, fórmula insesgada de Fisher-Pearson) — coinciden en las primeras 6
cifras significativas. Recalculado con LibreOffice (`recalc.py`): 11705
fórmulas, 0 errores.

**Simplificación deliberada:** a diferencia del script Python, esta hoja no
remuestrea a grilla uniforme por interpolación (usa los tiempos crudos tal
cual, ya a ~50 ms) y usa siempre los mismos `N_VENTANA=1200` puntos para
cada `deltaT` (en vez de aprovechar los `~1500-lag` disponibles), para que
las 300 fórmulas matriciales sean todas del mismo tamaño. Documentado en la
hoja Notas. Para el dataset completo (~36000 filas), seguir usando
`procesar_presion_ventanas.py`.
