"""V2.0.6: candidate detail uses geographic continuous ETOPO and true local DEM."""
from __future__ import annotations

from pathlib import Path

from mars_analog.data.mars_v2 import build_v2
from mars_analog.data.mars_v2_presentation import render_dashboard
from test_mars_v2 import fixture
from test_earth_continuous_v205 import _source
from test_mars_v2_atlas import _nasadem_file


def test_candidate_map_is_geographic_without_regional_texture_edges(tmp_path):
    data, _ = fixture(tmp_path)
    _source(data)
    result = build_v2(data, tmp_path/'out')
    page = Path(result['dashboard_html']).read_text(encoding='utf8')
    assert result['world_continuous_topography'] == 'available'
    assert 'candidateDrawGlobal' in page
    assert 'candidateSelectLevel' in page
    assert 'candidatePyramid' in page
    assert 'candidateCamera.z=Math.max(1,Math.min(2400' in page
    assert 'id="footprint-toggle" aria-pressed="false"' in page
    assert 'id="topo-canvas"' in page
    assert 'data:image/png;base64,' in page
    assert '<script src=' not in page
    assert 'candidateDrawLegacy' in page  # explicit fallback when ETOPO absent
    assert 'window.devicePixelRatio' in page
    assert 'requestAnimationFrame' in page


def test_actual_nasadem_only_at_georeferenced_sites(tmp_path):
    data, _ = fixture(tmp_path)
    _source(data)
    _nasadem_file(data, 'r026_c146_p04', -37.0)
    _nasadem_file(data, 'r026_c146_p08', -37.54)
    result = build_v2(data, tmp_path/'out')
    page = Path(result['dashboard_html']).read_text(encoding='utf8')
    assert result['atlas_maps_available'] >= 2
    assert 'candidateDrawLocal' in page
    assert 'candidateLocalContours' in page
    assert 'candidateSiteRaster' in page
    assert 'candidateSiteSample' in page
    assert 'if(candidateCamera.z<85)return;' in page
    assert 'candidateSiteCache' in page
    assert 'const alpha=tFade*tFade*(3-2*tFade)' in page
    assert 'GlIM' not in page or 'GLiM' in page


def test_missing_world_is_disclosed_not_simulated(tmp_path):
    data, _ = fixture(tmp_path)
    result = build_v2(data, tmp_path/'out')
    assert result['world_continuous_topography'] == 'unavailable'
    page = Path(result['dashboard_html']).read_text(encoding='utf8')
    assert 'candidateSource.status' in page
    assert 'candidateDrawLegacy' in page
    assert 'No se pudo leer la textura ETOPO' in page
    assert 'continuo' in page
