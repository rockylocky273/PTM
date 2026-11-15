"""Independent tests; network is stubbed. No geological labels are fabricated as user data."""
import csv
import json

import pytest

from mars_analog.data.mars_geology_v122 import (
    CRS, SOURCE, validate_metadata, east_to_signed, _offset_point, _classify,
    plan_geology, _read_plan, fetch_geology, summarize_geology, source_metadata)
from mars_analog.data.mars_domain_v122 import evaluate_domain, evidence_matrix
from mars_analog.data.mars_profiles_v12 import build_profiles, screen_profiles
from mars_analog.data.mars_profiles_audit_v121 import audit_rankings
from test_mars_profiles_v12 import create_mars, create_earth_and_catalog


class Response:
    def __init__(self, obj):
        self._obj=obj
        self.content=json.dumps(obj).encode('utf-8')
    def raise_for_status(self):pass
    def json(self):return self._obj


class FakeSession:
    def __init__(self, override=None):
        self.params=[]
        self.override=override
    def get(self, url, params=None, timeout=None):
        self.params.append((url,params))
        if not url.endswith('/query'):
            return Response({'name':'Geology','geometryType':'esriGeometryPolygon',
                             'extent':{'spatialReference':{'wkid':CRS}},
                             'fields':[{'name':x} for x in ('OBJECTID','Unit','UnitDesc')]})
        if self.override is not None:return Response(self.override)
        return Response({'features':[{'attributes':{
            'OBJECTID':101,'Unit':'AHv','UnitDesc':'Volcanic unit'}}]})


def _setup(tmp):
    mars=tmp/'mars.nc';create_mars(mars)
    man=tmp/'manifest.json'
    build_profiles(mars,'all',30,9,tmp/'profiles',man)
    return man


def test_conversion_on_both_sides_of_antimeridian():
    assert east_to_signed(357.5)==-2.5
    assert east_to_signed(226.0)==-134.
    assert east_to_signed(180.)==-180.
    assert east_to_signed(0)==0.
    assert east_to_signed(359.999)==-0.001
    with pytest.raises(ValueError):east_to_signed(-67)
    with pytest.raises(ValueError):east_to_signed(360)


def test_mars_offset_uses_mars_radius_not_earth():
    lat,lon,east = _offset_point(-37,67,0,100)
    assert lat==-37
    assert 69 < lon < 70
    assert east==lon


def test_layer_metadata_guard_and_service():
    sess=FakeSession()
    assert source_metadata(session=sess)['mars_custom_crs']==CRS
    with pytest.raises(ValueError,match='Referencia espacial'):
        validate_metadata({'name':'Geology','geometryType':'esriGeometryPolygon',
                           'extent':{'spatialReference':{'wkid':4326}},
                           'fields':[{'name':x} for x in ('OBJECTID','Unit','UnitDesc')]})


def test_plan_has_verified_manifest_and_signed_query_coords(tmp_path):
    man=_setup(tmp_path)
    plan=tmp_path/'geology.json'
    r=plan_geology(man,plan,9,100)
    assert r['profiles']==6 and r['samples']==54
    obj=_read_plan(plan)
    q=next(p for p in obj['points'] if p['profile_id']=='olympus_mons' and p['point_id'].endswith('p00'))
    assert q['lon_east_0_360']==226 and q['lon_signed_for_arcgis']==-134
    data=json.loads(plan.read_text());data['points'][0]['lon_signed_for_arcgis']=25
    plan.write_text(json.dumps(data))
    with pytest.raises(ValueError,match='Longitud'):_read_plan(plan)


def test_plan_rejects_outside_profile_window(tmp_path):
    man=_setup(tmp_path)
    with pytest.raises(ValueError, match='radio'):
        plan_geology(man,tmp_path/'plan.json',9,121)


def test_classification_distinguishes_ambiguous_and_missing():
    assert _classify([])[0]=='no_map_coverage'
    f={'attributes':{'OBJECTID':1,'Unit':'AHv','UnitDesc':'Volcanic unit'}}
    assert _classify([f])[1]=='AHv'
    assert _classify([f,f])[0]=='ambiguous_multiple_polygons'
    with pytest.raises(ValueError):_classify([{'attributes':{'Unit':'AHv'}}])


