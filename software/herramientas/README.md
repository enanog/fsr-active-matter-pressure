# Herramientas (línea de comandos)

Se corren desde la raíz del repositorio; `--help` muestra todas las opciones.

| Script | Para qué |
|---|---|
| `procesar_lote.py` | genera todos los `datos/presion/procesados/P_<código>.csv` con la configuración guardada en FSRScope |
| `reexportar.py` | reexporta una sesión de VidFetch (`VA_*.npz`) a CSV sin interfaz: recinto, resumen, un CSV por robot |
| `verificar_cinematica.py` | control visual y numérico de posiciones, ejes y velocidades de un `VP_*.csv` contra el video |
| `verificar_giro.py` | recortes del video desgirados con θ para verificar la orientación acumulada |
| `medir_corte.py` | mide el hueco entre las partes de un video partido → `datos/video/cortes.json` |
