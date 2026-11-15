"""Presentation V2.0.2 regression: real MOLA grids, named 25 earth cell centers."""
import json
from pathlib import Path

import numpy as np
import pytest
import xarray as xr

from mars_analog.data.mars_v2_atlas import (
    _COUNTRY_INDEX, _region_label, _read_mars_map,
    build_mars_topographic_atlas, build_topographic_atlas,
)
from mars_analog.data.mars_profiles_v12 import TARGETS
from mars_analog.data.download import sha256_file


def _sample_mola(data_root, *, planet='Mars', elev=500):
    lat=90-(np.arange(720)+0.5)*0.25
    lon=(np.arange(1440)+0.5)*0.25
    # Test-only synthetic DEM, not shipped in the software's deliverable data.
    xx=np.sin(lon[None,:]*np.pi/40)
    yy=np.cos(lat[:,None]*np.pi/30)
    z=(elev + 125*yy + 280*xx).astype('float32')
    ds=xr.Dataset({'elevation_m':(('latitude','longitude'),z)},
                  coords={'latitude':lat,'longitude':lon},
                  attrs={'planet':planet,'georeferenced':'true', 'longitude_range':'0_360'})
    p=data_root/'processed/mola_georeferenced.nc'
    p.parent.mkdir(parents=True,exist_ok=True)
    ds.to_netcdf(p)
    return p


def _profiles():
    return [dict(id=t[0],name=t[1],units={'lAv':9},domain_flag='within_sampled_earth_feature_ranges')
            for t in TARGETS]


def test_all_25_known_centers_have_countries_and_expected_spelling():
    countries=_COUNTRY_INDEX['countries']
    assert len(countries)==25
    assert set(countries.values()) >= {'Argentina','Rusia','Kazajistán','China','Bolivia','Camerún','Canadá'}
    assert countries['r069_c067']=='Rusia'
    assert countries['r067_c038']=='Kazajistán'
    assert countries['r026_c146']=='Argentina'
    assert countries['r036_c148']=='Bolivia'
    assert countries['r068_c061']=='China'
    assert all(_region_label(rid,0,0).startswith(name) for rid,name in countries.items())


def test_all_six_real_mola_windows_can_be_loaded_offline(tmp_path):
    p=_sample_mola(tmp_path)
    a=build_mars_topographic_atlas(tmp_path,_profiles())
    assert len(a['maps'])==6
    assert a['sources']['mola_georeferenced']['sha256']==sha256_file(p)
    for t in TARGETS:
        m=a['maps'][t[0]]
        assert m['status']=='available'
        assert m['source']=='NASA MOLA MEGDR' and m['planet']=='Mars'
        assert m['valid_samples']>=16
        assert m['elevation_min_m']<m['elevation_max_m']
        assert m['bounds'][2]-m['bounds'][0]<14
        assert m['shape'][0]==len(m['elevation'])
    # Meridiani is at the 0-360 seam; the map stays local rather than spanning 360°.
    mer=a['maps']['meridiani_planum']
    assert mer['bounds'][0]<357.5<mer['bounds'][2]
    assert mer['bounds'][2]>360


def test_mars_mola_missing_is_explicit_not_fabricated(tmp_path):
    a=build_mars_topographic_atlas(tmp_path,_profiles())
    assert not a['sources'].get('mola_georeferenced')
    assert all(v['status']=='unavailable' for v in a['maps'].values())


def test_earth_mosaic_is_rejected_if_passed_as_mars(tmp_path):
    _sample_mola(tmp_path,planet='Earth')
    with pytest.raises(ValueError,match='no es MOLA'):
        build_mars_topographic_atlas(tmp_path,_profiles())


def test_mola_manifest_integrity_is_enforced(tmp_path):
    p=_sample_mola(tmp_path)
    from mars_analog.data.mars_profiles_v12 import build_profiles
    manifest_file=tmp_path/'catalog/mars_profiles_v1_2.json'
    output_dir=tmp_path/'profiles/v1_2'
    # Generate profile manifest with a path relative to working project root.
    # This test validates MOLA data source hash directly in a manifest stub,
    # with profiles saved under the historically expected data/ layout.
    entries=[]
    for rid,*_ in TARGETS:
        path=tmp_path/'data/profiles/v1_2'/f'{rid}.json'
        path.parent.mkdir(parents=True,exist_ok=True)
        path.write_text(json.dumps({'profile_name':rid,'planet':'Mars','features':{}}))
        entries.append({'id':rid,'profile_file':f'data/profiles/v1_2/{rid}.json','sha256':sha256_file(path)})
    import os
    # data_root is project_root/data, source must live there.
    data_root=tmp_path/'data'
    source=data_root/'processed/mola_georeferenced.nc'
    source.parent.mkdir(parents=True,exist_ok=True)
    source.write_bytes(p.read_bytes())
    manifest=data_root/'catalog/mars_profiles_v1_2.json'
    manifest.parent.mkdir(parents=True,exist_ok=True)
    manifest.write_text(json.dumps({'schema_version':'mars_analog_multi_profiles_v1.2',
                                    'source_mola_sha256':'0'*64,'profiles':entries}))
    with pytest.raises(ValueError,match='no coincide'):
        build_mars_topographic_atlas(data_root,_profiles())


def test_profile_manifest_enriches_mars_metrics_without_recalculation(tmp_path):
    data=tmp_path/'data'
    p=_sample_mola(data)
    profiles=[]
    for t in TARGETS:
        path=data/'profiles/v1_2'/f'{t[0]}.json'
        path.parent.mkdir(parents=True,exist_ok=True)
        profile={'profile_name':t[0],'planet':'Mars',
                 'features':{'slope_median_deg':0.082,
                             'slope_p90_deg':0.41,
                             'roughness_std3_median_m':37.5,
                             'roughness_std3_p90_m':154.2,
                             'relief_p90_p10_m':589.}}
        path.write_text(json.dumps(profile), encoding='utf-8')
        profiles.append({'id':t[0],'profile_file':f'data/profiles/v1_2/{t[0]}.json',
                         'sha256':sha256_file(path)})
    manifest=data/'catalog/mars_profiles_v1_2.json'
    manifest.parent.mkdir(parents=True,exist_ok=True)
    manifest.write_text(json.dumps({'schema_version':'mars_analog_multi_profiles_v1.2',
                                    'source_mola_sha256':sha256_file(p),
                                    'profiles':profiles}), encoding='utf-8')
    obj=build_mars_topographic_atlas(data,_profiles())
    assert obj['profiles']['elysium_planitia']['features']['slope_median_deg']==0.082
    assert obj['maps']['olympus_mons']['status']=='available'
    assert obj['sources']['mars_profiles_manifest']['sha256']==sha256_file(manifest)
