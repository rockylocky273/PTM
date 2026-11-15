# V2.1 — Simulación de rover sobre DEM con unidades físicas

## Qué se reutilizó del simulador aportado

Los archivos `index.html`, `styles.css`, `app.js` y `simulation_engine.js` se preservan sin cambios en `rover_original/`. Inspiraron la selección de puntos de misión, la búsqueda A*, la visualización de amenazas, la animación y el registro de telemetría. **No se ejecutan directamente sobre los datos científicos**, porque el motor original:

- normalizaba cualquier DEM importado al intervalo artificial ~2–97 m;
- suponía separaciones horizontales de `CELL_WORLD_METERS = 1` para cualquier terreno;
- mezclaba configuraciones de gravedad, rozamiento y cohesión arbitrarias para imprimir julios;
- reportaba un porcentaje de «analogía validada» calculado a partir de dos índices de trayectoria, sin una validación física.

La V2.1 reemplaza esas operaciones para planificación de rutas: mantiene las elevaciones originales en metros, calcula la distancia horizontal real de cada paso y distingue un **índice relativo de recorrido**, no energía física ni seguridad.

## Fuentes y niveles de detalle

| Zona | Fuente | Modo |
|---|---|---|
| Argentina p04 | NASADEM HGT original procesado | Ruta de reconocimiento regional |
| Argentina p08 | NASADEM HGT original procesado | Ruta de reconocimiento regional |
| Otro sitio cargado por el usuario | JSON o DEM GeoTIFF | Ruta exploratoria al tamaño de celda declarado |
| MOLA de Marte (~15 km/celda) | MOLA MEGDR histórico | Solo visualización: **no** planificación de movilidad |
| ETOPO mundial (~18 km/celda) | ETOPO | Solo contexto regional |
| Terreno matemático de prueba | Funciones sintéticas | Demo de interfaz, **nunca** investigación empírica |

La conversión de NASADEM selecciona una ventana local de hasta 128 × 128 celdas **nativas** alrededor de p04 y p08, sin normalizar ni interpolar. En el ecuador 1 arcsec equivale nominalmente a ~30 m; la separación horizontal depende de la latitud. El programa registra el tamaño real x/y en metros. Las ventanas pueden tener menos celdas si el archivo NASADEM original es menor.

NASA LEDM / LOLA y MOLA del atlas son productos de resolución regional; una comparación visual no demuestra aptitud de navegación. Para simular rocas y obstáculos de menos de un metro se necesitan DEMs locales de alta resolución y/o sensores específicos, no un simple zoom.

## Interfaz integrada

1. Abrí **Simulación rover** en el panel V2.1.
2. Seleccioná `Argentina · P04` o `Argentina · P08` si ambas tienen DEM real. El origen de datos se muestra en la interfaz.
3. Ajustá **pendiente máxima** y **penalización por ascenso**.
4. Pulsá `Elegir inicio A`, hacé clic en el terreno y después `Elegir destino B`.
5. Ejecutá `Calcular ruta A*`, luego `Animar rover` o `Exportar ruta JSON`.
6. El botón `Simular ruta sobre este sector` en el detalle de p04/p08 también abre el rover.

El A* no atraviesa celdas sin elevación ni celdas que superen el límite de pendiente, impide diagonales a través de esquinas bloqueadas y reporta explícitamente si no existe ruta. El modelo minimiza distancia ponderada por ascenso y descenso; los parámetros son escenarios del usuario. No predice consumo energético, tracción, huellas o resistencia del suelo.

## Importar un modelo más detallado (GeoTIFF)

Instalá la dependencia opcional en el entorno del proyecto:

```powershell
.\.venv\Scripts\python.exe -m pip install -e ".[rover]"
```

Si reutilizás el Python de V1.3.3, podés instalar `rasterio` allí sin sobrescribir los demás paquetes:

```powershell
..\mars_analog_engine_v1_3_3\.venv\Scripts\python.exe -m pip install "rasterio>=1.3,<2"
```

Ejemplo de conversión de un DEM GeoTIFF local (originalmente en **metros verticales**, georreferenciado o con tamaño de píxel explícito):

```powershell
$env:PYTHONPATH = (Join-Path $PWD "src")
..\mars_analog_engine_v1_3_3\.venv\Scripts\python.exe -m mars_analog.data mars-rover-import-geotiff --input ".\mi_modelo_local.tif" --output ".\mi_modelo_rover.json" --size 128
```

Después elegí `Importar DEM` en el panel y cargá `mi_modelo_rover.json`. El conversor **no aumenta la resolución**; toma un recorte nativo, registra su SHA-256, sistema de coordenadas, separación horizontal y elevaciones originales. No acepta una proyección rotada ni una malla sin tamaño de píxel interpretable.

Un GeoTIFF que no informa CRS puede usarse **solo si conocés y especificás el tamaño de su píxel cuadrado en metros** mediante `--cell-size-m`. También debés verificar que las unidades de las elevaciones sean metros. Para modelos marcianos de alta resolución, verificá especialmente el datum, unidades, proyección y tamaño de celda antes de importarlos.

### JSON de entrada manual

```json
{
  "id": "my_field_dem",
  "display_name": "DEM local medido",
  "source": "levantamiento propio",
  "cell_size_x_m": 2.0,
  "cell_size_y_m": 2.0,
  "elevation_m": [[100.0, 100.1], [100.2, 100.4]]
}
```

*Nota: es un ejemplo de estructura. El importador de la interfaz requiere una matriz rectangular de al menos 10×10 valores; los huecos se representan con `null`.*

## Para los jueces

> «Conectamos una planificación de trayectorias A* a modelos digitales de elevación georreferenciados. El motor convierte diferencias de elevación en pendientes utilizando la separación física entre píxeles y encuentra rutas que respetan un límite de inclinación. La simulación es exploratoria: con un DEM de 30 metros podemos investigar el relieve local, pero no garantizar que un rover evite rocas o zanjas menores que una celda».
