# V1.3.0 — Motor multicriterio, matriz trazable y control de evidencia

## Propósito

La V1.3.0 cruza las evidencias independientes producidas hasta V1.2.2. **No convierte todo en una calificación conjunta** ni produce un porcentaje de parecido planetario. El objetivo es priorizar **qué hipótesis merecen verificarse**, no certificar un análogo de Marte.

Las dimensiones son:

| Dimensión | Archivo | Uso permitido | Uso prohibido |
|---|---|---|---|
| Topografía | Ranking V1.2 y dominio V1.2.2 | Puesto original y señal de extrapolación | Probabilidad de analogía o seguridad operativa |
| Geología Marte | USGS SIM 3292, resumen V1.2.2 | Códigos y descripciones observadas en puntos | Equivalencia mineralógica/área representativa |
| Geología terrestre | GLiM, `geology_top25.csv` | Clases litológicas identificadas en muestras | Equiparar taxonomía GLiM con unidades marcianas |
| Clima terrestre | NASA POWER, `environment_sample.json` | Contexto para campaña de campo en Tierra | Comparar directamente clima terrestre con clima marciano |
| Sensibilidad | Auditoría V1.2.1 y multiescala | Puestos según método y escala | Validación geológica independiente |

**Nota:** V1.3.0 no integra todavía cobertura del suelo MODIS/AppEEARS, imágenes de afloramientos, mapas geológicos regionales ni datos mineralógicos marcianos. No se declara faltante climático marciano igual a cero: figura `NOT_EVALUATED`.

## Requisitos en Windows (PowerShell)

Descomprimir el ZIP junto a `mars_analog_engine_v1_2_2` y abrir PowerShell dentro de la carpeta `mars_analog_engine_v1_3_0`.

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e ".[dev]"
.\.venv\Scripts\python.exe -m pytest -q
New-Item -ItemType Directory -Path .\data -Force | Out-Null
Copy-Item -Path "..\mars_analog_engine_v1_2_2\data\*" -Destination ".\data" -Recurse -Force
```

Comprobar entradas (idealmente todas son `True`):

```powershell
@(
 "data/reports/mars_evidence_matrix_v1_2_2.json",
 "data/reports/mars_domain_v1_2_2.json",
 "data/reports/mars_geology_points_v1_2_2.json",
 "data/results/geology_top25.csv",
 "data/reports/mars_profiles_screen_v1_2.json",
 "data/reports/environment_sample.json",
 "data/reports/mars_audit_v1_2_1/rank_audit_report.json",
 "data/reports/mars_audit_v1_2_1/scales/multiscale_audit_report.json"
) | ForEach-Object { [PSCustomObject]@{Archivo=$_; Existe=Test-Path $_} } | Format-Table -AutoSize
```

Las primeras **cinco** entradas son necesarias. NASA POWER y las dos auditorías son opcionales; su ausencia se registra como `not_available`. **Si un archivo existe pero es inconsistente o su hash no coincide, el motor aborta en lugar de ignorarlo**. Si no hay informe climático o no querés usarlo, pasá `--without-climate`.

## Construir la matriz multicriterio

```powershell
.\.venv\Scripts\python.exe -m mars_analog.data mars-multicriteria-build --shortlist-top 25
```

Se generan:

- `data/results/mars_multicriteria_v1_3_0.csv` — una fila por comparación Tierra–Marte con puertas de dominio, señales amplias y contexto terrestre.
- `data/reports/mars_multicriteria_v1_3_0.json` — libro de evidencia con trazabilidad por SHA-256 y advertencias.
- `data/reports/mars_multicriteria_v1_3_0.md` — tabla legible para inspección.

No se modifican `mars_profiles_v1_2`, los rankings históricos ni los archivos de V1.2.2.

## Revisar Elysium o el conjunto

```powershell
.\.venv\Scripts\python.exe -m mars_analog.data mars-multicriteria-review --profile elysium_planitia
.\.venv\Scripts\python.exe -m mars_analog.data mars-multicriteria-review --profile all
```

Para la comparación regional directa:

```powershell
Import-Csv .\data\results\mars_multicriteria_v1_3_0.csv |
  Where-Object { $_.mars_profile -eq 'elysium_planitia' } |
  Select-Object mars_profile,earth_region_id,topographic_rank_v12,topographic_gate,geological_signal,climate_status,scale_shortlist_stability,workflow_triage |
  Format-List
