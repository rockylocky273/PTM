"""V1.0.1: safe, selective AppEEARS *point* land-cover acquisition.

NASA AppEEARS API: https://appeears.earthdatacloud.nasa.gov/api/
Real server integration must be checked on user's machine; tests mock HTTP.
The 1-or-5 points per ~240km terrestrial window are *not* area coverage.
"""
from __future__ import annotations

import csv
import getpass
import json
import math
import os
import re
from datetime import datetime, timezone
from pathlib import Path

import requests

from .download import atomic_json, sha256_file
from .environment_global import read_plan

BASE='https://appeears.earthdatacloud.nasa.gov/api/'
PLAN_SCHEMA='mars_analog_appeears_point_plan_v1.0.1'
JOB_SCHEMA='mars_analog_appeears_task_v1.0.1'
TASK_ID=re.compile(r'^[A-Za-z0-9][A-Za-z0-9-]{5,127}$')


def _json_request(method:str,endpoint:str,token:str|None=None,session=None,**kwargs):
    s=session or requests
    headers={'Accept':'application/json'}
    if token:
        headers['Authorization']='Bearer '+token
    try:
        response=s.request(method,BASE+endpoint,headers=headers,
                           timeout=(20,180),**kwargs)
        response.raise_for_status()
        result=response.json()
    except requests.exceptions.RequestException as exc:
        # Do not echo headers, passwords, auth tokens, or URL query credentials.
        raise RuntimeError(f'AppEEARS no respondió correctamente en {endpoint} ({type(exc).__name__})') from exc
    except ValueError as exc:
        raise RuntimeError(f'AppEEARS devolvió un JSON inválido en {endpoint}') from exc
    return result


def get_layers(product:str='MCD12Q1.061',session=None) -> dict:
    if not re.fullmatch(r'[A-Za-z0-9_]+\.\d{3}',product):
        raise ValueError('Producto AppEEARS inválido')
    data=_json_request('GET','product/'+product,session=session)
    if not isinstance(data,dict):raise RuntimeError('Respuesta de capas inesperada')
    return {'product':product,'source':'NASA AppEEARS','layers':list(data),
            'layer_information':{k:data[k] for k in data if k in ('LC_Type1','LC_Prop1','LC_Type1_Assessment')},
            'note':'Elegí el nombre exacto de la capa antes de enviar el task'}


def _wrap_lon(lon:float) -> float:
    return (lon+180.)%360.-180.


def _coordinate_points(site:dict,n:int,spacing_km:float) -> list[dict]:
    lat=float(site['center_lat']);lon=float(site['center_lon_180'])
    if not -85<=lat<=85 or not -180<=lon<=180:
        raise ValueError('Centro fuera del rango operativo de la muestra AppEEARS')
    region=site['region_id']
    dlat=spacing_km/111.195
    dlon=spacing_km/(111.195*max(.05,math.cos(math.radians(lat))))
    offsets=[('c',0.,0.)]
    if n==5:
        offsets.extend([('n',dlat,0.),('s',-dlat,0.),('e',0.,dlon),('w',0.,-dlon)])
    result=[]
    for suffix,a,b in offsets:
        y=lat+a;x=_wrap_lon(lon+b)
        if not (-90<y<90):raise ValueError('Puntos próximos al polo no son compatibles')
        result.append({'id':region+'_'+suffix,'category':region,
                       'latitude':round(y,6),'longitude':round(x,6)})
    return result


def build_point_plan(environment_plan:Path,output:Path,year:int=2024,limit:int=5,
                     points_per_region:int=5,spacing_km:float=60.,
                     product:str='MCD12Q1.061',layer:str='LC_Type1') -> dict:
    if not (2001<=year<=2025 and 1<=limit<=125 and points_per_region in (1,5)
            and 0<=spacing_km<=100):
        raise ValueError('year [2001,2025], limit [1,125], points [1,5], spacing [0,100]')
    if not re.fullmatch(r'[A-Za-z0-9_]+\.\d{3}',product) or not re.fullmatch(r'[A-Za-z0-9_]+',layer):
        raise ValueError('Producto o capa inválidos')
    source=read_plan(environment_plan)
    sites=source['candidates'][:limit]
    coordinates=[p for site in sites for p in _coordinate_points(site,points_per_region,spacing_km)]
    ids=[p['id'] for p in coordinates]
    if len(ids)!=len(set(ids)):raise ValueError('Puntos duplicados')
    task={
        'task_type':'point',
        'task_name':f'MarsAnalog_Landcover_{year}_{limit}regions',
        'params':{'dates':[{'startDate':f'01-01-{year}','endDate':f'12-31-{year}'}],
                  'layers':[{'product':product,'layer':layer}],
                  'coordinates':coordinates}
    }
    obj={'schema_version':PLAN_SCHEMA,'status':'planned_not_submitted',
         'source_environment_plan_sha256':sha256_file(environment_plan),
         'year':year,'regions':len(sites),'points':len(coordinates),
         'spacing_km':spacing_km,'region_ids':[s['region_id'] for s in sites],
         'task':task,
         'scientific_warning':'Muestras puntuales dispersas: NO representan porcentajes de cobertura dentro de toda la ventana. Sin ranking planetario.'}
    output=Path(output);atomic_json(output,obj)
    return {'status':obj['status'],'source_environment_plan_sha256':obj['source_environment_plan_sha256'],
            'product':product,'layer':layer,'regions':len(sites),'points':len(coordinates),
            'plan_file':str(output),'plan_sha256':sha256_file(output),'year':year,
            'note':obj['scientific_warning']}


