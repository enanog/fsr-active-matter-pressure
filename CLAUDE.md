# CLAUDE.md — Contexto de sesiones con Claude

Este archivo documenta las adiciones hechas por Claude al repo, para poder
retomar el contexto en conversaciones futuras (chat, Claude Code, etc.).

## Convención de nombres (vigente)

- Código de ensayo `AAAAMMDD_HHMM_NNMM_TT`: fecha (ordena cronológicamente), hora, robots + modo, minutos nominales.
- **Modos (desde 2026-11-12):** `AH` = todos giran **antihorario** (solo motor izquierdo), `HO` = todos giran
  **horario** (solo motor derecho; reservado), `AL` = **aleatorio**. Antes `QR` y `QL` (los dos eran antihorario:
  mismo modo) → `AH`; `R` → `AL`. Las secciones históricas de abajo conservan `QR`/`QL`/`R` en el texto (los
  códigos de archivo ya están actualizados).

- `deltaT` — tamaño de ventana temporal, en segundos.
- `deltaG` — diferencia de conductancia `G(t) - G(t - deltaT)` (lo que antes
  se llamaba, incorrectamente, `deltaT`; se corrigió porque lo que se resta
  son valores de `G`, no de tiempo).

## 2026-11-24 — `figuras_seleccion.m` → `software/matlab/jamming_figures.m` (inglés, conjuntos, ajustes por figura)

- Renombrado (mv, sin copia vieja) y reescrito **todo en inglés**: variables, comentarios, consola y textos de las figuras
  (ejes, títulos, leyendas; archivos `V_distribution`, `V_ccdf[_normalized]`, `energy_distribution…`, `occupancy`,
  `G_survival`, `dG_skewness_vs_dT`, `dG_histogram`, `hist2d_V_G_<norm>`, `jam_G_survival`, `jam_G_quantiles`,
  `jam_times_<tc_type>`, `free_times`). Las entradas de abajo usan los nombres viejos (`umbral_tipo` → `threshold_type`
  'manual'|'relative', `mostrar_cortos` → `show_short`, `G_bajo_piso` 'cero' → `G_below_floor` 'zero', etc.).
- Arriba: `trial_sets` (random_removing_robots, counterclockwise_22, random_22, all_since_oct30) + `trial_set` (nombre,
  lista de códigos o {} = elegir); duración, guardado y ajustes compartidos (piso de G, ventanas de ΔG, clasificación
  atasco/libre). **Cada sección de figura empieza con sus propios ajustes** (`% ---- settings ----`).
- **Carga con `_conjunto.csv` primero:** `read_positions = false` → `cargar_datos(..., false)`; la fig. 4 (ocupación) lee los
  `_robots.csv` solo cuando hace falta (`E_pos`, cacheado por pedido).
- DATA arma `T` (campos en inglés: code, label, mode, mode_name, t, V, nf, v2, w2, N, x, y, ts, G, G_frame, step, offset,
  K…) desde `E_raw` (salida de cargar_datos, cacheada). Umbral por ensayo `u_thr` y `Vs` se calculan en DATA (la fig. 8
  dibuja u_thr de cada ensayo). `estados` recibe un struct con los nombres que espera.
- Fig. 2: `normalize_V` (V/⟨V⟩ o V [mm/s]).
- Fig. 3 sin masa (pedido): E/m = N⟨½v²⟩ y N⟨½kR²ω²⟩ [mm²/s²]. Error previo: al borrar `mass_g` quedó `factor` sin definir
  y MATLAB llamó a la función `factor`. Renombrados `values` → `bin_values`, `edges` → `edges_V1` (también son funciones).
- `cargar_datos.m`: `leyenda_por_modo(ax, idioma)`, `'en'` → encabezados COUNTERCLOCKWISE/CLOCKWISE/RANDOM (por defecto
  español; `figuras.m` sin cambios).
- Verificado: parser Octave 8.4 (ambos); armado de `T` y bloque de tiempos con datos sintéticos (mismos Tc/Tall/Tb/Tb_cut/Ti).
  No probado en MATLAB.

## 2026-11-23 — Medias del conjunto por cuadro: `VP_<código>_conjunto.csv` (VidFetch → MATLAB)

- **Pedido:** que VidFetch devuelva un archivo con las medias del conjunto y que `cargar_datos.m` lo use directamente.
- `software/vidfetch/core/conjunto.py` (nuevo, solo numpy/pandas): `ensemble_table(long_df, D, k, r_pared)` → una fila por
  cuadro; `write_ensemble` escribe `<x>_conjunto.csv` + `<x>_conjunto_info.json` (base de tiempo, D, k, r de la capa de
  pared, descripción de columnas). Columnas: frame, t_s, N, n_observados, n_v, V_media/mediana/p10/p90/desvio_mm_s,
  v2_media_mm2_s2, vx/vy_media_mm_s, orden_polar (|v| > 1 mm/s) + n_moviles, omega_media/abs_media_deg_s,
  w2_media_rad2_s2, n_omega, r_media_mm, v_tan/v_rad_media_mm_s, Omega_grupo_rad_s, n_pared, E_tras/E_rot/E_total_uJ_kg.
  Medias sobre todos los robots del cuadro (incl. interpolados, sin NaN) = criterio anterior de `cargar_datos`.
  r_pared = r_contacto/r_int · d_int/2 · κ_aplicado − D/2 (del _info.json; ≈ 61–63 mm).
- VidFetch: «Exportar CSV (todos los robots)» escribe también el `_conjunto.csv` (`_write_ensemble` en `main_window.py`);
  `herramientas/reexportar.py` también. `herramientas/exportar_conjunto.py [filtros] [--forzar]` lo genera desde los
  `_robots.csv` ya exportados (salta los que están al día). **Generados los 13** (`datos/video/trayectorias/`, ~2 MB c/u).
- `cargar_datos(ensayos, duracion_s, leer_robots = true)`: medias (E.t, V, v2, w2, N) desde `_conjunto.csv` si existe y no
  es más viejo que el `_robots.csv` (si no: cálculo anterior con groupsummary + aviso). Nuevo `E.conjunto` (tabla, base de
  tiempo real: t·f; `_mm_s/_deg_s/_rad_s` /f; `_mm2_s2/_rad2_s2/_uJ_kg` /f²). `leer_robots = false` no lee el CSV por robot
  (E.x, E.y, E.omega vacíos). Lista de ensayos incluye los que solo tienen `_conjunto.csv`. Unión de partes en `unir_parte`.
- `figuras.m`, `figuras_seleccion.m`: ajuste `leer_posiciones` (General); la ocupación se saltea sin posiciones; E se relee
  si falta `conjunto`. `atascos.m`/`parametros.m` sin cambios (en desuso).
- Verificado (Python): medias = groupby por cuadro de la tabla larga (dif. rel. < 1e-15, N idéntico); con 3,0→2,997 y 60 min
  E_tras/E_rot = 24,59/62,44 (24/09), 17,91/45,18 (30/10 12:00), 10,14/26,81 (12/11) = valores del 20/11. py_compile OK.
  **No probado en MATLAB ni la GUI** (sin MATLAB/Octave/PySide6 en el entorno).

## 2026-11-23 — `software/matlab/figuras_seleccion.m`: selección de figuras + tiempos de atasco/libre (figs. 11–12)

- Archivo aparte (pedido del usuario); `figuras.m` sin cambios. Mismo esquema AJUSTES → DATOS → una sección por figura;
  usa `cargar_datos.m` sin cambios (`E`, `asim` compatibles con los de `figuras.m`).
- Figuras: 1 P(V), 2 1−F(V/⟨V⟩), 3 distribución de E_c, 4 ocupación, 5 P(G ≥ g) (`G_normalizar`: G/⟨G⟩), 6 asimetría de ΔG
  vs ΔT (marca ΔT* y `deltaT_manual`), 7 histograma de ΔG en 2 paneles (ΔT* de máxima asimetría / `deltaT_manual`),
  8 histograma 2D V vs G, 9 P(G ≥ g) libre/atasco y 10 Q-Q de G_c vs G_b, **solo umbral manual** (`clas = clas(1)`).
  Fig. 5 sin opción de normalizar (pedido). Figs. 9–10: `normalizar_atasco = true` → g = G/⟨G⟩ del ensayo (todas sus
  muestras), adimensional como f_b, f_c del paper (allá f = fuerza de celda de carga, no frecuencia); mismo factor en los
  dos ejes ⇒ la identidad del Q-Q no cambia. Q-Q con ejes desde 0 y cuadrado (pbaspect), como fig. 3d.
- **Umbral por ensayo (figs. 9–12):** `umbral_tipo = 'relativo'` (por defecto) → u = `umbral_rel` (0,5) × mediana de V de cada
  ensayo; `'manual'` = `umbral` para todos. Motivo: con 0,35 mm/s fijo, 17/11 13:00 (20 robots) nunca atasca (Vs mín 0,49;
  V mediana 1,30 vs 0,70 el 16/11) y 17/11 16:00 suma 6,3 s en 4 atascos < 5 s. Relativo (Python, 0–40 min): u = 0,35 /
  0,65 / 0,535 mm/s; atascos completos ≥ 5 s: 13 / 2 / 4. Ojo: en 17/11 13:00 son frenadas (robots siguen moviéndose), no
  arrestos como el 16/11 (Vs hasta 0,11). Clasificación con `estados(E(i), u_est(i), ...)` por ensayo (sin tocar cargar_datos).
  Ensayos sin datos quedan en la leyenda (línea NaN con Tag) en 9–12; `min_muestras_estado` = 100. Fig. 11 muestra γ = 1 + β
  (como el paper; γ > 2 destrancado); 16/11 11:00 con 0,35: γ ≈ 3,1 ± 0,6 (n = 13).
- **Casos con pocos o ningún atasco (todas las figs. 9–12 muestran algo):** 9: cada panel por su cuenta (sin atasco igual
  se ve la curva libre; leyenda con Vs mín); < `min_muestras_estado` muestras → punteada con puntos. 10: punteada si pocas
  muestras; sin atasco, solo leyenda. 11: `mostrar_cortos = true` → curva con todos los episodios lentos completos (`Tall`,
  marcadores vacíos < τ_th, llenos ≥ τ_th; P sobre todos, γ solo con τ ≥ τ_th), como la parte de ráfagas de la fig. 1c del
  paper; recta τ⁻¹ anclada en el mayor P(T ≥ τ_th). 12: sin tramos completos → ▷ en el tramo libre cortado más largo
  (`Tb_cort`, cota inferior). Verificado en Octave con 3 casos sintéticos (atascos / solo frenadas cortas / nunca lento).
- **Figs. 11–12 (adaptación de Colantuono et al. PRE 2026, figs. 2c–d):** estado de Vs (movmean `suav_estado`) vs `umbral`;
  libres < `libre_min_s` entre dos atascos → atasco (0 = off); atascos < `tau_th` = 5 s → libre. T_c = duración de los
  atascos (o `tc_tipo = 'entre_atascos'`: inicio a inicio, sin cruzar huecos), T_b = tramos libres. Duraciones con los t
  de los cuadros (hueco > 2 cuadros corta el tramo). `incluir_bordes = false`: fuera los tramos cortados por inicio/fin/
  hueco/cuadros sin V. Fig. 11 log-log + τ⁻¹ (γ = 2) + β MLE de la cola (Pareto, τ ≥ tau_th; β < 1 ⇒ media diverge);
  fig. 12 semilog-y + exp(−τ/⟨T_b⟩) punteada.
- Verificado: parser Octave 8.4; lógica de tiempos con serie sintética (atascos 20/15/8 s, uno de 3 s absorbido, bordes y
  hueco excluidos: Tc, Tb, Ti exactos). No probado en MATLAB. Con 40 min hay pocos atascos por ensayo: β con error ~β/√n.

