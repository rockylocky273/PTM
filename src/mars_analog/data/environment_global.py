"""V1.0: diversified environmental sampling and NASA POWER point climatologies.

Preserves the V0.7 topographic ranking. This is a deliberately *selected* sample,
not a random, statistically representative sample of every terrestrial landform.
"""
from __future__ import annotations
import csv
import json
import math
import random
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path

from .download import atomic_json, sha256_file
from .climate_power import (_download_power_json, _read_cache, cache_path,
                            summarize_power, _validate_response)

SCHEMA = 'mars_analog_environment_plan_v1.0'
RESPONSE_SCHEMA = 'nasa_power_point_v1.0'


def _read_ranked(path: Path) -> list[dict]:
    with Path(path).open(encoding='utf-8', newline='') as f:
        raw = list(csv.DictReader(f))
    if not raw or len(raw) > 50000:
        raise ValueError('Ranking ausente o demasiado grande')
    seen = set()
    rows = []
    for i, row in enumerate(raw, 1):
        ident = row.get('region_id', '')
        if not ident.startswith('r') or not all(c.isalnum() or c == '_' for c in ident) or ident in seen:
            raise ValueError('Identificador regional inválido o repetido')
        seen.add(ident)
        try:
            rank = int(row['rank'])
            lat = float(row['center_lat'])
            lon = float(row['center_lon_180'])
            distance = float(row['distance_total'])
        except (ValueError, KeyError, TypeError) as exc:
            raise ValueError('Ranking mal formado') from exc
        if rank != i or not (-90 <= lat <= 90 and -180 <= lon <= 180) or not all(map(math.isfinite,[lat,lon,distance])) or distance < 0:
            raise ValueError('Ranking no ordenado consecutivamente o datos inválidos')
        rows.append({'region_id':ident,'center_lat':lat,'center_lon_180':lon,
                     'topographic_rank':rank,'distance_topographic':distance})
    return rows


def _geo_km(a: dict, b: dict) -> float:
    lat1,lat2 = math.radians(a['center_lat']), math.radians(b['center_lat'])
    dlat = lat2-lat1
    dlon = math.radians((b['center_lon_180']-a['center_lon_180']+180)%360-180)
    h = math.sin(dlat/2)**2+math.cos(lat1)*math.cos(lat2)*math.sin(dlon/2)**2
    return 6371.0088 * 2*math.asin(min(1.,math.sqrt(max(0,h))))


