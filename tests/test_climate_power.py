import calendar
import json
from pathlib import Path

import pytest

from mars_analog.data.climate_power import (
    sites_from_audit, power_request, summarize_power, fetch_candidate_climate,
    build_environment_report, _download_power_json
)


def audit_file(tmp_path):
    p=tmp_path/'audit.json'
    p.write_text(json.dumps({
        'schema_version':'mars_analog_ranking_audit_v0.8',
        'nominal_top_stability': [
            {'region_id':'r063_c140','center_lat':37.,'center_lon_180':-79.,
             'rank_original':1,'top_frequency':1.0},
            {'region_id':'r064_c139','center_lat':39.,'center_lon_180':-81.,
             'rank_original':2,'top_frequency':1.0}]
    }),encoding='utf-8')
    return p


def power_data(start=2020,end=2021):
    params={'T2M':{},'PRECTOTCORR':{},'RH2M':{}}
    for year in range(start,end+1):
        for month in range(1,13):
            k=f'{year:04d}{month:02d}'
            params['T2M'][k]=20.0
            params['PRECTOTCORR'][k]=1.0
            params['RH2M'][k]=40.0
    return {'properties':{'parameter':params},'parameters':{
        'T2M':{'units':'C'},'PRECTOTCORR':{'units':'mm/day'},'RH2M':{'units':'%'}}}


class Resp:
    headers={'Content-Type':'application/json'}
    def __init__(self, data): self.data=data
    def __enter__(self): return self
    def __exit__(self,*args): return False
    def raise_for_status(self): pass
    def iter_content(self,chunk_size): yield json.dumps(self.data).encode('utf-8')


class Session:
    def __init__(self,data): self.data=data; self.calls=0; self.params=None
    def get(self,url,**kwargs):
        self.calls+=1
        self.params=kwargs['params']
        assert url.startswith('https://power.larc.nasa.gov/')
        assert kwargs['stream'] is True
        return Resp(self.data)


def test_audit_rejects_mismatched_schema(tmp_path):
    p=audit_file(tmp_path); obj=json.loads(p.read_text()); obj['schema_version']='wrong'; p.write_text(json.dumps(obj))
    with pytest.raises(ValueError,match='V0.8'): sites_from_audit(p)


def test_audit_candidates_and_api_request(tmp_path):
    p=audit_file(tmp_path)
    sites=sites_from_audit(p,2)
    assert [x['region_id'] for x in sites]==['r063_c140','r064_c139']
    q=power_request(37,-79,2015,2024)
    assert q['parameters']=='T2M,PRECTOTCORR,RH2M'
    assert q['start']==2015 and q['end']==2024
    with pytest.raises(ValueError): power_request(37,-79,2024,2020)


def test_monthly_to_annual_uses_leap_days():
    summary=summarize_power(power_data(2020,2021),2020,2021)
    assert summary['status']=='complete'
    assert summary['complete_years']==2
    assert summary['complete_months']==24
    assert summary['precip_annual_mean_mm']==365.5
    assert summary['air_temp_mean_c']==20
    assert summary['relative_humidity_mean_pct']==40
    assert summary['seasonal_air_temp_range_c']==0


def test_fill_not_zero_and_no_missing_month_imputation():
    data=power_data(2020,2020)
    data['properties']['parameter']['PRECTOTCORR']['202006']=-999
    res=summarize_power(data,2020,2020)
    assert res['status']=='partial'
    assert res['complete_months']==11
    assert res['precip_annual_mean_mm'] is None


def test_reject_unexpected_units():
    data=power_data(2020,2020)
    data['parameters']['PRECTOTCORR']['units']='mm/month'
    with pytest.raises(ValueError,match='Unidad'): summarize_power(data,2020,2020)


def test_nasa_request_and_cache_reuse(tmp_path):
    audit=audit_file(tmp_path)
    sess=Session(power_data(2020,2021))
    dest=tmp_path/'raw'
    a=fetch_candidate_climate(audit,dest,2020,2021,top=2,limit=1,session=sess)
    assert a['new_downloads']==1 and a['total_cached']==1 and a['pending']==1
    assert sess.calls==1
    b=fetch_candidate_climate(audit,dest,2020,2021,top=2,limit=1,session=sess)
    assert b['new_downloads']==1 and b['total_cached']==2
    c=fetch_candidate_climate(audit,dest,2020,2021,top=2,limit=1,session=sess)
    assert c['new_downloads']==0 and c['total_cached']==2
    assert sess.calls==2
    report=build_environment_report(audit,dest,tmp_path/'report.csv',tmp_path/'report.json',2020,2021,top=2)
    assert report['climate_complete']==2 and report['climate_pending']==0
    assert (tmp_path/'report.csv').exists()


def test_cache_rejected_if_audit_changed(tmp_path):
    audit=audit_file(tmp_path)
    dest=tmp_path/'raw'
    fetch_candidate_climate(audit,dest,2020,2021,top=1,limit=1,session=Session(power_data()))
    obj=json.loads(audit.read_text());obj['nominal_top_stability'][0]['top_frequency']=0.95
    audit.write_text(json.dumps(obj))
    with pytest.raises(ValueError,match='incompatibles'):
        build_environment_report(audit,dest,tmp_path/'rep.csv',tmp_path/'rep.json',2020,2021,top=1)


def test_limit_response_size(tmp_path):
    site=sites_from_audit(audit_file(tmp_path))[0]
    class BigResp(Resp):
        def iter_content(self,chunk_size): yield b'x'*(65*1024)
    class Big(Session):
        def get(self,url,**kwargs): return BigResp({})
    with pytest.raises(ValueError,match='límite'):
        _download_power_json(site,2020,2021,64,session=Big(power_data()))


def test_report_handles_pending(tmp_path):
    audit=audit_file(tmp_path)
    result=build_environment_report(audit,tmp_path/'empty',tmp_path/'out.csv',tmp_path/'out.json',2020,2021,top=2)
    assert result['climate_pending']==2 and result['climate_complete']==0
    assert result['status']=='descriptive_climate_only_topography_rank_unchanged'
