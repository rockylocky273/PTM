"""Deterministic synthetic service fixtures; never claim NASA/GLiM live validation."""
import json
from pathlib import Path
from unittest.mock import Mock

import pytest

from mars_analog.data.download import atomic_json
from mars_analog.data.geology_glim import (
    LAYER_URL, _coords, build_plan, classify_response, fetch_points,
    inspect_layer, read_geology_plan, summarize,
)


def sample_environment(tmp_path):
    sites = [
        {'region_id':'r063_c140','center_lat':37.0,'center_lon_180':-79.0,'topographic_rank':1,'selection':'anchor_topography'},
        {'region_id':'r026_c146','center_lat':-37.0,'center_lon_180':-67.0,'topographic_rank':6,'selection':'stratified_exploration'},
    ]
    path=tmp_path/'environment_plan.json'
    atomic_json(path,{'schema_version':'mars_analog_environment_plan_v1.0',
                      'sample_size':2,'candidates':sites,
                      'source_ranking_sha256':'abc'})
    return path


class Response:
    def __init__(self, payload, status=200):
        self.payload=payload
        self.status_code=status
        self.content=json.dumps(payload).encode('utf-8')
    def raise_for_status(self):
        if self.status_code>=400:
            import requests
            raise requests.HTTPError(str(self.status_code))
    def json(self):
        return self.payload


class Session:
    def __init__(self, payloads):
        self.payloads=list(payloads)
        self.calls=[]
    def get(self, url, params, timeout):
        self.calls.append((url,params,timeout))
        return Response(self.payloads.pop(0))


def feature(lithology):
    return {'features':[{'attributes':{'xx_Description':lithology}}]}


def test_points_centered_and_deterministic():
    out=_coords(-37.,-67.,5,60.)
    assert out[0]==(-37.,-67.)
    assert len(out)==5
    assert out[1][0]>-37. and out[2][0]<-37.
    assert out[3][1]>-67. and out[4][1]<-67.
    assert _coords(-37.,-67.,5,60.)==out


def test_points_near_dateline_wrap():
    out=_coords(10,179.9,5,90.)
    assert -180 <= out[3][1] < -179


@pytest.mark.parametrize('n,km,lat',[(2,60.,1.),(5,-1.,1.),(5,1.,1.),(5,60.,85.)])
def test_points_invalid(n,km,lat):
    with pytest.raises(ValueError): _coords(lat,30.,n,km)


def test_build_plan_and_immutability(tmp_path):
    env=sample_environment(tmp_path)
    plan=tmp_path/'plan.json'
    first=build_plan(env,plan,limit=2,points_per_region=5)
    digest=first['plan_sha256']
    assert first['region_ids']==['r063_c140','r026_c146']
    assert first['points']==10
    second=build_plan(env,plan,limit=2,points_per_region=5)
    assert digest==second['plan_sha256']
    obj=read_geology_plan(plan)
    assert obj['points'][-1]['region_id']=='r026_c146'


def test_argentina_only_by_id(tmp_path):
    env=sample_environment(tmp_path)
    p=tmp_path/'plan.json'
    r=build_plan(env,p,limit=1,region_ids='r026_c146',points_per_region=9)
    assert r['region_ids']==['r026_c146'] and r['points']==9
    with pytest.raises(ValueError):build_plan(env,p,limit=1,region_ids='missing')
    with pytest.raises(ValueError):build_plan(env,p,limit=2,region_ids='r026_c146,r026_c146')


def test_classification():
    assert classify_response(feature('Basic volcanic rocks'))['status']=='classified'
    assert classify_response({'features':[]})['status']=='unmapped'
    assert classify_response(feature('Water Bodies'))['status']=='unclassified'
    assert classify_response({'features':[{"attributes":{"xx_Description":"Basic volcanic rocks"}},
                                                  {"attributes":{"xx_Description":"Unconsolidated sediments"}}]})['status']=='ambiguous'
    assert classify_response({'features':[], 'exceededTransferLimit':True})['status']=='ambiguous'
    with pytest.raises(ValueError): classify_response({'features':[{'attributes':{}}]})


def test_metadata_validation():
    sess=Session([{'fields':[{'name':'OBJECTID'},{'name':'xx_Description'}],
                   'geometryType':'esriGeometryPolygon'}])
    summary=inspect_layer(30.,session=sess)
    assert summary['description_field']=='xx_Description'
    assert sess.calls[0][0]==LAYER_URL
    with pytest.raises(ValueError):inspect_layer(30.,session=Session([{'fields':[],'geometryType':'esriGeometryPoint'}]))


def test_fetch_cache_and_summary_no_mars_score(tmp_path):
    env=sample_environment(tmp_path)
    plan=tmp_path/'plan.json'
    build_plan(env,plan,limit=2,points_per_region=1)
    source=Session([feature('Unconsolidated sediments'),feature('Basic volcanic rocks')])
    dest=tmp_path/'raw'
    result=fetch_points(plan,dest,limit=2,session=source)
    assert result['new_downloads']==2 and result['pending']==0
    assert source.calls[0][1]['geometry']=='-79.0,37.0'
    assert source.calls[1][1]['geometry']=='-67.0,-37.0'
    assert source.calls[0][1]['inSR']==4326
    assert source.calls[0][1]['outFields'].find('xx_Description')>=0
    assert fetch_points(plan,dest,limit=2,session=Session([]))['new_downloads']==0
    report=summarize(plan,dest,tmp_path/'geo.csv',tmp_path/'report.json')
    assert report['retrieved_points']==2
    assert report['classified_points']==2
    assert report['regions_with_sampled_basic_volcanics']==['r026_c146']
    assert report['pending_points']==0
    import csv
    with (tmp_path/'geo.csv').open(encoding='utf-8') as f:
        rows=list(csv.DictReader(f))
    assert rows[1]['basic_volcanic_sample_share_pct']=='100.0'
    assert rows[0]['topographic_rank']=='1'
    assert 'mars_score' not in rows[0]


def test_pending_and_failed_requests_are_not_fake_results(tmp_path):
    env=sample_environment(tmp_path)
    plan=tmp_path/'plan.json'
    build_plan(env,plan,limit=2,points_per_region=1)
    dest=tmp_path/'raw'
    result=summarize(plan,dest,tmp_path/'summary.csv',tmp_path/'report.json')
    assert result['pending_points']==2
    bad=Session([{'error':{'code':503,'message':'Unavailable'}}])
    result=fetch_points(plan,dest,limit=1,session=bad)
    assert result['new_downloads']==0 and result['pending']==2
    assert result['failures'][0]['point_id']=='r063_c140_p00'
    assert list(dest.rglob('*.json'))==[]


def test_cache_bound_to_plan_hash(tmp_path):
    env=sample_environment(tmp_path)
    plan=tmp_path/'plan.json'
    build_plan(env,plan,limit=1,points_per_region=1)
    dest=tmp_path/'raw'
    fetch_points(plan,dest,limit=1,session=Session([feature('Basic volcanic rocks')]))
    data=json.loads(plan.read_text())
    data['spacing_km']=75.
    atomic_json(plan,data)
    # V1.1.1: same exact coordinates may be reused across plans with provenance.
    # The original file remains stored in its own plan-hash directory.
    result=fetch_points(plan,dest,limit=1,session=Session([]))
    assert result['cached_before']==1 and result['reused_from_compatible_plan']==1
    assert result['new_downloads']==0