## 2026-11-20 — `software/matlab/figuras.m`: un solo archivo en bloques + G en atasco vs libre (figs. 14–15)

- **Pedido final del usuario (tras varias vueltas en el día):** todo en un solo archivo, bien dividido: qué es cada
  ajuste y dónde empieza cada gráfico. Se descartaron `parametros.m` y `atascos.m` (quedaron en la PC: el usuario los
  borra) y las figs. de prueba 14a/14b/16–18, banda muerta, ΔV y umbral por ensayo.
- `figuras.m`: bloques con secciones-título `%% ===== AJUSTES / DATOS / VELOCIDAD Y ENERGÍA (1–5) / G (6–13) /
  ATASCO VS LIBRE (14–15) =====`. AJUSTES agrupado por figura (General, Guardar, Velocidad, Energía, G piso, ΔG,
  Histograma 2D, Atasco vs libre, Aspecto). Cada figura tiene una línea `% Usa:` con los ajustes que la afectan.
  Figuras 1–13 sin cambios de código.
- **Atasco vs libre** (Colantuono et al. PRE 2026): sección de clasificación (`clas = estados(...)`) + fig. 14
  (P(G_b ≥ g), P(G_c ≥ g), Q-Q) + fig. 15 (histograma de ΔG, ΔT = `deltaT_estado`, asimetría en la leyenda). Filas:
  umbral manual (`umbral`) y estimado. Usa `E.G` ya con el piso de Datos. Variable `clas` (no `C`, que usa la fig. 13).
- `cargar_datos`: `estados(E, umbral, k_sigma, suav_s, dur_min_s)` e `incrementos(x, L, est, tramo, estado)`.
  Vs = movmean(V, `suav_estado` = 5 s); atasco Vs < u, libre Vs > u; tramos < `dur_min_estado` = 5 s fuera (≈ τ_th);
  muestra del sensor → cuadro más cercano (≤ 1 cuadro); ΔG solo dentro de un tramo.
- **Umbral estimado, uno para todos los ensayos (pedido del usuario):** 10^(moda − `k_umbral`·σ) de log10(Vs) de todos los
  ensayos juntos, σ = rms de la mitad sobre la moda (flujo libre). Vs no es bimodal (pico libre + cola baja).
- Esperado (Python, solo 30/10 11:00, 06/11 16:00, 30/10 12:00, 16/11 11:00 juntos): u = 0,52 mm/s; atasco 9,4 / 13,5 /
  5,5 / 21,7 %; ⟨G_c⟩/⟨G_b⟩ ×22 / ×1,2 / ×4,4 / ×2,3. Con u = 0,35: atasco 4,5 / 4,1 / 1,3 / 6,0 %. Con 7 ensayos cambia.
- No probado en MATLAB.

## 2026-11-20 — R_FEEDBACK 10 kΩ confirmado y piso de G en cuentas del ADC (`software/matlab/figuras.m`)

- **Confirmado por el usuario:** todos los registros desde el 30/10 (inclusive) son con **R_FEEDBACK = 10 kΩ** (descartado 3k7).
  `calibracion.csv`: notas de las 4 filas `20261030_*` y del prefijo `202611` actualizadas (valor 10000 sin cambios).
  Firmware `fsr_single_readV2.ino`: `R_FEEDBACK = 10000.0f` (antes 1000: la columna G de los R_ ya grabados sigue ×10 alta;
  MATLAB y FSRScope-MATLAB toman K solo de la lista). K = 3,3e6/(1023·0,7534·10 000) = **0,428 µS/cuenta**.
- **Diagnóstico de los valores bajos de G:** el firmware promedia N ≈ 482 conversiones por ventana de 50 ms ⇒ el promedio
  sale en pasos de 1/482 cuenta (8,9e-4 µS) pero no tiene esa resolución: el ADC no baja de 0 y sin contacto ~90–100 % de
  las conversiones dan 0 (`CLIP0/N`). El piso de cada día (mediana ADC 0,006 / 0,05 / 0,23 / 0,37 cuentas en 30/10 14:30,
  30/10 12:00, 12/11, 16/11) es ruido/offset del front-end, no conductancia. Aun con medias de 2–5 cuentas ~90 % de las
  conversiones son 0: la señal es impulsiva (contactos cortos de decenas de cuentas).
- `figuras.m`: se quitó el offset por ensayo (`offset_G`, `offset_G_frac`, `E.G_crudo`, `E.G_offset`; E se relee si quedó
  `G_offset` de la versión anterior). `G_minimo` → `G_minimo_cuentas = 1`; `G_piso = G_minimo_cuentas·[E.K]` (por ensayo:
  0,43 µS con 10 kΩ, 0,086 con 50 kΩ). Por debajo = «sin contacto»: fuera de los ejes log en figs. 6, 7 (P sigue sobre todas
  las muestras), 13 y las comentadas 8 y 12; consola: piso y % de muestras debajo. Fig. 13: 2.ª línea del título
  «sin contacto: X % de los cuadros», colores = fracción de los cuadros con contacto, eje G común (desde el piso más bajo).
  Esperado (log completo, ADC < 1 cuenta): 72 / 70 / 59 / 63 % (30/10 12:00, 14:30, 12/11, 16/11).
- Fig. 13, colores (pedido del usuario: los paneles con mucho «sin contacto» se veían más llenos y ruidosos): `norm_2d`
  = `'total'` (por defecto; cuentas / todos los cuadros válidos ⇒ un cuadro pesa igual en todos los paneles, ~1/10 800) o
  `'contacto'` (cuentas / cuadros con contacto; antes era esto, un cuadro pesaba ×3,4 en un ensayo con 71 % sin contacto).
  `celdas_2d = [25 20]` (antes 40×30: ~5–10 cuadros por celda, ruido de Poisson 30–45 %), `min_cuadros_2d` (vacía celdas
  con menos cuadros). Dibujo con `histcounts2` + `histogram2('BinCounts', ...)`; archivo `histograma2d_V_G_<norm_2d>`.
- Fig. 13: columna **S/C** (sin contacto) a la izquierda del piso más bajo, una celda de ancho + una celda vacía de
  separación; posición en G nominal (tick «S/C»), solo con `norm_2d = 'total'` (cada panel suma 100 %); línea punteada en
  el piso de cada ensayo. Fig. 6: línea punteada por piso distinto. Criterio: lo bajo el piso **nunca** se reemplaza por
  el valor del piso (sesgaría las medias ~0,3 µS con 70 % sin contacto). `G_bajo_piso = 'excluir'` (por defecto, G medido)
  | `'cero'` (G < piso → 0 en G y G_cuadro; cambia ΔG y su asimetría); se rehace desde `E.G_medido` en cada corrida de
  Datos; la clave de `asim` incluye `G_bajo_piso` y `G_minimo_cuentas`. El usuario fijó `G_minimo_cuentas = 0.5`.
- No probado en MATLAB.

## 2026-11-20 — `software/matlab`: energía cinética (fig. 4b)

- `cargar_datos`: `E.v2` (media de v² [mm²/s²]), `E.w2` (media de ω² [rad²/s²]) y `E.N` (robots por cuadro) por cuadro,
  con todos los robots (como V). `figuras.m` relee E si falta `w2`.
- **Fig. 4b `energia_cinetica`:** 3 paneles (traslación, rotación, total) con ejes x e y compartidos; E_tras = N·⟨½v²⟩,
  E_rot = N·⟨½kR²ω²⟩ (König), media móvil `suav`. Ajustes: `masa_g` (0 = por unidad de masa, mm²/s² = µJ/kg; > 0 → nJ),
  `diametro_mm` = 33, `k_inercia` = 0,5 (disco), `energia_log`. Consola: medias y E_rot/E_tras por ensayo.
- **Fig. 4c `energia_distribucion`:** histograma (probability, stairs) de la energía por cuadro sin suavizar, 3 paneles
  (tras/rot/total), 60 clases log comunes (p0,1–p99,9 de todos los valores; con los 10 ensayos 0,024–246 µJ/kg, 4 décadas),
  ejes compartidos. `energia_normalizada` → E/⟨E⟩ por ensayo y componente (solo forma; archivo `_normalizada`).
  `Ec_tras`/`Ec_rot` se calculan en la sección Datos (4b y 4c usan los mismos). Consola: mediana [p10 p90].
  Esperado (µJ/kg, Python): 24/09 tras 17,1 [1,35 59,2], rot 58,4 [17,1 112]; 30/10 16:00 tras 0,66 [0,07 31,4]
  (bimodal: atasco + flujo); 12/11 tras 6,55 [0,75 24,4]. Ancho p10–p90: tras 1,0–1,6 décadas, rot 0,5–1,0 (salvo 30/10 16:00).
- 4c con `energia_dist_juntas = true` (por defecto): tras, rot y total en un solo eje; color = ensayo, trazo = componente
  (tras `:`, rot `--`, total `-`; el trazo ya no marca el modo, la familia de color sí). Leyenda: una entrada por ensayo
  (la del total) + 3 claves de trazo en negro. Archivo `energia_distribucion_juntas[_normalizada]`; `false` = 3 paneles.
- Figs. 5 y 13 (ocupación, histograma 2D): se probó una figura por ensayo (`figuras_aparte`); el usuario pidió volver a
  los paneles en una sola figura ⇒ quedan como antes.
- Verificado: parser de Octave 8.4 en ambos .m; no probado en MATLAB. Valores esperados (cálculo independiente en Python,
  0–60 min, µJ/kg): E_tras / E_rot = 24,6/62,4 (24/09), 21,8/59,1, 23,2/67,8, 27,1/70,2 (30/10 11:00), 17,9/45,2 (12:00),
  19,0/56,2 (14:30), 8,3/21,7 (16:00), 19,5/49,1 (06/11), 10,1/26,8 (12/11), 12,3/34,1 (16/11). E_rot/E_tras = 2,5–3,0.
- **Validación para comparar (mismo cálculo):** AH vs AL sin diferencia significativa (test de permutación exacto, 6 vs 4:
  E_tras p = 0,15, % atasco p = 0,71) y confundido con la fecha: ½⟨v²⟩ de los primeros 10 min baja de 1,4–1,7 (sept.) a
  0,44–0,78 mm²/s² (nov.). En 24/09 y 25/09 12:30 ½⟨v²⟩ cae 60–80 % entre min 0–10 y 50–60. ρ Spearman (10 s) de G con
  V: −0,03 a −0,60 (más fuerte con atascos); robots en la capa de la pared ≈ 12,0–12,6 en todos (saturada, no explica G);
  retardo E_tras→G sin signo consistente (−60 a +21 s).

## 2026-11-16 — `matlab`: nombres legibles en leyendas, asimetría y σ de ΔG

- `cargar_datos`: `E.etiqueta` = `etiquetas(codigos)` → `'30/10 11:00 · AH'` (año y «N robots» solo si difieren entre los
  ensayos cargados; códigos sin el patrón quedan igual). `leyenda(ax)` reconoce el ensayo por el `Tag` de la curva
  (= código) + DisplayName como respaldo. `figuras.m`: `et = {E.etiqueta}` en leyendas y títulos de paneles, `'Tag',
  nombres{i}` en todas las curvas de ensayo; `nombres` (códigos) sigue en archivos y consola. E se relee si falta `etiqueta`.
- Figs. 8b, 10 y 11: leyenda con «asimetría x; σ = y µS» (σ de ΔG en µS; en 8b se calcula antes de normalizar).
- Corregido el eje Y de 8b: `ylabel('densidad [1/\\muS]')` (doble barra en texto sin sprintf) mostraba «1/\muS».
- Primera corrida del usuario (6 ensayos): ΔT* = 6,20 s; asimetrías −3,32 / 0,05 / 1,43 (AH 30/10 11:00, 16:00, 06/11) y
  0,13 / −1,64 / 0,48 (AL 30/10 12:00, 14:30, 12/11) ⇒ media de |·| ≈ 1,18, dominada por 30/10 11:00 y con signos mezclados.

