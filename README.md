# Mars Analog Discovery Engine V2.2 — Rover 3D con terreno DEM real

**Nuevo:** pestaña **Simulación rover** → **Terreno 3D · Explorar**. Visualización 3D WebGL2 completamente local, sin CDN ni conexiones al abrir el archivo. La malla conserva alturas NASADEM y separación horizontal originales, con LOD automático, tres cámaras, trayectoria A* amarilla y rover esquemático animado. La vista 2D original sigue planificando rutas.

## Ejecutar en Windows

Extraé `mars_analog_engine_v2_2.zip` **junto a** `mars_analog_engine_v1_3_3` (que contiene los datos históricos). En PowerShell, dentro de la carpeta V2.2:

```powershell
powershell -ExecutionPolicy Bypass -File .\EJECUTAR_V2.ps1 -SoloRover
```

Entrá en **Simulación rover**, elegí **Argentina P04** o **P08**, pulsá **Calcular ruta A\*** en el mapa 2D y después **Terreno 3D · Explorar**. Allí podés girar el terreno, cambiar de cámara, reproducir, pausar, reiniciar, ajustar velocidad y exageración vertical o elegir el mapa de pendientes. Los mismos resultados A* se mantienen; 3D no cambia el planificador.

**Importante:** la exageración vertical es únicamente gráfica (1× es la escala física); las alturas originales no se reescalan. El rover se representa ampliado para facilitar la observación. La resolución NASADEM nominal ~30 m **no detecta** piedras, zanjas o obstáculos de menos de una celda. Esta simulación es exploratoria, no valida seguridad de navegación real.

Si WebGL2 no está disponible, la vista 2D sigue operativa. Para datos propios podés importar un JSON o GeoTIFF mediante los comandos de V2.1. El archivo HTML final es autónomo; no requiere acceso a Internet.

[Documentación de la simulación 3D](docs/v2_2_rover_3d.md)

---

# Mars Analog Discovery Engine V2.1 — Atlas planetario + Simulación de rover

**Nueva función:** sección «Simulación rover» integrada en el atlas. Procesa los DEM reales NASADEM de los sectores argentinos p04 y p08 **a resolución nativa**, sin convertir las alturas a un rango artificial ni asumir un metro por celda. Usa A* con pendientes físicas, distancias en metros, coste heurístico, animación y exportación de rutas. Además acepta modelos locales de mayor resolución mediante JSON o GeoTIFF. **No certifica seguridad de navegación real.**

## Windows — ejecutar con datos históricos

Extraé la carpeta `mars_analog_engine_v2_1` junto a `mars_analog_engine_v1_3_3` (donde están los datos científicos históricos). Abrí PowerShell en V2.1 y ejecutá:

```powershell
powershell -ExecutionPolicy Bypass -File .\EJECUTAR_V2.ps1 -SoloRover
```

El lanzador reutiliza el Python y los datos de V1.3.3, reconstruye el atlas y abre `data\reports\mars_v2_0\mars_analog_dashboard_v2.html`. No realiza nuevas descargas. Para reconstruir además el contexto climático y lunar faltante, ejecutá el lanzador sin `-SoloRover`.

Entrá a **Simulación rover**. Podés cambiar entre `Argentina P04` y `Argentina P08`, elegir inicio A y destino B, variar la pendiente máxima y buscar una ruta, animarla y exportarla como JSON.

**Nota sobre la precisión:** NASADEM tiene una separación nominal de ~30 m, así que el planificador representa reconocimiento local, no detección de piedras, grietas o escalones menores a la celda. Para verdaderas rutas de rover se necesita un DEM de resolución métrica o submétrica, que podés importar con el comando documentado en [docs/v2_1_rover.md](docs/v2_1_rover.md). MOLA regional, LOLA LDEM_4 y ETOPO no se presentan como fuentes aptas para evitar obstáculos físicos.

Los cuatro archivos completos de tu simulador original están preservados en la carpeta `rover_original/` para auditoría y comparación del código.

---

## Funcionalidades de V2.0.6 heredadas

**Principal cambio:** el mapa de cada **región candidata** (menú «Explorar candidatos») ya no termina en una ventana regional rectangular. Se reemplazó la ampliación de una imagen fija por una cámara geográfica conectada al mosaico mundial histórico NOAA ETOPO. Podés alejarte indefinidamente hasta la vista global, recorrer regiones vecinas y acercarte de nuevo. El rectángulo de la celda 2° se mantiene solo como anotación, nunca como límite geográfico.

