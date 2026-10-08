# VidFetch

Aplicación de escritorio (PySide6) para recortar videos de la arena y seguir N robots: posición,
velocidad, orientación acumulada θ y velocidad angular ω, en SI y en tiempo real.

```
pip install -r requirements.txt
python main.py
```

- `core/`: cálculo sin interfaz (detección, calibración, seguimiento, rotación, cinemática, video).
- `gui/`: interfaz (pestañas *Original*, *Recortar*, *Procesar*, *Seguimiento*).

Para los videos del proyecto: escala de tiempo **3 cuadros = 1 s real**, diámetro del robot
**35 mm** y **Video espejado: horizontal**. La documentación completa está en
`informes/aplicacion/informe_aplicacion.pdf`.
