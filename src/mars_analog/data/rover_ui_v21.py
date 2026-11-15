"""Add a physically scaled, offline rover reconnaissance tab to the atlas.

Original user-provided simulation is preserved verbatim under rover_original/,
while this module avoids its 0..100 height rescaling, 1m cell assumption,
fictional Joule calculations and fabricated analog viability percentage.
"""
from __future__ import annotations
from pathlib import Path

NAV = '<button data-view="rover" aria-selected="false">Simulación rover</button>'
SECTION = '''
<section class="view" id="view-rover" hidden>
 <div class="panel rover-panel">
  <div class="kicker">V2.1 · Terrain Mobility Research</div>
  <h2>Simulación de rover · Rutas sobre topografía local</h2>
  <p class="lead">Planificá rutas entre dos puntos usando elevaciones físicas, distancias reales entre celdas y un algoritmo A*. La animación muestra un recorrido simulado. Los datos NASADEM permiten reconocimiento regional, <b>no detección de obstáculos pequeños ni certificación de transitabilidad</b>.</p>
  <div class="rover-grid">
   <aside class="rover-side">
    <label class="rover-label" for="rover-terrain-select">Terreno</label>
    <select id="rover-terrain-select"></select>
    <label class="rover-label" for="rover-upload">Importar DEM (JSON con metros por celda)</label>
    <input type="file" id="rover-upload" accept=".json,application/json">
    <p class="small">Acepta <code>elevation_m</code>, <code>cell_size_x_m</code> y <code>cell_size_y_m</code>. Sin normalización de altitudes.</p>
    <div class="rover-sep"></div>
    <label class="rover-label" for="rover-max-slope">Pendiente máxima <strong id="rover-slope-value">15°</strong></label>
    <input type="range" id="rover-max-slope" min="3" max="35" value="15" step="1">
    <label class="rover-label" for="rover-uphill">Penalización por ascenso <strong id="rover-uphill-value">5×</strong></label>
    <input type="range" id="rover-uphill" min="0" max="20" value="5" step="1">
    <div class="rover-sep"></div>
    <p class="rover-label">Puntos de misión</p>
    <div class="rover-tools"><button type="button" id="rover-pick-start">Elegir inicio A</button><button type="button" id="rover-pick-goal">Elegir destino B</button></div>
    <label class="rover-check"><input type="checkbox" id="rover-show-hazards" checked> Mostrar pendientes no transitables</label>
    <label class="rover-check"><input type="checkbox" id="rover-show-grid"> Mostrar celdas del DEM</label>
    <div class="rover-tools"><button id="rover-plan" class="primary">Calcular ruta A*</button><button id="rover-animate">Animar rover</button></div>
    <div class="rover-tools"><button id="rover-reset-view">Recentrar vista</button><button id="rover-export">Exportar ruta JSON</button></div>
    <p class="rover-source" id="rover-source">Eligiendo datos de elevación...</p>
   </aside>
   <div class="rover-main">
    <div class="rover-toolbar"><strong id="rover-map-name">Terreno de misión</strong><span id="rover-map-scale">—</span></div>
    <div class="rover-map-wrap"><canvas id="rover-canvas" width="920" height="660" tabindex="0" aria-label="Modelo topográfico y trayectoria de rover; clic para elegir origen y destino"></canvas><div class="rover-map-hint" id="rover-map-hint">Rueda: zoom · Arrastrar: mover · Botones: seleccionar A/B</div></div>
    <p class="small" id="rover-hover">Seleccioná el terreno. A y B se pueden ajustar haciendo clic en el mapa.</p>
    <div class="rover-metrics">
     <div><span>Longitud de ruta</span><strong id="rover-distance">—</strong></div>
     <div><span>Ascenso acumulado</span><strong id="rover-ascent">—</strong></div>
     <div><span>Pendiente máxima del recorrido</span><strong id="rover-route-slope">—</strong></div>
     <div><span>Coste relativo de recorrido</span><strong id="rover-cost">—</strong></div>
    </div>
    <div class="rover-feedback" id="rover-status" role="status">Cargá una zona con DEM disponible.</div>
    <p class="small"><b>Interpretación:</b> el coste es un índice heurístico ponderado, no energía en julios. El DEM de ~30 m no identifica rocas, escalones ni obstáculos menores a la separación de muestras. Una ruta encontrada no garantiza que un vehículo físico pueda recorrerla. El atlas Marte/Luna conserva sus mapas científicos, pero no se emplea para simulación operacional de movilidad con resolución kilométrica.</p>
   </div>
  </div>
 </div>
</section>
'''