## 2026-11-16 — `matlab`: carga recortada a 60 min desde el fin del LED

- **Pedido:** cargar solo hasta 60 min después de la última señal del LED; el video ya empieza ahí.
- `cargar_datos`: video `0 ≤ t_s ≤ duracion_s` (antes `t_s − min(t_s)`); sensor recortado (no solo NaN) a
  `t ∈ [desfase, desfase + duracion_s]`, grilla igual que FSRScope (arranca en t(1), se recorta después de interpolar);
  máscara de FSRScope (t_start/t_end/exclusiones/saturación) dentro de ese tramo. `led_fin` = fin del **último** pulso
  (antes el primero; aviso si hay > 1). Imprime por ensayo «video X min y sensor Y min desde el fin del LED».
- Revisado: R_ del 24/09, 30/10 11:00, 06/11, 12/11 y 16/11 tienen un solo pulso de 101 filas y ≥ 64,7 min tras el LED.
  t0 = primera fila del log (incluidas filas SYNC), igual en FSRScope (`log_io.load_log`); por eso el LED del 06/11 da
  120,37 s (no 30,65 como se anotó el 12/11; la sincronía no cambia porque t y desfase se corren juntos).
- `figuras.m`: el commit anterior había subido una copia vieja (sin la fig. 8b y con `guardar = false`); restaurado con la
  8b y `guardar = true` del usuario. Verificado por md5 contra el archivo de la PC. No probado en MATLAB.

## 2026-11-16 — `software/matlab/figuras.m`: modos diferenciados y ΔG con el ΔT de máxima asimetría

- **Modos:** `cargar_datos` agrega `E.modo` (`AH`/`HO`/`AL`/`otro`, de `modo_de(código)`; QR/QL → AH, R → AL) y
  `E.modo_nombre`, y ordena los ensayos por modo (AH, HO, AL, otro) y luego por fecha. `cargar_datos('estilos')` →
  `[colores, lineas, marcas] = estilos(E, linea_por_modo)`: familia de color por modo (AH azules, HO verdes, AL rojos/
  naranjas, otro grises; oscuro → claro en orden de fecha), trazo `-`/`-.`/`--`/`:` y marcador o/^/s/d.
  `cargar_datos('leyenda')` → `leyenda(ax)`: leyenda agrupada con un encabezado sin símbolo por modo (líneas NaN con
  Tag `cabecera_modo`); si hay un solo modo, leyenda normal. Helpers en `cargar_datos` (no funciones locales del
  script) para que anden con Ctrl+Enter, como `exportar`.
- `figuras.m`: `linea_por_modo` en Ajustes; todas las curvas con `LineStyle`; `legend` → `leyenda(gca)`; figs 5 y 13
  con una fila por modo (`tiledlayout(filas, columnas)`, `flow` si un modo tiene > 4 ensayos) y títulos con el modo en el
  color del ensayo; normal de la fig. 10 punteada (`k:`; el cortado es AL). E se relee si le falta `modo`.
- **Fig. 8b (nueva) — histograma de ΔG con ventana fija de máxima asimetría:** las curvas asimetría(ΔG) vs ΔT (0,05–15 s,
  paso 0,05) se calculan una vez en la sección Datos (`asim.s`, filas = ensayos; clave = códigos + `duracion_min`) y las
  usan 8b y 9 (9 ya no recalcula). ΔT* = argmax de la media sobre ensayos de |asimetría| dentro de `rango_deltaT_asim`
  (|·| para que asimetrías de distinto signo no se cancelen; la asimetría de cada ensayo no depende de su escala en µS).
  `deltaT_asim = []` → ΔT*; un número lo fija a mano. `normalizar_dG_asim`: false = ΔG en µS, true = (ΔG − media)/σ + normal.
  Clases comunes ±p99,9 de |ΔG|; leyenda con la asimetría de cada ensayo a ΔT*. La fig. 9 marca ΔT* con `xline`.
  Guardado `deltaG_histograma_asimetria_max`.
- Solo revisión de código: **no probado en MATLAB** (el entorno de Claude no lo tiene).

## 2026-11-16 — Menos carpetas en todo el repo

- Borrado: `datos/video/config/` y `datos/resumen_ensayos.csv` (Velocidades), `informes/figuras/matlab/`,
  `datos/presion/procesados/` (P_; FSRScope/`procesar_lote` lo recrean al exportar), intermedios de LaTeX, `.raw/.log`
  de LTspice, `poster.tex.bak_userparams`.
- Unido: `datos/presion/{Viejos,referencia}` → `crudos/` (`cargar_datos('R_feedback')` lee solo `crudos/`, sin columna
  `carpeta`; JSON de LabPlotter del póster apuntan a `crudos/Medicion Vacio.csv`); `software/docs/*.xlsx` →
  `informes/aplicacion/`; `comun/qt/{repo,widgets,worker}.py` → `comun/` (imports `comun.repo`, `comun.worker`,
  `comun.widgets`); `empaquetado/{lanzadores,iconos}/*` → `empaquetado/`; `informes/comun/*.tex` → `informes/`
  (`\input{../preambulo.tex}`, `\input{../config.tex}`).
- Verificado: py_compile OK; no se corrió FSRScope ni MATLAB ni LaTeX.

## 2026-11-16 — Limpieza de software/: los gráficos quedan solo en `matlab_figuras`

- **Borrado** (recuperable desde git, último commit antes de esta fecha): `software/matlab/` (versión MATLAB de 70
  archivos + caché), `comparador/`, `velocidades/`, `figuras/` (Python: generar_informe, comparar_ensayos/modos,
  figuras_metodo, plantilla), `comun/{mobility,summary,estilo}.py`, lanzadores e íconos de Comparador/Velocidades,
  `empaquetado/dist` y `build` (1,8 GB, no versionados), `__pycache__`.
- Ajustados: `empaquetado/construir.py` (solo vidfetch, fsrscope), `generar_iconos.py`, `comun/paths.py` (sin
  `VEL_CONFIG_DIR`/`SUMMARY_PATH`), `requirements.txt`, READMEs (raíz, software, fsrscope). Compilación de los .py OK.
- Queda: `vidfetch/` (genera VP_), `fsrscope/`, `comun/`, `herramientas/`, `matlab_figuras/` (sin cambios).
- Sin regenerar posible: `informes/*/generado/` y figuras de método f1–f9 (los .tex de informes siguen citando
  `software/figuras/...`). Datos de las apps borradas siguen en `datos/video/config/` y `datos/resumen_ensayos.csv`.
- `matlab_figuras` de FSRScope solo usa `datos/presion/config/<código>.json`: en los 7 configs offset automático,
  sin exclusiones, sin saturación excluida, step 0,05 s ⇒ hoy da lo mismo que los valores por defecto.

## 2026-11-13 — Ensayo `20261112_1600_22AH_60` (antes carpeta `raro/`)

- Código confirmado por el usuario: 12/11 16:00, 22 robots, **AH**, 60 min. `raro/` borrada.
  `hyperlapse_final.mp4` → `datos/video/originales/VR_20261112_1600_22AH_60.mp4`; `hyperlapse_final_recorte.mp4` →
  `datos/video/recortados/VC_20261112_1600_22AH_60.mp4`.
- `datos/video/sesiones/VA_20261112_1600_22AH_60.npz` = última sesión del usuario (`hyperlapse_final_analisis.npz`, 02:42:
  cuadros 0–11198, 156 correcciones, 0 cuadros con error, θ de 20 robots guardado); `..._completo.npz` = sesión completa
  0–12040 con 232 correcciones (incluye el tramo posterior al corte del cuadro 11199). `src_path` → VC_ nuevo en ambas.
- **Ojo:** el giro medido no parece AH: ω media por robot 8 antihorario / 8 horario (|ω̄| > 0,5 °/s), media −0,17 °/s
  (en los AH anteriores la mayoría gira antihorario). Pendiente confirmar el programa cargado.
- Pendiente: registro `R_20261112_1600_22AH_60.csv` (no está en `datos/presion/crudos/`); exportar `VP_` (VidFetch o
  `herramientas/reexportar.py`). En las entradas de abajo, `raro/...` = este ensayo.

## 2026-11-13 — Video `raro/hyperlapse_final`: corte en el cuadro 11199 y `herramientas/recortar_sesion.py`

- `hyperlapse_final.mp4`: 1080p, 30 fps nominal, 12 081 cuadros, re-codificado con libx264 (handler DJI.AVC, sin
  creation_time ni saltos de pts ⇒ partes unidas con ffmpeg; el hueco no se puede medir con el archivo). El recorte tiene
  40 cuadros menos al inicio. **Un solo corte**: diferencia entre cuadros 11198→11199 con z = 16 (ningún otro > 4 salvo
  el final, 12031–12039). Desplazamiento mínimo a través del corte (asignación húngara): mediana 5,2 mm, máx. 64,8 mm
  (vs 0,67 mm en 8 cuadros normales) ⇒ la identidad a través del corte no es confiable por posición.
- 454 de los 478 cuadros con error del seguimiento están desde el corte; antes: 24 (robots 11 y 17, 3788–5257).
- Corte a 11199/2,997 = 62,3 min del inicio del recorte ⇒ fuera de la ventana de 60 min (si el recorte arranca al fin del LED).
- `software/herramientas/recortar_sesion.py <npz> [--desde a] [--hasta b] [--salida]`: recorta candidatos, correcciones
  y tramo sin releer el video; re-sigue y resuelve θ solo con ese tramo (nada posterior al corte entra en las derivadas ni en
  el θ global); no toca la entrada. Generado `raro/hyperlapse_final_recorte_analisis_hasta_corte.npz` (0–11198, 5 de las 14
  correcciones; carga 3,6 s, v y θ 0,2 s).
- Sesión del usuario (02:29, 232 correcciones) → `raro/hyperlapse_final_recorte_analisis_0-11198.npz`: 189 correcciones,
  0 cuadros con error. Robot 17 corregido cuadro a cuadro en 5234–5373: paso entre cuadros manual 1,36 mm (p90 2,71) vs
  0,23 mm detectado ⇒ |v| del 17 en ese tramo 0,81 mm/s vs 0,38 fuera (ruido del clic). En 5300 hay candidato a 5,3 px con
  cobertura 0,70. Propuesto: ajustar el clic al candidato más cercano (no implementado).
- Pendiente: sin registro R_ identificado para este video; si hace falta el tramo posterior, medir el hueco con los
  archivos DJI originales (creation_time, `comun/cortes.py`) o por correlación con G.

## 2026-11-13 — VidFetch: correcciones manuales rápidas (θ por robot en caché, cinemática diferida, lote)

**Problema (video `raro/hyperlapse_final_recorte`, 12 041 cuadros, 22 robots, ~500 correcciones):** cada clic de corrección
recalculaba seguimiento (3,2 s) + cinemática completa (92 s, casi todo el giro θ con enlaces largos de los 22 robots).
Una corrección cambia la trayectoria de 1 robot (verificado: anchor en el cuadro 6000 → solo cambia el robot 5).
- `core/kinematics.py`: caché de θ por robot (`_THETA_CACHE`, clave blake2b de F + filas observadas + candidato asignado;
  256 columnas, se reinicia si cambia `cand_sig`). `cached_theta`/`seed_theta`. Recalcular tras 1 corrección: 3,3 s.
