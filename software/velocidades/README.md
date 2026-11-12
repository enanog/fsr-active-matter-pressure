# Velocidades

Movilidad de los robots de un ensayo a partir de las trayectorias de VidFetch
(`datos/video/trayectorias/VP_<código>_robots.csv`), con la presión del mismo ensayo sincronizada
como en FSRScope.

```
python software/velocidades/app.py                  # interfaz
python software/velocidades/app.py 20261030_1600    # abre directamente ese ensayo
python software/velocidades/app.py --resumen        # datos/resumen_ensayos.csv sin interfaz
```

Ejecutable: `software/empaquetado/dist/Velocidades/Velocidades.exe` (ver `software/README.md`).

Una pestaña por gráfico, con sus opciones arriba y un botón **Ventana aparte** (al cerrar la ventana
vuelve a su pestaña): V̄(t) (media de |v| entre robots por cuadro), ⟨|ω|⟩(t), energía cinética del
conjunto (Σ½mv² + Σ½Iω², I = k·m·R², por unidad de masa [µJ/kg] o en nJ si se carga la masa), V̄ y G,
umbral de atasco (línea arrastrable, atascos sombreados), histograma de velocidades medias, P(v),
1 − F(v), mapa de ocupación (robots/cm², todo / atasco / flujo) y **Resumen de ensayos** (una fila por
ensayo con los valores medios, también en `datos/resumen_ensayos.csv`).

- Todos los gráficos de tiempo llevan la misma media móvil (30 s por defecto, grupo «Visualización»)
  con la serie cruda en gris de fondo. Las distribuciones usan los datos sin suavizar; la casilla
  «Distribuciones de V̄ suavizada» existe solo para comparar.
- Atasco: el estadístico elegido (media por defecto), con mediana móvil de 30 s, por debajo del umbral
  (0,35 mm/s por defecto) durante ≥ 20 s; coincide con el criterio de los informes (p90 < 0,52 mm/s)
  en el ≥ 98,5 % de los cuadros de los 7 ensayos.
- Configuración propia (umbral, ventana en minutos de video, opciones de los gráficos):
  `datos/video/config/<código>.json`. De FSRScope solo lee la sincronía, la calibración, el recorte y
  las exclusiones (para G), sin escribir su configuración.

## Código

```
app.py             punto de entrada
gui/vel_window.py  ventana: lista de ensayos, parámetros, pestañas
gui/vel_plots.py   un gráfico por pestaña
```

El cálculo está en `software/comun/` (`mobility.py`: V̄, atascos, distribuciones, ocupación, energía;
`summary.py`: resumen por ensayo; `robots.py`: lectura de trayectorias y unión de videos partidos).
