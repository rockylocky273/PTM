"""V2.1 rover: original DEM values and spatial scale must survive untouched."""
from pathlib import Path
import json
import re

import numpy as np
import pytest
import xarray as xr

from mars_analog.data.rover_v21 import build_rover_terrain,_sample_site,SCHEMA
from mars_analog.data.rover_ui_v21 import add_rover_dashboard
from mars_analog.data.download import sha256_file
from test_mars_v2 import fixture
from mars_analog.data.mars_v2 import build_v2


def make_dem(root,site,lat0=-37.0,bad=False):
    ny,nx=190,215
    lat=lat0 + (np.arange(ny)-ny//2)/3600
    lon=-67.6756431 + (np.arange(nx)-nx//2)/3600
    yy,xx=np.meshgrid(np.arange(ny),np.arange(nx),indexing='ij')
    z=(1200+7*np.sin(xx/13)+9*np.cos(yy/17)).astype('float32')
    z[0,:]=np.nan
    ds=xr.Dataset({'elevation_m':(('latitude','longitude'),z),
                   'glim_basic_volcanic_mask':(('latitude','longitude'),np.ones_like(z,dtype='uint8'))},
                  coords={'latitude':lat,'longitude':lon},
        attrs={'dataset':'NASADEM_HGT.001','point_id':('invalid' if bad else site)})
    p=root/'processed'/('nasadem_argentina_'+site[-3:]+'.nc');p.parent.mkdir(parents=True,exist_ok=True)
    ds.to_netcdf(p)
    return p,z


def test_rover_sites_keep_metres_and_resolve_correct_cell_spacing(tmp_path):
    make_dem(tmp_path,'r026_c146_p04',-37.0)
    make_dem(tmp_path,'r026_c146_p08',-37.5395926)
    out=build_rover_terrain(tmp_path)
    assert out['schema_version']==SCHEMA
    assert out['available_sites']==2
    for s in out['sites']:
        assert s['status']=='available' and s['width']==128 and s['height']==128
        assert 20 < s['cell_size_x_m'] < 30
        assert 30 < s['cell_size_y_m'] < 32
        assert s['min_elevation_m']>1100
        assert s['max_elevation_m']<1300
        assert s['elevation_m'][0][0]>1100
        assert len(s['source_sha256'])==64
        assert s['simulation_level']=='regional_reconnaissance_only'


def test_missing_dem_explicit_no_fabricated_mars(tmp_path):
    result=build_rover_terrain(tmp_path)
    assert result['available_sites']==0
    assert all(s['status']=='missing_dem' and 'elevation_m' not in s for s in result['sites'])
    assert 'MOLA' in result['mars_warning']


def test_bad_provenance_fails(tmp_path):
    p,_=make_dem(tmp_path,'r026_c146_p04',bad=True)
    with pytest.raises(ValueError,match='no coincide'):
        build_rover_terrain(tmp_path)


def test_rover_joins_dashboard_and_exports_manifest(tmp_path):
    data,paths=fixture(tmp_path)
    make_dem(data,'r026_c146_p04',-37)
    make_dem(data,'r026_c146_p08',-37.5395926)
    out=data/'reports/mars_v2_0'
    result=build_v2(data,out)
    assert result['rover_real_dem_sites']==2
    html=(out/'mars_analog_dashboard_v2.html').read_text(encoding='utf-8')
    assert 'data-view="rover"' in html and 'view-rover' in html
    assert 'Simulación rover' in html
    assert 'mars_analog_rover_terrain_v2.1' in html
    assert 'source_sha256' in html and 'cell_size_x_m' in html
    manifest=json.loads((out/'rover_terrain_manifest_v21.json').read_text(encoding='utf-8'))
    assert manifest['available_sites']==2
    assert not any('elevation_m' in s for s in manifest['sites'])
    assert json.loads((out/'mars_analog_report_v2.json').read_text())['rover_v21']['available_sites']==2


def test_dashboard_markup_injection_rejects_malformed():
    with pytest.raises(ValueError,match='integración'):
        add_rover_dashboard('<html><body></body></html>')


def test_old_simulation_is_preserved_and_new_engine_has_no_fake_match_score():
    root=Path(__file__).resolve().parents[1]
    assert (root/'rover_original/simulation_engine.js').is_file()
    js=(root/'src/mars_analog/data/rover_view_v21.js').read_text(encoding='utf-8')
    assert 'relative_route_cost' in js
    assert 'validated_for_real_rover:false' in js
    assert 'analogSimilarity' not in js and 'CELL_WORLD_METERS' not in js
    assert 'array' not in SCHEMA


def test_geotiff_import_projected_dem_keeps_altitude_and_true_spacing(tmp_path):
    rasterio=pytest.importorskip('rasterio')
    from rasterio.transform import from_origin
    from mars_analog.data.rover_geotiff_v21 import import_rover_geotiff
    src=tmp_path/'detailed_dem.tif';out=tmp_path/'rover.json'
    vals=np.arange(80*90,dtype='float32').reshape(80,90)*.001+3011.0
    with rasterio.open(src,'w',driver='GTiff',width=90,height=80,count=1,
                       dtype='float32',crs='EPSG:32619',transform=from_origin(450000,6500000,3.0,3.0)) as ds:
        ds.write(vals,1)
    result=import_rover_geotiff(src,out,size=64)
    doc=json.loads(out.read_text())
    assert result['status']=='dem_imported_without_resampling'
    assert result['cell_size_m']==[3.,3.]
    assert doc['elevation_m'][0][0]>3011
    assert doc['max_elevation_m']>doc['min_elevation_m']
    assert doc['rover_safety_certified'] is False


def test_geotiff_missing_units_rejected(tmp_path):
    rasterio=pytest.importorskip('rasterio')
    from rasterio.transform import from_origin
    from mars_analog.data.rover_geotiff_v21 import import_rover_geotiff
    p=tmp_path/'unknown.tif'
    with rasterio.open(p,'w',driver='GTiff',width=40,height=40,count=1,dtype='float32',
                       transform=from_origin(0,100,1,1)) as ds:
        ds.write(np.full((40,40),15,dtype='float32'),1)
    with pytest.raises(ValueError,match='unidades conocidas'):
        import_rover_geotiff(p,tmp_path/'not_valid.json')
