# Mars Analog Discovery Engine V1.3.1 — Correspondencias geológicas por proceso

## Qué resuelve y qué NO resuelve

V1.3.0 examinaba 12 pares (6 perfiles marcianos × dos regiones terrestres). V1.3.1 examina **todos los candidatos que ya poseen muestreo GLiM** en `data/results/geology_top25.csv`, cruzados con los seis perfiles. Este archivo procede de un **conjunto de anclas seleccionadas** con información geológica: no representa todas las regiones terrestres ni contiene necesariamente los puestos topográficos 1–25. No se descarga nueva geología, no se recalcula el ranking ETOPO y no se altera ninguna versión previa.

El mapa de Marte USGS SIM 3292 es una **cartografía de unidades interpretadas** a 1:20 millones: `Unit` y `UnitDesc` no son análisis químicos ni mineralógicos. Los rótulos GLiM Nivel I representan **tipos generales de litología terrestre** en puntos muestreados. Son **taxonomías no equivalentes**; un recuento de 9 puntos no es una estimación de área ni una muestra aleatoria de los afloramientos.

No se asigna una puntuación de similitud, probabilidad de analogía ni incompatibilidad geológica confirmada. El resultado es una tabla de **hipótesis de trabajo y límites de inferencia**.

## Fuentes

- USGS SIM 3292, Tanaka et al. (2014): https://doi.org/10.3133/sim3292 (mapa científico global).
- Capa ArcGIS de terceros ya consultada en V1.2.2, que declara reproducir unidades de SIM 3292. No es una API del USGS.
- Hartmann y Moosdorf, GLiM (2012): https://doi.org/10.1029/2012GC004370. Nivel I litología terrestre, vía capa ArcGIS de terceros ya descargada V1.1.
- Rankings V1.2 y control de dominio V1.2.2 (cinco características topográficas).
- V1.3.0: libro de evidencia original con hashes y criterios de triage; se valida de nuevo.
- NASADEM HGT.001 y polígonos recortados GLiM de p04/p08: análisis descriptivo terrestre **opcional**, separado del mapa geológico marciano.

## Reglas de lectura y diagnóstico

1. Cuando `UnitDesc` contiene `volcanic`, el motor registra `volcanic_cartographic_unit`. Cuando contiene `impact`, registra `impact_cartographic_unit`. Las descripciones de transición, tierras altas, unidades indiferenciadas u otras no reciben por defecto un proceso definido. Es un **filtro literal conservador**, no interpretación integral de la memoria del mapa.
2. GLiM `Basic/Acid/Intermediate volcanic rocks` y `Pyroclastics` forman el grupo amplio volcánico / piroclástico. Las clases plutónicas **no** se interpretan como evidencia de erupción superficial. Las categorías sedimentarias, metamórficas y demás se conservan sin equipararlas a unidades marcianas.
3. Si ambos mapas contienen etiquetas volcánicas, el estado es `broad_volcanic_cartography_and_lithology_signal`. Esto autoriza únicamente estudiar una **hipótesis sobre procesos volcánicos generales**, nunca edad/composición/emplazamiento equivalentes.
4. Si solo uno contiene señal volcánica, se registra ausencia de señal **en la muestra disponible**, no ausencia de vulcanismo regional ni rechazo geológico definitivo.
5. `AHi` e impacto marciano: una litología terrestre común no permite comprobar el proceso de impacto; la correspondencia queda sin demostrar.
6. Topografía es un **filtro no compensatorio**: el motor conserva el control de dominio terrestre y no prioriza como análogo validado un perfil fuera del catálogo, por ejemplo Olympus Mons. La estabilidad de escala solo está disponible para los pares ya examinados en V1.3.0.
7. Los sitios `p04` y `p08` son sectores **dentro de una misma región** y sus círculos/polígonos GLiM pueden superponerse; no sumar sus áreas. NASADEM a ~30 m no detecta automáticamente rocas, grietas ni capacidad portante.

