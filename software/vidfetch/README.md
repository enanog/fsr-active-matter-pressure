# VidFetch

Aplicación de escritorio (PySide6) para recortar videos de la arena y seguir N robots: posición,
velocidad, orientación acumulada θ y velocidad angular ω, en SI y en tiempo real. Las posiciones se
exportan con **origen en el centro del recinto** (x a la derecha, y hacia arriba, escena real), que se
detecta automáticamente en cada cuadro o se marca a mano; el diámetro interior del recinto fija la escala.

```
pip install -r software/requirements.txt
python software/vidfetch/app.py [video]
```

Ejecutable: `software/empaquetado/dist/VidFetch/VidFetch.exe` (ver `software/README.md`).

- `core/`: cálculo sin interfaz (detección, calibración, seguimiento, rotación, recinto, cinemática, video).
- `gui/`: interfaz (pestañas *Original*, *Recortar*, *Procesar*, *Seguimiento*).
- Herramientas de línea de comandos en `software/herramientas/`: `reexportar.py` (reexporta una sesión
  `.npz` sin interfaz: recinto, CSV, resumen, un CSV por robot), `verificar_giro.py` (verificación visual
  de θ sobre el video) y `verificar_cinematica.py` (verificación visual y numérica de posiciones, ejes,
  desplazamientos y velocidades del CSV contra el video;
  `datos/video/verificacion/cinematica_<código>.png`, `_ejes.png`, `_centros.png` y `.txt`).

Para los videos del proyecto: escala de tiempo **3 cuadros = 1 s real**, diámetro del robot **33 mm**,
recinto **Ø 185 mm interior / 195 mm exterior**, **Orientación de la escena: rotada 180°** (vista del observador, parado en el borde superior del video;
los videos no están espejados), **Escala desde: Recinto**.

**Detección recomendada: "Borde de la pila"** (pestaña *Procesar* → Método). El centro de cada robot es el
centro del borde brillante de su pila, medido en la imagen a resolución completa con precisión sub-píxel; funciona
con pilas plateadas y doradas y con los LEDs encendidos. Los huecos entre robots no tienen pila adentro y quedan
afuera solos (contraste < 11 niveles de gris contra 24–100 de los robots).

Reanalizar una sesión guardada con ese método, sin interfaz (desde `software/`):

```
python -m vidfetch.reanalizar ..\datos\video\sesiones\VA_<código>.npz --procesos 4
```

Rehace los candidatos, el seguimiento y una "segunda mirada" a los cuadros dudosos (`core/second_look.py`):
vuelve a medir sobre la imagen a los robots relajados, interpolados o con saltos de 1–3 cuadros. Guarda la
sesión anterior como `<nombre>_antes.npz`.

Los robots se numeran **desde 1** en la pantalla y en todos los CSV (columna `particle`, columnas `r01_…`).

Exportaciones (pestaña *Seguimiento* → *Resultados*): CSV de todos los robots (largo o ancho), **un robot
con todas sus columnas**, un CSV por robot en una carpeta, resumen por robot, video anotado y sesión. Junto a
cada CSV se escribe `<nombre>_info.json` con el recinto, la escala y las convenciones.

Reexportar un ensayo sin interfaz (desde la raíz del repositorio):

```
python software/herramientas/reexportar.py datos/video/sesiones/VA_<código>_analisis.npz ^
       --video datos/video/recortados/VC_<código>.MP4 --orientacion rot180 --ventana 5 ^
       --diametro-robot 33 --escala recinto --cuadros-por-segundo 3 ^
       --salida datos/video/trayectorias/VP_<código>_robots.csv --resumen --guardar-sesion
```

La documentación completa (método, columnas, comandos) está en `informes/aplicacion/informe_aplicacion.pdf`.
