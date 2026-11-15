# Protocolo V2.0.4 — Extensión no retrospectiva de sensibilidad a 25 celdas

1. El conjunto de 25 IDs es el `earth_region_id` del perfil `elysium_planitia` en la correspondencia V1.3.1. Rechazamos IDs duplicados, faltantes o que no pertenezcan al catálogo de ranking de referencia. **No** se reordenan para optimizar resultados; el orden del informe es el puesto histórico a 30 km.
2. Invocamos el motor congelado `build_uncertainty` de V1.3.2 con los 25 IDs, las tres funciones, las tres escalas y las perturbaciones Dirichlet(W×35) de V1.2.1. La semilla real esperada es 2026 y 60 escenarios. La posición 30 km debe coincidir con la histórica para cada ID.
3. Comprobamos que los resultados originales de las tres regiones V1.3.2 sean idénticos en ranking por función, ranking por escala, frecuencias top-k y análisis de las 9 observaciones GLiM. Si no lo son, se rechaza la ampliación.
4. Si faltan posiciones en alguna escala, no se interpreta como puesto bajo ni se sustituye por cero. Los puestos de cada escala corresponden a poblaciones de distinto tamaño. El submuestreo GLiM conserva solo la estructura de los nueve puntos medidos.
5. Los mapas y auditorías del panel usan los valores nuevos **solo después** de comprobar su vinculación SHA-256 con el mismo informe V1.3.1 y la misma V1.3.2 usados por el atlas.

## Resultados esperados

25 filas y 25 fichas con pruebas homogéneas para Elysium Planitia. No son 25 nuevos análogos confirmados, ni porcentajes de similitud, ni una prueba de que la región con menor distancia sea geológicamente mejor. No presupone independencia espacial de las observaciones GLiM, ni seguridad de aterrizaje o desplazamiento.
