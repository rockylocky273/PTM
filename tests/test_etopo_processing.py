import numpy as np
import pytest
import xarray as xr
from mars_analog.data.etopo_processing import normalize_etopo,process_etopo


def make_etopo(path):
    ds=xr.Dataset(
        data_vars={'z':(('latitude','longitude'),np.array([[2206,3000],[3941,np.nan]],dtype=np.float32),{'units':'m'})},
        coords={'latitude':[-23.99,-23.95],'longitude':[291.0,291.05]},
    )
    ds.to_netcdf(path,engine='scipy')


def test_etopo_longitude_nodata_and_export(tmp_path):
    source=tmp_path/'etopo.nc'
    make_etopo(source)
    norm,summary=normalize_etopo(source)
    assert list(norm.longitude.values)==pytest.approx([-69.,-68.95])
    assert summary['valid_samples']==3
    assert summary['missing_samples']==1
    assert summary['elevation_min_m']==2206
    assert summary['elevation_max_m']==3941
    assert norm.elevation_m.attrs['units']=='m'
    dest=tmp_path/'normalized.nc'
    processed=process_etopo(source,dest)
    assert dest.is_file() and len(processed['output_sha256'])==64
    with xr.open_dataset(dest) as check:
        assert 'elevation_m' in check and check.longitude.min() < 0


def test_etopo_reject_unit_unknown(tmp_path):
    source=tmp_path/'bad.nc'
    xr.Dataset({'z':(('latitude','longitude'),[[1.]])},coords={'latitude':[0.],'longitude':[0.]}).to_netcdf(source,engine='scipy')
    with pytest.raises(ValueError,match='Unidad'):
        normalize_etopo(source)


def test_etopo_renormalization_does_not_duplicate(tmp_path):
    source=tmp_path/'wrap.nc'
    xr.Dataset({'z':(('latitude','longitude'),[[1.,2.]],{'units':'m'})}, coords={'latitude':[0.],'longitude':[0.,360.]})        .to_netcdf(source,engine='scipy')
    with pytest.raises(ValueError,match='duplicadas'):
        normalize_etopo(source)
