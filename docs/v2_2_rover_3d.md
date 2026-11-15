# V2.2 · Renderizador 3D del rover (WebGL2, offline)

La V2.2 integra el simulador 2D-A* de V2.1 con una vista tridimensional del **mismo modelo digital de elevación**. No descarga Three.js ni requiere servir la página por HTTP: todos los shaders y el motor WebGL2 están embebidos en el HTML autónomo de la V2.2.

## Utilización

1. Abrí el atlas con `EJECUTAR_V2.ps1 -SoloRover`.
2. En **Simulación rover** seleccioná `Argentina · P04` o `Argentina · P08` y definí A/B sobre el mapa 2D.
3. Pulsá `Calcular ruta A*` y revisá distancia y pendiente. Pulsá **Terreno 3D · Explorar**.
4. Cambiá la cámara entre **Orbital**, **Aérea** y **Seguir rover**. Usá `Reproducir`, `Pausar`, `Reiniciar`, `Velocidad` y `Pantalla completa`.
5. La rueda acerca/aleja, arrastrar rota y Shift+arrastrar desplaza el centro de cámara. Podés elegir representación por elevación, pendiente o celdas restringidas.
6. Volvé a **Mapa 2D · Planificar** para cambiar restricciones o puntos A/B y recalcular. El motor 3D recibe el resultado de ese cálculo: **no ejecuta un A* paralelo**.

## Sistema de unidades

La geometría usa coordenadas físicas locales en **metros**, con un origen desplazado al centro del DEM para evitar errores numéricos en WebGL. El eje horizontal conserva `cell_size_x_m` y `cell_size_y_m`. La altura se dibuja como `(elevation_m - min_elevation_m) × visual_vertical_exaggeration`; **la elevación original no cambia**. `1×` conserva proporciones físicas, mientras que `2×` (inicial) facilita reconocer cambios suaves del relieve a escala de kilómetros. La exageración **no modifica** rutas ni pendientes del A*.

Una banda amarilla dibuja la trayectoria como secuencia de centros de celda, sin interpolación lateral hacia otras celdas. El rover es un **símbolo 3D esquemático sobredimensionado para visualización**; su tamaño, dinámica, suspensión y agarre no simulan un vehículo validado. Su orientación general sigue el rumbo de la ruta; la inclinación gráfica responde al gradiente local de elevación, pero no es una solución de estabilidad dinámica.

## Rendimiento / LOD

- WebGL2 con buffers de geometría reutilizables y renderizado bajo demanda, salvo durante la animación.
- Calidad automática: malla completa cerca (`LOD ×1`), 1/2 a distancia media (`LOD ×2`) y 1/4 en panorámica (`LOD ×4`). También hay modos completo y económico.
- Se descartan polígonos sin datos válidos. Si un bloque de celdas nativas incluye un hueco, su polígono LOD no puentea el hueco artificialmente.
- La resolución del lienzo se limita a 1600×1100 píxeles y la densidad de pantalla a 1,6× para evitar cargar excesivamente la GPU.
- Al volver al mapa 2D se detiene la animación 3D. Si WebGL2 falla o no está disponible, el mapa A* 2D continúa operativo.

## Límites científicos

**NASADEM ~30 m** describe relieve regional/local, no obstáculos a escala de rueda. Un terreno que aparece llano en 3D puede tener rocas, dunas, surcos, suelos blandos o zanjas no representadas. No usar las rutas para una misión robótica física ni para afirmar transitabilidad.

**MOLA / LOLA regionales** mantienen función cartográfica y de contexto: no se activan como DEM de navegación. Se admiten DEM locales propios con tamaño de celda explícito mediante el importador de V2.1.

El índice de ruta es relativo, **no energía eléctrica real**; el rover 3D no aporta un modelo de dinámica, gravedad o interacción con regolito. En la feria puede mostrarse como **simulación geoespacial exploratoria basada en elevaciones medidas**.