La versión conserva todo lo anterior: mapas marcianos MOLA, atlas lunar LOLA, mapa mundial de los 25 candidatos, clima NASA POWER, geología GLiM, auditorías de sensibilidad e informes. No cambia ninguna cifra o ranking científico.

## Windows — instalación en un comando

Extraé `mars_analog_engine_v2_0_6.zip` **junto a** `mars_analog_engine_v1_3_3` (los datos históricos deben estar en la carpeta V1.3.3). Abrí PowerShell dentro de `mars_analog_engine_v2_0_6`:

```powershell
powershell -ExecutionPolicy Bypass -File .\EJECUTAR_V2.ps1 -SoloMapa
```

Para reconstruir todo el informe y completar clima/Luna cuando falten:

```powershell
powershell -ExecutionPolicy Bypass -File .\EJECUTAR_V2.ps1
```

El lanzador reutiliza el entorno de Python y los datos históricos de V1.3.3, y auditorías V2.0.4 si existen. No reescribe los datos originales. El panel se abre automáticamente y también queda en `data\reports\mars_v2_0\mars_analog_dashboard_v2.html`.

## Cómo utilizar el visor adaptativo

1. Abrí **Explorar candidatos** y seleccioná cualquier país de la lista.
2. Verás su ubicación y relieve **en un fondo topográfico continuo**, inicialmente con contexto regional de alrededor de 1.000 km de anchura (varía con latitud y tamaño de pantalla).
3. Rueda del mouse: acercar/alejar en torno al cursor. `+`, `−` y `Restablecer` también funcionan; arrastrá para recorrer alrededor de la región sin ningún borde artificial.
4. El visor indica la **anchura aproximada en kilómetros** que estás viendo y el **nivel LOD** de imagen utilizado. Mantiene una celda 2° punteada con fines explicativos, pero podés salir de ella.
5. Para Argentina, los sectores **p04 / p08** pasan a su ubicación exacta y utilizan imágenes NASADEM *si los NetCDF históricos existen*. Al aumentar el zoom, el visor combina esas elevaciones más finas con ETOPO y suaviza los bordes de la superposición. Las curvas de nivel se calculan a partir del conjunto de elevaciones visible (ETOPO en zoom regional; NASADEM cuando el recorte está suficientemente ampliado).
6. La pestaña **Mapa mundial** sigue ofreciendo el mapa del planeta con los 25 puntos simultáneos.

## Cómo evita saturar la computadora

- **LOD / mipmaps:** el PNG ETOPO mundial se pre-reduce a varios tamaños en el navegador, una sola vez. Al alejarte se elige la versión adecuada según el tamaño de las celdas en pantalla.
- **Recorte antes de dibujar:** se envía a la pantalla únicamente la porción visible de la imagen, no una textura global escalada a millones de píxeles.
- **Cotas decodificadas una sola vez:** la malla de elevaciones se mantiene en un arreglo entero para las consultas del cursor y curvas de nivel.
- **Curvas de nivel acotadas:** se evalúan sobre una malla de pantalla limitada y se detienen a zooms extremos salvo donde existe NASADEM.
- **Renderizado con requestAnimationFrame:** las operaciones de arrastre y zoom no se ejecutan más veces de lo que puede dibujar el navegador.
- **Sin Internet para visualizar:** los mapas se embeben en el HTML final, como en V2.0.5.

## Límite científico de resolución

ETOPO histórico tiene **10 minutos de arco (~18,5 km por celda en latitud)**: **acercarse a una zona no crea detalle superior a esa resolución**. El aumento real de detalle solo está disponible en los dos sectores NASADEM p04 y p08 (muestras locales preparadas desde datos nominales de ~30 m). Los mapas de todos los demás candidatos son continuos y navegables, pero su detalle topográfico es el de ETOPO hasta que se incorporen nuevas fuentes geoespaciales. El objetivo de los mipmaps es reducir costos al alejarse, no interpolar datos que no existen.

## Verificación

El proyecto incluye todas las pruebas anteriores y nuevas pruebas de integración que comprueban la existencia del visor continuo, su fuente y sus límites. El control visual de navegador se realizó usando archivos **sintéticos** exclusivamente para prueba del software. Los mapas definitivos provienen de tus datos reales al ejecutar el programa en Windows.
