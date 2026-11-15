# Mars Analog Engine V1.3.2 — Incertidumbre y comparación equilibrada

## Objetivo

Comparar las tres hipótesis volcánicas terrestres previamente destacadas para **Elysium Planitia** utilizando **el mismo conjunto común de evidencias**. No se hace un ranking geológico nuevo, no se reemplaza el ranking V1.2 ni se atribuye a los sitios una probabilidad de analogía planetaria.

Las regiones provienen de V1.3.1:

- `r026_c146`: Argentina, puesto original 6; dos puntos GLiM `Basic volcanic rocks` de nueve.
- `r069_c067`: puesto original 8; dos puntos `Pyroclastics` de nueve.
- `r067_c038`: puesto original 19; un punto `Intermediate volcanic rocks` de nueve.

**No se deducen posiciones nuevas de las versiones anteriores:** las posiciones bajo escala de 15 y 40 km, Robust Log L2, percentiles y perturbaciones de pesos se recalculan para las tres regiones en el equipo local del usuario. Las 25 regiones GLiM son anclas previamente seleccionadas; no son 25 sorteos aleatorios ni necesariamente los primeros 25 puestos.

## Qué se analiza (mismas pruebas para los tres)

1. **Distancias y métodos:** puesto de V1.2 + puesto Robust Log L2 + puesto de percentiles, calculados a partir de las características de los 2.617 candidatos del ranking V1.2 con las mismas fórmulas de V1.2.1. El archivo de auditoría V1.2.1 y los hashes quedan enlazados y verificados. No se comparan distancias numéricas no normalizadas entre métodos.
2. **Escalas:** puestos individuales a 15, 30 y 40 km mediante `multiscale_rankings.csv`. Se verifica que **todos** los puestos a 30 km reproducen el ranking V1.2. Si una región falta a una escala, se informa como *sin datos*, no como puesto malo.
3. **Pesos:** reproduce los escenarios `Dirichlet(W*35)` y la semilla grabados en el reporte de auditoría V1.2.1 (históricamente 60 escenarios, semilla 2026). Se registran mínimo, mediana, máximo, y número de escenarios dentro de los top 10, 25 y 50. Son simulaciones de sensibilidad, **no intervalos de confianza geológicos**.
4. **Nueve observaciones GLiM:** recuentos por litología y prueba leave-one-out: se omite sucesivamente cada una de las nueve observaciones y se verifica si aún existe alguna señal volcánica cartográfica. Por ejemplo, dos observaciones volcánicas de nueve sobreviven a las nueve eliminaciones simples; una sola observación sobrevive a ocho de las nueve. **No significa que conozcamos la proporción regional volcánica**.
5. **Submuestreo de las nueve observaciones:** la probabilidad combinatoria de conservar al menos una observación volcánica cuando se toman `k` de las nueve ya registradas (k=1,3,5,9) sin reemplazo. Esta cifra describe **únicamente esos nueve registros**, no es una probabilidad de presencia de rocas ni un intervalo de confianza para toda la región. Los puntos pueden estar espacialmente correlacionados.
6. **Categorías mezcladas:** una región con `Metamorphics` y sedimentos conserva ambas categorías; ya no se presenta como «solo sedimentos». La nueva versión añade una etiqueta corregida sin reescribir V1.3.1, preservando la relación antigua como evidencia histórica.

## Lo que NO se considera en la comparación común

- **p04/p08 Argentina**: los polígonos GLiM y NASADEM a ~30 m son importantes para geología local, pero los otros dos candidatos todavía no tienen polígonos y DEM analizados con exactamente el mismo protocolo. Se mantiene la investigación como **anexo asimétrico**; esos datos no contribuyen a la comparación tripartita.
- **Clima NASA POWER**: contexto de campo terrestre, no un análogo del clima marciano, por eso no entra en la sensibilidad topográfica.
- **Frecuencias de puntos**: ni las 9 observaciones de Marte ni las 9 de GLiM miden superficie, litología exacta, edad radiométrica o procesos confirmados.
- **Robustez espacial geológica real**: no está medida. Para analizarla se necesitan polígonos homogéneos y distancias entre observaciones, idealmente un diseño estratificado y mapas de mayor resolución para las tres regiones. La sensibilidad de escala que entrega esta versión es *topográfica*, no evaluación espacial de afloramientos.