- `core/tracking.py`: `TrackingSession.applied_anchors` (anchors con que se calculó `result`) y `pending_anchors`;
  `save` guarda `theta_keys` (n×16 uint8) + `theta_cols` (F×n) si están en caché; `load` los siembra
  (reabrir: 88 s → 2,9 s; archivo +1 MB). Versión de archivo sigue en 3 (claves opcionales).
- `gui/main_window.py`: `retrack` = solo seguimiento (`_track_task(with_kin=False)`, `kin = None`); `_needs_update(retry)`
  aplica correcciones pendientes y calcula la cinemática antes de los 5 exportadores; `prepare_results`;
  `_after_worker` encadena pasos tras liberar el worker (el `succeeded` llega antes de `finished`).
- `gui/tracking_tab.py`: casilla «Recalcular el seguimiento en cada corrección» (desmarcada = lote; cruz magenta en las
  pendientes), botón «Aplicar correcciones (R)» + tecla R, estado y botón «Calcular velocidades y giro» en Resultados;
  abrir la pestaña Resultados calcula lo pendiente.
- **Verificado:** θ y vx idénticos bit a bit al código anterior (sesión de `raro`); GUI offscreen (PySide6 6.12): corrección
  2,8 s, lote de 2 + R 2,8 s, Resultados 12,8 s (3 robots), exportar con 1 pendiente 12,7 s (34 columnas con ω).
- **Carga y análisis nuevo también sin cinemática** (`_track_task(with_kin=False)` en `load_session`, `session.run(...,
  kinematics=False)` en `_analyze_task`): abrir el `.npz` de `raro` sin θ guardado 88 s → 3,9 s; v y θ se calculan en
  Resultados/al exportar (90 s la primera vez si el archivo no trae θ, 0,1 s si lo trae).
- `raro/hyperlapse_final_recorte_analisis_con_giro.npz` (nuevo, mismas 14 correcciones + θ). El original no se tocó.
- Pendiente: reconstruir el .exe de VidFetch (`empaquetado/construir.py vidfetch`).

## 2026-11-12 — `matlab_figuras`: base de tiempo real del video (2,997 cuadros/s) y recorte de 60 min

- Verificado: cada R_ tiene **un solo** pulso de LED de 5 s (101 filas); desfase = fin del LED (30,75 / 17,05 / 21,45 / 8,00 /
  30,65 s para 30/10 11:00, 12:00, 14:30, 16:00 y 06/11). Todos tienen ≥ 60 min de video y de sensor tras el LED (el más
  justo 30/10 11:00: 60,9 min de video). Las 3 filas SYNC del 06/11 no son pulsos.
- Los VP_ se exportaron con `cuadros_por_segundo_real` = 3.0 (t_s = frame/3, verificado en 30/10 11:00); la cámara da 2,997 ⇒
  el video se atrasaba 0,1 % respecto del sensor (3,6 s al minuto 60). `cargar_datos.leer_trayectoria`: f = fr_exportado/2,997
  (lee el `_info.json`), t·f, v/f, ω/f; imprime la corrección por archivo. El hueco del video partido usa `fr_real()`.
  La ventana de 60 min queda en tiempo real. FSRScope/Velocidades/Comparador y `software/matlab` siguen con 3,0 y video completo.

## 2026-11-12 — `matlab_figuras`: vuelve al Statistics Toolbox

- El usuario instaló Statistics and Machine Learning Toolbox ⇒ `skewness(x,0)`, `corr(...,'Type','Spearman')`, `normpdf`,
  `prctile` nativos; se quitó el modo `cargar_datos('estadistica')` y las funciones propias (asimetria/spearman/rango/percentil).
  El resto de la corrección anterior (tema claro, ocupación, `G_minimo`, `VariableNamingRule`) se mantiene.

## 2026-11-12 — `matlab_figuras`: sin toolboxes, tema claro, ocupación y piso de G

**Primera corrida del usuario (MATLAB sin Statistics Toolbox, tema oscuro):** error en `skewness`; figuras con borde negro y
leyendas/rótulos casi invisibles; ocupación casi uniforme azul (tope 2,5 por los robots quietos del atasco 30/10 16:00) con
agujeros blancos; P(G≥g) con eje desde 1e-20 (G de redondeo ~1e-14); histograma de G serruchado < 1e-2 µS (escalones del ADC).
- `cargar_datos('estadistica')` → `est.asimetria` (= skewness(x,0)), `est.spearman` (rangos promedio con empates), `est.percentil`
  (interpolación lineal). Verificadas contra scipy/numpy con empates y NaN: idénticas (1.382505 / 0.559998 / 6.706000).
  `normpdf` → fórmula. Ya no hace falta ningún toolbox.
- Tema: `set(groot,'defaultFigureCreateFcn', @(f,~) theme(f,'light'))` si existe `theme` (R2025a+); `exportgraphics(...,
  'BackgroundColor','white')`.
- Ocupación: tope de color = percentil 99 de todas las celdas de todos los ensayos; transparente solo fuera de la pared
  (`AlphaData` = r ≤ 9,25 cm); pared en gris oscuro.
- `G_minimo = 1e-2` µS en Ajustes: piso de G(t), P(G≥g), histograma de G, G vs V y histogram2.
- `readtable(..., 'VariableNamingRule','preserve')` en los R_ (sin advertencias; columna `timestamp(ms)`).
- Solo sintaxis verificada (y las funciones estadísticas en Octave); falta la corrida del usuario.

## 2026-11-12 — VidFetch: calibración de tamaño en videos 1080p

**Problema:** grabación nueva en 1080p (no 4K), recorte de 380×384 px, robots de ~50–58 px de diámetro; la calibración automática
daba 10,2 px y N ≈ 89. La puntuación del filtro disco/anillo crecía hacia el radio mínimo de la grilla (detalles brillantes chicos:
lengüeta metálica, reflejos, LEDs) y superaba al pico real del robot (r ≈ 28 px). En 4K el robot es lo bastante grande para ganar.
- `core/calibration.py`: (1) prior por el recinto: `arena.detect_one` en los cuadros de muestra (color, cobertura ≥ 0,5) →
  r_previo = 0,164 · r_int del recinto (4K: 46,7/285; 1080: 28/181) y la búsqueda gruesa se limita a [0,6; 1,6]·r_previo;
  (2) `_best_on_grid` elige el mejor máximo **interior** (un máximo en el borde de la grilla es tendencia, no tamaño).
  `Calibration.arena_r_in` nuevo; `describe` indica si quedó acotado por el recinto.
- **Verificado** (Python, OpenCV 5, trackpy): cuadro de la captura de pantalla reescalado a 380×384 → diámetro 58,2 px, búsqueda
  18 px, 19 detecciones bien centradas (las 3 faltantes tienen encima los rótulos de la captura); VC 4K (`VC1_ultimo.jpg`,
  `VC2_primero.jpg`) → 93,5 / 93,2 px, igual que antes. Cada regla por separado ya da el resultado correcto.
- **Confirmado por el usuario** con `salida_80x_recorte.mp4` real: la calibración y el seguimiento funcionan bien.

## 2026-11-12 — `matlab_figuras`: R_FEEDBACK solo de la lista, 60 min, fondo claro

- `cargar_datos`: K = V_REF·1e6/(ADC_FS·V_EXC·R) con R **solo** de `calibracion.csv` (error si el registro no tiene fila); el factor
  del firmware ya no se usa, solo se reporta (`E.R_firmware`). `cargar_datos('R_feedback')` → tabla de todos los R_ en `crudos/` y
  `Viejos/` (los de agosto se movieron a `datos/presion/Viejos/`). `cargar_datos(ensayos, duracion_s)`: trayectorias con
  t − t_inicio ≤ duracion_s y G solo con t_video ∈ [inicio, inicio + duracion_s].
- `figuras.m`: `duracion_min = 60`; sección 0 = tabla R lista vs firmware; Datos imprime R y el factor de G por ensayo;
  `defaultFigureTheme` light (R2025a+, try) + `defaultAxesColor` w; ocupación con `AlphaData` (celdas vacías blancas).
- **Comparación R lista vs R del firmware** (V_EXC de la config o 0,7534 V): 24/08 ×4 = 12 000 / 12 000 (coincide);
  27/08 lista 12 000 vs firmware 6 797 (la nota de la lista dice «equivalente al K del firmware» = 6 797); 24/09 50 000 vs 5 000
  (confirmado 50 k); 25/09 12:30 y 15:00 lista 50 000 vs firmware 1 000 (la nota dice «valor del firmware»: no coincide);
  30/10 ×4 y 06/11 lista 10 000 vs firmware 1 000 (nota «a confirmar (3k7)»). El valor del firmware es la constante programada,
  no mide la resistencia real.
- Solo sintaxis verificada; no probado en MATLAB.

## 2026-11-12 — `software/matlab_figuras/`: versión simple (2 archivos, herramientas de MATLAB)

**Pedido:** dejar `software/matlab/` como está y hacer en otra carpeta algo más simple, con herramientas integradas de MATLAB,
pocos archivos y fácil de ver.
- `figuras.m`: un script, una sección `%%` por figura (Ctrl+Enter = una, F5 = todas). Ajustes arriba (ensayos, suav, umbral, deltaT,
  guardar) + estilo con `set(groot, 'default...')`; sección Datos lee una vez (E queda en el workspace, se relee si cambia `ensayos`).
  12 figuras: V(t), P(V) (`histogram` pdf stairs), 1−F(V/⟨V⟩), ω (`histogram`), ocupación (`histcounts2` + `imagesc`, `tiledlayout`,
  barra común), G(t), P(G≥g), histograma de G, asimetría de ΔG vs ΔT (`skewness(...,0)`), ΔG/σ vs `normpdf`, G mediana por clase
  de V (`discretize` + `accumarray`, `corr` Spearman), `histogram2` V vs G. Colores `lines(n)` iguales en todas; leyendas con
  Interpreter none; guardado `exportgraphics` → `informes/figuras/matlab_figuras/<figura>__<códigos>.png/.pdf`.
- `cargar_datos.m`: `readtable`/`detectImportOptions`, `groupsummary` (V media por cuadro), une partes (1)/(2) con `cortes.json`
  (sin emparejar identidades: no hace falta para estas figuras), sensor igual que FSRScope/`leer_presion` (unidades, filas basura,
  t0, fin del LED, K: calibracion.csv > manual > firmware, grilla `step_s`, recorte/exclusiones/saturación, desfase manual).
- Requiere MATLAB R2020b+ y Statistics and Machine Learning Toolbox. **No probado** (Octave no tiene readtable/histogram/
  tiledlayout/groupsummary); solo sintaxis verificada. `software/matlab/` sin cambios.

## 2026-11-12 — MATLAB: `fig_hexbin_velocidad_presion` reescrito con herramientas nativas

**Pedido:** usar todo lo integrado de MATLAB para simplificar.
- Rectángulos con `histogram2(ax, x, y, xe, ye, 'DisplayStyle','tile', 'ShowEmptyBins','off', 'Normalization', ...)`; paneles con
  `tiledlayout` + `nexttile`, barra de color compartida `cb.Layout.Tile = 'east'`, rótulos compartidos `xlabel(t)`/`ylabel(t)`,
  `yline` para el umbral, `ax.ColorScale = 'log'`, `CLim` común, `movmean(..., 'SamplePoints', t)`, título con `Interpreter none` y ρ
  en Unicode. Hexbin sigue con `funciones/hexbin.m` + `patch` (MATLAB no trae hexbin).
- Opciones simplificadas: `celdas = [nG nV]`, `normalizacion` = probability | count (se quitaron 'tiempo', 'porcentaje' y `min_cuentas`).
  Distribución manual en cm y arreglos de barra de color eliminados. 164 → 122 líneas.
