# Mars Analog Engine V2.0.2 — Atlas topográfico para presentación

## Objetivo

Presentar los hallazgos de la búsqueda Tierra–Marte de forma convincente, navegable y verificable. El panel abre con los resultados concretos, no con una lista de advertencias: seis perfiles marcianos, 25 regiones terrestres muestreadas con GLiM, 150 cruces geológicos y tres candidatos volcánicos de Elysium.

**No se afirma que la analogía geológica esté científicamente demostrada.** La diferencia es editorial: las limitaciones y la bibliografía están en su propia pestaña, mientras que la pantalla principal se concentra en los resultados observados.

## Instalación rápida Windows

1. Extraer `mars_analog_engine_v2_0_2.zip` junto a `mars_analog_engine_v1_3_3`.
2. Abrir PowerShell en la carpeta `mars_analog_engine_v2_0_2`.
3. Ejecutar:

```powershell
powershell -ExecutionPolicy Bypass -File .\EJECUTAR_V2.ps1
```

No hay que borrar la V2.0 anterior ni copiar gigabytes de datos. Se reutiliza la carpeta `data` y el entorno Python de V1.3.3 y se genera un HTML nuevo dentro de **la nueva carpeta V2.0.2**. También existe el lanzador `EJECUTAR_V2_0_1.ps1` con la misma funcionalidad.

Archivo para abrir posteriormente:
`data\reports\mars_v2_0\mars_analog_dashboard_v2.html`.

## Lista y coordenadas

La pestaña inicial presenta todas las **25 anclas terrestres con GLiM** de la búsqueda Elysium, por orden de puesto topográfico. Se muestra la latitud y longitud del **centro de la celda regional de 2°**, el puesto, las clases GLiM y la evidencia de volcanismo cuando existe.

Ejemplos de centros, **no ubicaciones de afloramientos ni coordenadas de una base**:

| ID | Lat. | Lon. | Tipo de evidencia previa |
|---|---:|---:|---|
| r026_c146 (Argentina) | -37° | -67° | 2 observaciones GLiM de rocas volcánicas básicas entre 9 |
| r069_c067 | 49° | 135° | 2 observaciones de piroclastos entre 9 |
| r067_c038 | 45° | 77° | 1 observación de rocas volcánicas intermedias entre 9 |
| r068_c061 | 47° | 123° | Señal volcánica y piroclástica; puesto 28 |

El campo `lat/lon` se calcula exclusivamente a partir del identificador de celda y la grilla de 2° del proyecto; no usa geolocalización automática.

## Mapas topográficos sin conexión

- **Regional, todos los 25:** lee `data/processed/earth_global_land.nc` generado en V0.6. Presenta elevación terrestre ETOPO 2022, rejilla histórica aproximada de 10 minutos de arco, centro y límites de la celda de 2° y curvas de nivel exploratorias.
- **Argentina p04:** lee `data/processed/nasadem_argentina_p04.nc`, generado por `nasadem-analyze`. Presenta elevación NASADEM, marcador p04 y máscara GLiM volcánica.
- **Argentina p08:** igual para `data/processed/nasadem_argentina_p08.nc`.

Para hacer el HTML liviano, NASADEM se **submuestrea para visualizar**, sin adjudicar resolución de 30 m a cada píxel dibujado. El texto debajo del mapa declara el salto. Las curvas de nivel son visualización de la grilla disponible, no productos cartográficos de precisión de campo.

El mapa permite mover con arrastre, acercar/alejar, activar curvas de nivel, alternar la máscara GLiM cuando existe, y consultar elevaciones y coordenadas al mover el cursor. Es completamente local y **no necesita acceso a mapas de terceros para mostrar el relieve**. El enlace opcional de OpenStreetMap sí requiere Internet.

Si faltan los NetCDF históricos se muestra **"Mapa no disponible"**: no se fabrica relieve y se conserva la ficha del candidato.

## Exportaciones

- `data/reports/mars_v2_0/mars_analog_dashboard_v2.html`: presentación interactiva y autocontenida con todos los mapas muestreados embebidos.
- `data/reports/mars_v2_0/elysium_candidates_geographic_atlas_v2.csv`: 25 regiones, coordenadas, puesto y observaciones.
- `data/reports/mars_v2_0/elysium_candidates_v2.csv`: las tres comparaciones prioritarias con escalas y métodos.
- `data/reports/mars_v2_0/mars_analog_report_v2.md`: informe con tabla de ubicación y fuentes.
- `data/reports/mars_v2_0/mars_analog_report_v2.json`: procedencia, conteos y hashes de mapas.

## Límites

Los centros de celda no son afloramientos. Los nueve puntos GLiM terrestres por región y nueve de USGS en Marte no estiman fracciones de superficie. El prototipo no realiza validación mineralógica ni determina seguridad de rutas, rovers o hábitats. El benchmark de nueve referencias externas sigue siendo inconcluso: tres de cuatro analogías directas quedaron fuera de la población terrestre clasificada.
