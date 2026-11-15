# V2.0.5 — visor topográfico continuo de la Tierra

## Problema resuelto

La V2.0.4 dibujaba ventanas de relieve independientes (~9° × 7°). El usuario no podía navegar más allá de esas ventanas, pese a existir un mosaico de elevación ETOPO continuo en su instalación. La V2.0.5 implementa un solo explorador mundial basado en ETOPO, con desplazamiento, zoom, enfoque en las 25 regiones de Elysium, y superposición local de NASADEM únicamente donde existen elevaciones.

## Datos, resolución y coordenadas

Fuente terrestre: `processed/earth_global_land.nc`, con atributos `planet=Earth` y `schema=global_land_surface_v0.6`; variable `land_elevation_m`, ejes `latitude`/`longitude` ascendentes. Se valida resolución angular uniforme y extensión global. El visor conserva `raster_lon_west_edge_deg` y `raster_lat_north_edge_deg` para respetar que el muestreo histórico a 10' retiene el origen de la grilla NOAA original. No se fuerzan celdas a centros geográficos no observados.

Se exportan dos imágenes RGB PNG dentro del HTML: una colorea altura y aplica sombreado derivado de diferencias de elevación; la otra codifica elevación terrestre redondeada a 1 m con `uint16 = elevación+32768`, dejando `65535` para ausencia de datos (océanos/áreas no cartografiadas). La consulta del cursor lee los dos bytes altos y aplica la máscara. Las imágenes se codifican con PNG zlib de la biblioteca estándar, sin paquetes externos de mapas o solicitudes de teselas.

Las elevaciones globales siguen siendo de 10 minutos (~18,5 km meridianos). Zoom no mejora su precisión ni incorpora alturas fuera de la cuadrícula. NASADEM p04/p08 aparece en una capa localizada, con extensión georreferenciada y resolución de pantalla limitada por el stride de muestreo previo. No se hacen afirmaciones sobre riesgo operativo de vehículos, aterrizaje o equivalencia geológica.

## Interacción

- Mapamundi inicial con los 25 marcadores.
- Clic sobre marcador o selector de candidatos para centrar y aproximar.
- Arrastre, zoom con rueda y botones, doble clic y teclas de flecha.
- Capas opcionales: ventana de análisis de 240 km, celdas de 2°, graticulado, detalles NASADEM argentinos.
- Botones para abrir la auditoría o la ficha original del candidato; desde la ficha hay enlace inverso al explorador.
- Mapa y datasets integrados en el HTML, apto para una demostración offline.
- El recuadro de 240 km señala la escala del método de comparación (aproximada en una esfera), no restringe la navegación.

## Ensayos de calidad

Pruebas locales para el codec PNG sin dependencia Pillow, sentinela de datos no disponibles, signos de altitud, validación de planetas y coordenadas, malla histórica desplazada, procedencia, regresiones y construcción del atlas. Prueba manual automatizada con Chromium/Playwright de interacciones y ausencia de errores JavaScript. Se usa una grilla **sintética** para las pruebas automatizadas; los mapas verdaderos se generan en el equipo del usuario desde su ETOPO y NASADEM históricos.
