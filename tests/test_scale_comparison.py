import numpy as np
import pytest
import xarray as xr

from mars_analog.data.mola_georeference import georeference_meg004
from mars_analog.data.terrain_features import terrain_features
from mars_analog.data.scale_comparison import (
    coarsen_earth_to_km, compare_nominal_scale, grid_step_km,
    process_nominal_scale,
)


def regional_earth(z=None):
    lat = np.linspace(-23.9916666667, -22.9916666667, 31)
    lon = np.linspace(-68.9916666667, -67.9916666667, 31)
    if z is None:
        z = 2500 + 90 * np.sin(np.linspace(0, 3*np.pi,31))[:,None] + 60 * np.cos(np.linspace(0, 2*np.pi,31))[None,:]
    ds = xr.Dataset({'elevation_m': (('latitude','longitude'), np.asarray(z,float))},
                    coords={'latitude':lat, 'longitude':lon},
                    attrs={'dataset':'ETOPO_2022_ice_surface','land_mask_applied':'false'})
    ds.elevation_m.attrs['units'] = 'm'
    return ds


@pytest.fixture(scope='module')
def mars_terrain():
    decoded = xr.Dataset({'elevation_m':(('line','sample'),np.zeros((720,1440),dtype=np.float32))})
    decoded.elevation_m.attrs['units'] = 'm'
    decoded.attrs = {'dataset':'NASA_PDS4_MOLA_MEGDR','source_file':'megt90n000cb.img',
        'source_label':'megt90n000cb.xml', 'source_sha256':'placeholder', 'label_sha256':'placeholder'}
    geo,_ = georeference_meg004(decoded)
    arr = geo.elevation_m.values
    latr = np.deg2rad(geo.latitude.values)
    lonr = np.deg2rad(geo.longitude.values)
    arr[:] = 500*np.sin(3*latr[:,None]) + 200*np.cos(5*lonr[None,:])
    features,_ = terrain_features(geo,'mars')
    return features


def test_coarsen_blocks_4x4_at_chile_latitudes():
    out,meta = coarsen_earth_to_km(regional_earth())
    assert out.elevation_m.shape == (7,7)
    assert meta['block_shape'] == [4,4]
    assert 13 < meta['coarse_cell_km']['north'] < 16
    assert 12 < meta['coarse_cell_km']['east'] < 16
    assert np.isfinite(out.elevation_m.values).all()


def test_coarsen_missing_values_propagated():
    z=np.ones((31,31))*2450
    z[0:20,0:20]=np.nan
    out,_=coarsen_earth_to_km(regional_earth(z))
    assert np.isnan(out.elevation_m.values).any()


def test_coarsen_rejects_invalid_units():
    ds=regional_earth()
    ds.elevation_m.attrs['units']='km'
    with pytest.raises(ValueError,match='metros'):
        coarsen_earth_to_km(ds)


def test_pilot_nominal_scale_produces_no_ranking(mars_terrain):
    coarse,report=compare_nominal_scale(regional_earth(),mars_terrain)
    assert report['status']=='descriptive_only_no_analog_ranking'
    assert coarse.elevation_m.shape == (7,7)
    assert report['earth']['features']['cell_count']==25
    assert report['mars']['features']['cell_count']==25
    assert max(report['scale_relative_error'].values()) < .15
    assert 'slope_median_deg' in report['earth_minus_mars']
    assert 'score' not in report


def test_mars_wrong_schema_rejected():
    wrong=xr.Dataset({'elevation_m': (('latitude','longitude'),[[2.]])},
                     coords={'latitude':[0.],'longitude':[0.]})
    with pytest.raises(ValueError):
        compare_nominal_scale(regional_earth(),wrong)


def test_mars_latitude_restriction(mars_terrain):
    with pytest.raises(ValueError,match='<=55'):
        compare_nominal_scale(regional_earth(),mars_terrain,mars_lat=60)


def test_earth_area_too_small():
    ds=regional_earth().isel(latitude=slice(0,12),longitude=slice(0,12))
    with pytest.raises(ValueError,match='demasiado pequeño'):
        coarsen_earth_to_km(ds)


def test_process_writes_report(tmp_path,mars_terrain):
    e=tmp_path/'eto.nc';m=tmp_path/'mar.nc'
    regional_earth().to_netcdf(e,engine='scipy')
    mars_terrain.to_netcdf(m,engine='scipy')
    out=tmp_path/'c.nc';report=tmp_path/'r.json'
    result=process_nominal_scale(e,m,out,report)
    assert out.exists() and report.exists()
    assert len(result['outputs']['earth_coarse_sha256']) == 64


def test_mars_roi_wraps_zero_meridian(mars_terrain):
    _,report=compare_nominal_scale(regional_earth(),mars_terrain,mars_lon=0.0)
    assert report['mars']['center_lon'] == pytest.approx(0.125,abs=0.15)
    assert report['scale_relative_error']['east'] < .15
