"""V1.2: invariantes científicas, integridad y operación de punta a punta sintética."""
import csv
import json
import numpy as np
import pytest
import xarray as xr

from mars_analog.data.mars_profiles_v12 import (
    targets_catalog, _select, _sampling, build_profiles, _load_profiles,
    screen_profiles, compare_profiles)
from mars_analog.data.analog_screen import create_mars_profile


def create_mars(path):
    lat=np.arange(89.875,-90.,-.25)
    lon=np.arange(.125,360.,.25)
    y,x=np.meshgrid(lat,lon,indexing='ij')
    z=(1400*np.cos(np.deg2rad(x*2))*np.sin(np.deg2rad(y*3))+
       280*np.cos(np.deg2rad(x*5+y*8))).astype('float32')
    xr.Dataset({'elevation_m':(('latitude','longitude'),z,{'units':'m'})},
               coords={'latitude':lat,'longitude':lon},
               attrs={'planet':'Mars','georeferenced':'true','longitude_range':'0_360'}).to_netcdf(path)


def create_earth_and_catalog(tmp):
    lat=np.arange(-89.99166666666667,90,1/6)
    lon=np.arange(-179.99166666666667,180,1/6)
    yy,xx=np.meshgrid(lat,lon,indexing='ij')
    z=(900*np.sin(np.deg2rad(xx*3))+500*np.cos(np.deg2rad(yy*4))+
       240*np.sin(np.deg2rad(xx+yy)*6)).astype('float32')
    land=np.ones_like(z,dtype='uint8')
    dest=tmp/'earth.nc'
    xr.Dataset({'elevation_m':(('latitude','longitude'),z,{'units':'m'}),
                'land_mask':(('latitude','longitude'),land)},
               coords={'latitude':lat,'longitude':lon},
               attrs={'schema':'global_land_surface_v0.6'}).to_netcdf(dest)
    catalog=tmp/'regions.csv'
    with catalog.open('w',newline='') as f:
        w=csv.DictWriter(f,fieldnames=['region_id','center_lat','center_lon_180',
                                       'status','land_fraction_area_approx'])
        w.writeheader()
        for i in range(16200):
            w.writerow({'region_id':f'r{i:05d}',
                        'center_lat':((i%11)-5)*2 if i<18 else 84,
                        'center_lon_180':((i*17)%340)-170,
                        'status':'land_candidate_unranked' if i<18 else 'ocean_or_not_mapped_land',
                        'land_fraction_area_approx':1})
    return dest,catalog


def test_catalog_has_official_coordinates_and_legacy_center():
    d=targets_catalog()
    assert len(d['targets'])==6
    assert len({v['id'] for v in d['targets']})==6
    assert d['targets'][0]['lat']==1.98
    assert d['targets'][0]['lon_east_0_360']==155.
    assert d['targets'][1]['lon_east_0_360']==77.69
    assert all(x['gazetteer'].startswith('https://planetarynames.wr.usgs.gov/') for x in d['targets'])


@pytest.mark.parametrize('selection', ['wrong','elysium_planitia,elysium_planitia','',','])
def test_reject_invalid_target_selection(selection):
    with pytest.raises(ValueError):
        _select(selection)


def test_sampling_invariants():
    for spacing,samples in [(0,9),(30,8),(120,9),(.5,4)]:
        with pytest.raises(ValueError):
            _sampling(spacing,samples)
    _sampling(30,9)


def test_elysium_is_numerically_compatible_with_v07(tmp_path):
    source=tmp_path/'mars.nc';create_mars(source)
    manifest=tmp_path/'manifest.json'
    result=build_profiles(source,'elysium_planitia,meridiani_planum',30,9,
                          tmp_path/'profiles',manifest)
    assert result['window_km']==240
    assert len(result['profiles'])==2
    new=json.loads((tmp_path/'profiles/elysium_planitia.json').read_text())
    old=create_mars_profile(source,tmp_path/'old.json','elysium_pilot',1.98,155.,30,9)
    for key,value in old['features'].items():
        assert new['features'][key]==pytest.approx(value)
    assert new['geology_verification']=='not_performed'
    assert not new['profile_name'].startswith('elysium_pilot')
    _load_profiles(manifest)
    # Tamper detection: SHA-256 mismatches fail closed.
    with (tmp_path/'profiles/elysium_planitia.json').open('a') as f:
        f.write(' ')
    with pytest.raises(ValueError,match='SHA256'):
        _load_profiles(manifest)


