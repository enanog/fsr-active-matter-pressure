# VidFetch

Aplicación de escritorio (PySide6) para recortar videos de la arena y seguir N robots: posición,
velocidad, orientación acumulada θ y velocidad angular ω, en SI y en tiempo real. Las posiciones se
exportan con **origen en el centro del recinto** (x a la derecha, y hacia arriba, escena real), que se
detecta automáticamente en cada cuadro o se marca a mano; el diámetro interior del recinto fija la escala.

```
pip install -r requirements.txt
python main.py
```

- `core/`: cálculo sin interfaz (detección, calibración, seguimiento, rotación, recinto, cinemática, video).
- `gui/`: interfaz (pestañas *Original*, *Recortar*, *Procesar*, *Seguimiento*).
- `tools/reexportar.py`: reexporta una sesión `.npz` sin interfaz (recinto, CSV, resumen, un CSV por robot).
- `tools/verificar_giro.py`: verificación visual de θ sobre el video.

Para los videos del proyecto: escala de tiempo **3 cuadros = 1 s real**, diámetro del robot **33 mm**,
recinto **Ø 185 mm interior / 195 mm exterior**, **Video espejado: horizontal**, **Escala desde: Recinto**.

Exportaciones (pestaña *Seguimiento* → *Resultados*): CSV de todos los robots (largo o ancho), **un robot
con todas sus columnas**, un CSV por robot en una carpeta, resumen por robot, video anotado y sesión. Junto a
cada CSV se escribe `<nombre>_info.json` con el recinto, la escala y las convenciones.

Reexportar un ensayo sin interfaz (desde la raíz del repositorio):

```
python software/vidfetch/tools/reexportar.py datos/video/sesiones/VA_<código>_analisis.npz ^
       --video datos/video/recortados/VC_<código>.MP4 --espejo horizontal --ventana 5 ^
       --diametro-robot 33 --escala recinto --cuadros-por-segundo 3 ^
       --salida datos/video/trayectorias/VP_<código>_robots.csv --resumen --guardar-sesion
```

La documentación completa (método, columnas, comandos) está en `informes/aplicacion/informe_aplicacion.pdf`.
