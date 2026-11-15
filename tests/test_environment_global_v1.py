import csv
import json
from pathlib import Path

import pytest

from mars_analog.data.environment_global import (
    _read_ranked, _geo_km, build_environment_plan, read_plan,
    fetch_environment, summarize_environment)
from mars_analog.data.climate_power import fetch_candidate_climate
from mars_analog.data.download import sha256_file
from mars_analog.data.environment_diagnostic import produce_diagnostic


def fixtures(tmp_path, n=250, top=5):
    path=tmp_path/'ranking.csv'
    columns=['rank','region_id','center_lat','center_lon_180','distance_total']
    with path.open('w',newline='',encoding='utf-8') as f:
        w=csv.DictWriter(f,fieldnames=columns);w.writeheader()
        for i in range(n):
            w.writerow({'rank':i+1,'region_id':f'r{i:03d}_c{i:03d}',
                        'center_lat':-60+(i%25)*5,
                        'center_lon_180':-175+((i*17)%350),
                        'distance_total':(i+1)/100})
    rows=_read_ranked(path)
    audit=tmp_path/'audit.json'
    audit.write_text(json.dumps({'schema_version':'mars_analog_ranking_audit_v0.8',
        'input_sha256':{'ranking':sha256_file(path)},
        'nominal_top_stability':[{'region_id':r['region_id'],'center_lat':r['center_lat'],
                                  'center_lon_180':r['center_lon_180'],
                                  'rank_original':r['topographic_rank']}
                                 for r in rows[:top]]}), encoding='utf-8')
    return path,audit


def power_data(start=2020,end=2021):
    params={key:{} for key in ('T2M','PRECTOTCORR','RH2M')}
    for y in range(start,end+1):
        for m in range(1,13):
            k=f'{y:04d}{m:02d}'
            params['T2M'][k]=20.;params['PRECTOTCORR'][k]=1.
            params['RH2M'][k]=45.
    return {'properties':{'parameter':params},'parameters':{'T2M':{'units':'C'},
            'PRECTOTCORR':{'units':'mm/day'},'RH2M':{'units':'%'}}}

class Resp:
    headers={}
    def __init__(self,payload):self.payload=payload
    def __enter__(self):return self
    def __exit__(self,*args):return False
    def raise_for_status(self):pass
    def iter_content(self,chunk_size):yield json.dumps(self.payload).encode()
class Session:
    def __init__(self):self.calls=0
    def get(self,*args,**kwargs):self.calls+=1;return Resp(power_data())


def test_plan_keeps_anchor_and_expands_across_rank_quintiles(tmp_path):
    rank,audit=fixtures(tmp_path)
    report=build_environment_plan(rank,audit,tmp_path/'plan.json',sample_size=55,anchor_top=5,
                                  min_separation_km=0,seed=2026)
    plan=read_plan(tmp_path/'plan.json')
    assert report['sample_size']==55 and report['anchors']==5
    assert [s['topographic_rank'] for s in plan['candidates'][:5]]==[1,2,3,4,5]
    extra=plan['candidates'][5:]
    assert len(set(s['region_id'] for s in extra))==50
    assert all(any(s['rank_quintile']==q for s in extra) for q in range(1,6))
    assert sum(int(x) for x in report['rank_quintile_counts'].values())==55


def test_plan_reproducible_same_seed(tmp_path):
    rank,audit=fixtures(tmp_path)
    build_environment_plan(rank,audit,tmp_path/'a.json',sample_size=45,anchor_top=5,min_separation_km=0,seed=50)
    build_environment_plan(rank,audit,tmp_path/'b.json',sample_size=45,anchor_top=5,min_separation_km=0,seed=50)
    a=read_plan(tmp_path/'a.json')['candidates']
    b=read_plan(tmp_path/'b.json')['candidates']
    assert a==b


def test_tampered_ranking_rejected(tmp_path):
    rank,audit=fixtures(tmp_path)
    s=rank.read_text();rank.write_text(s.replace('0.01','0.11',1))
    with pytest.raises(ValueError,match='modificado'):build_environment_plan(rank,audit,tmp_path/'plan.json',anchor_top=5)


def test_ranking_invalid_duplicate(tmp_path):
    rank,audit=fixtures(tmp_path)
    lines=rank.read_text().splitlines()
    lines[2]=lines[1]
    rank.write_text('\n'.join(lines))
    with pytest.raises(ValueError):_read_ranked(rank)


