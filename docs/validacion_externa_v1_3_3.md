# V1.3.3 — Validación externa: referencias independientes y auditoría de recuperabilidad

**Alcance real:** auditoría descriptiva *offline* contra casos de analogía por **proceso** documentados por NASA/USGS. **No** es una validación predictiva de equivalencia geomorfológica o mineralógica y **no** permite afirmar que el motor esté científicamente validado. Los casos y criterios están congelados **antes** de leer los nuevos resultados de referencia externa.

## Protocolo congelado (2026-11-14)

Ruta: `config/external_benchmarks_v1_3_3.json`. SHA-256 fijo en el código; las etiquetas no se cambian silenciosamente. Todas las referencias incluyen fuentes externas y condiciones de alcance.

**Cuatro analogías publicadas para perfiles marcianos específicos:**

1. **Holuhraun (Islandia) — Elysium Planitia.** Voigt et al., *Planetary Science Journal*, 2025, doi:[10.3847/PSJ/adb5f1](https://doi.org/10.3847/PSJ/adb5f1): analogía de emplazamiento de lava alimentada por fisuras para terrenos volcánicos jóvenes. Coordenadas del área de erupción de USGS EROS (64.8498, -16.829975). Referencias: https://www.usgs.gov/publications/2014-2015-holuhraun-lava-flow-field-iceland-a-planetary-analog-young-volcanic-terrains ; https://eros.usgs.gov/media-gallery/image-of-the-week/holuhraun-lava-flow-iceland
2. **Mauna Loa (Hawái, EE. UU.) — Olympus Mons.** Analogía morfológica de volcanes escudo reconocida por USGS. El Olympus Mons es enormemente mayor y tiene contexto geodinámico distinto. Coordenadas USGS: (19.475, -155.608). https://www.usgs.gov/news/volcano-watch-volcanism-other-planets ; https://www.usgs.gov/volcanoes/mauna-loa ; https://pubs.usgs.gov/publication/sim3470
3. **Lago Salda (Turquía) — Jezero.** NASA documenta analogías minerales y de depósitos carbonáticos/lacustres, **no** similitud de toda la ventana regional. Coordenadas 37.55, 29.68 de un informe de investigación de campo financiado por NASA. https://science.nasa.gov/blogs/earth-matters/2021/02/17/what-a-lake-in-turkey-can-tell-us-about-mars/ ; https://assets.science.nasa.gov/content/dam/science/psd/astrobiology/for-researchers/early-career-field-research-fund/report_lc_garczynski_project.pdf
4. **Death Valley (Badwater Basin como punto de referencia) — Gale.** NASA compara procesos de cuencas endorreicas y depósitos evaporíticos de Death Valley y Gale y destaca diferencias geológicas importantes. El punto Badwater (36.229805, -116.767413; NPS) **no** es el sitio preciso de todas las observaciones científicas citadas. https://science.nasa.gov/earth/earth-observatory/mars-rover-curiosity-on-a-familiar-landscape-78860/ ; https://www.nps.gov/planyourvisit/event-details.htm?id=59F834E6-C4AE-5BAF-60BB19B3BC28F3F3

**Referencias por proceso sin etiqueta de uno de los seis perfiles:** Craters of the Moon, Idaho (rocas basálticas y flujos; USGS); Meteor Crater, Arizona (impacto; USGS). **Contrastes de alcance:** Salda no es una etiqueta de volcán escudo Olympus; Meteor Crater no es una etiqueta de emplazamiento de lava Elysium. **No se afirman ausencias geológicas de esos lugares.** **Control de dimensión:** Atacama es un análogo NASA de extrema aridez/astrobiología; no se le inventa centro, ranking topográfico o equivalencia con Elysium.

## Hipótesis evaluable y limitaciones

- **Variable primaria registrada:** presencia/ausencia de cada sitio en la población de 2.617 regiones elegibles y causa reproducible de exclusión, si aplica. Esto mide **cobertura de catálogo**, no sensibilidad geológica.
- **Descriptores exploratorios:** puesto a 30 km, ingreso en top 25/100/250, percentil de puesto, puestos a 15/30/40 km disponibles y filtro topográfico de dominio.
- **Control clave:** asignar el sitio solamente a la **celda que contiene las coordenadas del sitio**, no al vecino mejor clasificado; si el sitio no está en catálogo, reportar la exclusión. Rejilla de 2° y ventana topográfica de 240 km **no representan las características del flujo volcánico o delta puntual**.
- **No comparabilidad de escala:** un análogo válido de una lava, delta o cuenca local podría no figurar entre los primeros puestos de un ranking de topografía regional.
- **Proceso diferente de forma:** la función topográfica puede ignorar por completo vulcanismo, impacto, sedimento y carbonatos; una buena clasificación no confirma esos procesos.
- **Olympus:** previamente medimos sus cinco características fuera del catálogo topográfico terrestre. Un ejemplo de volcán escudo (Mauna Loa) no revierte por sí solo esta limitación.
- **Muestra muy pequeña y selectiva:** no calcular accuracy, recall, ROC/AUC, sensibilidad/especificidad ni entrenar pesos con estos ejemplos. No son negativos estadísticos representativos, ni experimentos ciegos a la selección de literatura.
- **Futuro de validación de verdad:** cartografiar formas y unidades geológicas a escala comparable, ampliar referencias etiquetadas de forma independiente y separar entrenamiento de conjunto de prueba predefinido.

## Instrucciones Windows PowerShell

```powershell
# En mars_analog_engine_v1_3_3
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e ".[dev]"
.\.venv\Scripts\python.exe -m pytest -q
New-Item -ItemType Directory -Path .\data -Force | Out-Null
Copy-Item -Path "..\mars_analog_engine_v1_3_2\data\*" -Destination ".\data" -Recurse -Force

# No usa internet, ni descarga nuevos datos, ni cambia rankings.
.\.venv\Scripts\python.exe -m mars_analog.data mars-external-benchmark-build
.\.venv\Scripts\python.exe -m mars_analog.data mars-external-benchmark-review
.\.venv\Scripts\python.exe -m mars_analog.data mars-external-benchmark-review --case holuhraun_elysium
```

**Requisitos de archivos previos:** rankings V1.2, `data/catalog/earth_regions.csv`, reporte de dominio V1.2.2 y diagnóstico multiescala V1.2.1. La V1.3.2 trae estos archivos si se copiaron correctamente desde las versiones anteriores. Los archivos de la V1.3.3 se guardan en `data/results/mars_external_benchmark_v1_3_3.csv`, `data/reports/mars_external_benchmark_v1_3_3.json` y `data/reports/mars_external_benchmark_v1_3_3.md`.

Para una tabla breve:

```powershell
Import-Csv .\data\results\mars_external_benchmark_v1_3_3.csv |
  Select-Object case_id,mars_profile,earth_region_id,topographic_rank,evaluation_status |
  Format-Table -AutoSize
```

**Interpretar la salida:** `topographic_retrieval_descriptor_only` significa que existe una celda elegible y un puesto, no que se validó el caso. `external_site_not_in_screened_population` significa que el lugar quedó fuera de los 2.617 candidatos y se informa una causa. `topography_outside_reference_domain` impide emplear el puesto como prueba de analogía topográfica. `blocked_process_scope_contrast` indica el rechazo de una atribución *de proceso*, no que el lugar sea un negativo geológico.

## Integridad y reproducibilidad

El programa valida el SHA-256 del conjunto externo congelado, manifiesto V1.2, CSV de rankings, catálogo de 16.200 celdas, informes y CSVs de dominio y escala. El informe de salida registra los hashes de las fuentes. La opción `--benchmark` no permite crear etiquetas a posteriori: los cambios de contenido provocan un error hasta una versión nueva del protocolo. No hay consultas HTTP en el nuevo módulo.

## Siguiente estudio científico

Para validar realmente los análogos por **proceso**, no basta el ranking de 240 km: hay que medir proporciones areales de las unidades geológicas de ambas zonas en ventanas equivalentes, extraer rasgos específicos de morfología volcánica, sedimentaria o de impacto y realizar pruebas con un conjunto de referencia mucho mayor, sin utilizarlo para elegir los pesos. Esa es la línea de trabajo posterior a V1.3.3.
