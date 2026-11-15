# V1.2 — Perfiles marcianos múltiples con referencias USGS / IAU

**Objetivo:** pasar de un solo perfil de relieve (Elysium Planitia) a seis ventanas **independientes**, centradas en lugares de Marte cuya denominación y coordenadas constan en el *Gazetteer of Planetary Nomenclature* del USGS/IAU. Los datos topográficos proceden de la rejilla MOLA MEGDR PDS4 que el usuario ya descargó y georreferenció.

> Los nombres de las regiones NO son una medición geológica. Esta versión **no** importa los polígonos de unidades geológicas de la cartografía marciana SIM 3292 y **no** asigna basaltos, sedimentos ni edades al centro del perfil. La geología terrestre GLiM de V1.1 y el contexto climático siguen siendo análisis separados.

## 1. Región de referencia

| Perfil | Centro (latitud planetocéntrica) | Longitud Este (0–360) | Referencia |
|---|---:|---:|---|
| `elysium_planitia` | 1.98° | 155.00° | [USGS IAU Elysium Planitia](https://planetarynames.wr.usgs.gov/Feature/1784) |
| `jezero_entorno` | 18.41° | 77.69° | [USGS IAU Jezero](https://planetarynames.wr.usgs.gov/Feature/Jezero) |
| `gale_entorno` | −5.44° | 137.70° | [USGS IAU Gale](https://planetarynames.wr.usgs.gov/Feature/Gale) |
| `olympus_mons` | 18.40° | 226.00° | [USGS IAU Olympus Mons](https://planetarynames.wr.usgs.gov/Feature/4453) |
| `meridiani_planum` | 0.20° | 357.50° | [USGS IAU Meridiani Planum](https://planetarynames.wr.usgs.gov/Feature/3854) |
| `syrtis_major_planum` | 8.40° | 69.50° | [USGS IAU Syrtis Major Planum](https://planetarynames.wr.usgs.gov/Feature/5796) |

Coordenadas del *Gazetteer*: planetocéntricas, **Este positivo**. El nomenclátor admite centros y límites aproximados, no delimitaciones de afloramientos. El centro de Elysium **mantiene exactamente** (1.98, 155) del piloto anterior.

**Límites de interpretación:** la ventana predeterminada mide 240 km entre los centros extremos de las 9×9 celdas a 30 km de separación. El cráter Jezero (~47,5 km de diámetro) y el cráter Gale (~155 km) no quedan aislados dentro de estas ventanas; el programa evalúa relieve regional del **entorno**. Un análisis detallado de los cráteres necesita perfiles de menor extensión y fuentes de mayor resolución, y también ajustar la resolución del dataset terrestre de comparación para evitar sobrerresolución.

## 2. Instalación Windows (desde la carpeta V1.2)

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e ".[dev]"
.\.venv\Scripts\python.exe -m pytest -q

New-Item -ItemType Directory -Path .\data -Force | Out-Null
Copy-Item -Path "..\mars_analog_engine_v1_1_2_1\data\*" -Destination ".\data" -Recurse -Force
```

La copia debe contener, al menos:

- `data/processed/mola_georeferenced.nc` (Marte, MOLA)
- `data/processed/earth_global_land.nc` (Tierra, ETOPO y máscara terrestre)
- `data/catalog/earth_regions.csv` (catálogo de 16.200 regiones terrestres)

No hace falta repetir ninguna descarga. El módulo V1.2 funciona **sin conexión a Internet** al procesar archivos ya existentes. NASADEM p04/p08, GLiM, NASA POWER y AppEEARS permanecen intactos en el historial `data/`.

## 3. Ejecutar

### 3.1. Verificar referencias

```powershell
.\.venv\Scripts\python.exe -m mars_analog.data mars-targets
```

### 3.2. Crear perfiles MOLA (sin búsquedas en red)

```powershell
.\.venv\Scripts\python.exe -m mars_analog.data mars-profiles-build --targets all --spacing-km 30 --samples 9
```

Salidas:

- `data/catalog/mars_profiles_v1_2.json` — manifiesto con parámetros, hashes y fuentes.
- `data/profiles/v1_2/*.json` — seis perfiles individuales compatibles con el esquema V0.7.
- `data/profiles/v1_2/mars_sampling_footprints.geojson` — seis ventanas métricas aproximadas, **no** polígonos de geología ni límites IAU; coordenadas de Marte (no aplicar CRS terrestre WGS84 sin advertencia).

Prueba controlada opcional, solo Elysium y Jezero:

```powershell
.\.venv\Scripts\python.exe -m mars_analog.data mars-profiles-build --targets elysium_planitia,jezero_entorno
```

Si usaste la prueba de dos perfiles y deseas los seis, volvé a ejecutar el comando `--targets all`; nunca alterará los perfiles anteriores en `data/profiles/elysium_pilot.json`.

### 3.3. Screening de todos los perfiles con la misma población terrestre

```powershell
.\.venv\Scripts\python.exe -m mars_analog.data mars-profiles-screen --top 25 --min-separation-km 250
```

Esto calcula **seis rankings independientes** con la misma cuadrícula de 9×9 muestras métricas y las mismas reglas de pendiente, rugosidad y relieve del V0.7, usando una única lectura de la malla terrestre. No se suman puntuaciones de ambientes marcianos distintos.

Salidas:

- `data/reports/mars_profiles_screen_v1_2.json`
- `data/results/mars_profiles_v1_2/elysium_planitia_ranking.csv`
- `data/results/mars_profiles_v1_2/jezero_entorno_ranking.csv`
- `data/results/mars_profiles_v1_2/gale_entorno_ranking.csv`
- `data/results/mars_profiles_v1_2/olympus_mons_ranking.csv`
- `data/results/mars_profiles_v1_2/meridiani_planum_ranking.csv`
- `data/results/mars_profiles_v1_2/syrtis_major_planum_ranking.csv`

**El programa no escribe** `data/results/topography_ranking.csv`, `data/reports/analog_audit.json` ni los reportes de geología, NASADEM o clima.

### 3.4. ¿Qué ocurre con Argentina y China bajo cada perfil?

```powershell
.\.venv\Scripts\python.exe -m mars_analog.data mars-profiles-compare --watch r026_c146,r068_c061 --top-n 25

Import-Csv .\data\results\mars_profiles_watch_v1_2.csv | Format-Table -AutoSize
```

Salidas: `data/results/mars_profiles_watch_v1_2.csv` (puestos y distancias por perfil) y `data/reports/mars_profiles_compare_v1_2.json` (intersecciones/Jaccard entre los top 25 de los distintos perfiles).

**Atención:** el puesto 6 de Argentina se obtuvo para Elysium; puede ser diferente para Jezero, Gale, Olympus, Meridiani y Syrtis. No se presupone que un análogo de una región lo sea también para las demás.

## 4. Precauciones metodológicas

- La distancia es una **medida topográfica descriptiva**, no un porcentaje de similitud, probabilidad de analogía ni aptitud para un laboratorio o hábitat.
- MOLA global 4 píxeles por grado (~15 km meridionales) frente a ETOPO mundial ~18,5 km entre centros; igualar un espaciado de muestreo nominal **no iguala** las resoluciones instrumentales.
- La latitud terrestre se restringe a ±65°, se exige mínimo de cobertura y se excluyen las regiones que no superaron la máscara de tierra en V0.6; no son búsquedas de todo punto sobre tierra.
- Las seis comparaciones usan la **misma selección de regiones terrestres**, lo que permite estudiar cambios de puesto sin confundirlos con diferencias en la población.
- Las diferencias entre topónimos no prueban causalidad geológica. Antes de llamar a un lugar análogo sedimentario o volcánico, será necesario **intersectar cartografía USGS marciana** con el perfil y validarla frente a litologías terrestres.
- Los archivos contienen identificadores de esquema, coordenadas, parámetros y **SHA-256** de los insumos, para que los resultados sean auditables.

## 5. Bibliografía y procedencia

- USGS/IAU, [Gazetteer of Planetary Nomenclature](https://planetarynames.wr.usgs.gov/).
- NASA PDS Geosciences, [MGS MOLA MEGDR](https://pds-geosciences.wustl.edu/missions/mgs/megdr.html).
- Tanaka et al. (2014), *Geologic Map of Mars*, USGS SIM 3292: https://doi.org/10.3133/sim3292 (referencia cartográfica, **no** capa GIS aún procesada).
- Tanaka, Chapman & Scott (1992), *Geologic Map of the Elysium Region of Mars*, USGS I-2147: https://doi.org/10.3133/i2147 (contexto regional, **no** mapeo litológico por píxel).

## 6. Resultado validado hasta la entrega

Las pruebas automáticas crean mapas de Marte y Tierra **sintéticos**, reconstruyen el perfil antiguo de Elysium, calculan seis rankings, comprueban integridad SHA-256 y detectan alteración de archivos. Los resultados reales numéricos multirregión dependen de tus archivos MOLA/ETOPO y todavía deben calcularse en tu equipo. Los resultados de V1.1.2.1 sobre Argentina no se recalculan ni se sobreescriben.
