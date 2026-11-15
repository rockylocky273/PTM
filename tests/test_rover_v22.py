"""V2.2 offline WebGL2 UI integration and preservation of V2.1 planner."""
from pathlib import Path
import json
import pytest
from mars_analog.data.rover_ui_v22 import upgrade_rover_3d
from mars_analog.data.rover_ui_v21 import add_rover_dashboard
from mars_analog.data.mars_v2 import build_v2
from test_rover_v21 import make_dem
from test_mars_v2 import fixture

ROOT = Path(__file__).resolve().parents[1]
VIEW3D = ROOT/'src/mars_analog/data/rover_view_v22.js'
VIEW2D = ROOT/'src/mars_analog/data/rover_view_v21.js'


def test_3d_requires_rover_2d_markup():
    with pytest.raises(ValueError, match='mapa 2D'):
        upgrade_rover_3d('<html><style></style><body></body></html>')


def test_3d_js_is_offline_native_webgl_and_no_fake_terrain():
    s=VIEW3D.read_text(encoding='utf-8')
    assert "getContext('webgl2'" in s
    assert 'rover-3d-camera' in s and "mode==='follow'" in s
    assert 'mars-rover-bridge' in s and 'route.length' in s
    assert 'nativeValidRect' in s and 'currentStride' in s
    assert 'cell_size_x_m' in s and 'cell_size_y_m' in s
    assert 'elevation_m' in s
    assert 'https://' not in s and 'http://' not in s and 'THREE' not in s
    assert 'analogSimilarity' not in s and 'CELL_WORLD_METERS' not in s
    assert 'normalizeCustomGridTo60x60' not in s
    assert '</script' not in s.lower()


def test_bridged_2d_keeps_astar_in_one_engine():
    s=VIEW2D.read_text(encoding='utf-8')
    assert "window.MarsRoverBridgeV22" in s
    assert "bridgePublish('route')" in s
    assert "bridgePublish('terrain')" in s
    assert "bridgePublish('constraints')" in s
    assert 'function routePlan()' in s
    assert 'metrics={distance_m:' in s


def test_v22_dashboard_contains_view_switch_and_3d_controls(tmp_path):
    data,paths=fixture(tmp_path)
    make_dem(data,'r026_c146_p04',-37)
    make_dem(data,'r026_c146_p08',-37.5395926)
    out=tmp_path/'report'
    result=build_v2(data,out)
    assert result['rover_real_dem_sites']==2
    assert result['rover_3d']=='offline_webgl2_with_2d_fallback'
    text=(out/'mars_analog_dashboard_v2.html').read_text(encoding='utf-8')
    assert 'rover-view-2d' in text and 'rover-view-3d' in text
    assert 'rover-3d-stage' in text and 'rover-canvas-3d' in text
    assert 'LOD ×' in text and 'webgl2' in text
    assert text.index('MarsRoverBridgeV22') < text.index("getContext('webgl2'")
    assert 'rover_plan' not in text  # routePlan is the original JS function name
    meta=json.loads((out/'mars_analog_report_v2.json').read_text())
    assert meta['rover_v22']['elevation_rescaled'] is False
    assert meta['rover_v22']['physical_route_unchanged'] is True
    assert meta['rover_v22']['small_obstacles_resolved'] is False
    assert (ROOT/'rover_original/simulation_engine.js').is_file()
