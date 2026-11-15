"""Presentation atlas: real NetCDF sampling, honest missing-data fallback, and JS injection isolation."""
from __future__ import annotations

import json
import math
from pathlib import Path

import numpy as np
import pytest
import xarray as xr

from mars_analog.data.mars_v2_atlas import build_topographic_atlas, _serialize_grid
from mars_analog.data.mars_v2_presentation import render_dashboard


def _summary():
    anchors = [dict(mars_profile='elysium_planitia',earth_region_id=rid,topographic_rank=rank,
                    earth_glim_lithology_counts={'Basic volcanic rocks': 2,
                                                  'Unconsolidated sediments':7},
                    broad_process_relation='broad_volcanic_cartography_and_lithology_signal')
               for rid,rank in [('r026_c146',6),('r069_c067',8),('r067_c038',19)]]
    return {'elysium_anchors':anchors, 'candidates':[
        dict(id=rid,rank=rank,scale_ranks={'15km_17x17':2,'30km_9x9':rank,'40km_7x7':16},
             method_ranks={'original':rank}, weight_summary={'median':rank})
        for rid,rank in [('r026_c146',6),('r069_c067',8),('r067_c038',19)]]}


def _earth_file(root:Path):
    lat=np.arange(-45,56,.25)
    lon=np.arange(-180,180,.25)
    a,b=np.meshgrid(lat,lon,indexing='ij')
    zz=(320+900*np.exp(-((a+37)**2+(b+67)**2)/15)+90*np.sin(a*.23)*np.cos(b*.18)).astype('float32')
    ds=xr.Dataset({'land_elevation_m':(('latitude','longitude'),zz)},
                  coords={'latitude':lat,'longitude':lon},
                  attrs={'schema':'global_land_surface_v0.6','planet':'Earth'})
    p=root/'processed/earth_global_land.nc';p.parent.mkdir(parents=True,exist_ok=True)
    ds.to_netcdf(p)
    return p


def _nasadem_file(root:Path,site_id:str,lat0:float):
    lat=np.linspace(lat0-.15,lat0+.15,80)
    lon=np.linspace(-67.9,-67.4,90)
    a,b=np.meshgrid(lat,lon,indexing='ij')
    zz=(350+75*np.sin(14*b)+45*np.cos(15*a)).astype('float32')
    mask=((a<lat0+.04)&(b>-67.8)).astype('uint8')
    ds=xr.Dataset({'elevation_m':(('latitude','longitude'),zz),
                   'glim_basic_volcanic_mask':(('latitude','longitude'),mask)},
                  coords={'latitude':lat,'longitude':lon},
                  attrs={'dataset':'NASADEM_HGT.001','point_id':site_id})
    p=root/('processed/nasadem_argentina_'+site_id[-3:]+'.nc');p.parent.mkdir(parents=True,exist_ok=True)
    ds.to_netcdf(p)
    return p


def test_atlas_maps_use_measured_elevations_and_actual_cell_centers(tmp_path):
    _earth_file(tmp_path)
    _nasadem_file(tmp_path,'r026_c146_p04',-37.0)
    _nasadem_file(tmp_path,'r026_c146_p08',-37.54)
    atlas=build_topographic_atlas(tmp_path,_summary())
    assert len(atlas['entries'])==3
    assert atlas['map_source_status']=='global_etopo_available'
    assert len(atlas['sources'])==3
    arg=next(x for x in atlas['entries'] if x['id']=='r026_c146')
    assert arg['center_lat']==-37 and arg['center_lon']==-67
    assert arg['cell_bounds']==[-68,-38,-66,-36]
    assert arg['volcanic_points']==2
    for site in ('r026_c146','r069_c067','r067_c038','r026_c146_p04','r026_c146_p08'):
        m=atlas['maps'][site]
        assert m['status']=='available' and m['valid_samples']>=9
        assert m['elevation_min_m']<=m['elevation_max_m']
        assert m['shape'][0]==len(m['elevation'])
    assert atlas['maps']['r026_c146_p04']['source']=='NASADEM_HGT.001'
    assert atlas['maps']['r026_c146_p04']['native_resolution_arcsec']==1.
    assert 'volcanic_mask' in atlas['maps']['r026_c146_p08']
    assert all(isinstance(v,(int,type(None))) for row in atlas['maps']['r026_c146']['elevation'] for v in row)


