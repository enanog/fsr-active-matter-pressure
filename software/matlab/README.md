# Figuras en MATLAB

Un archivo por figura. Cada uno tiene arriba un bloque **SETTINGS** con todo lo que se puede cambiar
(qué ensayos, suavizado, colores, ejes, textos, tamaño, guardar); se edita ese bloque y se corre con
**Run** (F5). No hay que tocar nada más.

```
software/matlab/
├── figuras/      un script por figura (abrir y correr)
├── funciones/    lectura de datos y utilidades que usan los scripts
├── cache/        copia rápida de cada ensayo (se crea sola, no se versiona)
└── comparar_ensayos.m   versión anterior: todas las figuras juntas
```

## Figuras

**Velocidad y movimiento** (ensayos con video)

| Script | Figura | Ajustes principales |
|---|---|---|
| `fig_velocidad_tiempo.m` | rapidez del conjunto vs t | media, mediana o percentil 90 entre robots; suavizado, serie cruda en gris, umbral, atascos sombreados |
| `fig_rotacion_tiempo.m` | ⟨\|ω\|⟩ vs t | suavizado |
| `fig_energia_tiempo.m` | energía cinética vs t | total / traslación / rotación / ambas, masa, k de inercia, log |
| `fig_histograma_velocidad.m` | histograma (fracción de muestras) | V del conjunto o \|v\| individual, clases, contorno o barras |
| `fig_pdf_velocidad.m` | densidad P(v) | clases lineales o logarítmicas, log Y, marcadores |
| `fig_ccdf_velocidad.m` | 1 − F(v) | normalizar por ⟨v⟩, log X / log Y |

**Comparar varios ensayos: giro, circulación, difusión y ocupación** (ensayos con video)

| Script | Figura | Ajustes principales |
|---|---|---|
| `fig_giro_robots.m` | ω media (o vueltas netas) de cada robot, ordenados | cuántos giran en cada sentido (se imprime) |
| `fig_omega_distribucion.m` | distribución de ω con signo (o \|ω\|) | rango, clases, log |
| `fig_circulacion_tiempo.m` | circulación colectiva vs t | Φ (−1 a 1) u Ω del grupo [°/s], suavizado |
| `fig_msd.m` | desplazamiento cuadrático medio MSD(τ) | pendiente α en la leyenda, guías de pendiente 1 y 2 |
| `fig_densidad_radial.m` | densidad de robots vs r/R_c (capas) | todo / atasco / fluido, eje en mm, marca de la capa de pared |
| `fig_ocupacion.m` | mapa de ocupación, un panel por ensayo | celda, todo / atasco / fluido, escala log, mapa de color |
| `fig_comparar_modos.m` | una magnitud agrupada por modo AH / HO / AL (un punto por ensayo + media) | cualquier campo del resumen |
| `fig_barras_resumen.m` | una magnitud por ensayo en barras | cualquier campo del resumen |
| `tabla_resumen.m` | tabla en la consola (+ CSV) | columnas a mostrar |

Campos del resumen (`funciones/resumen_ensayo.m`), para barras, modos y tabla: `V_media`, `V_desvio`,
`v_mediana_indiv`, `omega_media`, `omega_media_signo`, `robots_antihorario`, `robots_horario`,
`Phi_circulacion`, `Omega_grupo`, `pared_pct`, `alfa_msd`, `atasco_pct`, `n_atascos`, `atasco_max_s`,
`E_tras`, `E_rot`, `E_rot_sobre_E_tras`, `G_media`, `G_mediana`, `G_mediana_fluido`, `G_mediana_atasco`,
`asim_dG`, `curt_dG`, `rho_V_G`.

**Presión** (cualquier registro del sensor, también los de agosto sin video)

| Script | Figura | Ajustes principales |
|---|---|---|
| `fig_presion_tiempo.m` | G vs t | eje en minutos de video o del registro, suavizado, log, marcar saturación |
| `fig_presion_supervivencia.m` | P(G ≥ g) | normalizar por ⟨G⟩, log X / log Y |
| `fig_presion_histograma.m` | densidad de probabilidad de G | clases logarítmicas, normalizar |
| `fig_deltaG_tiempo.m` | ΔG(t) = G(t) − G(t − ΔT) | ΔT, un panel por ensayo o todos juntos |
| `fig_deltaG_distribucion.m` | densidad de ΔG | varios ensayos con un ΔT, o un ensayo con varios ΔT; normalizar por σ, curva normal |
| `fig_asimetria_deltaT.m` | asimetría (y/o curtosis) de ΔG vs ΔT | ΔT máximo, paso del barrido, una o dos curvas |
| `fig_presion_vs_robots.m` | G vs cantidad de robots, un punto por ensayo | mediana o media, rango intercuartil, eje N o fracción de área |
| `tabla_presion.m` | tabla de presión por registro (+ CSV) | ΔT de la asimetría |

**Velocidad y presión juntas**

| Script | Figura | Ajustes principales |
|---|---|---|
| `fig_velocidad_y_presion.m` | **un** ensayo: V arriba y G abajo, mismo eje t | colores, atascos sombreados, límites de cada panel |
| `fig_presion_vs_velocidad.m` | G mediana por clase de V | clases, mínimo de cuadros por clase, banda 25–75 %, nube de puntos, ρ |

## Ajustes que se repiten en todos