def _rank_band(rank: int, n: int) -> int:
    return min(4, (rank-1)*5//n)


def _latitude_band(lat: float) -> int:
    return min(5,max(0, int((lat+65)//(130/6))))


def _longitude_band(lon: float) -> int:
    return min(5,max(0,int((lon+180)//60)))


def _read_audit(path: Path) -> dict:
    with Path(path).open(encoding='utf-8') as f:
        obj=json.load(f)
    if obj.get('schema_version')!='mars_analog_ranking_audit_v0.8':
        raise ValueError('Se requiere auditoría V0.8')
    top=obj.get('nominal_top_stability')
    if not isinstance(top,list) or not top:
        raise ValueError('Auditoría sin lista top')
    return obj


def build_environment_plan(ranking_csv: Path, audit_json: Path, output: Path,
                           sample_size: int = 125, anchor_top: int = 25,
                           min_separation_km: float = 250., seed: int = 2026) -> dict:
    if not (25 <= sample_size <= 1000 and 1 <= anchor_top <= 100 and
            0 <= min_separation_km <= 2000):
        raise ValueError('sample-size [25,1000], anchor-top [1,100], separación [0,2000]')
    rows=_read_ranked(ranking_csv)
    audit=_read_audit(audit_json)
    audited=audit['nominal_top_stability'][:anchor_top]
    by_id={r['region_id']:r for r in rows}
    anchor=[]
    for r in audited:
        ident=r['region_id']
        if ident not in by_id:
            raise ValueError('Auditoría y ranking no coinciden')
        found=by_id[ident]
        if (found['topographic_rank'] != int(r['rank_original']) or
            abs(found['center_lat']-float(r['center_lat']))>1e-7 or
            abs(found['center_lon_180']-float(r['center_lon_180']))>1e-7):
            raise ValueError('Diferencia entre ranking y auditoría')
        anchor.append({**found,'selection':'anchor_topography'})
    if sample_size < len(anchor):
        raise ValueError('sample-size debe incluir todos los anchors')
    if len({x['region_id'] for x in anchor}) != len(anchor):
        raise ValueError('Auditoría contiene candidatos repetidos')
    if audit.get('input_sha256',{}).get('ranking') and audit['input_sha256']['ranking']!=sha256_file(ranking_csv):
        raise ValueError('El ranking fue modificado desde la auditoría; detener')

    rng=random.Random(seed)
    excluded={a['region_id'] for a in anchor}
    groups=defaultdict(list)
    for r in rows:
        if r['region_id'] not in excluded:
            q=_rank_band(r['topographic_rank'],len(rows))
            groups[(q,_latitude_band(r['center_lat']),_longitude_band(r['center_lon_180']))].append(r)
    for vals in groups.values(): rng.shuffle(vals)
    selected=list(anchor)
    additions=[]
    qgroups={q:sorted((k for k in groups if k[0]==q)) for q in range(5)}
    for keys in qgroups.values(): rng.shuffle(keys)
    quotas=[(sample_size-len(anchor))//5 + (1 if q < ((sample_size-len(anchor))%5) else 0) for q in range(5)]
    def try_add(r):
        if any(_geo_km(r,a)<min_separation_km for a in selected): return False
        selected.append({**r,'selection':'stratified_exploration'})
        additions.append(r)
        return True
    for q in range(5):
        keys=qgroups[q]
        if not keys: continue
        accepted=0
        # Round robin across geographic buckets within rank quintile.
        while accepted<quotas[q] and any(groups[k] for k in keys):
            progress=False
            for k in keys:
                if accepted>=quotas[q]: break
                while groups[k]:
                    candidate=groups[k].pop()
                    if try_add(candidate):
                        accepted+=1; progress=True; break
            if not progress: break
    # Fill any geographic-distance constrained shortfalls; report shortfall if any.
    if len(selected)<sample_size:
        remaining=[r for r in rows if r['region_id'] not in {a['region_id'] for a in selected}]
        rng.shuffle(remaining)
        for r in remaining:
            if len(selected)>=sample_size: break
            try_add(r)
    for r in selected:
        r['rank_quintile'] = _rank_band(r['topographic_rank'],len(rows))+1
        r['latitude_band'] = _latitude_band(r['center_lat'])
        r['longitude_band'] = _longitude_band(r['center_lon_180'])
    # Anchors first to reuse V0.9, then balanced exploration.
    obj={'schema_version':SCHEMA,'status':'sample_design_not_global_climate_coverage',
         'source_ranking_sha256':sha256_file(ranking_csv),
         'source_audit_sha256':sha256_file(audit_json),
         'ranking_count':len(rows),'requested_sample_size':sample_size,
         'sample_size':len(selected),'anchors':len(anchor),
         'exploration':len(selected)-len(anchor),'seed':seed,
         'min_separation_km_exploratory':min_separation_km,
         'rank_quintile_counts':dict(sorted(Counter(str(r['rank_quintile']) for r in selected).items())),
         'selection_note':'Muestreo estratificado exploratorio; NO estima la distribución climática global ni corrige todos los sesgos',
         'candidates':selected}
    atomic_json(output,obj)
    return {k:v for k,v in obj.items() if k!='candidates'} | {'plan_file':str(output),'plan_sha256':sha256_file(output)}


def read_plan(path: Path) -> dict:
    with Path(path).open(encoding='utf-8') as f: obj=json.load(f)
    if obj.get('schema_version')!=SCHEMA:
        raise ValueError('Plan V1.0 inválido')
    candidates=obj.get('candidates')
    if not isinstance(candidates,list) or len(candidates)!=obj.get('sample_size') or len({r['region_id'] for r in candidates})!=len(candidates):
        raise ValueError('Plan corrupto o candidatos repetidos')
    for site in candidates:
        if (site.get('selection') not in ('anchor_topography','stratified_exploration') or
            not -90<=site['center_lat']<=90 or not -180<=site['center_lon_180']<=180):
            raise ValueError('Candidato inválido en plan')
    return obj


def _new_file(dest:Path,site:dict,start:int,end:int) -> Path:
    return Path(dest)/f"power_{site['region_id']}_{start}_{end}.json"


def _read_new(path:Path,site:dict,start:int,end:int,plan_hash:str):
    if not path.exists(): return None
    try:
        obj=json.loads(path.read_text(encoding='utf-8'))
        if (obj.get('schema_version')!=RESPONSE_SCHEMA or obj.get('region_id')!=site['region_id'] or
            obj.get('center_lat')!=site['center_lat'] or obj.get('center_lon_180')!=site['center_lon_180'] or
            obj.get('start_year')!=start or obj.get('end_year')!=end or obj.get('plan_sha256')!=plan_hash):
            raise ValueError('Metadatos incompatibles')
        _validate_response(obj['response'])
        return obj
    except (KeyError,ValueError,TypeError,OSError) as exc:
        raise ValueError(f'Caché incompatible {path}: {exc}') from exc


def _cached_entry(site:dict, start:int,end:int,plan_hash:str,audit_hash:str,old_dir:Path,new_dir:Path):
    if site['selection']=='anchor_topography':
        path=cache_path(old_dir,site,start,end)
        obj=_read_cache(path,site,start,end,audit_hash)
    else:
        path=_new_file(new_dir,site,start,end)
        obj=_read_new(path,site,start,end,plan_hash)
    return obj,path


def fetch_environment(plan: Path, old_dir: Path, dest: Path, start:int=2015,end:int=2024,
                      limit:int=5, max_kb:int=1024, connect_timeout:float=20.,
                      read_timeout:float=180.,retries:int=0,retry_wait:float=2.,session=None) -> dict:
    if not 1<=limit<=50 or not 64<=max_kb<=10240:
        raise ValueError('limit [1,50], max-kb [64,10240]')
    obj=read_plan(plan); plan_hash=sha256_file(plan); audit_hash=obj['source_audit_sha256']
    new_count=0; old_count=0; cached_count=0; failures=[]; completed=[]
    for site in obj['candidates']:
        prev,path=_cached_entry(site,start,end,plan_hash,audit_hash,old_dir,dest)
        if prev is not None:
            cached_count+=1
            continue
        if new_count>=limit: continue
        new_count+=1
        try:
            response=_download_power_json(site,start,end,max_kb,session=session,
                                          connect_timeout=connect_timeout,read_timeout=read_timeout,
                                          retries=retries,retry_wait=retry_wait)
            record={'schema_version':RESPONSE_SCHEMA if site['selection']!='anchor_topography' else 'nasa_power_point_v0.9',
                    'source':'NASA POWER monthly point','source_url':'https://power.larc.nasa.gov/api/temporal/monthly/point',
                    'region_id':site['region_id'],'center_lat':site['center_lat'],
                    'center_lon_180':site['center_lon_180'],'topographic_rank':site['topographic_rank'],
                    'start_year':start,'end_year':end,'retrieved_at_utc':datetime.now(timezone.utc).isoformat(),
                    'response':response}
            if site['selection']=='anchor_topography': record['audit_sha256']=audit_hash
            else: record['plan_sha256']=plan_hash
            atomic_json(path,record)
            old_count+=1
            completed.append({'region_id':site['region_id'],'sha256':sha256_file(path),'file':str(path)})
        except (RuntimeError,ValueError) as exc:
            failures.append({'region_id':site['region_id'],'error':str(exc)[:300]})
    total=sum(1 for site in obj['candidates'] if _cached_entry(site,start,end,plan_hash,audit_hash,old_dir,dest)[0] is not None)
    return {'schema_version':'environment_fetch_v1.0','status':'partial_climate_collection_no_rerank',
            'selected':len(obj['candidates']),'new_downloads':old_count,
            'attempted_new_requests':new_count,'cached_before':cached_count,'total_cached':total,
            'pending':len(obj['candidates'])-total,'failures':failures,'downloaded':completed,
            'note':'Una solicitud NASA POWER por centro candidato; orden topográfico no se altera'}


def summarize_environment(plan:Path,old_dir:Path,dest:Path,csv_out:Path,report:Path,
                          start:int=2015,end:int=2024) -> dict:
    obj=read_plan(plan);plan_hash=sha256_file(plan)
    rows=[]; provenance=[]
    for site in obj['candidates']:
        entry,path=_cached_entry(site,start,end,plan_hash,obj['source_audit_sha256'],old_dir,dest)
        vals= summarize_power(entry['response'],start,end) if entry else {
            'status':'not_downloaded','expected_months':(end-start+1)*12,
            'complete_months':0,'complete_years':0,
            'air_temp_mean_c':None,'precip_annual_mean_mm':None,
            'relative_humidity_mean_pct':None,'seasonal_air_temp_range_c':None}
        rows.append({**site,**vals})
        if entry: provenance.append({'region_id':site['region_id'],'sha256':sha256_file(path)})
    csv_out=Path(csv_out);csv_out.parent.mkdir(parents=True,exist_ok=True)
    tmp=csv_out.with_name(csv_out.name+'.tmp')
    try:
        with tmp.open('w',encoding='utf-8',newline='') as f:
            writer=csv.DictWriter(f,fieldnames=list(rows[0])); writer.writeheader();writer.writerows(rows)
        tmp.replace(csv_out)
    finally: tmp.unlink(missing_ok=True)
    by_q={str(q):{'selected':0,'complete':0} for q in range(1,6)}
    for row in rows:
        q=str(row['rank_quintile']);by_q[q]['selected']+=1
        if row['status']=='complete':by_q[q]['complete']+=1
    output={'schema_version':'mars_analog_environment_global_v1.0',
            'status':'descriptive_sampled_climate_not_global_census_or_mars_score',
            'plan_sha256':plan_hash,'selected':len(rows),
            'complete':sum(r['status']=='complete' for r in rows),
            'partial':sum(r['status']=='partial' for r in rows),
            'pending':sum(r['status']=='not_downloaded' for r in rows),
            'coverage_by_rank_quintile':by_q,'years':[start,end],
            'source_files':provenance,'csv_file':str(csv_out),'csv_sha256':sha256_file(csv_out),
            'limitations':['Muestreo seleccionado, no censo global climático',
                           'Un punto NASA POWER no caracteriza toda la ventana de ~240 km',
                           'No son temperaturas marcianas ni MODIS LST',
                           'Topografía no se reordena; no comparar puntajes planetarios'],
            'report_file':str(report)}
    atomic_json(report,output)
    return {k:v for k,v in output.items() if k!='source_files'}
