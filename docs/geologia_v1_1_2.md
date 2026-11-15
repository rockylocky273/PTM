**Actualización V1.1.2.1:** corrige reconocimiento de miembros NASADEM ZIP (`s37w068.hgt`). Se conservan los resultados y limitaciones de esta documentación.

# Mars Analog Engine V1.1.2 — NASADEM ~30 m + GLiM

## Objetivo y resultado permitido

Esta versión **no** confirma terrenos seguros para rovers ni la idoneidad de una base lunar o marciana. Permite mejorar la caracterización geomorfológica de las unidades cartografiadas por GLiM cerca de los puntos `r026_c146_p04` y `r026_c146_p08` de La Pampa, Argentina. El modelo original de similitud topográfica con Elysium Planitia **no cambia**.

La cadena ahora se compone de: plan de ventanas de 60 km definido en V1.1.1 → catálogo de 4 teselas NASADEM de 1° × 1° → descarga con Earthdata Login → ensamblaje HGT y recorte por coordenadas → intersección en una malla de ~30 m con polígonos GLiM → estadísticas morfométricas → comparación opcional con ETOPO en la misma región de recorte.

## Fuente, escala y precisión

- **NASA/JPL NASADEM_HGT.001**: DOI <https://doi.org/10.5067/MEaSUREs/NASADEM/NASADEM_HGT.001>, 1 segundo de arco, cobertura nominal 56° S–60° N. HGT int16 big-endian, matrices de 3601 × 3601 muestras en teselas de 1°. Datos mayormente derivados de SRTM 2000 con mejoras y productos de relleno auxiliares. HGT con alturas del DEM fusionado referidas al geoide EGM96. El producto incluye índices de procedencia NUM; **esta implementación no interpreta aún esa banda auxiliar**. Puede haber efectos de vegetación y error vertical, por lo que no debe tratarse automáticamente como relieve de roca desnuda.
- **GLiM**: mapa litológico global de baja resolución espacial y polígonos generalizados, descargados en V1.1.1; una clasificación `Basic volcanic rocks` no prueba que cada píxel de NASADEM contenga basalto expuesto. Los recortes son círculos de 25 km delimitados en el proceso V1.1.1, no el área integral del candidato topográfico.
- **ETOPO 2022 60s**: contexto de resolución más baja (~1,85 km meridional) obtenido previamente; no equivale a una muestra de alta resolución. Su referencia vertical tampoco debe suponerse idéntica a NASADEM o MOLA.

El algoritmo calcula pendiente a partir de diferencias de elevación y el tamaño de celda geodésico local; la rugosidad es la desviación estándar de altura en una ventana de 11 × 11 celdas (~250–340 m dependiendo de latitud y dirección). Con ETOPO, la rugosidad histórica de 3 × 3 celdas cubre varios kilómetros y **no es directamente comparable**. Se informan medianas y percentil 90, además de el área aproximada de componentes conexos de celdas de pendiente ≤5° *dentro* del polígono GLiM. Ningún umbral es un criterio de seguridad o de transitabilidad.

## Instalación Windows PowerShell