| Ajuste | Qué hace |
|---|---|
| `ensayos` | parte del código de cada ensayo: `{'20260924_1600', '20261030'}` (el segundo trae los cuatro del 30/10); `{}` abre una lista para elegir; `'todos'` = todos |
| | Cada ensayo tiene el mismo color en todas las figuras; con más de 8 ensayos los colores se repiten: usar `'modo'` o una lista propia |
| `nombres` | textos de la leyenda en el mismo orden; `{}` = automáticos (`24/09 16:00 · 22AH`) |
| `colores` | `{}` = paleta del proyecto (cada ensayo siempre del mismo color); `'modo'` = AH azul, HO naranja, AL verde; o una lista propia `{'#2a78d6', [1 0 0], 'k'}` |
| `suavizado_s` | media móvil en segundos (0 = datos crudos) |
| `lim_x`, `lim_y` | límites de los ejes, ej. `[0 60]`; `[]` = automáticos |
| `titulo`, `texto_x`, `texto_y` | textos (admiten `_{sub}`, `^{sup}`, `\mu`, `\omega`) |
| `leyenda` | posición: `'northeast'`, `'best'`, `'eastoutside'`, `'southoutside'`, …, `'ninguna'` |
| `ancho_cm`, `alto_cm`, `fuente`, `grosor` | tamaño real de la figura en el PDF (17 cm = ancho de página; 8,6 cm = una columna) |
| `guardar`, `archivo`, `formatos` | `guardar = true` escribe `informes/figuras/matlab/<archivo>.pdf` y `.png` |

En MATLAB, clic en una entrada de la leyenda oculta o muestra esa curva.

## Datos

- **Velocidades:** `datos/video/trayectorias/VP_<código>_robots.csv` (VidFetch). Un video partido
  `(1)/(2)` se une solo con el hueco de `datos/video/cortes.json`. **V media** = promedio de |v| de los
  robots en cada cuadro. **Atasco** = mediana móvil de 30 s de V por debajo de 0,35 mm/s durante ≥ 20 s
  (como en Velocidades).
- **Presión:** `datos/presion/crudos/R_<código>.csv`, procesado igual que FSRScope: grilla uniforme de
  50 ms, G = ADC·K (K del firmware, o de los parámetros si la calibración es manual), y la configuración
  guardada en FSRScope para cada ensayo (`datos/presion/config/<código>.json`): recorte, tramos excluidos,
  saturación, ΔT, sincronía con el video. ΔG(t) = G(t) − G(t − ΔT) es NaN si alguno de los dos extremos
  cae fuera de lo analizado; asimetría y curtosis con la corrección de sesgo (como Excel/pandas).
- **Ojo al comparar G entre días:** agosto (R_FEEDBACK 12 kΩ, G de base ~160 µS) y septiembre/octubre no
  están en la misma escala absoluta; la asimetría, la curtosis y las curvas normalizadas sí son comparables.
  El 24/09 se midió con 50 kΩ (G ×0,1 respecto de lo que logueó el firmware, que tenía 5 kΩ).
- **R_FEEDBACK de cada registro: `datos/presion/calibracion.csv`** (`codigo,r_feedback_ohm,nota`). Se edita a mano
  (Excel o cualquier editor; sin comas en `nota`). `codigo` puede ser el código completo o su comienzo
  (`20260924_1600`, `20260924`); gana la entrada más larga que coincida. Prioridad: lista > calibración manual
  de FSRScope > K del firmware (mediana G/ADC del registro). Valor vacío o registro ausente = siguiente en la
  prioridad. Cambiar un valor invalida solo la caché de ese ensayo. `tabla_presion` muestra el R usado
  (`R_FB_ohm`). FSRScope todavía no lee esta lista.
- La primera vez que se usa un ensayo se leen los CSV y se guarda una copia en `cache/`; después
  carga al instante. Si cambia un archivo de origen o la configuración de FSRScope, se rehace sola.
- **Verificado contra las apps de Python:** V media, % de atasco, duración máxima, ρ(V, G), ω media, robots que
  giran en cada sentido, circulación Φ y % de tiempo en la pared idénticos a `comparar_modos.py`; en los
  12 registros de presión, G media y desvío, saturación, asimetría y curtosis de ΔG idénticos (en 3
  registros la grilla tiene una muestra menos al final por redondeo al leer el CSV: diferencia ≤ 3·10⁻⁵).

## Hacer una figura nueva

Copiar el script más parecido, renombrarlo y cambiar el dibujo. Lo que se puede usar de cada ensayo
`D(i)` (ver `funciones/cargar_ensayo.m`): `D(i).t` [s], `D(i).V`, `D(i).W`, `D(i).v_ind`, `D(i).P`
(presión), por robot `D(i).X`, `.Y`, `.VX`, `.VY`, `.S`, `.Wr`, `.TH` (cuadros × robots), y las funciones `suavizar`, `presion_en_cuadros`, `atascos`, `energia`, `resumen_ensayo`.
Para presión: `R = cargar_presion({...})` y, de cada `R(i).P` (ver `funciones/leer_presion.m`), `P.t`,
`P.G`, `presion_valida(P)`, `delta_g(P, dT)`, `momentos(x)`, `momentos_vs_deltaT(P)`, `supervivencia(x)`.

Requiere MATLAB R2019b o posterior (sin toolboxes). También corre en GNU Octave 8 (sin el clic en la leyenda).