def read_point_plan(path:Path)->dict:
    obj=json.loads(Path(path).read_text(encoding='utf-8'))
    if obj.get('schema_version')!=PLAN_SCHEMA:raise ValueError('Plan de AppEEARS incompatible')
    task=obj.get('task',{});params=task.get('params',{})
    if task.get('task_type')!='point' or len(params.get('layers',[]))!=1:
        raise ValueError('Solo se admiten planes puntuales de una capa')
    coords=params.get('coordinates',[])
    if not coords or len(coords)>625 or len(coords)!=obj.get('points') or len({c['id'] for c in coords})!=len(coords):
        raise ValueError('Puntos ausentes, duplicados o excesivos')
    for c in coords:
        if not(-90<float(c['latitude'])<90 and -180<=float(c['longitude'])<=180):
            raise ValueError('Coordenadas inválidas')
    return obj


def _safe_auth_http_error(status: int | None, used_email: bool = False) -> str:
    """Never include provider response bodies, credentials or bearer tokens."""
    tag = f'HTTP {status}' if status is not None else 'HTTP desconocido'
    if status == 401:
        hint = ('Usá tu nombre de usuario de Earthdata, no tu correo, '
                'y comprobá la contraseña en https://urs.earthdata.nasa.gov/.')
        if used_email:
            hint = ('Parece que introdujiste un correo. AppEEARS API requiere '
                    'el nombre de usuario de Earthdata; no el correo electrónico.')
    elif status == 403:
        hint = ('La cuenta puede no tener acceso autorizado a AppEEARS. '
                'Iniciá sesión en https://appeears.earthdatacloud.nasa.gov/ '
                'y comprobá el estado de la cuenta.')
    elif status == 429:
        hint = 'El servicio limita solicitudes; evitá reintentos inmediatos.'
    elif status is not None and status >= 500:
        hint = 'Error del servidor NASA; probá más tarde y consultá el estado del servicio.'
    elif status == 400:
        hint = 'La API rechazó la solicitud de inicio de sesión; revisá el formato y la documentación.'
    else:
        hint = 'Verificá el usuario de Earthdata y la documentación oficial de AppEEARS.'
    return f'Autenticación AppEEARS fallida ({tag}). {hint}'


def authenticate(username:str|None=None,session=None) -> str:
    name=username or os.getenv('EARTHDATA_USERNAME') or input('Usuario NASA Earthdata (NO correo): ').strip()
    name=name.strip()
    if not name:raise ValueError('Usuario Earthdata vacío')
    password=getpass.getpass('Contraseña NASA Earthdata (no se guarda): ')
    if not password:raise ValueError('Contraseña vacía')
    s=session or requests
    try:
        resp=s.request('POST',BASE+'login',auth=(name,password),
                       headers={'Accept':'application/json'},
                       data={'grant_type':'client_credentials'},timeout=(20,180))
        resp.raise_for_status()
        result=resp.json()
    except requests.exceptions.HTTPError as exc:
        response=getattr(exc,'response',None) or locals().get('resp')
        status=getattr(response,'status_code',None)
        raise RuntimeError(_safe_auth_http_error(status,used_email='@' in name)) from None
    except requests.exceptions.RequestException as exc:
        # Avoid printing URLs, headers, passwords, response body, and tokens.
        raise RuntimeError(f'AppEEARS: fallo de red al autenticar ({type(exc).__name__}); '
                           'comprobá DNS, conexión y servicio.') from None
    except ValueError:
        raise RuntimeError('AppEEARS devolvió un formato de autenticación inválido (no JSON).') from None
    token=result.get('token') if isinstance(result,dict) else None
    if not isinstance(token,str) or not token:
        raise RuntimeError('AppEEARS no devolvió un token de autenticación válido.')
    return token


