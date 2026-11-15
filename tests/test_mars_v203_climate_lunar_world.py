"""V2.0.3 safety, source and navigation contracts (offline synthetic inputs)."""
import csv
import json
from pathlib import Path
import numpy as np
import pytest

from mars_analog.data.mars_v203_climate import build_candidate_climate
from mars_analog.data.mars_v203_audits import build_audits
from mars_analog.data.moon_v203 import acquire_lola,build_lunar_atlas,_moon_map,REGIONS,BYTES
from mars_analog.data.mars_v2_atlas import _read_mars_map
from mars_analog.data.mars_v2 import build_v2
from test_mars_v2 import fixture


def _entries(n=3):
    return [{'id':f'r{i:03d}_c100','country':'Ejemplo','label':f'Lugar {i}',
            'center_lat':i+1.,'center_lon':-70.,'topographic_rank':i+1,
            'lithology_counts':{'Basic volcanic rocks':2,'Siliciclastic sedimentary rocks':7},
            'volcanic_points':2,'relief_context_m':150,'elevation_range_m':[500,1000],
            'scale_ranks':None,'method_ranks':None,'climate_earth_context':None} for i in range(n)]


def test_v203_reads_climate_csv_for_all_sites_and_never_extrapolates(tmp_path):
    entries=_entries(3);path=tmp_path/'results/environment_sample.csv';path.parent.mkdir(parents=True)
    fields=['region_id','center_lat','center_lon_180','status','air_temp_mean_c','precip_annual_mean_mm','relative_humidity_mean_pct','seasonal_air_temp_range_c']
    with path.open('w',newline='') as f:
        w=csv.DictWriter(f,fieldnames=fields);w.writeheader()
        for e in entries:
            w.writerow(dict(region_id=e['id'],center_lat=e['center_lat'],center_lon_180=e['center_lon'],
                            status='complete',air_temp_mean_c=8.,precip_annual_mean_mm=350,
                            relative_humidity_mean_pct=55.,seasonal_air_temp_range_c=21.))
    d=build_candidate_climate(tmp_path,entries,[],fetch=False)
    assert (d['complete'],d['partial'],d['missing'])==(3,0,0)
    assert len(d['source_files'])==1
    assert all('Precipitación anual baja' in v['climate_descriptor'] for v in d['rows'].values())
    assert all(v['source']=='NASA POWER' for v in d['rows'].values())


def test_v203_rejects_wrong_coordinates_and_unrealistic_climate(tmp_path):
    entries=_entries(1);p=tmp_path/'results/environment_sample.csv';p.parent.mkdir(parents=True)
    p.write_text('region_id,center_lat,center_lon_180,status,air_temp_mean_c,precip_annual_mean_mm,relative_humidity_mean_pct,seasonal_air_temp_range_c\n'
                 'r000_c100,99,-70,complete,17,100,40,12\n')
    x=build_candidate_climate(tmp_path,entries,[],fetch=False)
    assert x['missing']==1 and x['download_attempts']==0
    p.write_text(p.read_text().replace('99,-70','1,-70').replace('17,100,40,12','1000,-500,200,300'))
    x=build_candidate_climate(tmp_path,entries,[],fetch=False)
    assert x['missing']==1


def test_v203_one_audit_per_region_without_invented_multiscale(tmp_path):
    entries=_entries(3)
    rel=[{'earth_region_id':e['id'],'mars_profile':'elysium_planitia',
          'topographic_rank':e['topographic_rank'],'research_triage':'not_prioritized'} for e in entries]
    d=build_audits(entries,rel,{})
    assert len(d)==3 and all(x['climate_status']=='missing' for x in d)
    assert all(not x['individual_multiscale_tested'] for x in d)
    assert all('no se realizó' in (' '.join(x['findings'])).lower() for x in d)


def test_v203_lola_missing_fails_visible_not_synthetic(tmp_path):
    x=build_lunar_atlas(tmp_path,fetch=False)
    assert len(x['regions'])==6 and x['source']['availability'] is False
    assert all(m['status']=='unavailable' for m in x['maps'].values())


def test_v203_lola_int16_half_meter_and_seam(tmp_path):
    p=tmp_path/'raw/moon/ldem_4.img';p.parent.mkdir(parents=True)
    a=np.zeros((720,1440),dtype='<i2')
    a[:,:]=300
    a[300:320,1300:1340]=1000
    a.tofile(p)
    assert p.stat().st_size==BYTES
    x=build_lunar_atlas(tmp_path,fetch=False)
    assert x['source']['availability'] is True
    assert all(m['status']=='available' for m in x['maps'].values())
    cop=x['maps']['copernicus']
    assert 0 < cop['bounds'][2]-cop['bounds'][0] < 70
    assert cop['elevation_min_m']==150
    assert cop['planet']=='Moon'
    # The raw 300 DN means 150m above 1737.4km ref sphere; never 1,737,550m.
    assert cop['elevation_max_m'] < 10000


def test_v203_lola_rejects_truncated_cache(tmp_path):
    p=tmp_path/'raw/moon/ldem_4.img';p.parent.mkdir(parents=True)
    p.write_bytes(b'bad')
    with pytest.raises(ValueError,match='incompleto'):
        acquire_lola(tmp_path,fetch=False)


def test_v203_download_mock_keeps_official_size(tmp_path):
    class Response:
        def __enter__(self):return self
        def __exit__(self,*a):pass
        def raise_for_status(self):pass
        def iter_content(self,chunk_size=65536):
            yield bytes(BYTES)
    class Session:
        def get(self,url,**kwargs):
            assert 'lola_gdr' in url
            return Response()
    d=acquire_lola(tmp_path,fetch=True,session=Session())
    assert d['available'] and d['downloaded']
    assert d['sha256']


def test_v203_web_dashboard_contains_new_sections_and_exports(tmp_path):
    data,_=fixture(tmp_path)
    out=tmp_path/'reports203';d=build_v2(data,out)
    assert d['individual_audits']==3
    assert d['lunar_maps_available']==0
    page=(out/'mars_analog_dashboard_v2.html').read_text(encoding='utf-8')
    for phrase in ('data-view="world"','data-view="moon"','data-view="audits"','id="world-canvas"','id="moon-canvas"','id="audit-list"','world_land'):
        assert phrase in page
    assert len(json.loads((out/'candidate_audits_v203.json').read_text())['audits'])==3
    assert (out/'world_candidates_v203.csv').is_file()
    assert 'external src=' not in page