def test_missing_maps_reported_without_substitution(tmp_path):
    atlas=build_topographic_atlas(tmp_path,_summary())
    assert atlas['map_source_status']=='etopo_not_found'
    assert all(v['status']=='unavailable' for v in atlas['maps'].values())
    assert atlas['entries'][0]['center_lon']==-67


def test_wrong_global_planet_rejected(tmp_path):
    p=_earth_file(tmp_path)
    with xr.open_dataset(p) as ds:
        bad=ds.load()
    bad.attrs['planet']='Mars'
    bad.to_netcdf(p)
    with pytest.raises(ValueError,match='ETOPO terrestre'):
        build_topographic_atlas(tmp_path,_summary())


def test_wrong_local_site_rejected(tmp_path):
    _nasadem_file(tmp_path,'r026_c146_p04',-37)
    p=tmp_path/'processed/nasadem_argentina_p04.nc'
    with xr.open_dataset(p) as ds:
        bad=ds.load()
    bad.attrs['point_id']='r026_c146_p08'
    bad.to_netcdf(p)
    with pytest.raises(ValueError,match='no corresponde'):
        build_topographic_atlas(tmp_path,_summary())


def test_presentation_escapes_script_strings():
    doc=_summary();doc['topographic_atlas']=build_topographic_atlas(Path('/nonexistent'),doc)
    doc['profiles']=[];doc['benchmark_cases']=[]
    doc['benchmark_summary']={'direct_sites_missing_from_ranked_population':3,'direct_target_process_analogues':4}
    doc['input_hashes']={'x':'f'*64};doc['limitations']=['validación externa pendiente']
    doc['candidates']=[{'id':'r026_c146','rank':6,'volcanic_samples':2,'glim_samples':9,'scale_ranks':{'15km_17x17':2,'30km_9x9':6,'40km_7x7':16}}]
    doc['topographic_atlas']['entries'][0]['label']='</script><script>alert(1)</script>'
    page=render_dashboard(doc)
    assert '<script>alert(1)</script>' not in page
    assert '\\u003c/script\\u003e' in page
    assert 'topo-canvas' in page and 'map-tabs' in page
    assert 'data-view="reference"' in page


def test_invalid_grid_does_not_invent_terrain():
    grid=_serialize_grid(np.arange(4),np.arange(4),np.full((4,4),np.nan))
    assert grid['status']=='insufficient_valid_elevations'


def test_global_map_crossing_antimeridian_is_contiguous(tmp_path):
    lat=np.arange(-5,6,.25);lon=np.arange(-180,180,.25)
    z=np.ones((len(lat),len(lon)),dtype='float32')*500
    ds=xr.Dataset({'land_elevation_m':(('latitude','longitude'),z)},
                  coords={'latitude':lat,'longitude':lon},
                  attrs={'schema':'global_land_surface_v0.6','planet':'Earth'})
    p=tmp_path/'processed/earth_global_land.nc';p.parent.mkdir(parents=True,exist_ok=True);ds.to_netcdf(p)
    from mars_analog.data.mars_v2_atlas import _read_global_map
    with xr.open_dataset(p) as opened:
        for center in (-179,179):
            mapinfo=_read_global_map(opened,0.,center)
            assert mapinfo['status']=='available'
            assert 8<mapinfo['bounds'][2]-mapinfo['bounds'][0]<10
            assert mapinfo['bounds'][0]<center<mapinfo['bounds'][2]
