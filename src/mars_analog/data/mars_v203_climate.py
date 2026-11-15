"""V2.0.3: terrestrial NASA POWER climate evidence for every shortlisted region.

Prioritize existing, signed/cached historical records. Optional, bounded downloads
are NASA POWER point climatologies, not planetary similarity or area statistics.
"""
from __future__ import annotations
import csv
import json
import math
from pathlib import Path
from typing import Any
from .climate_power import _download_power_json, summarize_power, POWER_URL
from .download import atomic_json, sha256_file

VARS = ('air_temp_mean_c','precip_annual_mean_mm','relative_humidity_mean_pct','seasonal_air_temp_range_c')
START, END = 2015, 2024
CSV_FILES = ('results/environment_sample.csv','results/environment_context.csv')
LIMITS = ((-100,75),(0,30000),(0,100),(0,100))


def _num(x, low, high):
    try: v=float(x)
    except (TypeError, ValueError): return None
    return round(v,3) if math.isfinite(v) and low <= v <= high else None


def _extract(row:dict, source:str, years:Any=None) -> dict|None:
    v={k:_num(row.get(k),*bounds) for k,bounds in zip(VARS,LIMITS)}
    if all(x is None for x in v.values()): return None
    if row.get('status')=='not_downloaded':return None
    count=sum(x is not None for x in v.values())
    return {**v,'status':'complete' if count==len(VARS) and row.get('status')=='complete' else 'partial',
            'source':'NASA POWER', 'source_detail':source, 'years': years,
            'point_context_only':True,'fields_available':count,
            'climate_descriptor':_descriptor(v)}


def _descriptor(x):
    # Descriptive precipitation bands ONLY: not Köppen classification, no climate-model claim.
    p=x['precip_annual_mean_mm'];t=x['air_temp_mean_c']
    if p is None: return 'Clima no clasificado (falta precipitación)'
    moisture=('Precipitación anual muy baja' if p<250 else
              'Precipitación anual baja' if p<500 else
              'Precipitación anual intermedia' if p<1000 else
              'Precipitación anual elevada')
    temp=('; temperatura media bajo 0 °C' if t is not None and t<0 else
          '; temperatura media inferior a 10 °C' if t is not None and t<10 else
          '; temperatura media superior a 20 °C' if t is not None and t>20 else '')
    return moisture+temp


def _read_csv(path:Path, entries:list[dict]) -> dict:
    if not path.is_file():return {}
    allowed={x['id']:(x['center_lat'],x['center_lon']) for x in entries}
    out={}
    with path.open('r',newline='',encoding='utf-8-sig') as f:
        for row in csv.DictReader(f):
            rid=row.get('region_id')
            if rid not in allowed or rid in out:continue
            # If reported coordinates are present, they must match the original 2° center.
            try:
                lat=float(row.get('center_lat'))
                lon=float(row.get('center_lon_180'))
            except (ValueError,TypeError):continue
            if abs(lat-allowed[rid][0])>0.01 or abs(lon-allowed[rid][1])>0.01:continue
            result=_extract(row, f'Histórico {path.name}; fila {rid}', 'período histórico del CSV')
            if result:out[rid]=result
    return out


def _cache_file(root:Path,rid:str):
    return root/'raw'/'nasa_power_v203'/f'power_{rid}_{START}_{END}.json'


def _cached(root:Path,e:dict) -> dict|None:
    path=_cache_file(root,e['id'])
    if not path.is_file():return None
    o=json.loads(path.read_text(encoding='utf-8'))
    if (o.get('schema_version')!='mars_analog_power_point_v2.0.3' or
        o.get('region_id')!=e['id'] or o.get('years')!=[START,END] or
        o.get('coords')!=[e['center_lat'],e['center_lon']]):
        raise ValueError('Caché NASA POWER V2.0.3 incompatible: '+str(path))
    from .climate_power import _validate_response
    _validate_response(o['response'])
    return _extract(summarize_power(o['response'],START,END),f'NASA POWER; caché {path.name}',[START,END])


def _historical_csv_provenance(root:Path)->list[dict]:
    sources=[]
    for rel in CSV_FILES:
        path=root/rel
        if path.is_file():
            sources.append({'file':str(path),'sha256':sha256_file(path)})
            for reportrel in ('reports/environment_global_v1_0.json','reports/environment_context.json'):
                report=root/reportrel
                if report.is_file():
                    try:
                        data=json.loads(report.read_text(encoding='utf-8'))
                        if Path(str(data.get('csv_file',''))).name==path.name and data.get('csv_sha256') and data['csv_sha256']!=sha256_file(path):
                            raise ValueError('CSV climático modificado desde informe: '+str(path))
                    except json.JSONDecodeError as exc:raise ValueError('Informe de clima inválido: '+str(report)) from exc
    return sources


def build_candidate_climate(root:Path,entries:list[dict],historical:list[dict],
                            *,fetch:bool=False,max_downloads:int=25) ->dict:
    root=Path(root)
    if not 0<=max_downloads<=25:raise ValueError('max_downloads debe estar entre 0 y 25')
    source_files=_historical_csv_provenance(root)
    by_id={}
    for rel in CSV_FILES:
        for k,v in _read_csv(root/rel,entries).items():
            if k not in by_id or v['fields_available']>by_id[k]['fields_available']:
                by_id[k]=v
    for row in historical:
        rid=row.get('earth_region_id')
        if rid not in {e['id'] for e in entries}:continue
        v=_extract({**row, 'status':row.get('status') or 'complete'},'V1.3.0 NASA POWER; informe multicriterio','período V1.3.0')
        if v and (rid not in by_id or v['fields_available']>by_id[rid]['fields_available']):by_id[rid]=v
    downloaded=0;failures=[];failed_in_a_row=0
    for e in entries:
        rid=e['id']
        if rid in by_id and by_id[rid]['fields_available']==4:continue
        cached=_cached(root,e)
        if cached and (rid not in by_id or cached['fields_available']>by_id[rid]['fields_available']):by_id[rid]=cached
        if rid in by_id and by_id[rid]['fields_available']==4:continue
        if not fetch or downloaded>=max_downloads or failed_in_a_row>=3:continue
        downloaded+=1
        site={'region_id':rid,'center_lat':e['center_lat'],'center_lon_180':e['center_lon']}
        try:
            raw=_download_power_json(site, START,END,1024,connect_timeout=7.,read_timeout=22.,retries=0)
            summary=summarize_power(raw,START,END)
            obj={'schema_version':'mars_analog_power_point_v2.0.3','source':POWER_URL,
                 'region_id':rid,'coords':[e['center_lat'],e['center_lon']],
                 'years':[START,END],'response':raw}
            path=_cache_file(root,rid);path.parent.mkdir(parents=True,exist_ok=True)
            atomic_json(path,obj)
            v=_extract(summary,f'NASA POWER {START}–{END} (descarga actual)',[START,END])
            if v:by_id[rid]=v
            failed_in_a_row=0
        except (OSError,ValueError,RuntimeError,KeyError,TypeError) as exc:
            failures.append({'region_id':rid,'error':str(exc)[:180]});failed_in_a_row+=1
    for e in entries:
        path=_cache_file(root,e['id'])
        if path.is_file():source_files.append({'file':str(path),'sha256':sha256_file(path)})
    return {'rows':by_id,'source_files':source_files,'complete':sum(v['status']=='complete' for v in by_id.values()),
            'partial':sum(v['status']=='partial' for v in by_id.values()),
            'missing':len(entries)-len(by_id),'download_attempts':downloaded,
            'download_failures':failures,'source':'NASA POWER monthly point; contexto terrestre no extrapolado a toda la celda'}
