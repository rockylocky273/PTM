# Mars Analog Engine V1.1.1 — Delimitación geológica y refino local

**Alcance:** complementa la V1.1; **NO cambia** el ranking topográfico original, ni realiza todavía un cruce geológico cuantitativo con Marte.

## Resultados previos suministrados por el investigador

La región `r026_c146` (37° S, 67° O) tuvo 2 muestras GLiM `Basic volcanic rocks` y 7 `Unconsolidated sediments` entre nueve puntos de un plan GLiM. Es una **observación de puntos**, no cobertura areal, ni prueba petrográfica de basaltos. En los primeros seis candidatos, solamente Argentina tuvo dicha clasificación en los puntos muestreados.

## A. Obtener geometría de las unidades que contienen los puntos volcánicos

La V1.1.1 identifica exclusivamente puntos con clasificación `Basic volcanic rocks` ya guardada en el plan geológico y realiza una nueva consulta ArcGIS `returnGeometry=true`, `outSR=4326`, `geometryPrecision=5`, `maxAllowableOffset=0.001`. Rechaza respuestas truncadas, excesivas, no válidas o cuya litología ya no coincida. Realiza un recorte local circular de **25 km de radio**, proyectado aproximadamente en coordenadas kilométricas locales, y guarda un **GeoJSON WGS84** por punto.

```powershell
.\.venv\Scripts\python.exe -m mars_analog.data geology-boundaries-fetch --plan data/catalog/geology_argentina_plan.json --region-id r026_c146 --limit 2 --radius-km 25 --timeout 120
.\.venv\Scripts\python.exe -m mars_analog.data geology-boundaries-summary --plan data/catalog/geology_argentina_plan.json --region-id r026_c146 --radius-km 25
```

Archivos típicos:

- `data/processed/glim_boundaries/<hash-plan>/r026_c146_p04_r25p00km.geojson`
- `data/processed/glim_boundaries/<hash-plan>/r026_c146_p08_r25p00km.geojson`
- `data/results/geology_argentina_boundaries.csv`
- `data/reports/geology_argentina_boundaries.json`

Estos GeoJSON pueden abrirse en QGIS. El área recortada **es una estimación aproximada dependiente de la generalización**. No debe presentarse como extensión geológica precisa, densidad de afloramientos, ni porcentaje de la ventana topográfica original. No debe sumarse la superficie de los dos recortes: se podrían solapar.

La consulta de puntos original y el recorte se vinculan al SHA256 del plan geológico. El archivo de caché incluye procedencia SHA256 y fecha UTC. Modificar radio produce otro recorte y conserva el anterior.

## B. Preparar recortes del relieve cerca de p04 y p08

```powershell
.\.venv\Scripts\python.exe -m mars_analog.data geology-terrain-bboxes --plan data/catalog/geology_argentina_plan.json --region-id r026_c146 --half-width-km 30
```

El resultado en `data/catalog/geology_argentina_terrain_rois.json` propone comandos `etopo --bbox=... --stride 1` para obtener datos NOAA ETOPO 2022 en ventanas ~60×60 km. ETOPO de 1 arco-minuto es **demasiado grueso para evaluar obstáculos de rovers, trayectos o pendientes a escala de metro**. Esta función planifica el muestreo; no descarga nada ni afirma que se haya calculado un modelo de movilidad.

## C. Extender la comparación a los 25 candidatos topográficos

```powershell
.\.venv\Scripts\python.exe -m mars_analog.data geology-plan --limit 25 --points-per-region 9 --spacing-km 60 --output data/catalog/geology_top25_plan.json
.\.venv\Scripts\python.exe -m mars_analog.data geology-fetch --plan data/catalog/geology_top25_plan.json --limit 100 --timeout 120
.\.venv\Scripts\python.exe -m mars_analog.data geology-fetch --plan data/catalog/geology_top25_plan.json --limit 100 --timeout 120
.\.venv\Scripts\python.exe -m mars_analog.data geology-summary --plan data/catalog/geology_top25_plan.json --csv data/results/geology_top25.csv --report data/reports/geology_top25.json
```

Los puntos previos se reutilizan únicamente si coinciden *ID, coordenadas, fuente y clase válida*; el nuevo archivo conserva la referencia SHA256 del caché original. Aunque se amplíe a 225 puntos, no será un porcentaje real de superficie geológica ni un muestreo imparcial de la litología mundial.

## D. Referencia marciana bibliográfica, no extraída del GIS

- **USGS**, Tanaka, Chapman y Scott (1992): *Geologic map of the Elysium region of Mars*, escala 1:5 millones, https://pubs.usgs.gov/publication/i2147
- **USGS**, Tanaka et al. (2014): *Geologic map of Mars*, escala 1:20 millones, https://pubs.usgs.gov/sim/3292/

No se han procesado todavía unidades geológicas vectoriales de esos mapas para la ventana marciana de Elysium. Por ello **no hay comparación composicional ni score geológico Tierra–Marte**. Las clases globales GLiM y la cartografía planetaria USGS tampoco tienen la misma resolución ni método de clasificación.

## Verificación y estado

Pruebas automatizadas locales: **146**. Las pruebas nuevas simulan el servidor GLiM: validan geometría, respuestas erróneas, cachés y exportación, **sin garantizar que el servicio acepte la nueva consulta real**. Se requiere la primera ejecución del usuario para confirmar los GeoJSON reales de Argentina. Si una descarga falla, no se fabrica ni guarda una capa vacía.
