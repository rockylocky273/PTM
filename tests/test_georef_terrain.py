import numpy as np
import pytest
import xarray as xr

from mars_analog.data.mola_georeference import georeference_meg004
from mars_analog.data.terrain_features import terrain_features, R_MARS


def _decoded_mola():
    ds=xr.Dataset({'elevation_m':(('line','sample'),np.zeros((720,1440),dtype='float32'))})
    ds.elevation_m.attrs['units']='m'
    ds.attrs={'dataset':'NASA_PDS4_MOLA_MEGDR', 'source_file':'megt90n000cb.img',
              'source_label':'megt90n000cb.xml', 'source_sha256':'abc', 'label_sha256':'def',
              'georeferenced':'false'}
    return ds


def test_mola_grid_pixel_centers_and_extent():
    geo,summary=georeference_meg004(_decoded_mola())
    assert geo['elevation_m'].shape==(720,1440)
    assert geo.latitude.values[0]==pytest.approx(89.875)
    assert geo.latitude.values[-1]==pytest.approx(-89.875)
    assert geo.longitude.values[0]==pytest.approx(0.125)
    assert geo.longitude.values[-1]==pytest.approx(359.875)
    assert summary['georeferenced'] is True


def test_mola_georef_reject_other_product():
    ds=_decoded_mola()
    ds.attrs['source_file']='megt90n000eb.img'
    with pytest.raises(ValueError, match='producto desconocido'):
        georeference_meg004(ds)


def test_mars_require_georeferenced():
    with pytest.raises(ValueError, match='georreferenciado'):
        terrain_features(_decoded_mola(),'mars')


def test_mars_flat_slopes_zero_and_polar_mask():
    geo,_=georeference_meg004(_decoded_mola())
    out,s=terrain_features(geo,'mars')
    assert s['valid_elevation_samples']==720*1440
    assert s['slope_p90_deg']==pytest.approx(0.0)
    assert s['roughness_p90_m']==pytest.approx(0.0)
    assert np.isnan(out.slope_deg.values[0]).all()
    assert np.isfinite(out.slope_deg.values[10]).all()


def _earth(z,lat=None,lon=None):
    n,m=z.shape
    if lat is None: lat=np.linspace(-1,1,n)
    if lon is None: lon=np.linspace(-1,1,m)
    ds=xr.Dataset({'elevation_m':(('latitude','longitude'),z)}, coords={'latitude':lat,'longitude':lon},
                  attrs={'dataset':'ETOPO_2022_ice_surface','land_mask_applied':'false'})
    ds.elevation_m.attrs['units']='m'
    return ds


def test_earth_flat_zero():
    ds=_earth(np.full((5,5),137.0))
    out,s=terrain_features(ds,'earth')
    assert s['slope_median_deg']==pytest.approx(0.0)
    assert s['roughness_median_m']==pytest.approx(0.0)


def test_earth_constant_northward_grade():
    # z = distance * 0.01 at equator => slope ~ atan(0.01) (~0.573 deg)
    lat=np.array([-0.02,-0.01,0,0.01,0.02])
    meridian_per_rad=6335439.0
    h=np.deg2rad(lat)*meridian_per_rad*0.01
    z=np.repeat(h[:,None],5,axis=1)
    out,s=terrain_features(_earth(z,lat,np.arange(5)*0.01),'earth')
    assert s['slope_median_deg']==pytest.approx(np.degrees(np.arctan(0.01)),abs=0.005)


def test_nan_neighbor_not_silently_filled():
    z=np.arange(25,dtype=float).reshape(5,5)
    z[2,2]=np.nan
    out,s=terrain_features(_earth(z),'earth')
    assert np.isnan(out.slope_deg.values[2,2])
    assert np.isnan(out.roughness_std3_m.values[2,2])


def test_mars_periodic_lon_gradient_at_edges():
    geo,_=georeference_meg004(_decoded_mola())
    # Smooth periodic oscillation, gradients near first and last columns finite and close.
    lon=np.deg2rad(geo.longitude.values)
    geo['elevation_m'][:]=np.sin(lon)[None,:]*200
    out,_=terrain_features(geo,'mars')
    assert out.slope_deg.values[350,0]==pytest.approx(out.slope_deg.values[350,-1],rel=0.01)
