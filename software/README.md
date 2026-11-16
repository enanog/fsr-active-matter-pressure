# Software

Dos aplicaciones de escritorio (cada una con su `.exe`) que generan los datos, una biblioteca común,
herramientas de línea de comandos y las figuras en MATLAB.

```
software/
├── vidfetch/        App: recorte de video y seguimiento de robots → datos/video/trayectorias/VP_*.csv
├── fsrscope/        App: presión con video sincronizado (calibración, recorte, exclusiones → datos/presion/config/)
├── comun/           biblioteca de FSRScope y herramientas (paths, log_io, signal, stats, cortes, video, robots…)
├── herramientas/    línea de comandos: medir_corte, procesar_lote, reexportar, recortar_sesion, verificar_*
├── matlab_figuras/  figuras de comparación: figuras.m (una sección por figura) + cargar_datos.m
├── empaquetado/     construcción de los .exe (PyInstaller)
└── requirements.txt
```

Dependencias (sin ciclos): `vidfetch` es autónoma; `fsrscope` depende de `comun`; `herramientas` usa
`comun` y `vidfetch.core`. `matlab_figuras` no usa Python: lee `VP_*_robots.csv`, `R_*.csv`,
`datos/presion/calibracion.csv`, `datos/presion/config/<código>.json` (si existe) y `datos/video/cortes.json`.

## Instalar y correr desde Python

```
pip install -r software/requirements.txt
python software/vidfetch/app.py [video]
python software/fsrscope/app.py [código]
```

(o, desde `software/`: `python -m vidfetch`, `python -m fsrscope`)

## Figuras (MATLAB)

Abrir `software/matlab_figuras/figuras.m` (R2020b+, Statistics and Machine Learning Toolbox), elegir los
ensayos y opciones en *Ajustes* y correr: F5 = todas, Ctrl+Enter = una sección. `guardar = true` exporta a
`informes/figuras/matlab_figuras/`.

## Ejecutables (.exe)

En la PC con Windows, doble clic en `software/empaquetado/construir.bat`, o:

```
pip install -r software/requirements.txt -r software/empaquetado/requirements-build.txt
python software/empaquetado/construir.py                       # las dos
python software/empaquetado/construir.py fsrscope              # una
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
- Íconos: `empaquetado/*.ico` (regenerables con `generar_iconos.py`).

## Convenciones

- Código de ensayo `AAAAMMDD_HHMM_XXYY_TT` (ordena cronológicamente); `paths.code_label` lo formatea.
  Modo `YY`: `AH` antihorario (motor izquierdo), `HO` horario (motor derecho), `AL` aleatorio.
- Imports absolutos desde `software/` (`from comun.stats import …`, `from vidfetch.core import …`).
  Los scripts de `herramientas/` agregan `software/` al path, así que se corren con
  `python software/<carpeta>/<script>.py` desde la raíz del repositorio.
- Comentarios del código en inglés; textos de la interfaz en español.
