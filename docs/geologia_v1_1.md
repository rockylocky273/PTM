# V1.1: Litología terrestre GLiM, módulo de puntos

## Objeto de esta entrega

Proporcionar evidencia **cartográfica** independiente de la topografía y el clima.
Esta primera iteración no afirma que la litología terrestre de los candidatos sea
idéntica a la de Marte. Mantiene intactos los archivos originales de ranking.

### Datos de origen

- Hartmann, Jens y Moosdorf, Nils (2012): *The new global lithological map
  database GLiM: A representation of rock properties at the Earth surface.*
  G3 13(Q12004), DOI https://doi.org/10.1029/2012GC004370.
- Servicio de consulta público (publicación por terceros, no por los autores de
  GLiM): https://services8.arcgis.com/4KhTMTZ1x0f76DSg/arcgis/rest/services/GLiM_Niveau_I/FeatureServer/1
- Capa: `GLiM_Niveau_I`, polígonos de primer nivel, campo `xx_Description`.
  La consulta transforma puntos en EPSG:4326 y pide hasta 10 coincidencias.
- Contexto de Marte: Tanaka, Chapman y Scott, mapa de la región Elysium
  https://doi.org/10.3133/i2147 y página de datos USGS
  https://www.usgs.gov/data/geologic-map-elysium-region-mars.

**Advertencias:** la fecha de publicación del mapa geológico, su escala de
compilación, contactos de polígonos y unidades generalizadas pueden diferir
considerablemente de las características del afloramiento real. La presencia de
`Basic volcanic rocks` no verifica composición basáltica instrumentalmente.
Las muestras puntuales no son fracciones de superficie; frecuencias son
porcentajes de muestras válidas, exclusivamente. Ni la clasificación global ni
la temperatura pueden representar por sí solas Marte o la Luna.

### Workflow Windows PowerShell (dentro de V1.1)

1. Instalar dependencias `py -3.12 -m venv .venv` y
   `.\.venv\Scripts\python.exe -m pip install -e ".[dev]"`.
2. Copiar `data/` desde V1.0.2 para reutilizar el ranking, plan ambiental,
   climatología, auditoría y estado del task AppEEARS.
3. Inspeccionar metadatos del servidor, sin muestras:
   `.\.venv\Scripts\python.exe -m mars_analog.data geology-metadata`
4. Plan local para Argentina únicamente:
   `.\.venv\Scripts\python.exe -m mars_analog.data geology-plan --region-ids r026_c146 --limit 1 --points-per-region 9 --spacing-km 60 --output data/catalog/geology_argentina_plan.json`
5. Consultar nueve posiciones con caché y sin credenciales:
   `.\.venv\Scripts\python.exe -m mars_analog.data geology-fetch --plan data/catalog/geology_argentina_plan.json --limit 9 --timeout 120`
6. Resumen limitado a muestras puntuales:
   `.\.venv\Scripts\python.exe -m mars_analog.data geology-summary --plan data/catalog/geology_argentina_plan.json --csv data/results/geology_argentina.csv --report data/reports/geology_argentina.json`
7. Luego, plan de seis regiones con 5 puntos cada una:
   `.\.venv\Scripts\python.exe -m mars_analog.data geology-plan --limit 6 --points-per-region 5 --spacing-km 60`
   (escribe el plan por defecto `data/catalog/geology_plan.json`).
   Consultar con `geology-fetch --limit 10`; resumir con `geology-summary`.

Los planes nuevos se guardan en subcarpetas de caché identificadas con su hash,
para impedir utilizar accidentalmente mediciones de un plan distinto.
Un fallo de red NO genera un registro científico falsamente completo.

### Salidas

- `data/catalog/geology_plan.json`: especificación estable y puntos exactos;
  contiene referencias a la fuente y hashes de las entradas.
- `data/raw/geology_glim/<plan_hash_prefijo>/<region>_pNN.json`:
  una clase y trazabilidad por punto, o estado `unmapped`, `ambiguous`,
  `unclassified`. Errores HTTP no se cachean.
- `data/results/geology_context.csv`: conteos de puntos válidos por clase,
  sin extrapolación de superficie ni puntuación planetaria.
- `data/reports/geology_context.json`: cobertura, incertidumbre y procedencia.

### Qué NO está implementado todavía

- Cartografía mineralógica in situ de los afloramientos argentinos.
- Intersección de polígonos GLiM con ventanas ponderadas por área.
- Intersección geológica de mapas USGS marcianos en coordenadas planetarias;
  es el siguiente subpaso y requiere preservar el datum/convención de longitudes.
- Clasificación automática de análogos de Marte o de la Luna.
- Conexión del resultado con la tarea pendiente de MODIS AppEEARS.

### Verificación

Los tests nuevos usan respuestas **simuladas** del servicio ArcGIS. El servicio
remoto no pudo probarse desde el entorno de desarrollo. La prueba decisiva
es `geology-metadata` seguida de `geology-fetch` en la computadora del usuario.
