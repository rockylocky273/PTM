import csv
import numpy as np
import pytest
from mars_analog.data.landcover_modis import (
    _extract_2deg_window,summarize_igbp_window,search_modis_landcover,
    download_modis_landcover,CLASS_NAMES)


def test_landcover_majority_class_fractions():
    a=np.full((40,40),16,dtype=np.uint8)
    a[:10]=13
    a[10:20]=12
    a[20:30]=1
    r=summarize_igbp_window(a,0)
    assert abs(r['class16_bare_sparsely_vegetated_pct']-25)<.01
    assert abs(r['urban_majority_pct']-25)<.01
    assert abs(r['cropland_majority_pct']-25)<.01
    assert abs(r['forest_majority_pct']-25)<.01
    assert r['dominant_land_igbp_class'] in (1,12,13,16)


def test_landcover_missing_zero_not_inflated():
    a=np.full((40,40),255,dtype=np.uint8)
    a[:10]=16
    a[10:20]=0
    r=summarize_igbp_window(a,0)
    assert abs(r['classification_coverage_pct']-50)<.01
    assert abs(r['mapped_land_pct_among_valid']-50)<.01
    assert r['class16_bare_sparsely_vegetated_pct']==100


def test_landcover_all_water():
    r=summarize_igbp_window(np.zeros((40,40)),30)
    assert r['mapped_land_pct_among_valid']==0
    assert r['dominant_land_igbp_class'] is None
    assert r['urban_majority_pct'] is None


def test_landcover_empty_rejected():
    with pytest.raises(ValueError):summarize_igbp_window(np.zeros((0,0)),0)


def test_window_lat_lon_position():
    arr=np.zeros((3600,7200),dtype=np.uint8)
    arr[0:40,0:40]=16
    clip=_extract_2deg_window(arr,89.,-179.)
    assert clip.shape==(40,40) and (clip==16).all()
    with pytest.raises(ValueError):_extract_2deg_window(arr,90.,-179.)


def test_class_names_reference():
    assert CLASS_NAMES[13]=='urban_built_up' and CLASS_NAMES[16]=='barren_or_sparsely_vegetated'


class Granule(dict):
    size=50
    def data_links(self,access='external'):
        return ['https://example.nasa.gov/test.hdf']
class EA:
    def __init__(self):self.login_called=False
    def search_data(self,**kw):
        assert kw['short_name']=='MCD12C1' and kw['version']=='061'
        return [Granule(meta={'concept-id':'G123'},umm={'GranuleUR':'MCD12C1.A2024001.061.XXXX.hdf'})]
    def login(self):self.login_called=True


def test_landcover_cmr_search_metadata_only():
    x=search_modis_landcover(2024,ea=EA())
    assert len(x['matches'])==1 and x['matches'][0]['size_mb']==50


def test_landcover_download_reject_budget_before_auth(tmp_path):
    e=EA()
    with pytest.raises(ValueError,match='Tamaño'):
        download_modis_landcover(2024,tmp_path,max_mb=10,ea=e)
    assert not e.login_called


def test_landcover_year_validation():
    with pytest.raises(ValueError):search_modis_landcover(1900,ea=EA())
