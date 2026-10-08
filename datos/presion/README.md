# Datos de presión (sensor FSR)

| Carpeta | Contenido |
|---|---|
| `crudos/` | `R_<código>.csv`: registro del sensor a 20 Hz (tiempo en s, ADC, G, R, envolvente, contadores de saturación, columna `LED` con el pulso de sincronización de 5 s al inicio) |
| `procesados/` | `P_<código>.csv`: salida de `software/fsrscope` (G remuestreada, ΔG, asimetría vs. ventana, función de supervivencia; columnas elegibles) |
| `config/` | `<código>.json`: parámetros de FSRScope de cada ensayo (calibración, recorte, exclusiones, sincronía, gráficos, columnas) |
| `referencia/` | mediciones sin robots o de calibración (arena vacía, sala vacía) y procesados antiguos sin código de modo |

Los nombres siguen el código de ensayo descripto en el `README.md` de la raíz. El registro
`R_20260824_1400_00_07.csv` (0 robots) es una medición de prueba sin modo de movimiento.
