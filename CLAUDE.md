# CLAUDE.md — Contexto de sesiones con Claude

Este archivo documenta las adiciones hechas por Claude al repo, para poder
retomar el contexto en conversaciones futuras (chat, Claude Code, etc.).

## Convención de nombres (vigente)

- `deltaT` — tamaño de ventana temporal, en segundos.
- `deltaG` — diferencia de conductancia `G(t) - G(t - deltaT)` (lo que antes
  se llamaba, incorrectamente, `deltaT`; se corrigió porque lo que se resta
  son valores de `G`, no de tiempo).

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