- **Ya no corre en Octave** (sin `tiledlayout`/`histogram2`); requiere R2020b+. `funciones/histograma2d.m` quedó sin uso (se puede borrar).
- Solo verificada la sintaxis (parser de Octave); **no probado en MATLAB**.

## 2026-11-12 — MATLAB: hexbin de V vs G

- `figuras/fig_hexbin_velocidad_presion.m` (nuevo): un punto por cuadro, x = G en el cuadro (`presion_en_cuadros`, máscara FSRScope), y = V media
  (o |v| de cada robot observado, `fuente_v = 'individual'`); color = % de los puntos del ensayo (o tiempo, cuadros), escala log
  (`ColorScale` en MATLAB, log10 en Octave). Hexágonos y escala de color comunes a todos los paneles; G log por defecto (binning en
  log10 G); suavizado 0 por defecto (suavizar convierte la nube en trayectorias); ρ de Spearman en 2.ª línea del título; `juntar`.
- `funciones/hexbin.m` (nuevo): algoritmo de matplotlib (dos redes intercaladas, métrica du²+3dw²); filas = nx·(alto/ancho)/√3 para
  hexágonos regulares en pantalla. Se dibuja con un solo `patch` (Faces/Vertices).
- Agregado a `comparar_todo` en `false`. Verificado en Octave 8.4 (Qt/Xvfb) con 3 ensayos sintéticos, modos media e individual.
- `tipo = 'histogram2'`: celdas rectangulares (`funciones/histograma2d.m`, misma salida que `hexbin`, dibujo común con `patch`; no usa
  `histogram2` de MATLAB para compartir escala de color y correr en Octave). `celdas` reemplaza a `hexagonos`; `archivo = ''` →
  `hexbin_velocidad_presion` / `hist2_velocidad_presion`. Distribución manual de paneles en cm (márgenes para título de 2 líneas);
  barra de color en el margen derecho con `cb.Position` en MATLAB (Octave la ignora: queda la automática).

## 2026-11-12 — MATLAB: nombres de gráficos = códigos de medición

**Pedido:** leyendas, archivos, ventanas y títulos coherentes con las mediciones; G en vez de «presión».
- `etiqueta_ensayo` devuelve el código (`20261030_1200_22AL_60`) en vez de `30/10 12:00 · 22AL`: leyendas, títulos de panel, listas.
- `texto_tex.m` (nuevo): escapa `_` → `\_` salvo `_{...}` (TeX); usado en `poner_leyenda`, títulos de `fig_ocupacion`, `fig_deltaG_tiempo`,
  `fig_velocidad_y_presion`, ticks de `fig_barras_resumen`, rótulos de punto de `fig_comparar_modos`/`fig_presion_vs_robots` (ahora
  `AAAAMMDD_HHMM`, antes `etiqueta(1:5)`).
- `elegir_codigos` guarda la selección (`appdata(0,'codigos_actuales')`); `nueva_figura` nombra la ventana `<figura> - <códigos>` y
  guarda los códigos en la figura; `guardar_figura` agrega `__<c1>-<c2>-...` (`nombre_con_codigos.m`, nuevo; > 110 caracteres →
  `__Nensayos_<primero>_a_<último>`; no repite códigos ya presentes en el nombre).
- Ventanas: `Presion vs tiempo/robots/velocidad` → `G vs tiempo`, `G vs robots`, `G vs V media`. Ejes ya decían G [µS].
  Nombres de script y de `archivo` (`presion_*`) sin cambios.
- `comparar_ensayos.m` (versión anterior): `etiqueta` = código (**corrige** la heurística vieja día/mes que mostraba el 06/11 como
  «11/06»), leyendas escapadas, ventanas con G, archivos exportados `<nombre>__<códigos>`.
- **Verificado en Octave 8.4** con 3 ensayos sintéticos y los 12 scripts marcados en `comparar_todo` (renderer Qt bajo Xvfb, que
  interpreta TeX como MATLAB): leyendas y títulos `20261030_1100_22AH_60`, ventanas con códigos, 12 PNG `<figura>__<códigos>.png`.
  (gnuplot muestra `\_` como subíndice: es limitación de ese toolkit.) No probado en MATLAB.

## 2026-11-12 — MATLAB: `comparar_todo.m` (figuras principales en tanda)

**Pedido:** un script que corra las figuras más importantes de cada tema para comparar.
- `software/matlab/comparar_todo.m`: elige ensayos una vez (`elegir_codigos` sobre `buscar_ensayos`) y corre la tabla `figuras`
  (script, true/false). Activas: velocidad_tiempo, ccdf_velocidad, omega_distribucion, giro_robots, circulacion_tiempo, msd,
  densidad_radial, presion_tiempo, presion_supervivencia, asimetria_deltaT, deltaG_distribucion, presion_vs_velocidad,
  barras_resumen, comparar_modos, tabla_resumen; el resto en false. `por_ensayo_VG` = fig_velocidad_y_presion por ensayo.
  `guardar` → `informes/figuras/matlab/comparacion_<fecha>/<script sin fig_>[_k].pdf/png`; `agrupar` = docked después de guardar.
  Un error no corta la tanda (lista al final; errores de guardado aparte).
- `funciones/correr_figura.m` (nuevo): impone los ensayos con `setappdata(0,'lote_ensayos')` + `onCleanup` (se borra aunque falle o
  Ctrl+C); corre el script con `run` dentro de una subfunción para que su `clear` no borre las variables del maestro; devuelve las
  figuras nuevas ordenadas. Los scripts de `figuras/` no se tocaron.
- `funciones/elegir_codigos.m` (nuevo): lógica de selección común ('todos' | {} lista con ensayos_base | filtro) + override por
  `lote_ensayos`; `cargar_ensayos` y `cargar_presion` la usan (se quitó la `coincide` duplicada).
- **Verificado en Octave 8.4** con datos vacíos y scripts de prueba (con `clear` y uno que falla a propósito): selección impuesta a
  los 17 scripts (presión resuelve el mismo código en `buscar_registros`), un ensayo por figura en V-G, variables del maestro
  intactas, `lote_ensayos` borrado al final, 16 figuras guardadas, la que falla queda listada. Filtros y 'todos' sin tanda: iguales.
  **No probado en MATLAB ni con los scripts reales**.

## 2026-11-12 — MATLAB: lista de ensayos con selección por defecto (`ensayos_base`)

**Pedido:** que todos los scripts trabajen con 20261030_1100, _1200, _1430, _1600 y 20261106_1600, pero pudiendo elegir entre todos.
- `funciones/ensayos_base.m` (nuevo): única definición de esos 5 códigos.
- Los 24 scripts de `figuras/` (salvo `fig_velocidad_y_presion`, que grafica un solo ensayo) usan `ensayos = {}` ⇒ `listdlg` con **todos**
  los ensayos (`cargar_ensayos`) o registros (`cargar_presion`, incluye agosto y la referencia de 0 robots), con `ensayos_base` ya marcado
  (`InitialValue`). Función local `coincide` (filtro por parte del código) en ambos cargadores. `'todos'` y `{'...'}` siguen funcionando.
- `comparar_ensayos.m`: `addpath(funciones)`; `ensayos = {}` ⇒ `listdlg` de los códigos de `VP_*_robots.csv` (partes (1)/(2) como uno),
  con `ensayos_base` marcado; `{'...'}` busca `VP_<código>*_robots.csv`; `archivos` explícito tiene prioridad. Se quitó `uigetfile`.
- README de `software/matlab` actualizado. **No probado** en MATLAB ni Octave.

## 2026-11-12 — MATLAB: R_FEEDBACK por registro en `datos/presion/calibracion.csv`

**Pedido:** el 24/09 sí fue con 50 kΩ (confirmado por el usuario); poder editar R de cada ensayo en una lista.
- Antes: K = mediana(G/ADC) del firmware (modo auto) o parámetros si la config de FSRScope era manual (solo 24/09
  50 kΩ y 25/09 12:30 1 kΩ). R equivalente del firmware: agosto 12 kΩ, 27/08 6797 Ω (K 0,6299 con V_EXC 0,7534),
  24/09 5 kΩ, resto 1 kΩ.
- `calibracion.csv` (12 registros, precargado con esos valores y 50 000 en 24/09); prioridad lista > FSRScope
  manual > firmware; prefijo de código válido (gana el más largo); vacío = siguiente.
- `funciones/r_feedback_lista.m` (nuevo); `leer_presion` → `P.r_feedback` (R equivalente a K) y `P.origen_K`;
  aviso en consola (ya no warning «Revisar») si difiere > 2 % del firmware. Cachés: `cargar_presion` v2,
  `cargar_ensayo` v4, firma incluye el valor de la fila del ensayo. `tabla_presion` + columna `R_FB_ohm`.
- Verificado en Octave: K 0,3568 / 0,6299 / 0,0856 / 4,2817 (24/08, 27/08, 24/09, 30/10 12:00); vacío → FSRScope;
  restaurar → vuelve a la lista y relee.
- Pendiente: FSRScope/Velocidades/Comparador (Python) no leen la lista.
- (Superado el 20/11: confirmado 10 kΩ.) Usuario: 30/10 y los registros actuales usan **3k7 (a confirmar, no lo recuerda)**; el firmware logueó con 1 kΩ ⇒ G ×0,27. Lista: 4 filas 20261030_* = 3700 y prefijo `202611` = 3700 (06/11 en adelante).

## 2026-11-12 — FSRScope: detección de video partido y desfase automático de las partes

**Pedido:** que FSRScope se dé cuenta si el video está cortado y calcule cuánto desfasar las otras partes.
- **`comun/cortes.py` (nuevo):** `video_parts(code)` (VC_<c>(n), si no VR_), `mp4_creation_time` (lee `moov/mvhd`
  del MP4 sin ffprobe; = ffprobe en los 9 VR, 0,03 s por archivo de 4 GB), `measure(code)` (hueco = inicio(k+1) −
  inicio(k) − (cuadros_VR(k) − 1)/f_r, f_r = 2,997; residuo de cierre por mtime), `save_cut`/`load_cuts`,
  `split_info(code, manual_gaps, remeasure)` (manual > cortes.json > medido ahora y guardado), `part_starts`
  (inicio(k+1) = inicio(k) + cuadros_VC(k) − 1 + round(hueco·f_r), misma regla que `robots.py`). Avisos: VC(k≥2)
  con cuadros ≠ VR(k); VC(1) recortado al inicio (no afecta); cierre anormal.
- Los VC_ no traen creation_time y VC(1) tiene 41 cuadros menos que VR(1) (recorte del LED) ⇒ la medición usa los VR_.
- **`comun/video.PartedVideoSource`:** varias partes en un eje de cuadros (`locate`, `gap_at`; `read` → None en el hueco).
- **FSRScope:** `paths.find_video` también encuentra `VC_<c>(1)`; `_open_video` arma `split_info` y usa
  `PartedVideoSource`; video_view muestra «Sin video: hueco entre la parte k y la k+1» y «parte k/n, cuadro local»;
  pestaña Video → grupo «Video partido» (descripción, «Hueco automático», hueco manual `31.8; 12`, «Medir de nuevo en
  los originales»); `Sync.gaps_auto`/`gaps_s` en la config del ensayo. `TrialData.apply_split` recarga los robots con
  los mismos huecos (overlay alineado también con hueco manual).
- **`robots.load_robots(path, gaps=None, fr=None)`:** si cortes.json no tiene el ensayo, mide y guarda (Velocidades,
  MATLAB vía cortes.json). `herramientas/medir_corte.py` reescrito sobre `comun.cortes` (sin ffprobe; sin código = todos).