## Cómo instalar en PowerShell

Extraer `mars_analog_engine_v1_3_1.zip` junto a `mars_analog_engine_v1_3_0`, abrir la carpeta nueva y ejecutar:

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e ".[dev]"
.\.venv\Scripts\python.exe -m pytest -q

New-Item -ItemType Directory -Path .\data -Force | Out-Null
Copy-Item -Path "..\mars_analog_engine_v1_3_0\data\*" -Destination ".\data" -Recurse -Force
```

Se necesitan los archivos anteriores:

```powershell
@(
  "data/reports/mars_multicriteria_v1_3_0.json",
  "data/reports/mars_geology_points_v1_2_2.json",
  "data/reports/mars_domain_v1_2_2.json",
  "data/results/geology_top25.csv",
  "data/reports/mars_profiles_screen_v1_2.json"
) | ForEach-Object { [PSCustomObject]@{Archivo=$_; Existe=Test-Path $_} } | Format-Table -AutoSize
```

### Construir las comparaciones de procesos

```powershell
.\.venv\Scripts\python.exe -m mars_analog.data mars-geology-correspondence-build --top-n 25
```

Entregables:

- `data/results/mars_geology_correspondence_v1_3_1.csv`: una fila por pareja perfil Marte × región terrestre GLiM, incluye `topographic_rank` y `broad_process_relation`.
- `data/reports/mars_geology_correspondence_v1_3_1.json`: detalle íntegro de unidades USGS, muestras GLiM, advertencias, procedencia y hashes.
- `data/reports/mars_geology_correspondence_v1_3_1.md`: tabla por perfil sin score.

Si hay 25 anclas GLiM y las seis tienen ranking, se esperan **150 pares**. El comando declara el número real de anclas y pares; no debe asumirse un número fijo a priori.

### Revisar Elysium y Argentina

```powershell
.\.venv\Scripts\python.exe -m mars_analog.data mars-geology-correspondence-review --profile elysium_planitia --limit 25
.\.venv\Scripts\python.exe -m mars_analog.data mars-geology-correspondence-review --profile elysium_planitia --region r026_c146
```

Para ver todas las regiones del catálogo de anclas GLiM ordenadas por su puesto de Elysium:

```powershell
Import-Csv .\data\results\mars_geology_correspondence_v1_3_1.csv |
 Where-Object { $_.mars_profile -eq 'elysium_planitia' } |
 Select-Object earth_region_id,topographic_rank,topographic_domain_gate,broad_process_relation,research_triage |
 Format-Table -AutoSize
```

### Revisión local argentina (opcional)

Si conservaste los informes NASADEM `p04`/`p08`, sus archivos NetCDF y polígonos GeoJSON GLiM de V1.1.2.1:

```powershell
.\.venv\Scripts\python.exe -m mars_analog.data mars-geology-local-review
```

Produce `data/reports/mars_geology_argentina_local_v1_3_1.json`, con estadísticas de los dos polígonos recortados y notas de límites. Si los informes faltan, copiá la carpeta `data` de la versión que los generó antes de ejecutar este comando. La revisión no valida rovers ni afirma minerales equivalentes a Marte.

## Integridad, límites y siguiente paso

El motor comprueba hashes de V1.3.0, dominio V1.2.2, glims, geología de Marte y cada uno de los rankings V1.2; además compara de nuevo las **12 parejas históricas** con los valores V1.3.0 antes de publicar. Cualquier inconsistencia bloquea la generación final. Los informes nuevos también se verifican antes de revisarlos.

Para V1.3.2: cuantificar incertidumbre ligada a fronteras y categorías geológicas, ampliar la cobertura GLiM con selección estratificada de candidatos alternativos y diseñar controles contra sesgo de selección. Para validar realmente los procesos se requerirán imágenes, mapas regionales y observaciones mineralógicas/geológicas independientes.
