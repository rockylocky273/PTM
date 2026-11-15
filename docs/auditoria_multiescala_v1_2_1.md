# Mars Analog Discovery Engine V1.2.1 — Auditoría de discriminación y escalas

La V1.2.1 audita **el modelo numérico topográfico**, sin cambiar el ranking de V1.2 ni atribuir similitud geológica. **No requiere internet ni nuevas descargas** si ya están los archivos de V1.2.

## Instalación Windows (PowerShell)

Extraer `mars_analog_engine_v1_2_1.zip` en Descargas, junto a la carpeta V1.2. En la nueva carpeta:

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e ".[dev]"
.\.venv\Scripts\python.exe -m pytest -q
New-Item -ItemType Directory -Path .\data -Force | Out-Null
Copy-Item -Path "..\mars_analog_engine_v1_2\data\*" -Destination ".\data" -Recurse -Force
```

Comprueba que existen `data/reports/mars_profiles_screen_v1_2.json`, `data/catalog/mars_profiles_v1_2.json`, `data/processed/mola_georeferenced.nc`, `data/processed/earth_global_land.nc` y `data/catalog/earth_regions.csv`.

## Experimento A — Auditoría de rankings existentes

```powershell
.\.venv\Scripts\python.exe -m mars_analog.data mars-audit-rankings --top-ks 25,50,100 --scenarios 60 --seed 2026 --watch r026_c146,r068_c061
```

Ver resúmenes:

```powershell
Import-Csv .\data\reports\mars_audit_v1_2_1\pairwise_rank_correlations.csv | Select-Object profile_a,profile_b,spearman_full,kendall_full,overlap_top25,overlap_top50,overlap_top100 | Format-Table -AutoSize
Import-Csv .\data\reports\mars_audit_v1_2_1\feature_saturation.csv | Where-Object { [double]$_.uniform_sign_fraction -ge 0.95 } | Format-Table -AutoSize
Import-Csv .\data\reports\mars_audit_v1_2_1\alternative_distance_methods.csv | Format-Table -AutoSize
Import-Csv .\data\reports\mars_audit_v1_2_1\watched_candidates.csv | Format-Table -AutoSize
```

Salida principal: `data/reports/mars_audit_v1_2_1/rank_audit_report.json`.

### Qué se evalúa

- Spearman y Kendall de **rankings completos** sobre el mismo conjunto de regiones, no solo top 25.
- Solapamiento en top 25, 50 y 100 de **rankings absolutos**. El control aleatorio `k²/N` es solo descriptivo porque las ventanas terrestres se solapan y no son independientes.
- Saturación unilateral: proporción de regiones terrestres con característica mayor/menor a la referencia MOLA. Proporciones cercanas a 1 advierten falta de discriminación.
- **Dos funciones alternativas**, sin sustituir la histórica: (1) distancia L2 con escala robusta basada en MAD de log-características terrestres; (2) L1 de percentiles empíricos terrestres. Esta última satura al quedar Marte fuera del rango terrestre.
- 60 perturbaciones reproducibles de los tres pesos, usando Dirichlet centrada en 0,35/0,35/0,30 y concentración 35. Se calculan cambios de puestos y top 25 de Argentina y China.
- Validación estricta de SHA-256, perfiles, coordenadas, conjuntos y distancias históricas.

## Experimento B — Comparación multiescala con ventana de 240 km fija

```powershell
.\.venv\Scripts\python.exe -m mars_analog.data mars-audit-scales --scales 15:17,30:9,40:7 --top-k 25
```

Las configuraciones mantienen **240 km entre centros extremos**:

| Paso | Muestras por eje | Extensión centro a centro |
| --- | ---: | ---: |
| 15 km | 17 | 240 km |
| 30 km | 9 | 240 km (baseline V1.2) |
| 40 km | 7 | 240 km |

No usamos 60 km / 5×5 porque el extractor exige por lo menos 16 pendientes interiores y esa malla solo aporta 9. No cambiamos el control de calidad para forzar el experimento.

Archivos en `data/reports/mars_audit_v1_2_1/scales/`:

- `multiscale_rankings.csv`: distancias y puestos por escala, perfil y región.
- `multiscale_mars_features.csv`: características MOLA medidas por escala.
- `multiscale_comparison.csv`: solapamiento top 25, Spearman sobre las regiones comunes, recuento de regiones que entran y salen.
- `multiscale_audit_report.json`: hashes de entrada, parámetros, coberturas y limitaciones.

La configuración 30:9 **debe reproducir exactamente el ranking V1.2**; si no, el programa aborta. No modifica los archivos de V1.2. La comparación entre resoluciones no prueba mayor exactitud, especialmente porque el espaciado de 15 km interpola información de píxeles ETOPO más gruesos en parte de la Tierra.

```powershell
Import-Csv .\data\reports\mars_audit_v1_2_1\scales\multiscale_comparison.csv | Format-Table -AutoSize
```

## Interpretación científica y límites

Un valor alto de Spearman, un top 25 estable o un error bajo **NO demuestran** que exista un análogo geológico validado. Las seis referencias provienen de ventanas MOLA centradas en topónimos USGS: Jezero y Gale incluyen terreno exterior a los cráteres. No se incorporan litología marciana, geocronología, clima extraplanetario ni riesgos de aterrizaje. Las perturbaciones de pesos y el muestreo multiescala son **pruebas de sensibilidad internas**; la validación independiente mediante cartografía geológica y controles negativos es el siguiente desarrollo.

## Integridad de resultados

Los reportes conservan SHA-256 de los datos fuente y CSV. No se almacenan credenciales ni se envían tareas AppEEARS. Los resultados NASADEM de p04/p08 y GLiM de V1.1.x se conservan pero no intervienen en esta auditoría.
