import json
from pathlib import Path
import pytest

from mars_analog.data import appeears_landcover as app
from mars_analog.data.download import atomic_json


def sample_environment_plan():
    return {'schema_version':'mars_analog_environment_plan_v1.0',
            'sample_size':2,'candidates':[
                {'region_id':'r063_c140','center_lat':37.0,'center_lon_180':-79.0,'selection':'anchor_topography'},
                {'region_id':'r077_c062','center_lat':65.0,'center_lon_180':125.0,'selection':'stratified_exploration'}]}


def test_coordinate_points_center():
    pts=app._coordinate_points(sample_environment_plan()['candidates'][0],1,60)
    assert pts==[{'id':'r063_c140_c','category':'r063_c140','latitude':37.0,'longitude':-79.0}]


def test_coordinate_points_five():
    pts=app._coordinate_points(sample_environment_plan()['candidates'][1],5,60)
    assert len(pts)==5 and len({p['id'] for p in pts})==5
    assert pts[1]['latitude']>65 and pts[4]['longitude']<125


def test_longitude_wrapping():
    pts=app._coordinate_points({'region_id':'r000_c000','center_lat':0,'center_lon_180':179.9},5,60)
    assert pts[3]['longitude']< -179


def test_build_point_plan(tmp_path,monkeypatch):
    p=tmp_path/'old.json'; p.write_text('irrelevant')
    monkeypatch.setattr(app,'read_plan',lambda _:sample_environment_plan())
    result=app.build_point_plan(p,tmp_path/'new.json',limit=2)
    assert result['points']==10
    obj=app.read_point_plan(tmp_path/'new.json')
    assert obj['task']['params']['dates']==[{'startDate':'01-01-2024','endDate':'12-31-2024'}]
    assert obj['task']['task_type']=='point'
    assert obj['task']['params']['layers']==[{'product':'MCD12Q1.061','layer':'LC_Type1'}]
    assert 'token' not in str(obj)


def test_point_plan_reject_bad_args(tmp_path,monkeypatch):
    monkeypatch.setattr(app,'read_plan',lambda _:sample_environment_plan())
    with pytest.raises(ValueError):app.build_point_plan(tmp_path/'old.json',tmp_path/'new.json',limit=0)
    with pytest.raises(ValueError):app.build_point_plan(tmp_path/'old.json',tmp_path/'new.json',points_per_region=9)


def test_read_plan_reject_duplicate(tmp_path):
    p=tmp_path/'plan.json'
    atomic_json(p,{'schema_version':app.PLAN_SCHEMA,'points':2,'task':{'task_type':'point','params':{
        'layers':[{'product':'MCD12Q1.061','layer':'LC_Type1'}],
        'coordinates':[{'id':'same','latitude':0,'longitude':0},{'id':'same','latitude':0,'longitude':0}]}}})
    with pytest.raises(ValueError):app.read_point_plan(p)


def test_product_layers(monkeypatch):
    monkeypatch.setattr(app,'_json_request',lambda method,route,**kwargs:{'LC_Type1':{'Description':'IGBP'},'LC_Prop1':{}})
    out=app.get_layers()
    assert out['layers']==['LC_Type1','LC_Prop1']
    with pytest.raises(ValueError):app.get_layers('https://example.org/')


def test_submit_valid_job(tmp_path,monkeypatch):
    p=tmp_path/'plan.json';p.write_text('plan')
    j=tmp_path/'job.json'
    monkeypatch.setattr(app,'read_point_plan',lambda _: {'task':{'task_name':'pilot','params':{'layers':[{'product':'MCD12Q1.061','layer':'LC_Type1'}]}},'year':2024,'points':5})
    monkeypatch.setattr(app,'get_layers',lambda product,session=None:{'layers':['LC_Type1']})
    monkeypatch.setattr(app,'_json_request',lambda *args,**kwargs:{'task_id':'c250e8d7-0000-4000-a123-123456789abc'})
    first=app.submit_plan(p,j,'secret')
    assert first['status']=='submitted_not_done'
    assert 'secret' not in j.read_text()
    again=app.submit_plan(p,j,'secret')
    assert again['status']=='already_submitted'