- **Verificado:** 30/10 16:00 → partes en 0 y 8692, video 12 184 cuadros = robots 12 184; hueco auto 31,79 s (real y con
  VR sintéticos de mismo creation_time/cuadros), manual 40 s → 8717; overlay de robots coincide en la parte 2; ensayo sin
  cortes sin cambios; Velocidades une con 94 cuadros de hueco.
- Pendiente: reconstruir los .exe de FSRScope/Velocidades; precisión ±1 s (3 cuadros): ajustar a mano si se ve corrido.
- **Corrección (mismo día, «no se actualizó»):** la config del 30/10 16:00 tenía `sync.video_path` elegido a mano
  (`VS_…(1).mp4`, de cuando FSRScope no encontraba video) y el video manual salteaba la detección. Ahora
  `cortes.sibling_parts(path)` junta las partes hermanas de un video manual `(n)` (VS_, VC_ o VR_) y `split_info(...,
  parts=)` las ubica con el mismo hueco. VS(k) = VC(k) en cuadros y tamaño (8598/3492, 610×610).
- **Aviso al abrir a mano:** «Abrir video…» con una parte `(n)` muestra un mensaje (parte k de n, partes cargadas, hueco
  y su origen) y pasa a la pestaña Video; si faltan las otras partes en la carpeta, advierte. Al abrir un ensayo
  partido la barra de estado lo indica. Probado con los archivos reales en tu PC (lógica sin Qt) y la GUI offscreen.

## 2026-11-12 — Nomenclatura de modos: QR/QL → AH, R → AL (HO reservado)

**Pedido del usuario:** todos los `QR` son en realidad `QL` (giran antihorario con el motor izquierdo); propuso usar una
nomenclatura más clara. `QR`/`QL` eran ambiguos (¿motor o sentido?) y `R` se confundía con «right» y con el prefijo `R_`.
- 110 renombres (`datos/`, `informes/`, videos VR/VC/VS, sesiones, trayectorias, configs, `generado/<código>/`), 45
  archivos de texto (códigos `2[2-7](QR|QL)` → `AH`, `2[2-7]R` → `AL`, tokens sueltos `QR`/`QL`; `,R,` y `hh:mm R` en
  `resumen_ensayos.csv` y `resumen_modos.csv`), 27 reemplazos puntuales y `src_path` de las 9 sesiones `.npz`.
  En las configs de FSRScope `"R"` es la resistencia (no se tocó). Caché de MATLAB borrada (se regenera).
- Código: `estilo.MODE_COLOR = {AH azul, HO naranja, AL aqua}`; `comparar_modos` `MODE_NAME`/orden AH, HO, AL;
  `verificar_cinematica.EXPECTED_SPIN = {AH: antihorario, HO: horario}`; MATLAB `colores_ensayos` (por modo),
  `fig_comparar_modos` (`orden_modos = {'AH','HO','AL'}`).
- Textos corregidos: «solo el motor derecho» → «solo el motor izquierdo» (conclusiones, discusión); README raíz con la
  tabla de modos; «otros modos (R, QZ)» → «(AL, HO)».
- Aparecieron archivos del 06/11 procesados por el usuario (`VA_/VP_20261106_1600_22AH_60`); sin registro R_ todavía.

## 2026-11-12 — MATLAB: comparación de varios ensayos (giro, circulación, MSD, capas, ocupación, modos)

- **Figuras nuevas** (port de `figuras/comparar_ensayos.py` y `comparar_modos.py`): `fig_giro_robots` (ω̄ o vueltas por
  robot ordenadas), `fig_omega_distribucion`, `fig_circulacion_tiempo` (Φ u Ω), `fig_msd` (α 1–20 s en la leyenda),
  `fig_densidad_radial` (r/R_c, todo/atasco/fluido), `fig_ocupacion` (paneles, escala hasta p99), `fig_comparar_modos`
  (cualquier campo del resumen agrupado QR/QL/R). `fig_velocidad_tiempo` con `estadistico` media|mediana|p90|p10.
- **`cargar_ensayo` (caché v3):** matrices cuadros × robots X, Y, VX, VY, S, Wr [°/s], TH, OBS. Video partido: identidad
  por vecino más cercano (greedy) entre el último cuadro de (1) y el primero de (2); θ de (2) continúa desde el último.
  `M.OBS = logical(...)` (en Octave `[]`+logical concatena a double y el indexado fallaba).
- **Funciones nuevas:** `percentil` (= numpy.nanpercentile, sin Statistics Toolbox), `rapidez_conjunto`, `radio_contacto`
  (q99,5 de r observados), `circulacion` (Φ con |v| > 1 mm/s y r > 0,3 R_c; Ω = Σ(x vy − y vx)/Σr²),
  `desplazamiento_cuadratico` (lags log hasta min(F/4, 20 min); pares que cruzan el hueco de un video partido excluidos
  por segmento). `resumen_ensayo` + `omega_media_signo`, `robots_antihorario/horario` (|ω̄| > 0,5), `Phi_circulacion`,
  `Omega_grupo`, `pared_pct` (r ≥ R_c − 16,5 mm), `alfa_msd`, `asim_dG`/`curt_dG` (ΔT de FSRScope).
- **Verificado contra `resumen_modos.csv` (24/09, 30/10 12:00, 30/10 16:00):** ω media 2,811 / −1,956 / 1,163 °/s, robots
  14/4, 5/13, 12/2, Φ 0,2119 / −0,1661 / 0,1555, pared 56,04 / 56,63 / 54,99 % — idénticos. α = 1,35 / 1,41 / 1,39.
  Los 25 scripts corren en Octave 8.4 (`parula` → `viridis` si no existe).

## 2026-11-12 — MATLAB: gráficos de presión

- **Figuras nuevas** (`software/matlab/figuras/`): `fig_presion_supervivencia` (P(G≥g), normalizable), `fig_presion_histograma`
  (clases log), `fig_deltaG_tiempo` (paneles por ensayo), `fig_deltaG_distribucion` (varios ensayos con un ΔT o un
  ensayo con varios ΔT; /σ, curva normal), `fig_asimetria_deltaT` (asimetría/curtosis/ambas vs ΔT, como el póster),
  `fig_presion_vs_robots` (mediana/media + IQR vs N o φ, color por modo), `tabla_presion` (+ CSV).
  `fig_presion_tiempo` rehecho: cualquier registro (también agosto sin video), eje video|sensor, marcar saturación.
- **`leer_presion` reescrito = FSRScope** (`comun/log_io` + `signal` + `stats`): grilla uniforme `step_s`, G = ADC
  interpolado·K (K firmware en auto, parámetros en manual), saturación (ADC ≥ FS−0,5 en la fila siguiente o
  CLIPSAT ≥ N), máscara recorte/exclusiones/saturación, ΔT y clases de la config. Devuelve G completo + `mascara`
  (`presion_valida(P)` = NaN fuera). Bordes de la interpolación fijos como `np.interp`.
- **Funciones nuevas:** `buscar_registros` (incluye la referencia 0 robots), `cargar_presion` (caché
  `cache/presion_<código>.mat`), `presion_valida`, `delta_g`, `momentos` (asimetría/curtosis insesgadas),
  `momentos_vs_deltaT`, `supervivencia`. `presion_en_cuadros` toma la muestra de grilla más cercana (como
  Velocidades). `colores_ensayos` indexa sobre registros ∪ trayectorias (mismo color en todas las figuras MATLAB).
  Caché de `cargar_ensayo` → versión 2.
- **Verificado en Octave contra Python (12 registros):** n, K, G media/desvío, % saturado, asimetría y curtosis de ΔG
  (2,5 s) y asimetría a 15 s idénticos en 9; en 3 la grilla difiere en 1 muestra final (el parseo del CSV cambia el
  último ulp del tiempo y el floor): diferencias ≤ 3e-5. Las 18 figuras corren y guardan.
- Advertencia en README: G absoluto de agosto (12 kΩ, base ~160 µS) no comparable con sept/oct; 24/09 con 50 kΩ manual.

## 2026-11-11 — MATLAB: un script por figura (`software/matlab/figuras/`, `funciones/`)

**Pedido:** las apps de comparación son difíciles de entender (mucha información, poca personalización) ⇒
scripts simples, uno por figura, con un bloque SETTINGS arriba (ensayos, nombres, colores, suavizado, límites,
textos, leyenda, tamaño en cm, guardar).
- **Figuras:** `fig_velocidad_tiempo`, `fig_rotacion_tiempo`, `fig_energia_tiempo` (total/tras/rot/ambas),
  `fig_presion_tiempo`, `fig_velocidad_y_presion` (un ensayo, 2 paneles, sin doble eje), `fig_histograma_velocidad`,
  `fig_pdf_velocidad`, `fig_ccdf_velocidad`, `fig_presion_vs_velocidad` (mediana + IQR por clase, ρ),
  `fig_barras_resumen` (cualquier campo de `resumen_ensayo`), `tabla_resumen` (+ CSV). Salida
  `informes/figuras/matlab/<archivo>.pdf/.png`.
- **Funciones:** `cargar_ensayos(filtros | 'todos' | {} = listdlg)`, `cargar_ensayo` (series por cuadro: t, V, W,
  V2, W2, v_ind observados, P; caché `software/matlab/cache/<código>.mat` invalidada por datenum+bytes de los
  orígenes, gitignored), `leer_csv` (textscan, sin readtable: MATLAB y Octave; nombres de columna saneados
  `timestamp(ms)` → `timestamp_ms_`), `leer_presion` (port de comparar_ensayos.m), `presion_en_cuadros`,
  `suavizar` (conv con NaN), `mediana_movil`, `atascos`, `energia`, `resumen_ensayo`, `colores_ensayos`
  (paleta de `comun/estilo.py` por índice del ensayo | 'modo' | propios), `nueva_figura`, `poner_leyenda`
  (clic oculta curva), `guardar_figura` (exportgraphics o print), `raiz_proyecto` (sin rutas fijas).
- **Verificado en GNU Octave 8.4 (los 11 scripts corren y guardan):** V media, % atasco, duración máx. y ρ(V,G)
  idénticos a Python (0,90414/0,928137/0,401742; 17,06/0/72,75 %; 380/2963 s; −0,384/−0,236/−0,417).
  **No probado en MATLAB** (sintaxis compatible R2019b+; `h = []; h(end+1) = plot(...)`).
- `comparar_ensayos.m` queda como versión anterior (sin cambios).

## 2026-11-11 — Reorganización de software/: 4 apps con .exe, biblioteca común, figuras, empaquetado

**Pedido:** apps bien separadas, cada una empaquetable como .exe, y un lugar para los gráficos (scripts de
figuras + app de comparación). Estructura vigente (detalle en `software/README.md`):

| Antes | Ahora |
|---|---|
| `software/fsrscope/core/*` | `software/comun/*` (+ `comun/qt/`: `worker.py`, `widgets.py` dspin/note, `repo.py`) |
| `fsrscope/main.py` | `fsrscope/app.py` (+ `__main__.py`) |
| `fsrscope/velocidades.py`, `gui/vel_*.py` | `velocidades/app.py`, `velocidades/gui/` |
| `vidfetch/main.py` | `vidfetch/app.py` |
| `fsrscope/procesar_lote.py` | `herramientas/procesar_lote.py` (lógica en `comun/lote.py`) |
| `vidfetch/tools/*`, `analisis_video/medir_corte.py` | `herramientas/` |
| `analisis_video/{generar_informe,comparar_ensayos,comparar_modos,figuras_metodo}.py` | `figuras/` |
| `fsrscope/docs/*.xlsx` | `software/docs/` |
| `*/requirements.txt` | `software/requirements.txt` (único) |
| — | `comparador/` (app nueva), `figuras/plantilla.py`, `comun/estilo.py`, `empaquetado/` |

