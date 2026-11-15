import math
import csv
import json
from pathlib import Path
import numpy as np
import pytest
import xarray as xr

from mars_analog.data.analog_screen import (
    GlobalSampler,patch_features,distance_metrics,diverse_top,
    create_mars_profile,screen_earth)


def test_constant_offset_does_not_change_topographic_metrics():
    p=(np.arange(81).reshape(9,9)**2).astype(float)
    a=patch_features(p,30)
    b=patch_features(p+24000,30)
    assert a is not None
    for key in ('slope_median_deg','slope_p90_deg','roughness_std3_median_m',
                'roughness_std3_p90_m','relief_p90_p10_m'):
        assert a[key]==pytest.approx(b[key],rel=1e-8,abs=1e-8)


def test_no_mixing_seafloor_and_land_in_interpolation():
    lat=np.arange(-2,3,1.,dtype=float)
    lon=np.arange(0,360,1.,dtype=float)
    z=np.full((len(lat),len(lon)),100.0)
    z[:,0]=-2000
    mask=np.ones_like(z,dtype=np.int8)
    mask[:,0]=0
    ds=xr.Dataset({'elevation_m':(('latitude','longitude'),z,{'units':'m'}),
                   'land_mask':(('latitude','longitude'),mask)},
                   coords={'latitude':lat,'longitude':lon},
                   attrs={'schema':'global_land_surface_v0.6'})
    s=GlobalSampler(ds,'Earth')
    p=s.sample(0,0,30,9)
    assert np.isnan(p).any()
    assert np.nanmin(p)==pytest.approx(100.0)
    q=s.sample(0,10,30,9)
    assert np.all(np.isfinite(q))
    assert np.allclose(q,100.)


def test_wrap_dateline_mars():
    lat=np.arange(89.875,-90.,-0.25)
    lon=np.arange(0.125,360.,0.25)
    z=np.full((len(lat),len(lon)),777,dtype='f4')
    ds=xr.Dataset({'elevation_m':(('latitude','longitude'),z,{'units':'m'})},
                  coords={'latitude':lat,'longitude':lon},
                  attrs={'planet':'Mars','georeferenced':'true','longitude_range':'0_360'})
    s=GlobalSampler(ds,'Mars')
    p=s.sample(0,359.99,30,9)
    assert np.allclose(p,777.)


def test_gradient_and_roughness_and_validation():
    y,x=np.mgrid[-4:5,-4:5]
    p=100.*x.astype(float)
    v=patch_features(p,30)
    assert v['sample_count']==81
    assert v['slope_median_deg']==pytest.approx(math.degrees(math.atan(100/30000)),rel=1e-6)
    assert v['relief_p90_p10_m']>0
    assert v['roughness_std3_median_m']>0
    p[:2,:]=np.nan
    assert patch_features(p,30) is None


def test_distance_zero_and_order_and_geographic_diversity():
    x={'slope_median_deg':0.1,'slope_p90_deg':1.,
       'roughness_std3_median_m':50.,'roughness_std3_p90_m':100.,
       'relief_p90_p10_m':1000.}
    d=distance_metrics(x,x)
    assert d['distance_total']==pytest.approx(0.,abs=1e-12)
    y={k:10*v for k,v in x.items()}
    assert distance_metrics(y,x)['distance_total']>0
    records=[{'center_lat':0.,'center_lon_180':0.,'id':1},
             {'center_lat':0.,'center_lon_180':1.,'id':2},
             {'center_lat':0.,'center_lon_180':20.,'id':3}]
    chosen=diverse_top(records,2,250)
    assert [v['id'] for v in chosen]==[1,3]


def test_reject_inconsistent_coordinates():
    ds=xr.Dataset({'elevation_m':(('latitude','longitude'),np.zeros((5,4)),{'units':'m'}),
                   'land_mask':(('latitude','longitude'),np.ones((5,4),dtype=int))},
                  coords={'latitude':np.linspace(-2,2,5),'longitude':[0,90,180,271]},
                  attrs={'schema':'global_land_surface_v0.6'})
    with pytest.raises(ValueError,match='ejes uniformes'):
        GlobalSampler(ds,'Earth')


def test_profile_save_synthetic_mola(tmp_path):
    lat=np.arange(89.875,-90.,-.25)
    lon=np.arange(.125,360.,.25)
    lons,lats=np.meshgrid(lon,lat)
    z=(100*np.sin(np.deg2rad(lats))*np.cos(np.deg2rad(lons))).astype('f4')
    source=tmp_path/'mars.nc'
    xr.Dataset({'elevation_m':(('latitude','longitude'),z,{'units':'m'})},
               coords={'latitude':lat,'longitude':lon},
               attrs={'planet':'Mars','georeferenced':'true','longitude_range':'0_360'}).to_netcdf(source)
    obj=create_mars_profile(source,tmp_path/'profile.json','elysium_pilot',1.98,155.)
    assert obj['features']['sample_count']==81
    assert json.loads((tmp_path/'profile.json').read_text())['profile_name']=='elysium_pilot'


def test_earth_screen_end_to_end_on_synthetic_global_earth(tmp_path):
    lat=np.arange(-89.99166666666667,90,1/6)
    lon=np.arange(-179.99166666666667,180,1/6)
    assert len(lat)==1080 and len(lon)==2160
    # Elevación variable, explícitamente terrestre.
    z=np.broadcast_to((100*np.sin(np.deg2rad(lon*2)))[None,:],(len(lat),len(lon))).copy().astype('float32')
    land=np.ones_like(z,dtype='int8')
    earth=tmp_path/'earth.nc'
    xr.Dataset({'elevation_m':(('latitude','longitude'),z,{'units':'m'}),
                'land_mask':(('latitude','longitude'),land)},
               coords={'latitude':lat,'longitude':lon},
               attrs={'schema':'global_land_surface_v0.6'}).to_netcdf(earth)
    catalog=tmp_path/'regions.csv'
    with catalog.open('w',newline='') as f:
        wr=csv.DictWriter(f,fieldnames=['region_id','center_lat','center_lon_180','status','land_fraction_area_approx'])
        wr.writeheader()
        for j in range(16200):
            wr.writerow({'region_id':f'r{j:05d}','center_lat':0 if j<2 else 80,
                         'center_lon_180':j*10 if j<2 else 0,
                         'status':'land_candidate_unranked' if j<2 else 'ocean_or_not_mapped_land',
                         'land_fraction_area_approx':1})
    feats=patch_features(np.zeros((9,9)),30)
    profile=tmp_path/'profile.json'
    profile.write_text(json.dumps({'schema_version':'mars_analog_profile_v0.7',
      'status':'topographic_profile_only_not_geologically_validated',
      'planet':'Mars','profile_name':'flat_test','center_lat':0,'center_lon_east_0_360':20,
      'features':feats,'spacing_km':30,'samples_per_axis':9,
      'window_extent_center_to_center_km':240}))
    result=screen_earth(profile,earth,catalog,tmp_path/'ranking.csv',tmp_path/'report.json',top=2)
    assert result['counts']['land_candidates']==2
    assert result['counts']['ranked']==2
    assert len(result['top_diverse'])==2
    assert (tmp_path/'report.json').exists()
    assert len(list(csv.DictReader((tmp_path/'ranking.csv').open())))==2
