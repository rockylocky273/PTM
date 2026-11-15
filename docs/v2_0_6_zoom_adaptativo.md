# V2.0.6 — Visor topográfico continuo dentro de cada candidato

## Problema corregido
La versión anterior ampliaba una textura `atlas.maps[region_id]` de tamaño fijo: al arrastrar o alejar la cámara quedaban visibles sus bordes. El nuevo visor coloca los candidatos directamente sobre las coordenadas del modelo de elevación mundial.

## Solución
- La cuadrícula NOAA ETOPO en `processed/earth_global_land.nc` se valida antes del renderizado, igual que V2.0.5.
- La representación global en PNG se decodifica una vez y se prepara una pirámide de niveles de imagen; el renderizador selecciona un nivel con base en la escala pantalla/celda.
- El navegador dibuja solamente la fracción visible del terreno (`drawImage` de origen y destino recortados), con repetición controlada en el antimeridiano y desplazamiento libre.
- Elevaciones consultables provienen de la imagen sin pérdida que codifica metros mediante dos bytes, sin interpolaciones inventadas.
- Curvas de nivel ETOPO calculadas por marching squares desde una grilla visible de tamaño acotado; cuando el usuario se aproxima al recorte NASADEM se sustituyen por curvas locales.
- Los modelos NASADEM disponibles solo en p04/p08 se dibujan con feathering transparente para integrar los recortes en el fondo continuo, y muestran opcionalmente máscara GLiM.
- La celda 2° o el área local estudiada se muestran bajo demanda con el botón «Celda de estudio» (desactivado por defecto). No son fronteras que impidan el desplazamiento.
- La vista nunca afirma mejorar los datos nativos de ETOPO: los mipmaps simplifican la visualización al alejarse, y únicamente NASADEM introduce cotas locales más finas.

## Ensayos
Pruebas automatizadas heredadas e integración en Python, más inspección en Chromium con datos sintéticos a tamaño mundial de 2160 × 1080, zoom a escala mundial y acercamiento, longitudes cercanas a 180°, y navegación entre Tierra/Marte/Luna. Sin cambios en criterios de analogía ni resultados cuantitativos.