## Instalación en Windows PowerShell

Descomprimir `mars_analog_engine_v1_3_2.zip` en la carpeta Downloads, al lado de V1.3.1; ejecutar dentro de `mars_analog_engine_v1_3_2`:

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e ".[dev]"
.\.venv\Scripts\python.exe -m pytest -q
New-Item -ItemType Directory -Path .\data -Force | Out-Null
Copy-Item -Path "..\mars_analog_engine_v1_3_1\data\*" -Destination ".\data" -Recurse -Force
```

**Requisitos previos de datos** (todos producidos en versiones anteriores):

```powershell
@(
  'data/reports/mars_geology_correspondence_v1_3_1.json',
  'data/reports/mars_profiles_screen_v1_2.json',
  'data/catalog/mars_profiles_v1_2.json',
  'data/reports/mars_audit_v1_2_1/rank_audit_report.json',
  'data/reports/mars_audit_v1_2_1/scales/multiscale_audit_report.json'
) | ForEach-Object { [PSCustomObject]@{Archivo=$_; Existe=(Test-Path $_)} } | Format-Table -AutoSize
```

## Ejecutar la V1.3.2

```powershell
.\.venv\Scripts\python.exe -m mars_analog.data mars-uncertainty-build
```

Resultados:

- `data/results/mars_uncertainty_v1_3_2.csv`: tres filas, una por candidato, con puestos de cada prueba.
- `data/results/mars_uncertainty_v1_3_2_anchor_controls.csv`: clasificaciones GLiM corregidas de todas las anclas disponibles en el perfil.
- `data/reports/mars_uncertainty_v1_3_2.json`: recuentos, pesos, rangos, exhaustividad, advertencias e integridad SHA-256.
- `data/reports/mars_uncertainty_v1_3_2.md`: informe en tabla, revisable a simple vista.

Consulta resumida:

```powershell
.\.venv\Scripts\python.exe -m mars_analog.data mars-uncertainty-review
```

Solo Argentina:

```powershell
.\.venv\Scripts\python.exe -m mars_analog.data mars-uncertainty-review --region r026_c146
```

Tabla de puestos con columnas sencillas:

```powershell
Import-Csv .\data\results\mars_uncertainty_v1_3_2.csv |
 Select-Object earth_region_id,topographic_rank_original,refined_lithology_observation,volcanic_observed,leave_one_out_retained |
 Format-Table -AutoSize
```

Controles con nueva clasificación:

```powershell
Import-Csv .\data\results\mars_uncertainty_v1_3_2_anchor_controls.csv |
 Select-Object region_id,topographic_rank,refined_lithology_observation |
 Format-Table -AutoSize
```

También se puede comparar un subconjunto alternativo de al menos dos regiones muestreadas:

```powershell
.\.venv\Scripts\python.exe -m mars_analog.data mars-uncertainty-build --candidates r026_c146,r069_c067,r067_c038 --top-ks 10,25,50
```

Todos los comandos son **offline**: no consultan NASA, USGS, GLiM ni AppEEARS y no modifican los resultados históricos. La validación con los datos reales del usuario está pendiente de ejecución local; las pruebas del paquete usan datos sintéticos.

## Próxima fase V1.3.3

Una validación externa debería seleccionar **análogos y controles conocidos antes de puntuar resultados**, y recopilar cartografía geológica regional, imágenes orbitales, geometría de afloramientos y evidencia mineralógica independiente para cada candidato en condiciones comparables. Una búsqueda que selecciona sus propios mejores casos no puede validarse únicamente con los mismos datos que utilizó para elegirlos.