- **Imports absolutos desde `software/`** (`from comun.X`, `from vidfetch.core.X`, `from fsrscope.gui.X`); antes
  cada app usaba paquetes top-level `core`/`gui` que chocaban entre sí (los scripts hacían sys.path hacks).
  `app.py` agrega `software/` al path si se corre como script. Grafo: vidfetch autónoma; fsrscope, velocidades,
  comparador → comun; figuras/herramientas → comun + vidfetch.core.
- **`comun/paths.py`:** raíz del repo = `PRESION_REPO` > subir desde el .exe (congelado) o desde el archivo >
  carpeta recordada en `~/.proyecto_presion.json` > cwd; válida si tiene `datos/presion` o `datos/video`.
  `set_repo_root()` rebindea todas las rutas (+ `VEL_CONFIG_DIR`, `SUMMARY_PATH`, `CUTS_PATH`; `mobility` y
  `summary` ya no copian rutas al importar). `comun/qt/repo.ensure_repo()` pide la carpeta si no la encuentra
  (antes de importar las ventanas). `discover_trials(root=None)`, `code_label()`. `summary.date_key` sin la
  heurística día/mes.
- **Comparador (`comparador/`):** port de `comparar_ensayos.m` con parámetros comunes a todos los ensayos.
  `core.py` (curvas por ensayo vía `MobilityData` + overrides, clases comunes, G vs V̄ mediana + IQR con clases
  vacías = NaN, Spearman), `exportar.py` (matplotlib con `comun.estilo`, ancho columna/página/póster),
  `gui/window.py` (pestañas V̄, ⟨|ω|⟩, energía, histograma, P(v), 1−F, G vs V̄, resumen; cálculo en hilo
  `LatestJobRunner`, caché de `MobilityData`; QSettings «ITBA/Comparador»). Verificado: resumen = `resumen_ensayos.csv`
  (dif 0); ρ(V̄,G) −0,38 / −0,24 / −0,42 (24/09, 30/10 12:00, 30/10 16:00), como el .m.
- **`comun/estilo.py`:** paleta categórica de 8 (validada CVD; contraste < 3:1 en aqua/amarillo/magenta ⇒ leyenda +
  tabla), color fijo por ensayo según su índice en la lista completa (no por selección), trazo como 2.ª
  codificación > 8; `MODE_COLOR` (QR azul, QL naranja, R aqua; `comparar_modos.py` lo importa); `mpl_rc`,
  `figsize`, `save`.
- **Empaquetado:** `empaquetado/construir.py [apps] [--onefile]` (+ `construir.bat`, `requirements-build.txt`,
  `lanzadores/lanzar_<app>.py` — no pueden llamarse como el paquete, se autoimportan —, `iconos/*.ico` +
  `generar_iconos.py`). onedir por defecto (onefile descomprime ~400 MB por arranque). Excluye módulos Qt no usados;
  trackpy/matplotlib fuera de FSRScope y Velocidades; `--collect-submodules trackpy` en VidFetch. Salida
  `empaquetado/dist/<App>/` (gitignored, con `build/` y `*.spec`). Probado en Linux (PyInstaller 6.22, Py 3.13):
  las 4 congeladas arrancan, encuentran `datos/` subiendo desde el ejecutable y cargan ensayos; fuera del repo
  muestran el diálogo. Tamaños Linux: VidFetch 619 MB, FSRScope 586, Comparador 406, Velocidades 381. **No probado
  en Windows.**
- **Verificación:** las 4 apps desde fuente (offscreen) y congeladas (Xvfb); `procesar_lote` nuevo vs código anterior
  en 24/09 y 30/10 12:00: dif 0; `velocidades --resumen` = CSV existente; `comparar_modos` corre; `--help` de todos
  los scripts. `comparar_modos.py:430` ya no exige Python ≥ 3.12.
- Rutas actualizadas en READMEs (raíz, software, cada app, figuras, herramientas, informes, datos/video) y en
  `informes/aplicacion/secciones/{introduccion,metodologia,procedimiento}.tex`, `informes/ensayos/informe_ensayos.tex`.
  Las secciones históricas de este archivo conservan las rutas viejas (ver tabla).
- **Pendientes:** construir los .exe en Windows (`construir.bat`) y probarlos; commit (`git add -A`); `software/matlab/
  comparar_ensayos.m` sigue con `carpeta = C:\Users\dylan\Desktop\...`; config 24/09 con R_FEEDBACK 50 000 Ω
  (G ×0,1, ver 06/11) sigue sin confirmar; el `P_20260924` guardado no coincide con la config actual (regenerar
  con `herramientas/procesar_lote.py` si corresponde).

## 2026-11-11 — Código de fecha pasado a `AAAAMMDD` (orden cronológico)

- Antes: año-día-mes (`20262409` = 24/09) → por nombre el 30/10 quedaba antes que agosto. Ahora
  **`AAAAMMDD_HHMM_XXYY_TT`** en todo el repo. Mapeo: `20262409→20260924`, `20262509→20260925`,
  `20263010→20261030`, `20260611→20261106` (VR del 06/11, sin procesar). Agosto ya estaba bien.
- Renombrados archivos de `datos/`, `informes/ensayos/{figuras,generado}`; contenido de py/tex/md/json/csv;
  `src_path` dentro de los `VA_*.npz` (reescritos y verificados). Las secciones de abajo ya usan los códigos nuevos.
- El commit «Programa de procesado» (16:26 UTC) volvió a traer archivos con nombres viejos (configs, `VA_…1100…`,
  velocidades, CLAUDE.md): se tomó su contenido como vigente y se renombró; `VA_20263010_1100` era idéntico salvo
  `src_path` → borrado.

## 2026-11-06 (noche) — `software/matlab/comparar_ensayos.m`: superposición de ensayos en MATLAB

- Elige varios `VP_*_robots.csv` (diálogo o lista `archivos`); une `(1)/(2)` con `cortes.json` (t₂ + t_fin₁ + hueco).
  Una ventana por gráfico: V̄(t), ⟨|ω|⟩(t), E total, E tras/rot, histograma (fracción, clases comunes), P(v),
  1−F(v), **G vs V̄** (mediana de G por clase de V̄, ambas suavizadas 30 s, clases ≥ 30 cuadros) y **V̄ y G vs t**
  por ensayo (doble eje, atascos sombreados). Leyendas con clic → muestra/oculta todas las curvas del ensayo
  (Tag = etiqueta); `ocultar` = ensayos ocultos al inicio. Tabla en consola (+ CSV si `guardar_figuras`).
- Presión como FSRScope: t0 = primera fila válida, desfase = fin del LED (o manual de la config), recorte y
  exclusiones de la config, G del firmware o ADC·K si la calibración es manual (aviso si difiere > 2 %).
  Verificado contra FSRScope: desfases idénticos en los 7 ensayos, G dif. relativa ≤ 6e-6.
- Spearman V̄–G (30 s): −0,08 a −0,45 en los 7 ensayos (más velocidad ↔ menos presión).
- **Hallazgo:** `datos/presion/config/20260924_1600_22AH_60.json` tiene calibración manual con R_FEEDBACK = 50 000 Ω;
  el firmware registró K = 0,8563 µS/cuenta (= 5 kΩ, lo documentado) ⇒ G de FSRScope ×0,1 para 24/09 (y en
  resumen_ensayos.csv). Probable cero de más: pendiente que el usuario lo confirme/corrija.

## 2026-11-06 (tarde) — velocidades.py: media móvil global, ⟨|ω|⟩(t), energía cinética, ventanas aparte

- **Origen:** script de MATLAB del usuario (V̄(t), histograma, PDF, 1−F); se revisó (paneles 2–4 usaban |v|
  individual, no V̄; etiqueta 1−P(v≤V) invertida; 1−F en lineal) y se pasó todo a la app.
- **`VelSettings`** nuevos: `smooth_s` (30 s, media móvil de todos los gráficos de tiempo, cruda en gris),
  `dist_smoothed` (distribuciones de V̄ suavizada; solo para comparar), `mass_g` (0 = por unidad de masa),
  `k_inertia` (0,5). `from_dict` genérico.
- **`robots.py`** lee `omega_rad_s` (o `omega_deg_s`) → `Robots.omega_rad_s`, también en videos partidos.
- **Energía** (`MobilityData.energy`): E_tras = N·⟨½v²⟩, E_rot = N·⟨½kR²ω²⟩ por cuadro (König: la órbita ya
  está en v); [mm²/s² = µJ/kg] o ×m[g] → nJ. Rot/tras = 2,5–2,9 con k = 0,5 (R·|ω| ≈ 1,5 mm/s > |v| típica).
  Piso de ruido de ω (robots quietos en atasco 30/10 16:00): ω rms 0,62 °/s → e_rot 0,008 mm²/s² (< 0,5 %).
  En el atasco de 30/10 16:00 la rotación vuelve a subir desde min ~55 con traslación ~0 (robots girando
  en el lugar).
- **GUI:** pestañas nuevas ⟨|ω|⟩(t) y Energía cinética; botón «Ventana aparte» en cada gráfico
  (`DetachedWindow`, vuelve a su pestaña al cerrar); grupos laterales «Visualización» y «Energía cinética»;
  panel lateral con scroll. Usar ⟨⟩ y no `<|ω|>` en textos (Qt/pyqtgraph lo toman como HTML y lo borran).
- **Resumen:** columnas `omega_abs_media_deg_s`, `energia_unidad`, `masa_g`, `k_inercia`, `E_traslacion_media`,
  `E_rotacion_media`, `E_total_media`, `E_rot_sobre_E_tras`.
- Verificado contra el cálculo del script: 30/10 12:00 ΣE_tras 18,2 y ΣE_rot 45,7 µJ/kg (= 22 × 0,827 / 2,075).

## 2026-11-06 — App de velocidades `software/fsrscope/velocidades.py` (FSRScope queda solo para presión + video)

**Pedido del usuario:** los gráficos de velocidad dentro de FSRScope eran demasiada información junta ⇒
FSRScope volvió exacto a su versión anterior (main_window, panels, plots, session, export, stats, settings,
procesar_lote) y las velocidades van en una interfaz aparte que comparte `core/`.

- **Archivos nuevos:** `velocidades.py` (interfaz; `--resumen [CSV]` sin interfaz), `gui/vel_window.py` (lista de
  ensayos con trayectorias + umbral + ventana a la izquierda; una pestaña por gráfico), `gui/vel_plots.py`
  (V̄(t), V̄ y G doble eje, umbral arrastrable, histograma, P(v), 1−F(v), mapa de ocupación; opciones en una
  barra sobre cada gráfico), `core/mobility.py` (`Mobility`, `VelSettings`, `MobilityData`, atascos,
  distribuciones, ocupación, G por estado), `core/summary.py` (resumen por ensayo). Pestaña «Resumen de
  ensayos» muestra la tabla del CSV.
- **Compartidos con FSRScope:** `core/robots.py` (lee x_mm/y_mm/status, filas contiguas por cuadro, `v_mean`,
  une `VP_<c>(1)/(2)` con `cortes.json` por asignación húngara) y `core/paths.find_trajectories` (devuelve la
  parte (1)) ⇒ FSRScope ahora también encuentra las trayectorias del 30/10 16:00.
- **Configuración separada:** `datos/video/config/<código>.json` (umbral, ventana en min de video, opciones de
  gráficos). De `datos/presion/config/` solo se lee (sincronía, calibración, recorte, exclusiones para G).
- **Eje X:** minutos de video; G se ubica con t_video = t_sensor − desfase (FSRScope).
- **Criterio de atasco:** estadístico (media/mediana/p90 entre robots) → mediana móvil `smooth_s` → < umbral
  ≥ `min_duration_s`. Default media 0,35 mm/s, 30 s, 20 s: coincide con p90 < 0,52 en 98,5–100 % de los
  cuadros de los 7 ensayos (0,30 y 0,40 coinciden menos). Runs separados solo por hueco de video se unen.
