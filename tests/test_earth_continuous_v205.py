"""Synthetic data contracts for the v2.0.5 continuous offline world explorer."""
from __future__ import annotations

import base64
import struct
import zlib
from pathlib import Path

import numpy as np
import pytest
import xarray as xr

from mars_analog.data.earth_continuous_v205 import (
    build_continuous_earth, _png_rgb, _height_image, _uniform_global,
)
from mars_analog.data.mars_v2 import build_v2
from test_mars_v2 import fixture


def _source(root: Path, invalid=False) -> Path:
    lat = np.arange(-89.5, 90, 1.0)
    lon = np.arange(-179.5, 180, 1.0)
    z = np.full((180,360), np.nan, dtype=np.float32)
    # Synthetic elevated region and ocean gap; NOT actual relief.
    z[52:54, 112:115] = [100, 1200, 3400]
    z[60:68, 160:210] = 200 + np.arange(50)[None,:]
    ds = xr.Dataset({'land_elevation_m':(('latitude','longitude'),z)},
        coords={'latitude':lat,'longitude':lon},
        attrs={'schema':'global_land_surface_v0.6','planet':'Mars' if invalid else 'Earth'})
    p=root/'processed/earth_global_land.nc';p.parent.mkdir(parents=True,exist_ok=True)
    ds.to_netcdf(p)
    return p


def _read_rgb_png(raw: bytes):
    assert raw[:8]==b'\x89PNG\r\n\x1a\n'
    cursor=8;compressed=b'';w=h=None
    while cursor < len(raw):
        n=struct.unpack('>I',raw[cursor:cursor+4])[0]
        tag=raw[cursor+4:cursor+8]
        value=raw[cursor+8:cursor+8+n]
        if tag==b'IHDR':
            w,h,depth,mode,_,_,_=struct.unpack('>IIBBBBB',value)
            assert depth==8 and mode==2
        if tag==b'IDAT':compressed+=value
        cursor+=n+12
    assert w and h
    rows=zlib.decompress(compressed);pitch=w*3+1
    assert len(rows)==h*pitch
    assert all(rows[y*pitch]==0 for y in range(h))
    return np.frombuffer(b''.join(rows[y*pitch+1:(y+1)*pitch] for y in range(h)),dtype='uint8').reshape(h,w,3)


def _rgb_from_data_uri(s):
    assert s.startswith('data:image/png;base64,')
    return _read_rgb_png(base64.b64decode(s.split(',',1)[1]))


def test_missing_global_reports_unavailable_no_guessed_pixels(tmp_path):
    v=build_continuous_earth(tmp_path)
    assert v['status']=='unavailable' and v['texture_data_uri'] is None


def test_png_roundtrip_signed_elevation_and_null_ocean():
    z=np.array([[np.nan,-250,0],[123,3500,8450]],dtype=float)
    png=_png_rgb(_height_image(z))
    rgba=_read_rgb_png(png)
    vals=(rgba[:,:,0].astype('uint16')<<8)+rgba[:,:,1].astype('uint16')
    assert vals[0,0]==65535
    assert [int(x)-32768 for x in vals.ravel()[1:]] == [-250,0,123,3500,8450]


def test_rejects_malformed_coordinate_grids_and_planet(tmp_path):
    p=_source(tmp_path,invalid=True)
    with pytest.raises(ValueError, match='no verificado'):build_continuous_earth(tmp_path)
    with xr.open_dataset(p) as ds:correct=ds.load()
    correct.attrs['planet']='Earth'
    correct=correct.assign_coords(longitude=correct.longitude.values+10)
    correct.to_netcdf(p)
    with pytest.raises(ValueError,match='retícula'):build_continuous_earth(tmp_path)


def test_earth_relief_texture_has_correct_samples_and_original_sha(tmp_path):
    p=_source(tmp_path)
    result=build_continuous_earth(tmp_path)
    assert result['status']=='available'
    assert result['nominal_resolution_arcmin']==60
    assert result['grid_shape']==[180,360]
    assert result['land_elevation_cells']==406
    color=_rgb_from_data_uri(result['texture_data_uri'])
    encoded=_rgb_from_data_uri(result['height_data_uri'])
    assert color.shape==(180,360,3) and encoded.shape==(180,360,3)
    assert int(encoded[180-1-52,112,0])*256+int(encoded[180-1-52,112,1]) != 65535
    assert int(encoded[0,0,0])*256+int(encoded[0,0,1])==65535
    assert result['source_sha256'] and result['texture_png_bytes']<200_000


def test_global_narrow_window_does_not_substitute_fake_land(tmp_path):
    _source(tmp_path)
    v=build_continuous_earth(tmp_path)
    encoded=_rgb_from_data_uri(v['height_data_uri'])
    # Ocean never gets synthetic elevation (code 65535).
    assert encoded[0,0,0]==255 and encoded[0,0,1]==255


def test_full_integration_embeds_true_world_and_preserves_science(tmp_path):
    data,_=fixture(tmp_path)
    _source(data)
    out=tmp_path/'out'
    d=build_v2(data,out)
    assert d['world_continuous_topography']=='available'
    assert d['world_topography_arcmin']==60.0
    page=(out/'mars_analog_dashboard_v2.html').read_text(encoding='utf-8')
    assert 'id="world-canvas"' in page
    assert 'id="world-select"' in page
    assert 'id="world-local-check"' in page
    assert 'id="explore-global-candidate"' in page
    assert 'data:image/png;base64,' in page
    assert '<script src=' not in page
    import json
    report=json.loads((out/'mars_analog_report_v2.json').read_text(encoding='utf-8'))
    assert report['continuous_terrain_v205']['status']=='available'
    assert 'texture_data_uri' not in report['continuous_terrain_v205']
    assert report['analog_accuracy'] is None


def test_historic_etopo_grid_centers_not_falsely_recentered(tmp_path):
    # V0.6 mosaics sampled every 10 arcminutes retain the original +0.5' origin.
    d=10/60
    lat=-90+1/120+np.arange(1080)*d
    lon=-180+1/120+np.arange(2160)*d
    assert _uniform_global(lat,lon)==pytest.approx(d)
    z=np.full((1080,2160),np.nan,dtype=np.float32)
    z[100,120]=520.0
    p=tmp_path/'processed/earth_global_land.nc';p.parent.mkdir(parents=True)
    xr.Dataset({'land_elevation_m':(('latitude','longitude'),z)},
        coords={'latitude':lat,'longitude':lon},
        attrs={'schema':'global_land_surface_v0.6','planet':'Earth'}).to_netcdf(p)
    output=build_continuous_earth(tmp_path)
    assert output['status']=='available'
    assert output['nominal_resolution_arcmin']==pytest.approx(10)
    assert output['raster_lon_west_edge_deg']==pytest.approx(-180-0.075)
    assert output['raster_lat_north_edge_deg']==pytest.approx(90-0.075)
    image=_rgb_from_data_uri(output['height_data_uri'])
    y=1080-1-100
    value=int(image[y,120,0])*256+int(image[y,120,1])-32768
    assert value==520