def test_submit_reject_unavailable_layer(tmp_path,monkeypatch):
    p=tmp_path/'plan.json';p.write_text('plan')
    monkeypatch.setattr(app,'read_point_plan',lambda _: {'task':{'task_name':'pilot','params':{'layers':[{'product':'MCD12Q1.061','layer':'BAD'}]}},'year':2024,'points':5})
    monkeypatch.setattr(app,'get_layers',lambda product,session=None:{'layers':['LC_Type1']})
    with pytest.raises(ValueError):app.submit_plan(p,tmp_path/'job.json','secret')


def test_status_and_bundle(tmp_path,monkeypatch):
    j=tmp_path/'job.json';atomic_json(j,{'schema_version':app.JOB_SCHEMA,'task_id':'abcdef-123456'})
    monkeypatch.setattr(app,'_json_request',lambda method,route,token=None,session=None:
        {'status':'done'} if route.startswith('task/') else {'files':[{'file_id':'test','file_name':'sample.csv'}]})
    assert app.task_status(j,'tok')['done'] is True
    assert app.bundle_files(j,'tok')['files'][0]['file_name']=='sample.csv'


def test_preview(tmp_path):
    p=tmp_path/'data.csv';p.write_text('id,value\na,1\n')
    assert app.preview_csv(tmp_path)['files'][0]['columns']==['id','value']


def test_auth_no_persist(monkeypatch):
    class Res:
        def raise_for_status(self):pass
        def json(self):return {'token':'S3CR3T'}
    class Session:
        def request(self,method,url,**kw):
            assert method=='POST' and kw['auth']==('alice','password')
            return Res()
    monkeypatch.setattr(app.getpass,'getpass',lambda _: 'password')
    assert app.authenticate(username='alice',session=Session())=='S3CR3T'

@pytest.mark.parametrize('status,hint',[
    (401,'HTTP 401'), (403,'HTTP 403'), (429,'HTTP 429'),
    (503,'HTTP 503'), (400,'HTTP 400'),
])
def test_auth_http_diagnostic_status_without_secrets(monkeypatch,status,hint):
    import requests
    class FakeResponse:
        status_code=status
        def raise_for_status(self):
            raise requests.exceptions.HTTPError('secret-token should never leak',response=self)
    class FakeSession:
        def request(self,*args,**kwargs):
            return FakeResponse()
    monkeypatch.setattr(app.getpass,'getpass',lambda _: 'SECRET_PASSWORD')
    with pytest.raises(RuntimeError) as exc:
        app.authenticate(username='demo-user',session=FakeSession())
    assert hint in str(exc.value)
    assert 'SECRET_PASSWORD' not in str(exc.value)
    assert 'secret-token' not in str(exc.value)
    assert 'demo-user' not in str(exc.value)


def test_auth_recommends_real_username_not_email(monkeypatch):
    import requests
    class FakeResponse:
        status_code=401
        def raise_for_status(self):
            raise requests.exceptions.HTTPError('unauthorized',response=self)
    class FakeSession:
        def request(self,*args,**kwargs):return FakeResponse()
    monkeypatch.setattr(app.getpass,'getpass',lambda _: 'somepw')
    with pytest.raises(RuntimeError) as exc:
        app.authenticate(username='someone@example.org',session=FakeSession())
    assert 'nombre de usuario' in str(exc.value)
    assert 'someone@example.org' not in str(exc.value)


def test_auth_check_command_does_not_expose_token(monkeypatch,capsys):
    from mars_analog.data import cli
    monkeypatch.setattr(app,'authenticate',lambda username=None:'VERY_SECRET_TOKEN')
    assert cli.main(['appeears-auth-check','--username','test-account'])==0
    printed=capsys.readouterr().out
    assert 'authenticated' in printed
    assert 'VERY_SECRET_TOKEN' not in printed
