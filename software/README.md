# Software

Cuatro aplicaciones de escritorio independientes (cada una con su `.exe`), una biblioteca común,
scripts de figuras y herramientas de línea de comandos.

```
software/
├── comun/          biblioteca compartida, sin interfaz (+ comun/qt: widgets comunes)
│   ├── paths.py        carpeta del proyecto, búsqueda de ensayos por código, rutas de datos/
│   ├── settings.py     configuración de FSRScope por ensayo (datos/presion/config/)
│   ├── log_io.py, signal.py, stats.py, export.py, session.py, lote.py   presión
│   ├── robots.py, mobility.py, summary.py                                trayectorias y velocidades
│   ├── video.py        lectura de cuadros
│   └── estilo.py       colores por ensayo/modo y estilo de matplotlib para informes
├── vidfetch/       App: recorte de video y seguimiento de robots (core/ propio + gui/)
├── fsrscope/       App: presión (G, ΔG, asimetría, supervivencia) con video sincronizado
├── velocidades/    App: movilidad de un ensayo (V̄, atascos, distribuciones, ocupación, energía)
├── comparador/     App: superposición de varios ensayos con parámetros comunes + figuras exportables
├── figuras/        scripts de figuras e informes (plantilla.py para figuras nuevas)
├── herramientas/   línea de comandos: procesar_lote, reexportar, verificar_*, medir_corte
├── empaquetado/    construcción de los .exe (PyInstaller)
├── docs/           planilla con la metodología de cálculo de la presión
├── matlab/         figuras en MATLAB: un script por figura con sus ajustes arriba (ver matlab/README.md)
└── requirements.txt
```

Dependencias entre paquetes (sin ciclos): `vidfetch` es autónoma; `fsrscope`, `velocidades` y
`comparador` dependen solo de `comun`; `figuras` y `herramientas` usan `comun` y `vidfetch.core`.

## Instalar y correr desde Python

```
pip install -r software/requirements.txt
python software/vidfetch/app.py [video]
python software/fsrscope/app.py [código]
python software/velocidades/app.py [código]
python software/comparador/app.py
```

(o, desde `software/`: `python -m vidfetch`, `python -m fsrscope`, …)

## Ejecutables (.exe)

En la PC con Windows, doble clic en `software/empaquetado/construir.bat`, o:

```
pip install -r software/requirements.txt -r software/empaquetado/requirements-build.txt
python software/empaquetado/construir.py                       # las cuatro
python software/empaquetado/construir.py fsrscope comparador   # algunas
```

Resultado: `software/empaquetado/dist/<App>/<App>.exe`, una carpeta por app (300–600 MB, se copia
entera; no se versiona). Cada `.exe` funciona sin Python instalado.

- **Carpeta del proyecto:** las apps buscan `datos/` subiendo desde donde está el `.exe`, así que dentro
  del repositorio no hay que configurar nada. Si se copia la carpeta de la app a otro lado, la primera
  vez pide la carpeta del proyecto y la recuerda (`~/.proyecto_presion.json`); también se puede fijar con
  la variable de entorno `PRESION_REPO`. VidFetch no la necesita.
- **Por qué una carpeta por app y no un único archivo:** con `--onefile` cada arranque descomprime
  ~400 MB a una carpeta temporal (10–30 s). Disponible igual: `construir.py --onefile`.
- Hay que reconstruir el `.exe` después de cambiar el código (la configuración y los datos no: se leen de
  `datos/` en cada arranque).
- Íconos: `empaquetado/iconos/*.ico` (regenerables con `generar_iconos.py`).

## Convenciones

- Código de ensayo `AAAAMMDD_HHMM_XXYY_TT` (ordena cronológicamente); `paths.code_label` lo formatea.
  Modo `YY`: `AH` antihorario (motor izquierdo), `HO` horario (motor derecho), `AL` aleatorio.
- Imports absolutos desde `software/` (`from comun.mobility import …`, `from vidfetch.core import …`).
  Los scripts de `figuras/` y `herramientas/` agregan `software/` al path, así que se corren con
  `python software/<carpeta>/<script>.py` desde la raíz del repositorio.
- Comentarios del código en inglés; textos de la interfaz en español.