Descomprimir V1.1.2 junto a V1.1.1, sin sustituir la carpeta original. Dentro de V1.1.2:

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e ".[dev]"
.\.venv\Scripts\python.exe -m pytest -q
New-Item -ItemType Directory -Path .\data -Force | Out-Null
Copy-Item -Path "..\mars_analog_engine_v1_1_1\data\*" -Destination ".\data" -Recurse -Force
```

Al copiar se conservan: `data/catalog/geology_argentina_terrain_rois.json`, `data/results/geology_argentina_boundaries.csv`, GeoJSON de GLiM, archivos ETOPO normalizados, 125 series NASA POWER y el estado de AppEEARS (si estaban en V1.1.1).

## 1. Planificar NASADEM sin descargar nada

Si no se guardó la planificación previa:

```powershell
.\.venv\Scripts\python.exe -m mars_analog.data geology-terrain-bboxes --plan data/catalog/geology_argentina_plan.json --region-id r026_c146 --half-width-km 30
```

Luego:

```powershell
.\.venv\Scripts\python.exe -m mars_analog.data nasadem-plan --rois data/catalog/geology_argentina_terrain_rois.json
```

Se esperan dos áreas y **cuatro teselas**: `s37w068`, `s37w069`, `s38w068`, `s38w069`. La selección espacial es reproducible y está asociada al SHA-256 del archivo de áreas.

## 2. Buscar los gránulos NASADEM en CMR sin autenticación

```powershell
.\.venv\Scripts\python.exe -m mars_analog.data nasadem-search
```

El catálogo de resultados se guarda en `data/catalog/nasadem_argentina_search.json`. Exigimos exactamente un gránulo coincidente por tesela. Si falta alguno, **no** se crea un enlace ficticio ni se permite descargar un conjunto incompleto.

## 3. Descargar en lotes pequeños con NASA Earthdata Login

```powershell
.\.venv\Scripts\python.exe -m mars_analog.data nasadem-download --limit 1 --max-mb 60
```

Si la primera descarga es correcta, repetir con `--limit 3` (o volver a ejecutar el mismo comando); reutiliza ZIP ya verificados. Earthaccess puede pedir usuario y contraseña. El motor llama `earthaccess.login(strategy='all',persist=False)` y no escribe credenciales en sus informes; evitá compartir tokens, archivos `.netrc` o capturas con contraseñas.

Los archivos se guardan en `data/raw/nasadem/NASADEM_HGT_sXXwYYY.zip`. Cada ZIP se inspecciona: archivo HGT de 3601² muestras, longitud sin comprimir, CRC y SHA-256, sin extraer rutas del ZIP al sistema. Se limita el tamaño por gránulo antes de la descarga cuando CMR informa su tamaño.

## 4. Cruzar relieve de alta resolución y polígonos GLiM

```powershell
.\.venv\Scripts\python.exe -m mars_analog.data nasadem-analyze --point-id r026_c146_p04 --etopo data/processed/argentina_p04_elevation.nc
.\.venv\Scripts\python.exe -m mars_analog.data nasadem-analyze --point-id r026_c146_p08 --etopo data/processed/argentina_p08_elevation.nc
```

Salidas de cada sector:
- `data/processed/nasadem_argentina_p04.nc` (o `p08.nc`): elevaciones, pendiente, rugosidad 11x11 y máscara de unidad cartográfica GLiM.
- `data/reports/nasadem_argentina_p04.json` (o `p08.json`): estadísticas, hashes NASADEM/GLiM/ETOPO, estimación de área por malla, observaciones de calidad y advertencias.

Se bloquea el análisis si falta un ZIP, el GeoJSON carece de SHA-256 coincidente o un punto no pertenece al plan. No interpola celdas sin datos para generar un terreno artificialmente liso.

## 5. Comparación descriptiva final

```powershell
.\.venv\Scripts\python.exe -m mars_analog.data nasadem-compare
```

Crea `data/reports/nasadem_argentina_comparison.json`. Debe comparar los dos sectores con **el mismo umbral**; no etiqueta ninguno como «seguro» o «ganador» para construir una base. Una evaluación operativa necesitaría imágenes y topografía de resolución métrica, composición/peligros del regolito, logística, permisos y visitas de validación.

## Pruebas y límites de validación

- Tests locales incluyen teselas HGT sintéticas completas comprimidas, unión de teselas, control de inventario, máscara GLiM, pendiente analítica y pipeline real de archivos locales con datos sintéticos.
- **No** se realizó acceso en vivo a NASA Earthdata desde la sesión de preparación: las consultas de `nasadem-search` y `nasadem-download` requieren comprobación en la computadora del usuario.
- No se compara automáticamente la litología terrestre con las unidades geológicas GIS de Marte; eso sigue pendiente de la V1.2.

**Fuentes oficiales:** NASA LP DAAC NASADEM_HGT.001; USGS NASADEM Data Dictionary; earthaccess documentation.
