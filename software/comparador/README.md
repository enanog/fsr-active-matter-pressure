# Comparador de ensayos

Superpone varios ensayos con **los mismos parámetros para todos** (suavizado, criterio de atasco,
clases, masa), para compararlos y exportar figuras listas para el informe o el póster. Es la versión
con interfaz de `software/matlab/comparar_ensayos.m`.

```
python software/comparador/app.py
```

Ejecutable: `software/empaquetado/dist/Comparador/Comparador.exe` (ver `software/README.md`).

## Pestañas

| Pestaña | Contenido |
|---|---|
| V̄(t) | velocidad media del conjunto, suavizada; umbral de atasco; atascos sombreados (opcional) |
| ⟨\|ω\|⟩(t) | giro propio medio de los robots |
| Energía cinética | total, o traslación (—) y rotación (···) por separado; log Y opcional |
| Histograma | fracción de las muestras con clases comunes a todos los ensayos |
| P(v) | densidad de probabilidad; clases lineales o logarítmicas |
| 1 − F(v) | P(V ≥ v), de v o de v/⟨v⟩ (normalizada por la media de cada ensayo) |
| G vs V̄ | mediana de G por clase de V̄ (ambas suavizadas), rango intercuartil, ρ de Spearman en la leyenda; las clases con menos de N cuadros quedan vacías |
| Resumen | una fila por ensayo (V̄, \|v\|, ⟨\|ω\|⟩, atascos, energía, capa de pared, G fluido/atasco, saturación, ρ); ordenable |

- Cada ensayo conserva su color aunque cambie la selección (paleta validada para daltonismo,
  `software/comun/estilo.py`). Clic en la leyenda: oculta o muestra la curva.
- **Exportar**: figura de la pestaña actual en PDF/PNG/SVG con matplotlib y el estilo de los informes
  (ancho de columna 8,6 cm, página 17 cm o póster 25 cm); resumen completo en CSV (todas las columnas
  de `comun/summary.py` + ρ + los parámetros usados); series de tiempo en CSV.
- La presión de cada ensayo usa su calibración, recorte, exclusiones y sincronía de FSRScope (solo
  lectura). La ventana guardada en Velocidades se usa solo si se marca «Ventana guardada en Velocidades».
- Parámetros, selección y tamaño de la ventana se recuerdan entre sesiones.

## Código

```
app.py         punto de entrada
core.py        curvas por ensayo con opciones comunes, distribuciones, G vs V̄, columnas del resumen
exportar.py    figura de matplotlib de cada pestaña
gui/window.py  ventana
```
