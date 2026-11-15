# Mars Analog Discovery Engine V2.0 — entrega integrada

## Propósito

Presentar una investigación **exploratoria, reproducible y auditable** de búsqueda de análogos terrestres de paisajes de Marte con seis perfiles MOLA, ETOPO, cartografía SIM 3292 y GLiM, contexto NASA POWER, y pruebas de incertidumbre. La V2.0 **no inventa puntuaciones conjuntas de similitud** ni anuncia validación planetaria no obtenida.

La V2.0 agrega un **tablero HTML interactivo y sin conexión** (pestañas para candidatos, seis perfiles, referencias externas y metodología), gráficos de estabilidad, grilla geográfica, tabla de NASA POWER terrestre, CSV, JSON, un informe Markdown con limitaciones y huellas SHA-256. Conserva todos los comandos de V1.3.3 y los informes históricos.

## Uso rápido (Windows PowerShell)

Extraer `mars_analog_engine_v2_0.zip` junto a `mars_analog_engine_v1_3_3`. **No eliminar ni editar los datos históricos.**

**Modo turbo (recomendado): no copia los datos ni reinstala librerías.**

```powershell
powershell -ExecutionPolicy Bypass -File .\EJECUTAR_V2.ps1
```

El lanzador reutiliza el Python y los datos de V1.3.3 si están en la carpeta vecina; si no encuentra el entorno antiguo, instalará el necesario. No modifica la V1.3.3.

**Modo manual igualmente rápido:**

```powershell
$env:PYTHONPATH = (Resolve-Path .\src).Path
& "..\mars_analog_engine_v1_3_3\.venv\Scripts\python.exe" -m mars_analog.data mars-v2-build --data-root "..\mars_analog_engine_v1_3_3\data" --output-dir ".\data\reports\mars_v2_0"
Start-Process ".\data\reports\mars_v2_0\mars_analog_dashboard_v2.html"
```

Si tu V1.3.3 no tiene `.venv` o `data`, podés instalar las dependencias en V2.0 (`py -3.12 -m venv .venv`, luego `.\.venv\Scripts\python.exe -m pip install -e ".[dev]"`) y copiar la carpeta `data` de V1.3.3; después ejecutar `mars-v2-build` normalmente.

Todos los resultados nuevos van a `data/reports/mars_v2_0/` dentro de V2.0. **No se descargan datos de NASA/USGS, no se copian gigabytes y no se sobrescriben informes históricos.**

## Archivos finales

| Archivo | Descripción |
|---|---|
| `mars_analog_dashboard_v2.html` | Panel visual auto-contenido: navegador, sin servidor |
| `mars_analog_report_v2.md` | Conclusiones científicas y limitaciones |
| `mars_analog_report_v2.json` | Resultado estructurado con SHA-256 |
| `elysium_candidates_v2.csv` | Tres candidatos y sensibilidades a escala/método |
| `mars_profiles_v2.csv` | Seis regiones MOLA, unidades y dominio topográfico |
| `external_references_v2.csv` | Nueve casos de referencia externa |

## Datos exigidos (V1.3.3)

- `data/reports/mars_domain_v1_2_2.json`
- `data/reports/mars_geology_points_v1_2_2.json`
- `data/reports/mars_multicriteria_v1_3_0.json`
- `data/reports/mars_geology_correspondence_v1_3_1.json`
- `data/reports/mars_uncertainty_v1_3_2.json`
- `data/reports/mars_external_benchmark_v1_3_3.json`

Junto a todos los CSV y archivos originales referenciados por esos informes. Se verifican hashes de las fuentes cuando están declarados; si hay mezcla de versiones o archivos editados, el motor detiene la exportación con un error específico.

## Qué significan los resultados

- **Argentina (`r026_c146`)**: puestos Elysium originales 6, escalas 15/30/40 km 2/6/16; 2 observaciones volcánicas básicas entre 9 GLiM. Prioridad para validar la hipótesis volcánica, **no análogo probado**.
- **`r069_c067`**: puesto 8; escalas 47/8/1; piroclastos en 2 de 9 muestras GLiM. Competidor relevante, sensibilidad alta a escala.
- **`r067_c038`**: puesto 19; escalas 28/19/4; rocas volcánicas intermedias en 1 de 9 muestras GLiM. Evidencia más frágil a eliminación de puntos.
- **Benchmark V1.3.3**: 9 casos externos; 4 analogías directas documentadas, **3 fuera de la población clasificada**. El cuarto queda con extrapolación topográfica. No hay medición válida de accuracy, AUC ni porcentaje de analogía.

Las posiciones de 15 y 40 km no están basadas en datos de mayor resolución geológica; solo alteran el muestreo y pueden responder a artefactos de escala. La cobertura de sitios costeros, volcanes insulares, entornos lacustres y paisajes locales es insuficiente en este catálogo de 2°/240 km. Los controles por procesos no son sitios negativos inventados.

## Qué dejamos fuera para llegar a V2.0

No agregamos nuevas descargas, detección mineralógica automática, nuevas muestras NASADEM para rivales, otro barrido global, pesos multicriterio optimizados, ni certificación de ingeniería rover/hábitat. Estos trabajos necesitan nuevos datos y validación externa; quedan como posibles extensiones.

## Procedencia y bibliografía de los datos

- MOLA: NASA Planetary Data System; referencias a las ventanas marcianas y consulta de la misión MGS.
- ETOPO: NOAA National Centers for Environmental Information.
- NASA POWER: contexto climatológico de la Tierra, no condiciones climáticas marcianas.
- GLiM: cartografía litológica terrestre generalizada.
- USGS global Mars map SIM 3292 (Tanaka et al. 2014), https://doi.org/10.3133/sim3292; las consultas fueron a un servicio ArcGIS de terceros que publica las descripciones.
- Referencias externas predefinidas: `config/external_benchmarks_v1_3_3.json`, con URLs NASA y USGS para cada caso.

Todos los informes históricos permanecen intactos en `data/reports/` y las descargas originales en `data/raw/`.