CSS = r'''
/* V2.1 rover reconnaissance, deliberately independent of planetary rankings */
.rover-grid{display:grid;grid-template-columns:280px minmax(0,1fr);gap:16px;align-items:start;margin-top:15px}
.rover-side{border:1px solid #d8e6e8;border-radius:12px;padding:17px;background:#f7fbfb;display:flex;flex-direction:column;gap:10px}
.rover-label{display:block;font-weight:750;color:#285966;font-size:12px;margin-top:5px}
.rover-label strong{float:right;color:#0a727b}.rover-side select,.rover-side input[type=file]{width:100%;border:1px solid #c4d9dc;border-radius:8px;padding:9px;background:white;color:#254d58}
.rover-side input[type=range]{width:100%;accent-color:#10878a}.rover-side code{font-size:11px}.rover-sep{height:1px;background:#dce7e8;margin:6px 0}
.rover-tools{display:flex;gap:7px;flex-wrap:wrap}.rover-tools button{border:1px solid #b4d2d6;background:#fff;color:#195d69;border-radius:8px;padding:9px 10px;font-weight:750;font-size:12px;flex:1;min-width:100px}
.rover-tools button.primary,.rover-tools button[aria-pressed=true]{background:#0f7480;color:white;border-color:#0f7480}.rover-tools button:disabled{opacity:.4;cursor:not-allowed}
.rover-check{color:#395e66;font-size:12px;display:flex;align-items:center;gap:7px}.rover-check input{accent-color:#127c82}
.rover-source{font-size:11px;line-height:1.5;color:#566f78;overflow-wrap:anywhere;padding:10px;background:#eaf4f5;border-radius:8px}
.rover-main{min-width:0}.rover-toolbar{display:flex;justify-content:space-between;flex-wrap:wrap;gap:7px;margin-bottom:8px;color:#245661}
.rover-toolbar span{color:#5c7b83;font-size:12px}.rover-map-wrap{border-radius:13px;overflow:hidden;background:#112e3c;position:relative;min-height:350px}
.rover-map-wrap canvas{width:100%;display:block;aspect-ratio:920/660;height:auto;touch-action:none;cursor:grab}.rover-map-hint{position:absolute;top:11px;left:11px;background:#132e3ddb;color:white;border-radius:8px;padding:7px 10px;font-size:11px;pointer-events:none}
.rover-metrics{display:grid;grid-template-columns:repeat(4,1fr);gap:9px;margin:10px 0}.rover-metrics>div{padding:12px;background:#f2f8f8;border:1px solid #daebec;border-radius:9px}.rover-metrics span{font-size:11px;color:#52707a;display:block}.rover-metrics strong{font-size:17px;color:#0e5b68;display:block;margin-top:5px}
.rover-feedback{padding:10px 13px;background:#edf7f7;border-left:3px solid #158b80;color:#285260;border-radius:5px;margin-bottom:10px;font-size:12px}
@media(max-width:940px){.rover-grid{grid-template-columns:1fr}.rover-side{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:9px}.rover-side .rover-sep{grid-column:1/-1}.rover-source{grid-column:1/-1}.rover-metrics{grid-template-columns:repeat(2,1fr)}}
@media(max-width:520px){.rover-side{display:flex}.rover-metrics{grid-template-columns:repeat(2,1fr)}}
'''


def add_rover_dashboard(page: str) -> str:
    """Add a fully offline new section without changing historical JS behavior."""
    if page.count('</nav>')!=1 or page.count('</style>')!=1 or page.count('</body>')!=1:
        raise ValueError('HTML del atlas no contiene los puntos de integración esperados')
    page = page.replace('</style>', CSS+'</style>',1)
    page = page.replace('</nav>', NAV+'</nav>',1)
    page = page.replace('<section class="view" id="view-reference"',SECTION+'<section class="view" id="view-reference"',1)
    js_path = Path(__file__).with_name('rover_view_v21.js')
    script = js_path.read_text(encoding='utf-8')
    if '</script' in script.lower():
        raise ValueError('Script rover contiene una etiqueta de cierre no permitida')
    page = page.replace('</body>', '<script>'+script+'</script></body>',1)
    return page.replace('V2.0.6 ·', 'V2.1 ·').replace('V2.0.6 /', 'V2.1 /')