def submit_plan(plan:Path,job:Path,token:str,session=None) -> dict:
    obj=read_point_plan(plan)
    job=Path(job)
    if job.exists():
        prev=read_job(job)
        if prev['plan_sha256']==sha256_file(plan):
            return {'status':'already_submitted','task_id':prev['task_id'],'job_file':str(job)}
        raise ValueError('Existe un task previo de otro plan; usá otro --job')
    layer=obj['task']['params']['layers'][0]
    # The AppEEARS product registry is the authority for current availability.
    available=get_layers(layer['product'],session=session)['layers']
    if layer['layer'] not in available:
        raise ValueError(f'Capa {layer["layer"]} no encontrada en AppEEARS. Usá appeears-layers')
    response=_json_request('POST','task',token,session=session,json=obj['task'])
    task_id=response.get('task_id') if isinstance(response,dict) else None
    if not isinstance(task_id,str) or not TASK_ID.fullmatch(task_id):
        raise RuntimeError('AppEEARS no devolvió un task_id válido; consultá el portal antes de reenviar')
    manifest={'schema_version':JOB_SCHEMA,'task_id':task_id,'plan_file':str(plan),
              'plan_sha256':sha256_file(plan),'created_at_utc':datetime.now(timezone.utc).isoformat(),
              'task_name':obj['task']['task_name'],'product':layer['product'],
              'layer':layer['layer'],'year':obj['year'],'points':obj['points']}
    atomic_json(job,manifest)
    return {'status':'submitted_not_done','task_id':task_id,'job_file':str(job),
            'note':'Usá appeears-status para consultar; no hay ejecución en segundo plano de este programa.'}


def read_job(job:Path) -> dict:
    obj=json.loads(Path(job).read_text(encoding='utf-8'))
    if obj.get('schema_version')!=JOB_SCHEMA or not TASK_ID.fullmatch(obj.get('task_id','')):
        raise ValueError('Archivo de tarea AppEEARS inválido')
    return obj


def task_status(job:Path,token:str,session=None) -> dict:
    obj=read_job(job)
    reply=_json_request('GET','task/'+obj['task_id'],token,session=session)
    if not isinstance(reply,dict):raise RuntimeError('Estado AppEEARS inesperado')
    return {'task_id':obj['task_id'],'status':reply.get('status','unknown'),
            'done':reply.get('status')=='done',
            'message':reply.get('message') if isinstance(reply.get('message'),str) else None}


def bundle_files(job:Path,token:str,session=None) -> dict:
    obj=read_job(job)
    res=_json_request('GET','bundle/'+obj['task_id'],token,session=session)
    files=res.get('files') if isinstance(res,dict) else None
    if not isinstance(files,list):raise RuntimeError('Bundle AppEEARS no contiene lista de archivos')
    return {'task_id':obj['task_id'],'files':[
        {'file_id':f.get('file_id'),'file_name':f.get('file_name'),'file_size':f.get('file_size')}
        for f in files if isinstance(f,dict)]}


def download_bundle(job:Path,directory:Path,max_mb:int,token:str,session=None) -> dict:
    if not 1<=max_mb<=100:raise ValueError('max-mb fuera de [1,100]')
    status=task_status(job,token,session=session)
    if not status['done']:raise ValueError('Task aún no está terminado; consultá appeears-status')
    obj=read_job(job);bundle=bundle_files(job,token,session=session)
    files=bundle['files'];directory=Path(directory);directory.mkdir(parents=True,exist_ok=True)
    eligible=[]
    for f in files:
        name=f.get('file_name');file_id=f.get('file_id')
        if not isinstance(name,str) or Path(name).name!=name or not isinstance(file_id,str):continue
        if not re.fullmatch('[A-Za-z0-9_.-]+',file_id):continue
        if Path(name).suffix.lower() not in ('.csv','.json','.txt'):continue
        eligible.append((name,file_id))
    downloaded=[];s=session or requests
    for name,file_id in eligible:
        final=directory/name
        if final.exists():
            downloaded.append({'file':str(final),'sha256':sha256_file(final),'cached':True});continue
        tmp=directory/(name+'.part')
        try:
            with s.request('GET',BASE+'bundle/'+obj['task_id']+'/'+file_id,
                           headers={'Authorization':'Bearer '+token},timeout=(20,180),stream=True) as resp:
                resp.raise_for_status()
                count=0
                with tmp.open('wb') as fp:
                    for chunk in resp.iter_content(chunk_size=1024*256):
                        count+=len(chunk)
                        if count>max_mb*1024*1024:
                            raise ValueError(f'Archivo supera límite {max_mb} MB: {name}')
                        fp.write(chunk)
            tmp.replace(final)
            downloaded.append({'file':str(final),'sha256':sha256_file(final),'cached':False,'size_bytes':final.stat().st_size})
        except requests.exceptions.RequestException as exc:
            raise RuntimeError(f'Fallo al descargar archivo AppEEARS {name}: {type(exc).__name__}') from exc
        finally:
            tmp.unlink(missing_ok=True)
    return {'task_id':obj['task_id'],'downloaded':downloaded,
            'excluded_non_text_files':len(files)-len(eligible),
            'note':'Descarga solo archivos CSV/JSON/TXT. Validar encabezados y códigos IGBP antes de agregación.'}


def preview_csv(directory:Path)->dict:
    files=sorted(Path(directory).glob('*.csv'))
    info=[]
    for p in files:
        with p.open(encoding='utf-8-sig',newline='') as stream:
            columns=next(csv.reader(stream),[])
        info.append({'name':p.name,'columns':columns,'sha256':sha256_file(p)})
    return {'files':info,
            'note':'No se infieren clases IGBP automáticamente sin validar el formato del CSV.'}
