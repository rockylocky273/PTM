import io
import json
from pathlib import Path
import zipfile

import numpy as np
import pytest
import shapefile
import xarray as xr

from mars_analog.data.global_tiles import create_plan, build_global_tile_url
from mars_analog.data.download import atomic_json, sha256_file
from mars_analog.data.global_surface import (assemble_global,build_land_regions,
                                             _masked_topography, _regions)
from mars_analog.data.landmask import land_centers_mask, _read_shapes


def make_land_zip(path):
    # Región terrestre ficticia: -20..20 longitud, -10..10 latitud.
    with shapefile.Writer(str(path.parent/'ne_50m_land'),shapeType=shapefile.POLYGON) as w:
        w.field('name','C')
        w.poly([[[-20,-10],[20,-10],[20,10],[-20,10],[-20,-10]]])
        w.record('land')
    with zipfile.ZipFile(path,'w') as z:
        for ext in ('shp','shx','dbf'):
            p=path.parent/f'ne_50m_land.{ext}'
            z.write(p,p.name)
    return path


def test_mask_correctly_distinguishes_negative_land_from_ocean(tmp_path):
    p=make_land_zip(tmp_path/'ne_50m_land.zip')
    mask=land_centers_mask(np.array([-15,0,15]),np.array([0,10,180,350]),p)
    assert mask.shape == (3,4)
    assert mask[1].tolist()==[True,True,False,True]
    assert not mask[0].any() and not mask[2].any()


def test_mask_rejects_missing_zip_content(tmp_path):
    path=tmp_path/'ne_50m_land.zip'
    with zipfile.ZipFile(path,'w') as f: f.writestr('random.txt','bad')
    with pytest.raises(ValueError): _read_shapes(path)


def test_mask_rejects_nonmonotonic_lon(tmp_path):
    p=make_land_zip(tmp_path/'ne_50m_land.zip')
    with pytest.raises(ValueError):
        land_centers_mask(np.array([-1,1]),np.array([350,0]),p)


def test_slope_ignores_ocean_interface_and_wraps_longitude():
    lat=np.array([-2,-1,0,1,2],dtype=float)
    lon=np.arange(0,360,60,dtype=float)
    z=np.zeros((5,6),dtype=float)
    z[:,2:]=10000.0 # cambio abrupto en el litoral
    land=np.zeros_like(z,dtype=bool)
    land[:,0:2]=True
    slope,rough,interior=_masked_topography(z,lat,lon,land)
    assert not np.isfinite(slope).any() # ancho terrestre solo 2 celdas
    assert not interior.any()


def test_region_stats_handles_negative_land_and_equator():
    lat=-2+1/120+np.arange(4)*1
    lon=1/120+np.arange(4)*1
    elev=-50*np.ones((4,4),dtype=float)
    land=np.ones((4,4),dtype=bool)
    slope=np.zeros_like(elev)
    rough=np.zeros_like(elev)
    rows=_regions(lat,lon,elev,land,slope,rough,region_deg=2,minimum_land_fraction=0.8)
    assert len(rows)==4
    assert all(r['status']=='land_candidate_unranked' for r in rows)
    assert all(r['land_elev_median_m']==-50 for r in rows)


def test_assemble_requires_full_inventory(tmp_path):
    p=tmp_path/'plan.json'
    atomic_json(p,create_plan(30,60))
    with pytest.raises(ValueError,match='incompleto'):
        assemble_global(p,tmp_path/'missing',tmp_path/'out.nc')


def test_full_synthetic_global_assemble_and_mask(tmp_path,monkeypatch):
    # 72 archivos muy pequeños (stride 60), todos con SHA y metadata idénticos
    # en estructura a la adquisición real. Prueba la unión entre teselas.
    monkeypatch.chdir(tmp_path)
    plan=create_plan(30,60)
    path=Path('data/catalog/global_etopo_plan.json')
    atomic_json(path,plan)
    raw=Path('data/raw/global_etopo')
    raw.mkdir(parents=True)
    for t in plan['tiles']:
        lat=t['south']+1/120+np.arange(30)
        lon=t['west_0_360']+1/120+np.arange(30)
        val=np.full((30,30), -100.0 + 0.01*t['south'],dtype=np.float32)
        ds=xr.Dataset({'z':(('latitude','longitude'),val,{'units':'meters'})},
                      coords={'latitude':lat,'longitude':lon})
        target=raw/f'etopo_{t["id"]}_stride60.nc'
        ds.to_netcdf(target,engine='scipy')
        atomic_json(Path(str(target)+'.metadata.json'),{
            'url':build_global_tile_url(t,60),'sha256':sha256_file(target)})
    summary=assemble_global(path,raw,Path('data/processed/mosaic.nc'))
    assert summary['shape']==[180,360]
    assert summary['filled_grid_cells']==64800
    with xr.open_dataset('data/processed/mosaic.nc') as ds:
        assert ds.latitude.values[0]<-89.9
        assert ds.longitude.values[-1]>359
    # La comparación con un polígono sintético se hace aparte para aislar redes.


def test_regional_catalog_file_roundtrip(tmp_path):
    lat=-90+1/120+np.arange(180)
    lon=1/120+np.arange(360)
    z=np.full((180,360),-25.0,dtype=np.float32) # puede haber tierra por debajo de cero
    ds=xr.Dataset({'elevation_m':(('latitude','longitude'),z)},
                  coords={'latitude':lat,'longitude':lon},
                  attrs={'mosaic_schema':'mars_analog_global_mosaic_v0.6'})
    path=tmp_path/'mosaic.nc';ds.to_netcdf(path,engine='scipy')
    ne=make_land_zip(tmp_path/'ne_50m_land.zip')
    out=build_land_regions(path,ne,tmp_path/'land.nc',tmp_path/'region.csv',
                           tmp_path/'report.json',region_deg=2,min_land_fraction=0.8)
    assert out['region_count']==16200
    assert out['land_centers']>0
    assert out['category_counts']['land_candidate_unranked']>0
    assert out['analogs_ranked'] is False
    with xr.open_dataset(tmp_path/'land.nc') as ds:
        assert ds.longitude.values[0]<-179
        assert 'land_mask' in ds
        assert float(ds.land_elevation_m.max())==-25.0
        assert int(ds.land_mask.sum())==out['land_centers']