def test_fetch_caches_and_uses_custom_crs(tmp_path):
    man=_setup(tmp_path);plan=tmp_path/'plan.json'
    plan_geology(man,plan,1,100)
    session=FakeSession()
    out=tmp_path/'raw'
    first=fetch_geology(plan,out,3,session=session)
    assert first['new_queries']==3 and first['pending']==3
    query=[x for x in session.params if x[0].endswith('/query')][0][1]
    assert query['inSR']=='104971'
    assert query['geometryType']=='esriGeometryPoint'
    g=json.loads(query['geometry'])
    assert g['spatialReference']['wkid']==104971
    second=fetch_geology(plan,out,10,session=session)
    assert second['cached_before']==3 and second['new_queries']==3 and second['pending']==0
    third=fetch_geology(plan,out,1,session=session)
    assert third['cached_before']==6 and third['attempted']==0
    result=summarize_geology(plan,out,tmp_path/'summary.csv',tmp_path/'summary.json')
    assert result['mapped_points']==6 and result['pending_points']==0
    assert 'AHv' in result['profiles'][0]['unit_code_counts']


def test_missing_is_not_material_observation(tmp_path):
    man=_setup(tmp_path);plan=tmp_path/'plan.json';plan_geology(man,plan,1,50)
    raw=tmp_path/'raw';sess=FakeSession({'features':[]})
    fetch_geology(plan,raw,6,session=sess)
    summary=summarize_geology(plan,raw,tmp_path/'s.csv',tmp_path/'s.json')
    assert summary['mapped_points']==0 and summary['no_coverage_points']==6
    assert summary['pending_points']==0


def test_cache_does_not_silently_mix_plans(tmp_path):
    man=_setup(tmp_path);plan=tmp_path/'plan.json';plan_geology(man,plan,1,50)
    raw=tmp_path/'raw';sess=FakeSession();fetch_geology(plan,raw,1,session=sess)
    # One mismatch must stop the run instead of mixing geological coordinate systems.
    cached=next(raw.glob('*.json'));d=json.loads(cached.read_text());d['query_crs']=4326
    cached.write_text(json.dumps(d))
    with pytest.raises(ValueError,match='Caché geológico'):
        fetch_geology(plan,raw,1,session=sess)


def test_domains_and_matrix_end_to_end(tmp_path):
    man=_setup(tmp_path)
    geo_plan=tmp_path/'geoplan.json';plan_geology(man,geo_plan,1,50)
    raw=tmp_path/'georaw';fetch_geology(geo_plan,raw,6,session=FakeSession())
    mars_report=tmp_path/'geology_report.json'
    summarize_geology(geo_plan,raw,tmp_path/'geology.csv',mars_report)
    earth,catalog=create_earth_and_catalog(tmp_path)
    screen=tmp_path/'screen.json'
    screen_profiles(man,earth,catalog,tmp_path/'rankings',screen,top=5,min_separation=0)
    audit=tmp_path/'audit'
    audit_rankings(screen,man,audit,ks=(5,8,10),scenarios=3,seed=2026,watch=('r00000',))
    domain_file=tmp_path/'domain.json'
    result=evaluate_domain(audit/'rank_audit_report.json',tmp_path/'domain.csv',domain_file)
    assert result['evaluated_profiles']==6
    assert len(result['profiles'])==6
    glim=tmp_path/'earth_glim.csv'
    with glim.open('w',newline='') as f:
        w=csv.DictWriter(f,fieldnames=['region_id','classified','basic_volcanic_sample_count','observed_lithology_classes'])
        w.writeheader();w.writerow({'region_id':'r00000','classified':9,'basic_volcanic_sample_count':2,
                                    'observed_lithology_classes':'{"Basic volcanic rocks": 2}'})
    matrix=evidence_matrix(mars_report,domain_file,glim,screen,tmp_path/'matrix.csv',tmp_path/'matrix.json',watch='r00000')
    assert matrix['rows']==6
    assert 'without_joint_score' in matrix['status']
    with (tmp_path/'matrix.csv').open() as f:
        vals=list(csv.DictReader(f))
    assert all(v['geological_compatibility_score']=='NOT_COMPUTED' for v in vals)
    # Tamper must be detected.
    with (audit/'feature_saturation.csv').open('a') as f:f.write('tamper')
    with pytest.raises(ValueError, match='SHA-256'):
        evaluate_domain(audit/'rank_audit_report.json',tmp_path/'new.csv',tmp_path/'new.json')


def test_errors_do_not_create_false_observations(tmp_path):
    man=_setup(tmp_path);plan=tmp_path/'plan.json';plan_geology(man,plan,1,50)
    raw=tmp_path/'raw';sess=FakeSession({'error':{'code':400,'message':'Invalid geometry'}})
    result=fetch_geology(plan,raw,2,session=sess)
    assert result['new_queries']==0 and result['pending']==6
    assert len(result['failures'])==2
    assert not list(raw.glob('*.json'))