def test_plan_respects_exploratory_separation(tmp_path):
    rank,audit=fixtures(tmp_path)
    build_environment_plan(rank,audit,tmp_path/'plan.json',sample_size=50,anchor_top=5,min_separation_km=250,seed=12)
    selected=read_plan(tmp_path/'plan.json')['candidates']
    for i,site in enumerate(selected):
        if site['selection']=='stratified_exploration':
            assert all(_geo_km(site,older)>=250 for older in selected[:i])


def test_read_rejects_bad_schema(tmp_path):
    path=tmp_path/'x.json';path.write_text('{"schema_version":"bad"}')
    with pytest.raises(ValueError):read_plan(path)


def test_fetch_and_report_partial_then_full(tmp_path):
    rank,audit=fixtures(tmp_path)
    plan=tmp_path/'plan.json'
    build_environment_plan(rank,audit,plan,sample_size=25,anchor_top=5,min_separation_km=0)
    sess=Session()
    old=tmp_path/'old';new=tmp_path/'new'
    r=fetch_environment(plan,old,new,start=2020,end=2021,limit=4,session=sess)
    assert r['new_downloads']==4 and r['pending']==21
    summary=summarize_environment(plan,old,new,tmp_path/'c.csv',tmp_path/'c.json',2020,2021)
    assert summary['complete']==4 and summary['pending']==21
    r=fetch_environment(plan,old,new,start=2020,end=2021,limit=30,session=sess)
    assert r['new_downloads']==21 and r['pending']==0
    summary=summarize_environment(plan,old,new,tmp_path/'c.csv',tmp_path/'c.json',2020,2021)
    assert summary['complete']==25 and summary['pending']==0
    assert sess.calls==25
    r=fetch_environment(plan,old,new,start=2020,end=2021,limit=4,session=sess)
    assert r['new_downloads']==0 and r['pending']==0 and sess.calls==25


def test_reuses_v09_cache_on_anchor(tmp_path):
    rank,audit=fixtures(tmp_path)
    plan=tmp_path/'plan.json'
    build_environment_plan(rank,audit,plan,sample_size=25,anchor_top=5,min_separation_km=0)
    old=tmp_path/'old'
    sess=Session()
    fetch_candidate_climate(audit,old,start=2020,end=2021,top=5,limit=5,session=sess)
    assert sess.calls==5
    res=fetch_environment(plan,old,tmp_path/'new',start=2020,end=2021,limit=2,session=sess)
    assert res['cached_before']==5
    assert sess.calls==7


def test_reject_tampered_new_cache(tmp_path):
    rank,audit=fixtures(tmp_path)
    plan=tmp_path/'plan.json'
    build_environment_plan(rank,audit,plan,sample_size=25,anchor_top=5,min_separation_km=0)
    new=tmp_path/'new'
    fetch_environment(plan,tmp_path/'old',new,start=2020,end=2021,limit=6,session=Session())
    f=next(new.glob('*.json'))
    data=json.loads(f.read_text());data['center_lat']+=1;f.write_text(json.dumps(data))
    with pytest.raises(ValueError,match='incompatible'):
        summarize_environment(plan,tmp_path/'old',new,tmp_path/'c.csv',tmp_path/'c.json',2020,2021)


def test_diagnostic_keeps_separate_context(tmp_path):
    rank,audit=fixtures(tmp_path)
    plan=tmp_path/'plan.json'
    build_environment_plan(rank,audit,plan,sample_size=25,anchor_top=5,min_separation_km=0)
    fetch_environment(plan,tmp_path/'old',tmp_path/'new',start=2020,end=2021,limit=5,session=Session())
    summarize_environment(plan,tmp_path/'old',tmp_path/'new',tmp_path/'c.csv',tmp_path/'c.json',2020,2021)
    obj=produce_diagnostic(plan,tmp_path/'c.csv',tmp_path/'nonexistent.csv',tmp_path/'diag.csv',tmp_path/'diag.json')
    assert obj['climate_complete']==5
    assert obj['landcover_available']==0
    with (tmp_path/'diag.csv').open(newline='') as f:
        rows=list(csv.DictReader(f))
    assert len(rows)==25
    assert all(row['landcover_status']=='not_loaded' for row in rows)
    assert rows[0]['topographic_rank']=='1'


def test_reject_diagnostic_missing_plan_site(tmp_path):
    rank,audit=fixtures(tmp_path)
    plan=tmp_path/'plan.json'
    build_environment_plan(rank,audit,plan,sample_size=25,anchor_top=5,min_separation_km=0)
    c=tmp_path/'c.csv';c.write_text('region_id,topographic_rank\nwrong,1\n')
    with pytest.raises(ValueError,match='no contiene'):
        produce_diagnostic(plan,c,tmp_path/'none.csv',tmp_path/'d.csv',tmp_path/'d.json')