- **Convenciones:** V̄ incluye interpolados (N constante); «media de cada robot» e «individual» solo observados.
  G entra en la ventana de velocidades ∩ máscara de FSRScope. Mapa: robots/cm² promedio, celdas 5 mm, vista
  del observador (él en y = −R). G < 1e-3 µS oculto en log (redondeo del remuestreo, hay G ~1e-14).
- **Resumen** `datos/resumen_ensayos.csv` (7 ensayos): atasco 17,1 / 3,3 / 7,3 / 4,8 / 0 / 0,5 / 72,7 %; máx.
  380 s (24/09, = 382 s de los informes) y 2963 s (30/10 16:00 a través del corte). G media atasco ≫ flujo.
- **Verificado:** P_ de FSRScope idénticos al código anterior; ventana 10–40 min = 5401 cuadros.
- **Limitación:** en el ensayo partido la superposición de robots sobre el video (FSRScope) solo coincide con
  la parte (1).

## 2026-11-06 — Ensayos del 30/10 (QL/R), video partido y comparación por modo

- **Video partido `20261030_1600_22AH_60(1)/(2)`:** hueco = **31,8 ± 1 s** (≈ 94 cuadros sin grabar) entre el
  último cuadro de (1) y el primero de (2). Método: `creation_time` del MP4 (inicio, 1 s) + cuadros/f_r
  (`software/analisis_video/medir_corte.py` → `datos/video/cortes.json`). Controles: VC(1) termina en el último
  cuadro de VR(1) (template matching 0,998, recorte 1:1, solo se cortó el inicio, 41 cuadros); en los 6 VR
  completos `mtime − inicio − cuadros/f_r` = −1,0…+0,3 s; VR(1) da +25,5 s (cierre anormal: ~25 s finales
  perdidos). Robots casi quietos a través del corte (desplazamiento mediana 0,25 mm, máx 13,6 mm) ⇒
  identidad por asignación húngara sin ambigüedad (cociente 1.º/2.º vecino ≤ 0,41). El fin de la actividad
  en G (4070 s) cae 3 s antes del fin predicho de (2) (4073 s): consistente, pero no es ancla (en 1100/1200
  los robots siguieron ~90–100 s tras cortar la cámara).
- **f_r = 2,997 exacto** (30000/1001/10) según los metadatos; `comparar_modos.py` lo usa para el eje de
  tiempo/sincronía (con 3,0 el desfase acumulado es ~4 s a los 67 min). Velocidades de los VP_ sin tocar (0,1 %).
- **`software/analisis_video/comparar_modos.py` (nuevo):** une partes con hueco NaN (`status = sin video`),
  θ de la parte 2 continúa desde el último θ; presión cruda (`fsrscope.core.log_io`, K del firmware) entre
  inicio y fin del video. Salida `informes/ensayos/generado/modos/`: `series_tiempo`, `distribuciones`,
  `giro_circulacion`, `ocupacion`, `sensor` (G vs movilidad + asimetría ΔG), `resumen_modos` (png/csv),
  `corte_<código>.png`, `serie_<código>.csv`. Colores por modo (QR azul, QL naranja, R aqua); sin doble eje.
- **Resultados (7 ensayos, 22 robots):**
  - **QL gira antihorario** (ω media +5,3 / +1,2 °/s; 18/0 y 12/2 robots antihorario/horario; Φ +0,25/+0,16),
    igual que QR. Verificado a ojo en el VC crudo (robot 5, 1100: LED 3→1 h en 3 cuadros) y la escena no está
    espejada (misma disposición del laboratorio que 24/09). **Pendiente: confirmar qué programa es QL.**
  - **R:** ω media −2,0 / −1,0 °/s (13 y 10 robots horario), Φ −0,17 / −0,09, **0 atascos**, |v| mediana 0,67.
  - El signo de Φ sigue al signo de la ω media en los 7 ensayos.
  - **1600 QL:** a los 18,0–18,6 min la movilidad colapsa (|v| mediana 0,77 → 0,1 mm/s) y G salta de ~6 a
    ~1000 µS; queda así hasta el final (atasco de ≥ 49,5 min, 73 % del ensayo). 20 robots con giro neto 0
    durante 47 min; solo 12 y 15 siguen girando (−49 y +31 vueltas); el robot 3 queda contra la pared en
    φ ≈ 295°. Misma firma que el atasco de 382 s del 24/09 (20 quietos, 2 girando). Antes del atasco:
    |v| 0,77, ω +4,6 °/s, Φ +0,35. **Pendiente: mirar el video ~min 18 (¿atasco real o robots detenidos?).**
  - 1100 QL: atasco de 3 min al inicio con G ~100–1000 µS. Tiempo en la capa de la pared 55–57 % en todos.
  - Asimetría de ΔG fuertemente negativa solo en ensayos con atascos/eventos grandes (24/09, 1100 QL, 1430 R).
- **Ubicación del sensor por correlación (robot en el sector vs log G):** no robusta; solo 30/10 R ×2 y 1600
  QL coinciden en ~285–295°. Descartada de las figuras: medir la posición física.
- Cuadros de verificación en `datos/video/verificacion/corte_20261030_1600/` (corte y giro).

## 2026-10-09 — Orientación: el video NO está espejado; vista rotada 180°

**Corrección del usuario:** en modo `QR` los robots giran **antihorario** (solo motor derecho). El "giran a
la derecha" anterior era por el motor, no horario. Verificado en el video crudo (robot 6: el clip va de las 3
a las 12). ⇒ la suposición "video espejado horizontal" (08/10) era **falsa** e invertía y, θ, ω, v_t, φ.
El observador está parado en el borde superior del video (y_px = 0) mirando hacia y_px = 2160 (VR 3840×2160).

- **`core/orientation.py` (nuevo):** claves `no | rot180 | horizontal | vertical`; signos (sx, sy, s_rot) =
  (+,+,+) | (−,−,+) | (−,+,−) | (+,−,−); `image`, `points` (involutivo: sirve para clics), `vectors`,
  `from_frame`. Export: x = s·sx·(X−Xc), y = −s·sy·(Y−Yc). Con rot180: x = −s(X−Xc), y = +s(Y−Yc).
- **VidFetch:** `KinematicsParams.mirror` (nombre conservado por compatibilidad) = orientación, por defecto
  **rot180**. Combo "Orientación de la escena". La vista de Seguimiento, el video exportado (`annotator`,
  `draw_oriented`) y el recinto (`arena.oriented`) se dibujan sobre la imagen ya orientada (rótulos derechos);
  `_on_click` convierte display→imagen con `ori.points`. Análisis siempre sobre la imagen original.
  CSV: columna `orientacion` (antes `espejo`); `_info.json`: `orientacion`, `orientacion_descripcion`.
- **Herramientas:** `reexportar.py --orientacion` (alias `--espejo`); `verificar_cinematica.py` orienta las
  imágenes y controla ω contra el giro programado (`EXPECTED_SPIN = {"QR": "antihorario"}`,
  `--giro-esperado`); `verificar_giro.py` orienta los recortes; `generar_informe.py` dibuja la captura sobre la
  imagen orientada; FSRScope `Sync.view = "rot180"` (antes `mirror: bool`), configs de `datos/presion/config`.
- **Datos regenerados (exacto):** respecto de los CSV del 08/10: x, vx, r, |v| iguales; y, vy, θ, ω, v_t, φ,
  vel_dir cambian de signo (diferencia 0). ω media +2,81 / +2,62 / +3,35 °/s; 14 robots antihorario, 8
  contrarrotan (horario); Φ = +0,21 / +0,20 / +0,25 (circulación antihoraria). Capas, rapideces, atascos y
  escala sin cambios. Pared: contrarrotantes 64,9/56,7/74,7 % vs programados 51,7/57,8/45,4 %. Macro nueva
  `PccwCw` (% del tiempo antihorario de los que giran horario en neto).
- **Figuras:** `atascos.png` (cada panel rotado), `recinto_movimiento.png` (Δy cambia de signo: el anillo se
  aleja ~2 mm del observador los primeros 15 min), capturas y ocupación regeneradas. Figuras de método f1–f9
  del informe de la aplicación regeneradas en la vista del observador con `software/analisis_video/figuras_metodo.py`
  (primer minuto de 24/09; f2 cuadro 160: 25 candidatos, 22 aceptados 0,85–1,00, 3 rechazados 0,72–0,81; f4 robot 8,
  hueco 60–89, desvío 6,3 mm sin ancla / 3,4 con ancla; f5 robot 5; f6 robot 12, Δθ +58,7° q 0,79, conjunta +61,8°;
  f7 robots 5 y 8; f8 cuadro 90). Docs de Claude «Detección de robots…» y «Seguimiento de robots — informe técnico»
  actualizados (figuras, sistema de coordenadas, columnas, ejemplos).

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
  panel C = 6 robots ampliados ×5 con centro exportado vs centro independiente (borde del cuerpo: 180 rayos,
  paso oscuro→claro subpíxel, círculo Kåsa radio libre + MAD); cuadrícula mm del recinto en todos los paneles
  (A 10 mm, B 5 mm, C 1 mm); salidas `cinematica_<c>.png`, `_ejes.png`, `_centros.png`, `.txt` (5 controles).
  Resultado en los 3 ensayos: transformación 0,0005 mm; ∫v vs Δpos 10 s mediana 0,13 mm (2,5–2,8 %);
  v vs diferencia finita cruda r = 0,96, pendiente 1,05; centro vs borde mediana 0,71–0,74 mm (p90 1,4),
  D cuerpo medido 33,03–33,05 mm, sesgo radial ≤ 0,3 % r. Hough descartado como referencia (mediana 1,7 mm,
  radios erráticos). Pendiente: pruebas físicas (regla, flecha/letra, velocidad cronometrada).
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
- `VP_20260924_1600_22AH_60_robots.csv` había sido sobrescrito con el resumen por robot (22 filas): renombrado a `_resumen.csv` y trayectoria completa regenerada desde `VA_…npz` con `TrackingSession.load → run → to_dataframe` (265 518 filas × 25 col.); giro total y rapidez media coinciden con el resumen (|Δv| < 1e-5 px/s).

## 2026-10-08 — Material didáctico: detección + v + ω

- `informes/aplicacion/deteccion_cinematica.xlsx`: rehace con fórmulas (43k, 0 errores en LibreOffice) la detección, v y ω
  del robot 3, ensayo `20260924_1600`, cuadros 6034/6035 (5998–6092 para v y ω). Hojas: Parametros (nombres definidos),
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

## 2026-10-08 — Video espejado y análisis de los 3 ensayos (SUPERADO el 09/10: el video NO está espejado, ver arriba)

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
  `20260924_1600`: 12105 cuadros / 4055.1 s = 2.985; `20260925_1230`: 9907 / 3368.4 s = 2.941;
  `20260925_1500`: 11038 / 3699.5 s = 2.984 → consistente con time-lapse ×10 (`f_r` = 2.997).
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
- (Superado el 11/11: el código de fecha es `AAAAMMDD`.)

## 2026-09-24 — Saturación del ADC en `R_20260924_1600_23AH_60.csv` y ajuste de `R_FEEDBACK`

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
`23AH`, `23QZ`, `23AL` (23 robots, cada uno de los 3 modos).

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
`R_20260824_1430_25AH_30.csv` si esa corrida fue "todos a la derecha").
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

**Validado con:** árbol sintético con el formato nuevo (`23AH`, `23QZ`,
`23AL`, con y sin prefijo `R_`, headers en mayúscula/minúscula mezclados) y
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