```

Para los puestos de Argentina en las tres escalas, el JSON conserva `scale_ranks` por candidato. El siguiente ejemplo muestra el valor sin truncamiento:

```powershell
$p = Get-Content .\data\reports\mars_multicriteria_v1_3_0.json -Raw | ConvertFrom-Json
$p.candidates |
  Where-Object { $_.mars_profile -eq 'elysium_planitia' -and $_.earth_region_id -eq 'r026_c146' } |
  Select-Object mars_profile,earth_region_id,topographic_rank_v12,scale_ranks,alternative_method_ranks |
  Format-List
```

## Reglas deterministas del motor

1. **Puerta de dominio:** si al menos tres de las cinco características de Marte están fuera de los rangos terrestre observados, se bloquea la priorización de analogía topográfica. Una característica fuera del rango o varias en colas extremas producen advertencias explícitas.
2. **Señal volcánica cartográfica amplia:** si alguna descripción de unidad SIM 3292 contiene la palabra literal `volcanic` y alguna muestra GLiM pertenece al conjunto documentado de clases volcánicas, se registra `shared_broad_volcanic_mapping_signal`. **No equivale a la misma litología, origen, composición o edad.** Una ausencia en nueve puntos no significa incompatibilidad.
3. **Contexto NASA POWER:** se añade solo si el informe está completo y su archivo CSV coincide con SHA-256; los parámetros corresponden a Tierra, sin score climatológico marciano.
4. **Sensibilidad:** si están disponibles las auditorías V1.2.1, se añaden puestos alternativos y multiescala. El indicador de estabilidad marca si cada candidato está o no entre los mejores `N` de cada escala; **no acredita una analogía**.
5. **Triage de flujo de trabajo:** las etiquetas `candidate_for_targeted_geological_validation`, `secondary_volcanic_hypothesis_only`, `hold_reference_domain`, etc., orientan la investigación **sin hacer promedios de criterios inconmensurables**. `--shortlist-top` cambia un umbral exploratorio, no una frontera física.

## Integridad y alcance

El módulo verifica los hashes de los informes V1.2.2, su CSV, los rankings V1.2 para los seis perfiles, las clases GLiM, los CSV de dominio y geología, y los insumos opcionales de clima/auditoría. Compara nuevamente los puestos y distancias de la matriz con los rankings originales y los conteos de unidades con las fuentes, antes de generar los resultados.

El catálogo ETOPO filtra latitudes y superficies, por lo que `all_features_outside_sampled_earth_range` **no significa imposible en toda la Tierra**. Los datos NASA POWER son mensuales históricos 2015–2024; un punto no caracteriza toda la región. Las unidades del mapa marciano son generalizadas y los nueve puntos no miden cobertura areal.

## Etapas previstas

- **V1.3.1:** reglas geológicas interpretables por procesos, con fuentes regionales, controles de incompatibilidad y evidencia explícita de ausencia.
- **V1.3.2:** incertidumbre por límites de unidades y escalas, sensibilidad de umbrales y evaluación espacial de zonas.
- **V1.3.3:** referencias externas y controles negativos *predefinidos* antes de ajustar cualquier ranking combinado.

**Fuentes principales:** USGS SIM 3292 (https://doi.org/10.3133/sim3292), GLiM (Hartmann & Moosdorf, 2012), NASA POWER, NOAA ETOPO y NASA MOLA PDS. El archivo geológico marciano procede de una republicación ArcGIS de terceros que referencia SIM 3292; no es una API USGS.
