# V2.0.2 — Topografía de Marte, países de los 25 candidatos, nueva capa descriptiva

La V2.0.2 conserva exactamente el motor exploratorio y los rankings previos. Amplía **solo la presentación y los informes**, sin nuevas consultas a servidores ni puntuaciones de similitud inventadas.

## Ejecutar en Windows

1. Descomprimir `mars_analog_engine_v2_0_2.zip` en Descargas, junto a `mars_analog_engine_v1_3_3`.
2. Dentro de la carpeta V2.0.2, ejecutar:

```powershell
powershell -ExecutionPolicy Bypass -File .\EJECUTAR_V2.ps1
```

El lanzador usa la instalación y los datos existentes de V1.3.3 (sin copiar gigabytes ni volver a descargar datos). Abrirá `data\reports\mars_v2_0\mars_analog_dashboard_v2.html`.

## Qué cambia visualmente

- Pestaña **Regiones de Marte**: Elysium Planitia, Jezero, Gale, Olympus Mons, Meridiani Planum y Syrtis Major Planum se seleccionan por clic, muestran un mapa de altitud **MOLA** hecho a partir de `data/processed/mola_georeferenced.nc`, centro y coordenadas planetocéntricas 0–360° Este, métricas históricas y unidades cartográficas USGS. El mapa es un contexto aproximado de 640 km por lado; el recuadro punteado indica la zona de análisis de 240 km. La fuente tiene **0,25° por celda (~15 km en latitud)**: no es una fotografía detallada de superficie ni un mapa de seguridad de rover.
- Pestaña **Explorar candidatos**: **los 25 candidatos GLiM tienen un país nombrado**. Ejemplo: `Rusia · Extremo Oriente ruso · observaciones piroclásticas — 49° N, 135° E`, y `Kazajistán — 45° N, 77° E`. El país se obtuvo mediante intersección espacial del centro de la celda de 2° con los polígonos Natural Earth de baja resolución (dominio público). En zonas de frontera, la atribución describe **el centro**, no toda la celda.
- **Fichas enriquecidas**: relieve regional ETOPO y P98–P02 cuando hay grilla, clase litológica GLiM más observada (sin llamar porcentaje de área a los recuentos) y temperatura, precipitación, humedad NASA POWER **solo si los registros están disponibles para esa región**. El clima no se interpreta como semejanza climática Marte–Tierra.
- Argentina conserva los mapas NASADEM p04/p08, no se modifica su análisis previo.
- Exporta `elysium_candidates_geographic_atlas_v2.csv` con nombres y países, y `mars_topography_profiles_v2.csv` con la procedencia de los seis perfiles.

## Comprobar la disponibilidad de datos

Desde el proyecto V2.0.2:

```powershell
Test-Path ..\mars_analog_engine_v1_3_3\data\processed\mola_georeferenced.nc
Test-Path ..\mars_analog_engine_v1_3_3\data\catalog\mars_profiles_v1_2.json
Test-Path ..\mars_analog_engine_v1_3_3\data\processed\earth_global_land.nc
```

Si falta MOLA, el panel informa «Topografía no disponible» para Marte y no crea mapas ficticios. Si falta el mosaico terrestre, los mapas ETOPO faltantes se informan del mismo modo. Si existe el manifiesto de perfiles MOLA, se comprueban sus SHA-256. Este flujo conserva la procedencia y los límites científicos del proyecto.

## Fuentes

- [NASA PDS / MOLA MEGDR](https://pds-geosciences.wustl.edu/missions/mgs/megdr.html)
- [USGS SIM 3292 · Geología global de Marte](https://doi.org/10.3133/sim3292)
- [NOAA ETOPO](https://www.ncei.noaa.gov/products/etopo-global-relief-model)
- [Natural Earth · países 1:110 millones](https://www.naturalearthdata.com/downloads/110m-cultural-vectors/) — datos cartográficos de dominio público

## Limitaciones

Los centros de celdas de 2° no son afloramientos. Las métricas MOLA corresponden a una ventana de muestreo de 240 km, distinta de la ventana de visualización de contexto. Las clases GLiM y USGS no demuestran equivalencia mineralógica. La validación externa V1.3.3 es inconclusa; no puede usarse como precisión de clasificación.
