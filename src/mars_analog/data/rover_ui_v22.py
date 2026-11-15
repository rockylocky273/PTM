"""Upgrade the V2.1 rover pane with a bundled WebGL2 (offline) 3D viewer.

Reuses the exact V2.1 route and the physical DEM; no new scientific data are
created by this presentation layer. WebGL support is optional with 2D fallback.
"""
from pathlib import Path

CSS = r'''
/* V2.2: fully offline, bounded-resolution WebGL2 terrain display */
.rover-view-switch{display:flex;gap:8px;margin:8px 0 11px;flex-wrap:wrap}
.rover-view-switch button{border:1px solid #bbd7db;border-radius:9px;background:#f6fbfb;color:#245d66;padding:9px 16px;font-weight:750;cursor:pointer}
.rover-view-switch button[aria-pressed=true]{background:#0b6575;color:white;border-color:#0b6575}
.rover-3d-controls{display:flex;gap:10px;flex-wrap:wrap;align-items:center;background:#edf6f6;border:1px solid #cee1e5;padding:11px;border-radius:11px;margin-bottom:7px}
.rover-3d-controls label{font-size:11px;color:#235964;font-weight:700;display:flex;flex-direction:column;gap:4px}
.rover-3d-controls select{border:1px solid #bcd2d7;border-radius:7px;background:white;color:#1f5865;padding:6px 9px;font-size:12px;min-width:105px}
.rover-3d-controls input[type=range]{width:86px;accent-color:#117f88}
.rover-3d-controls button{border:1px solid #a8c8ce;background:white;color:#185c68;border-radius:8px;padding:8px;font-weight:700;cursor:pointer}
.rover-3d-controls button.strong{background:#0d7481;color:white}
.rover-3d-canvas-wrap{position:relative;border-radius:12px;overflow:hidden;background:#102531}
#rover-canvas-3d{display:block;width:100%;height:auto;aspect-ratio:920/620;touch-action:none;cursor:grab}
.rover-3d-hud{position:absolute;top:12px;left:12px;display:flex;gap:7px;flex-wrap:wrap;pointer-events:none}
.rover-3d-hud span{background:#0e2936de;color:#eaf8f7;padding:6px 9px;font-size:11px;border-radius:7px;font-weight:700}
#rover-3d-stage:fullscreen{background:#0a202c;padding:15px;overflow-y:auto}
#rover-3d-stage:fullscreen .rover-3d-canvas-wrap{height:calc(100vh - 126px)}
#rover-3d-stage:fullscreen #rover-canvas-3d{height:100%;aspect-ratio:auto}
.rover-3d-notes{font-size:11px;line-height:1.5;color:#416a73;margin:8px 0}
#rover-3d-info{font-size:11px;color:#526e77;background:#eff7f7;padding:8px 11px;border-radius:7px;margin-top:7px}
@media(max-width:700px){.rover-3d-controls{gap:6px}.rover-3d-controls select{min-width:85px}}
'''

SWITCH = '''
    <div class="rover-view-switch" role="group" aria-label="Vista del simulador">
     <button type="button" id="rover-view-2d" aria-pressed="true">Mapa 2D · Planificar</button>
     <button type="button" id="rover-view-3d" aria-pressed="false">Terreno 3D · Explorar</button>
    </div>
'''

STAGE = '''
    <div id="rover-3d-stage" hidden>
     <div class="rover-3d-controls">
      <label>Cámara<select id="rover-3d-camera"><option value="orbit">Orbital</option><option value="aerial">Aérea</option><option value="follow">Seguir rover</option></select></label>
      <label>Color del terreno<select id="rover-3d-layer"><option value="elevation">Elevación</option><option value="slope">Pendiente</option><option value="hazards">Zonas restringidas</option></select></label>
      <label>Detalle de malla<select id="rover-3d-quality"><option value="auto">Automático LOD</option><option value="full">Máximo</option><option value="economy">Económico</option></select></label>
      <label>Exageración vertical <strong id="rover-3d-vertical-label">2×</strong><input id="rover-3d-vertical" type="range" min="1" max="6" value="2" step="1"></label>
      <label>Velocidad<select id="rover-3d-speed"><option value="0.5">0,5×</option><option value="1" selected>1×</option><option value="2">2×</option><option value="4">4×</option></select></label>
      <button type="button" class="strong" id="rover-3d-play">▶ Reproducir</button>
      <button type="button" id="rover-3d-restart">↺ Reiniciar</button>
      <button type="button" id="rover-3d-reset">Centrar cámara</button>
      <button type="button" id="rover-3d-fullscreen">Pantalla completa</button>
     </div>
     <div class="rover-3d-canvas-wrap">
      <canvas id="rover-canvas-3d" width="920" height="620" aria-label="Vista tridimensional WebGL del terreno y rover, con escala física horizontal" tabindex="0"></canvas>
      <div class="rover-3d-hud"><span id="rover-3d-lod">LOD en espera</span><span>Avance <b id="rover-3d-progress">0%</b></span></div>
     </div>
     <p id="rover-3d-info" role="status">Preparando la visualización 3D…</p>
     <p class="rover-3d-notes"><b>Controles:</b> arrastrar = rotar · Shift + arrastrar = desplazar cámara · rueda = acercar/alejar. La malla usa elevaciones y separación de celdas originales. La exageración vertical cambia solo la vista; <b>no recalcula pendientes ni rutas</b>. El vehículo se dibuja ampliado para que pueda verse. Los huecos del DEM no se convierten en terreno inventado.</p>
    </div>
'''


def upgrade_rover_3d(page: str) -> str:
    if page.count('<div class="rover-map-wrap"><canvas id="rover-canvas"') != 1:
        raise ValueError('No se encontró el único mapa 2D del rover V2.1')
    if page.count('<p class="small" id="rover-hover">') != 1:
        raise ValueError('No se encontró la posición del visor 3D')
    if page.count('</style>') != 1 or page.count('</body>') != 1:
        raise ValueError('HTML no admite la integración 3D')
    page = page.replace('</style>', CSS + '</style>', 1)
    page = page.replace('<div class="rover-map-wrap"><canvas id="rover-canvas"',
                        SWITCH + '<div id="rover-map-two-d" class="rover-map-wrap"><canvas id="rover-canvas"', 1)
    page = page.replace('<p class="small" id="rover-hover">', STAGE + '<p class="small" id="rover-hover">', 1)
    js = Path(__file__).with_name('rover_view_v22.js').read_text(encoding='utf-8')
    if '</script' in js.lower():
        raise ValueError('Script 3D contiene una etiqueta de cierre no permitida')
    page = page.replace('</body>', '<script>' + js + '</script></body>', 1)
    return page.replace('V2.1 ·', 'V2.2 ·').replace('V2.1 /', 'V2.2 /')
