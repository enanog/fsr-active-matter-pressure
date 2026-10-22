# Datos de video

Se versionan las sesiones (`sesiones/`, 54–64 MB) y las trayectorias (`trayectorias/`, 60–73 MB),
todas por debajo del límite de GitHub de 100 MB por archivo. Los videos (0,6–4 GB) no entran: se
transfieren por pendrive y se copian a mano en `originales/`, `recortados/` y `seguimiento/`, de las
que solo se versiona un `.gitkeep` para conservar la estructura (ver `.gitignore`).

| Carpeta | Contenido | Origen |
|---|---|---|
| `originales/` | `VR_<código>.MP4`: video de la cámara DJI fija sobre la arena, 3840×2160, H.264, *time-lapse* | cámara |
| `recortados/` | `VC_<código>.MP4`: recorte a la arena (~610×610 px); empieza al terminar el pulso LED del registrador | VidFetch, pestaña *Recortar* |
| `sesiones/` | `VA_<código>_analisis.npz`: candidatos, firmas de rotación, anclas manuales, recinto y parámetros | VidFetch, *Guardar análisis…* |
| `trayectorias/` | `VP_<código>_robots.csv`: una fila por robot y cuadro; posición en mm con origen en el centro del recinto (y hacia arriba), polares, distancia a la pared, velocidad, θ, ω, estado | VidFetch, *Exportar CSV (todos los robots)…* o `tools/reexportar.py` |
| `trayectorias/` | `VP_<código>_robots_info.json`: recinto (centro, radio, escala, movimiento, zoom), convenciones, κ | ídem |
| `trayectorias/` | `VP_<código>_robots_resumen.csv`: una fila por robot (rapidez, giro, ω, capa de la pared…) | ídem, *Exportar resumen…* |
| `seguimiento/` | `VS_<código>_seguimiento.mp4`: video con los robots marcados | VidFetch, exportar video de seguimiento |

Los videos **no están espejados**. El observador mira la arena desde el borde superior del video, así que
las sesiones y trayectorias de esta carpeta usan la orientación `rot180` (columna `orientacion` en los CSV):
imagen rotada 180°, x a la derecha del observador, y hacia la pared de enfrente, ángulos antihorarios
positivos. Hasta el 08/10 se exportaban como si el video estuviera espejado (`espejo = horizontal`), lo que
invertía y, θ y ω; los CSV actuales (09/10) ya están corregidos.

Las trayectorias actuales (09/10) se regeneraron con `tools/reexportar.py` (orientación rot180, ventana 5,
robot 33 mm, escala del recinto Ø 185 mm, recinto medido cada 30 cuadros). Respecto de las anteriores,
longitudes y velocidades son 13 % menores (la escala anterior, del anillo oscuro del robot, estaba 15 % alta).

## Ensayos

| Código | Original | Cuadros (VR / VC) | Duración real | Sesión y trayectorias |
|---|---|---|---|---|
| `20262409_1600_22QR_60` | 4,04 GB | 12105 / 12069 | 67,0 min | sí |
| `20262509_1230_22QR_60` | 3,30 GB | 9907 / 9881 | 54,9 min | sí |
| `20262509_1500_22QR_60` | 3,68 GB | 11038 / 11012 | 61,2 min | sí |

Al agregar un ensayo, sumar una fila (código, tamaño, cuadros, duración real y si ya se analizó).
