# Informes

| Carpeta | Documento | Contenido |
|---|---|---|
| `aplicacion/` | `informe_aplicacion.tex` | La app VidFetch: usos, organización del código, formatos de archivo, bibliotecas y funciones usadas, escala de tiempo, método (detección, seguimiento, velocidad, rotación) con fragmentos de código, procedimiento y exportaciones. No depende de los datos. |
| `aplicacion/` | `deteccion_cinematica.xlsx` | Hoja de cálculo didáctica: detección de un robot, vector velocidad y ω con fórmulas sobre los píxeles de un cuadro real. |
| `ensayos/` | `informe_ensayos.tex` | Resultados de los ensayos filmados: datos, calidad del seguimiento, comparación entre ensayos, atascos, contraste con el sensor de presión y una sección por ensayo. |
| `comun/` | `preambulo.tex`, `config.tex` | Paquetes, macros y configuración compartida (título, autor, diámetro del robot, escala de tiempo). |

En `ensayos/`, el texto escrito a mano está en `secciones/` y el contenido calculado en
`generado/` (no editar: lo reescriben `software/analisis_video/generar_informe.py` y
`comparar_ensayos.py`). Las observaciones propias de cada ensayo van en
`generado/<código>/notas.tex`, que los scripts nunca sobrescriben.

Compilar desde la carpeta de cada informe con `latexmk -pdf <archivo>.tex` (o dos pasadas de
`pdflatex`).
