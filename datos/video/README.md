# Datos de video

Se versionan las sesiones (`sesiones/`, 54–64 MB) y las trayectorias (`trayectorias/`, 45–56 MB),
todas por debajo del límite de GitHub de 100 MB por archivo. Los videos (0,6–4 GB) no entran: se
transfieren por pendrive y se copian a mano en `originales/`, `recortados/` y `seguimiento/`, de las
que solo se versiona un `.gitkeep` para conservar la estructura (ver `.gitignore`).

| Carpeta | Contenido | Origen |
|---|---|---|
| `originales/` | `VR_<código>.MP4`: video de la cámara DJI fija sobre la arena, 3840×2160, H.264, *time-lapse* | cámara |
| `recortados/` | `VC_<código>.MP4`: recorte a la arena (~610×610 px); empieza al terminar el pulso LED del registrador | VidFetch, pestaña *Recortar* |
| `sesiones/` | `VA_<código>_analisis.npz`: candidatos, firmas de rotación, anclas manuales y parámetros | VidFetch, *Guardar análisis…* |
| `trayectorias/` | `VP_<código>_robots.csv`: una fila por robot y cuadro (posición, velocidad, θ, ω, estado) | VidFetch, *Exportar CSV (todos los robots)…* |
| `trayectorias/` | `VP_<código>_resumen.csv`: una fila por robot (rapidez media, giro total, ω media…) | VidFetch, *Exportar resumen…* |
| `seguimiento/` | `VS_<código>_seguimiento.mp4`: video con los robots marcados | VidFetch, exportar video de seguimiento |

Todos los videos son espejados respecto del eje vertical; las sesiones y trayectorias de esta carpeta
ya tienen la corrección aplicada (columna `espejo = horizontal` en los CSV).

## Ensayos

| Código | Original | Cuadros (VR / VC) | Duración real | Sesión y trayectorias |
|---|---|---|---|---|
| `20262409_1600_22QR_60` | 4,04 GB | 12105 / 12069 | 67,0 min | sí |
| `20262509_1230_22QR_60` | 3,30 GB | 9907 / 9881 | 54,9 min | sí |
| `20262509_1500_22QR_60` | 3,68 GB | 11038 / 11012 | 61,2 min | sí |

Al agregar un ensayo, sumar una fila (código, tamaño, cuadros, duración real y si ya se analizó).
