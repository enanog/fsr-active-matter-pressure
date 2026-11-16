# Datos de presión (sensor FSR)

| Carpeta | Contenido |
|---|---|
| `crudos/` | `R_<código>.csv`: registro del sensor a 20 Hz (tiempo en s, ADC, G, R, envolvente, contadores de saturación, columna `LED` con el pulso de sincronización de 5 s al inicio) |
| `config/` | `<código>.json`: parámetros de FSRScope de cada ensayo (calibración, recorte, exclusiones, sincronía, gráficos, columnas) |
| `calibracion.csv` | R_FEEDBACK de cada registro (prefijo de código; gana el más largo); de acá sale el factor de G en MATLAB |

`crudos/` también tiene los registros de agosto y las mediciones de referencia (arena vacía `Medicion Vacio.csv`,
sala vacía `20260827_1534_ROOM_EMPTY_PRE_26ROBOTS_30MIN.csv`, procesado antiguo `20260827_1534_26_30.csv`).
`procesados/` (P_ de FSRScope) se crea al exportar desde FSRScope o con `herramientas/procesar_lote.py`.

Los nombres siguen el código de ensayo descripto en el `README.md` de la raíz. El registro
`R_20260824_1400_00_07.csv` (0 robots) es una medición de prueba sin modo de movimiento.