def test_build_all_six_and_multi_screen_compare_end_to_end(tmp_path):
    mars=tmp_path/'mars.nc';create_mars(mars)
    manifest=tmp_path/'manifest.json'
    obj=build_profiles(mars,'all',30,9,tmp_path/'profiles',manifest)
    assert len(obj['profiles'])==6
    earth,catalog=create_earth_and_catalog(tmp_path)
    ranked=screen_profiles(manifest,earth,catalog,tmp_path/'results',
                           tmp_path/'screen.json',top=5,min_separation=0)
    assert ranked['counts']['ranked_per_profile']==18
    assert len(ranked['profiles'])==6
    assert all(len(p['top_diverse'])==5 for p in ranked['profiles'])
    assert all(p['ranked_count']==18 for p in ranked['profiles'])
    assert (tmp_path/'results/elysium_planitia_ranking.csv').exists()
    cmp=compare_profiles(tmp_path/'screen.json',tmp_path/'watch.csv',
                         tmp_path/'compare.json',watch='r00000,r00001',top_n=5)
    assert len(cmp['pairwise_top_n_overlap'])==15
    assert all(0<=x['jaccard']<=1 for x in cmp['pairwise_top_n_overlap'])
    assert len(list(csv.DictReader((tmp_path/'watch.csv').open())))==12
    # Los rankings históricos NO se generan ni sobrescriben.
    assert not (tmp_path/'results/topography_ranking.csv').exists()
    # El ranking debe permitir verificar que cada distancia sea finita.
    for item in ranked['profiles']:
        with open(item['ranking_csv']) as f:
            rows=list(csv.DictReader(f))
        assert [int(row['rank']) for row in rows]==list(range(1,19))
        ds=[float(r['distance_total']) for r in rows]
        assert np.all(np.isfinite(ds)) and ds==sorted(ds)
    # La salida no contiene un falso puntaje geológico combinado.
    assert cmp['status']=='profile_rank_comparison_no_joint_score'
    assert 'combined_analog_score' not in json.dumps(cmp)


def test_compare_rejects_altered_ranking(tmp_path):
    obj={'schema_version':'mars_analog_multi_profiles_v1.2',
         'status':'separate_topographic_rankings_not_mars_analog_confirmation',
         'profiles':[{'id':'elysium_planitia','ranking_csv':str(tmp_path/'x.csv'),
                      'ranking_sha256':'x','ranked_count':3}]}
    (tmp_path/'report.json').write_text(json.dumps(obj))
    (tmp_path/'x.csv').write_text('region_id,rank\na,1')
    with pytest.raises(ValueError,match='Ranking alterado'):
        compare_profiles(tmp_path/'report.json',tmp_path/'a.csv',tmp_path/'b.json')


def test_multi_screen_elysium_matches_legacy_ranking(tmp_path):
    from mars_analog.data.analog_screen import screen_earth
    mars=tmp_path/'mars.nc';create_mars(mars)
    earth,catalog=create_earth_and_catalog(tmp_path)
    man=tmp_path/'manifest.json'
    obj=build_profiles(mars,'elysium_planitia',30,9,tmp_path/'profiles',man)
    assert obj['sampling_footprints_geojson'].endswith('.geojson')
    fc=json.loads((tmp_path/'profiles/mars_sampling_footprints.geojson').read_text())
    assert len(fc['features'])==1
    assert len(fc['features'][0]['geometry']['coordinates'][0])==5
    legacy_profile=tmp_path/'old.json'
    create_mars_profile(mars,legacy_profile,'elysium_pilot',1.98,155.,30,9)
    screen_earth(legacy_profile,earth,catalog,tmp_path/'old_rank.csv',tmp_path/'old_report.json',top=5,min_separation_km=0)
    new=screen_profiles(man,earth,catalog,tmp_path/'new_results',tmp_path/'new_report.json',top=5,min_separation=0)
    with (tmp_path/'old_rank.csv').open(newline='') as f:
        old=list(csv.DictReader(f))
    with open(new['profiles'][0]['ranking_csv'],newline='') as f:
        fresh=list(csv.DictReader(f))
    assert [r['region_id'] for r in old]==[r['region_id'] for r in fresh]
    for a,b in zip(old,fresh):
        assert float(a['distance_total'])==pytest.approx(float(b['distance_total']))
