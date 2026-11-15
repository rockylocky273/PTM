# V2.0.3 — Clima, 25 auditorías, mapa mundial y atlas lunar

## Ejecución Windows (un comando)

Extraer el ZIP en `C:\Users\HP\Downloads\mars_analog_engine_v2_0_3`, junto a `mars_analog_engine_v1_3_3` (con su carpeta `data` y `.venv`). En PowerShell dentro de V2.0.3:

```powershell
powershell -ExecutionPolicy Bypass -File .\EJECUTAR_V2.ps1
```

La versión reutiliza `..\mars_analog_engine_v1_3_3\data`, NO copia archivos multigigabyte ni recalcula rankings. El lanzador usa `--fetch-climate` y `--fetch-lunar` solo para los datos que falten. Para generar sin descargar nada:

```powershell
powershell -ExecutionPolicy Bypass -File .\EJECUTAR_V2.ps1 -SinDescargas
```

Para ejecutar a mano con el Python de la carpeta de V1.3.3:

```powershell
$env:PYTHONPATH=(Join-Path (Get-Location) 'src')
..\mars_analog_engine_v1_3_3\.venv\Scripts\python.exe -m mars_analog.data mars-v2-build --data-root ..\mars_analog_engine_v1_3_3\data --output-dir .\data\reports\mars_v2_0 --fetch-climate --fetch-lunar --mars-context-km 1600
```

El generador sigue creando `data/reports/mars_v2_0/mars_analog_dashboard_v2.html`, junto a:

- `candidate_climate_v203.csv`: 25 centros, climatologías y ausencias documentadas
- `candidate_audits_v203.csv` y `.json`: auditorías individuales, hasta 25
- `world_candidates_v203.csv`: 25 marcadores, paises, coordenadas y puestos
- `lunar_regions_v203.csv`: seis regiones lunares, coordenadas y explicación del proceso
- `mars_analog_report_v2.md`: nuevo capítulo con auditorías y Luna
- `mars_analog_report_v2.json`: resumen de cobertura, archivos y SHA-256

## Clima

1. Recupera NASA POWER de los CSV históricos: `data/results/environment_sample.csv` y `data/results/environment_context.csv`; valida coordenadas por `region_id` y rangos numéricos.
2. Usa el clima explícitamente verificado de V1.3.0 como alternativa.
3. Si faltan campos, revisa su caché `data/raw/nasa_power_v203/power_<region_id>_2015_2024.json`.
4. Si `--fetch-climate` está activo, descarga solo las series faltantes desde `https://power.larc.nasa.gov/api/temporal/monthly/point`, con T2M, PRECTOTCORR y RH2M para 2015–2024. Máximo 25 solicitudes nuevas; corta tras tres errores de red consecutivos. Se pueden reintentar ejecuciones posteriores sin perder la caché.
5. Resumen anual de temperatura, precipitación, humedad y amplitud térmica estacional usando `summarize_power` existente. Distingue `complete`, `partial`, `missing`.

La etiqueta de precipitación muy baja/baja/intermedia/elevada **no es una clasificación climática Köppen**. Las mediciones representan condiciones meteorológicas agregadas en un punto NASA POWER, no todo el cuadro de 2° ni el clima de Marte. La cobertura de fuente figura en consola y en el dashboard.

## Auditorías individuales

Se genera una ficha por cada ancla GLiM de Elysium. **Todos los 25** tienen coordenadas, puestos, relieve ETOPO de contexto cuando se cargó, todas las litologías GLiM observadas, clima disponible y las correspondencias frente a hasta seis perfiles MOLA. **Solo tres** candidatos conservan pruebas completas de sensibilidad de escala/método/pesos; no se atribuyen a otros.

## Mapamundi

Contornos de países procedentes de Natural Earth 1:110m (dominio público, simplificados para la web). Veinticinco marcadores proceden de los centros de las celdas 2°, no de parcelas de campo. Se puede hacer clic para abrir la ficha y el mapa ETOPO. Código verde: los tres candidatos volcánicos priorizados; ámbar: otros con muestras GLiM volcánicas; azul: el resto.

## Topografía lunar

La región `data/raw/moon/ldem_4.img` NO viene inventada ni incrustada en el proyecto: se descarga desde el archivo científico de NASA PDS `https://pds-geosciences.wustl.edu/lro/lro-l-lola-3-rdr-v1/lrolol_1xxx/data/lola_gdr/cylindrical/img/ldem_4.img` (**2.073.600 bytes**). Si la descarga falla, se muestra un motivo visible en cada panel y la ruta para obtenerla. La fuente original se conserva en caché local, con SHA-256.

Interpretación del PDS3 IMG original: 720 filas norte-sur × 1.440 columnas oeste-este, little-endian int16 firmado, `SCALING_FACTOR = 0.5`. El `OFFSET = 1737400` es el **radio de referencia** lunar y se muestra **altura relativa** a esa esfera; no se añade al rótulo de elevación. Escala: 4 píxeles/grado (~7.6 km en ecuador). Se marcan seis regiones: Mare Imbrium, Copernicus, Tycho, Mare Tranquillitatis, Oceanus Procellarum y cuenca Orientale.

**No hay ranking Tierra–Luna ni homologación de procesos lunares con Marte.** El atlas lunar es una capa visual y contextual independiente.

## Marte más alejado

Los mapas MOLA ahora muestran aproximadamente 1.600 km de ancho (parámetro `--mars-context-km`; ventana de análisis estadístico SIGUE siendo de 240 km). Se preserva la marca de la ventana interna y los mismos rankings originales.

## Fuentes

- NASA PDS LRO LOLA: https://pds-geosciences.wustl.edu/missions/lro/lola.htm
- NASA PDS FAQ de escala y offset LOLA: https://pds-geosciences.wustl.edu/missions/lro/lola_faq.htm
- NASA POWER API mensual: https://power.larc.nasa.gov/docs/services/api/temporal/monthly/
- Natural Earth: https://www.naturalearthdata.com/about/terms-of-use/

## Pruebas y límites

Los tests del proyecto usan datos sintéticos para probar algoritmos, archivos corruptos y visualización sin conexión. No validan geológicamente los análogos ni sustituyen las elevaciones reales del usuario. La fuente lunar requiere una primera descarga en la computadora del usuario y se muestra como pendiente hasta que exista. No se afirma éxito de red ni valores climáticos faltantes sin comprobación.
