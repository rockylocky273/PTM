# V1.2.2 — Geología marciana USGS SIM 3292 y controles de dominio

## Alcance exacto

Esta versión incorpora **observaciones cartográficas puntuales** de unidades geológicas de Marte, tomadas de una capa ArcGIS pública que cita al mapa global de Tanaka et al. (2014), *USGS SIM 3292*, a escala 1:20.000.000. No descarga los 790 MB del archivo GIS original, ni rasteriza unidades, ni crea porcentajes de cobertura geológica. El servicio ArcGIS es una **republicación de terceros**; USGS es el autor del mapa, pero no necesariamente del servicio hospedado.

Referencia primaria: https://doi.org/10.3133/sim3292

Servicio utilizado: https://services.arcgis.com/nzS0F0zdNLvs7nc8/ArcGIS/rest/services/Mars_Geology_feature_layer/FeatureServer/0

Metadatos verificados contra la página pública: `Geology`, geometría `esriGeometryPolygon`, campos `OBJECTID`, `Unit`, `UnitDesc` y código espacial personalizado `104971`. No utilizar `EPSG:4326`: es un sistema **de Marte**. El motor convierte longitudes este `[0,360)` de MOLA a `[-180,180)` del servicio ArcGIS.

El mapa global de 2014 se basa en cartografía e interpretación geológica remota, por lo que la clase del mapa no equivale a mineralogía o a una medición de composición de una roca en campo.

## Procedimiento Windows PowerShell

1. Instalar Python 3.12, entorno y pruebas:

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e ".[dev]"
.\.venv\Scripts\python.exe -m pytest -q
```

2. Copiar los datos de la V1.2.1 en la nueva carpeta:

```powershell
New-Item -ItemType Directory -Path .\data -Force | Out-Null
Copy-Item -Path "..\mars_analog_engine_v1_2_1\data\*" -Destination ".\data" -Recurse -Force
```

3. Comprobar los datos de origen (todos se generaron anteriormente):

```powershell
Test-Path .\data\catalog\mars_profiles_v1_2.json
Test-Path .\data\reports\mars_audit_v1_2_1\rank_audit_report.json
Test-Path .\data\results\geology_top25.csv
```

Si falta `geology_top25.csv`, se puede copiar desde `..\mars_analog_engine_v1_1_1\data\results\geology_top25.csv`, siempre que corresponda al análisis de 225 muestras ya realizado. Si falta `rank_audit_report.json`, ejecutar en la V1.2.2 `mars-audit-rankings --top-ks 25,50,100 --scenarios 60 --seed 2026` para regenerar los resultados usando las fuentes originales.

4. Informe numérico de validez (sin Internet):

```powershell
.\.venv\Scripts\python.exe -m mars_analog.data mars-domain-report
```

5. Validar la API geológica (necesita Internet; **sin credenciales**):

```powershell
.\.venv\Scripts\python.exe -m mars_analog.data mars-geology-source
```

6. Crear un plan de 54 muestras (nueve por perfil; desplazamientos de hasta 100 km):

```powershell
.\.venv\Scripts\python.exe -m mars_analog.data mars-geology-plan --points-per-profile 9 --radius-km 100
```

7. Iniciar con tres consultas reales, no con 54 de golpe:

```powershell
.\.venv\Scripts\python.exe -m mars_analog.data mars-geology-fetch --limit 3 --timeout 90
```

Si no hay fallos de servicio, continuar por lotes:

```powershell
.\.venv\Scripts\python.exe -m mars_analog.data mars-geology-fetch --limit 15 --timeout 90
```

El programa conserva en caché cada respuesta con coordenadas, plan SHA-256, código y descripción. Repetir el último comando hasta obtener `pending: 0`. Un error `400` o un punto sin cobertura no es evidencia geológica: revisar `failures` y, si corresponde, consultar el servicio. **No repetir indefinidamente consultas fallidas sin diagnosticar el motivo.**

8. Resumir las unidades cartográficas:

```powershell
.\.venv\Scripts\python.exe -m mars_analog.data mars-geology-summary
```

Archivos: `data/results/mars_geology_points_v1_2_2.csv` y `data/reports/mars_geology_points_v1_2_2.json`. El informe contiene observaciones individuales y descripciones verbatim de `UnitDesc`. Las palabras clave interpretativas se identifican como *pistas textuales*, no como química de rocas o procesos validados.

9. Crear una matriz de evidencia independiente:

```powershell
.\.venv\Scripts\python.exe -m mars_analog.data mars-evidence-matrix --watch r026_c146,r068_c061
```

Produce `data/results/mars_evidence_matrix_v1_2_2.csv` y reporte JSON. Reúne rankings V1.2, geología GLiM terrestre y observaciones cartográficas marcianas, más alertas topográficas de extrapolación. **No calcula ninguna puntuación de compatibilidad geológica ni un ranking combinado.**

## Diagnóstico de extrapolación

`mars-domain-report` reutiliza `feature_saturation.csv` de V1.2.1 (verificado por SHA-256) y distingue:

- número de 5 características marcianas que quedan fuera del rango mínimo–máximo del catálogo terrestre;
- número de características con ≥95 % de candidatos terrestres a un mismo lado de la referencia marciana (concentración en cola extrema);
- etiqueta informativa por perfil (`domain_flag` y `tail_flag`).

La extrapolación estadística no implica que **ningún sitio de la Tierra** pueda ser análogo. Nuestro catálogo de 2.617 regiones está filtrado espacialmente, utiliza ETOPO y una escala nominal de 30 km. Incluso cuando un perfil está dentro del rango, no queda demostrado como análogo geológico.

## Qué falta después

Polígonos del mapa geológico marciano, porcentajes de unidad en ventanas definidas, validación específica mediante mapas regionales y reglas de correspondencia con GLiM que representen hipótesis sobre procesos, no equivalencias taxonómicas automáticas. La matriz es un paso explícito y reproducible **previo** al motor multicriterio V1.3.
