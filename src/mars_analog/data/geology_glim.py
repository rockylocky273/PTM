"""V1.1: exploratory GLiM Level I lithology via public ArcGIS feature-layer point queries.

NOT a geologic verification of Mars analog status. The service is a third-party
ArcGIS publication of GLiM-derived polygons, not an authoritative geological
survey of a particular exposure. Point samples are not area fractions.
"""
from __future__ import annotations

import csv
import hashlib
import json
import math
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import requests

from .download import atomic_json, sha256_file
from .environment_global import read_plan

SCHEMA_PLAN = 'mars_analog_geology_point_plan_v1.1'
SCHEMA_POINT = 'mars_analog_glim_point_response_v1.1'
SCHEMA_REPORT = 'mars_analog_geology_context_v1.1'
LAYER_URL = ('https://services8.arcgis.com/4KhTMTZ1x0f76DSg/arcgis/rest/'
             'services/GLiM_Niveau_I/FeatureServer/1')
ORIGINAL_DOI = 'https://doi.org/10.1029/2012GC004370'

# Class labels are taken verbatim from the public GLiM Level I layer metadata.
CLASSES = (
    'Acid plutonic rocks', 'Acid volcanic rocks', 'Basic plutonic rocks',
    'Basic volcanic rocks', 'Carbonate sedimentary rocks', 'Evaporites',
    'Ice and Glaciers', 'Intermediate plutonic rocks',
    'Intermediate volcanic rocks', 'Metamorphics',
    'Mixed sedimentary rocks', 'No Data', 'Pyroclastics',
    'Siliciclastic sedimentary rocks', 'Unconsolidated sediments',
    'Water Bodies',
)
ALLOWED = frozenset(CLASSES)
VOLCANIC = frozenset({'Acid volcanic rocks', 'Basic volcanic rocks',
                      'Intermediate volcanic rocks', 'Pyroclastics'})
FILL = frozenset({'No Data', 'Water Bodies', 'Ice and Glaciers'})


def _coords(center_lat: float, center_lon: float, count: int, spacing_km: float) -> list[tuple[float,float]]:
    if count not in (1, 5, 9):
        raise ValueError('points-per-region debe ser 1, 5 o 9')
    if not (5. <= spacing_km <= 120.) or not math.isfinite(spacing_km):
        raise ValueError('spacing-km debe estar entre 5 y 120 km')
    if abs(center_lat) > 80 or not -180 <= center_lon <= 180:
        raise ValueError('Latitud geológica fuera de rango (±80 grados)')
    offsets = [(0.,0.)]
    if count >= 5:
        offsets += [(spacing_km,0.),(-spacing_km,0.),(0.,spacing_km),(0.,-spacing_km)]
    if count == 9:
        offsets += [(spacing_km,spacing_km),(spacing_km,-spacing_km),
                    (-spacing_km,spacing_km),(-spacing_km,-spacing_km)]
    points = []
    for north,east in offsets:
        lat = center_lat + north/111.195
        lon = center_lon + east/(111.195*math.cos(math.radians(center_lat)))
        if abs(lat)>85:
            raise ValueError('Muestra geológica demasiado próxima al polo')
        lon = (lon + 180)%360-180
        points.append((round(lat,7),round(lon,7)))
    return points


def build_plan(environment_plan: Path, output: Path, limit: int=6, points_per_region: int=5,
               spacing_km: float=60., region_ids: str|None=None) -> dict:
    source = read_plan(environment_plan)
    sites = source['candidates']
    if not (1 <= limit <= len(sites)):
        raise ValueError(f'limit debe estar entre 1 y {len(sites)}')
    if region_ids:
        requested = [x.strip() for x in region_ids.split(',') if x.strip()]
        if not requested or len(set(requested)) != len(requested) or len(requested) > limit:
            raise ValueError('region-ids inválido: repetido, vacío o mayor que limit')
        by_id = {r['region_id']:r for r in sites}
        missing = [x for x in requested if x not in by_id]
        if missing:
            raise ValueError(f'Regiones ausentes del plan ambiental: {missing}')
        chosen = [by_id[x] for x in requested]
    else:
        chosen = sites[:limit]
    if len(chosen)*points_per_region > 1000:
        raise ValueError('Máximo 1000 puntos por plan. Reducí limit o points-per-region')
    points = []
    for site in chosen:
        for j,(lat,lon) in enumerate(_coords(float(site['center_lat']),float(site['center_lon_180']),
                                              points_per_region,spacing_km)):
            points.append({'point_id':f"{site['region_id']}_p{j:02d}",
                           'region_id':site['region_id'], 'point_index':j,
                           'lat':lat,'lon':lon})
    obj = {'schema_version':SCHEMA_PLAN,
           'status':'point_sampling_plan_not_geologic_area_mapping',
           'environment_plan_sha256':sha256_file(environment_plan),
           'source_ranking_sha256':source['source_ranking_sha256'],
           'source_glim_level':'Level I', 'provider_layer_url':LAYER_URL,
           'dataset_reference':ORIGINAL_DOI,
           'points_per_region':points_per_region, 'spacing_km':spacing_km,
           'region_count':len(chosen), 'point_count':len(points),
           'regions':[{'region_id':s['region_id'],
                       'center_lat':s['center_lat'],
                       'center_lon_180':s['center_lon_180'],
                       'topographic_rank':s['topographic_rank']} for s in chosen],
           'points':points,
           'limitations':['Muestras puntuales; no son proporciones de área.',
                          'GLiM Level I es litología generalizada; no identifica muestras de basalto con certeza.',
                          'Servicio de terceros que republica GLiM, no el repositorio original.',
                          'Sin reclasificación ni puntuación geológica de Marte.']}
    atomic_json(output,obj)
    return {'status':obj['status'],'regions':len(chosen),'points':len(points),
            'region_ids':[s['region_id'] for s in chosen],
            'plan_file':str(output),'plan_sha256':sha256_file(output),
            'source':LAYER_URL}


def read_geology_plan(path: Path) -> dict:
    obj = json.loads(Path(path).read_text(encoding='utf-8'))
    if not isinstance(obj,dict) or obj.get('schema_version')!=SCHEMA_PLAN:
        raise ValueError('Se requiere geology-plan V1.1')
    pts = obj.get('points')
    regions = obj.get('regions')
    if not isinstance(pts,list) or not isinstance(regions,list) or len(pts) != obj.get('point_count') or len(regions) != obj.get('region_count'):
        raise ValueError('Plan geológico incompleto')
    ids = [p['point_id'] for p in pts]
    if len(set(ids)) != len(ids) or len(pts)>1000:
        raise ValueError('Puntos repetidos o excesivos')
    by_region = {r['region_id'] for r in regions}
    if len(by_region)!=len(regions):
        raise ValueError('Regiones repetidas')
    for p in pts:
        if p['region_id'] not in by_region or not (-85<=float(p['lat'])<=85 and -180<=float(p['lon'])<=180):
            raise ValueError('Geometría o región inválida')
    if obj.get('provider_layer_url') != LAYER_URL:
        raise ValueError('Proveedor geológico no coincide')
    return obj


def inspect_layer(timeout: float=30., session=None) -> dict:
    data = _request_json(LAYER_URL,{'f':'json'},timeout,session=session)
    names = {x['name'] for x in data.get('fields',[]) if isinstance(x,dict) and 'name' in x}
    required = {'OBJECTID','xx_Description'}
    if not required.issubset(names) or data.get('geometryType') != 'esriGeometryPolygon':
        raise ValueError(f'Metadatos inesperados del servicio GLiM: {sorted(names)}')
    return {'status':'source_metadata_validated_no_geology_download',
            'layer':LAYER_URL,'description_field':'xx_Description',
            'classes':list(CLASSES),'published_fields':sorted(names),
            'original_paper':ORIGINAL_DOI}


def _request_json(url: str,params:dict,timeout:float,session=None) -> dict:
    if not (5 <= timeout <= 240):
        raise ValueError('timeout [5,240]')
    client = session if session is not None else requests
    try:
        response = client.get(url,params=params,timeout=(15,timeout))
        response.raise_for_status()
        if len(response.content)>256*1024:
            raise ValueError('La respuesta GLiM excede el límite de seguridad de 256 KB')
        data = response.json()
    except (requests.RequestException,ValueError) as exc:
        raise RuntimeError(f'No se pudo consultar capa GLiM: {type(exc).__name__}: {exc}') from exc
    if not isinstance(data,dict):
        raise ValueError('Respuesta GLiM no es objeto JSON')
    if 'error' in data:
        err=data['error']
        raise RuntimeError(f'ArcGIS GLiM devolvió error: {err.get("code", "?") if isinstance(err,dict) else err}')
    return data


def classify_response(obj:dict) -> dict:
    if obj.get('exceededTransferLimit') is True:
        return {'status':'ambiguous', 'lithology':None,'polygon_matches':None}
    features=obj.get('features')
    if not isinstance(features,list) or len(features)>10:
        raise ValueError('La respuesta no contiene una lista válida de polígonos')
    classes=[]
    for feat in features:
        attrs=feat.get('attributes') if isinstance(feat,dict) else None
        if not isinstance(attrs,dict) or 'xx_Description' not in attrs:
            raise ValueError('Faltan atributos litológicos esperados en GLiM')
        name=attrs['xx_Description']
        if not isinstance(name,str):
            raise ValueError('Clase GLiM no es texto')
        classes.append(name)
    if not classes:
        return {'status':'unmapped','lithology':None,'polygon_matches':0}
    distinct=set(classes)
    if len(distinct)>1:
        return {'status':'ambiguous','lithology':None,'polygon_matches':len(features)}
    name=classes[0]
    if name not in ALLOWED or name in FILL:
        return {'status':'unclassified','lithology':name,'polygon_matches':len(features)}
    return {'status':'classified','lithology':name,'polygon_matches':len(features)}


def _point_file(folder:Path,point:dict,plan_hash:str) -> Path:
    """Avoid collisions between independent plans over the same sites."""
    return folder / plan_hash[:16] / (point['point_id']+'.json')


def _read_cached(path:Path,point:dict,plan_hash:str) -> dict|None:
    if not path.exists():return None
    obj=json.loads(path.read_text(encoding='utf-8'))
    if (obj.get('schema_version')!=SCHEMA_POINT or obj.get('plan_sha256')!=plan_hash or
        obj.get('point_id')!=point['point_id'] or obj.get('lat')!=point['lat'] or
        obj.get('lon')!=point['lon'] or obj.get('region_id')!=point['region_id'] or
        obj.get('layer_url')!=LAYER_URL):
        raise ValueError(f'Caché geológico obsoleto: {path}')
    if obj.get('status') not in ('classified','unclassified','unmapped','ambiguous'):
        raise ValueError(f'Estado de caché geológico inválido: {path}')
    name = obj.get('lithology')
    if obj['status']=='classified' and name not in ALLOWED-FILL:
        raise ValueError(f'Clase en caché no reconocida: {path}')
    return obj



def _reuse_from_compatible_plan(folder: Path, point: dict, current_plan_hash: str) -> dict | None:
    """Reuse same-location, same-layer V1.1 observation without losing its provenance.

    Different sampling plans carry different SHA values. The original cache is
    never modified; the new cache is copied only when point identity AND precise
    coordinates match, which avoids reusing an old grid with changed spacing.
    """
    for path in sorted(folder.glob(f'*/{point["point_id"]}.json')):
        if path.parent.name == current_plan_hash[:16]:
            continue
        source = json.loads(path.read_text(encoding='utf-8'))
        if (source.get('schema_version') != SCHEMA_POINT
            or source.get('region_id') != point['region_id']
            or source.get('point_id') != point['point_id']
            or source.get('lat') != point['lat']
            or source.get('lon') != point['lon']
            or source.get('layer_url') != LAYER_URL
            or source.get('status') not in ('classified','unclassified','unmapped','ambiguous')):
            continue
        if source.get('status') == 'classified' and source.get('lithology') not in ALLOWED-FILL:
            continue
        copy = dict(source)
        copy['source_cached_plan_sha256'] = source.get('plan_sha256')
        copy['source_cache_file_sha256'] = sha256_file(path)
        copy['plan_sha256'] = current_plan_hash
        return copy
    return None


def fetch_points(plan:Path,dest:Path,limit:int=10,timeout:float=60.,
                 session=None) -> dict:
    obj=read_geology_plan(plan)
    plan_hash=sha256_file(plan)
    points=obj['points']
    if not (1<=limit<=100):
        raise ValueError('limit debe estar entre 1 y 100 puntos por ejecución')
    cached=0
    reused=0
    pending=[]
    for pt in points:
        newfile = _point_file(dest,pt,plan_hash)
        if _read_cached(newfile,pt,plan_hash):
            cached+=1
            continue
        compatible = _reuse_from_compatible_plan(dest, pt, plan_hash)
        if compatible is not None:
            atomic_json(newfile, compatible)
            # Confirm the newly attributed record satisfies strict cache checks.
            _read_cached(newfile, pt, plan_hash)
            cached+=1
            reused+=1
        else:
            pending.append(pt)
    successes=[]
    failures=[]
    for pt in pending[:limit]:
        params = {'f':'json','where':'1=1',
                  'geometry':f"{pt['lon']},{pt['lat']}",
                  'geometryType':'esriGeometryPoint','inSR':4326,
                  'spatialRel':'esriSpatialRelIntersects',
                  'outFields':'OBJECTID,xx_Description,xx,Litho,IDENTITY_',
                  'returnGeometry':'false','resultRecordCount':10}
        try:
            data = _request_json(LAYER_URL+'/query',params,timeout,session=session)
            result=classify_response(data)
            sha=hashlib.sha256(json.dumps(data,sort_keys=True,separators=(',',':')).encode('utf-8')).hexdigest()
            record={'schema_version':SCHEMA_POINT,'plan_sha256':plan_hash,
                    'region_id':pt['region_id'],'point_id':pt['point_id'],
                    'lat':pt['lat'],'lon':pt['lon'],'layer_url':LAYER_URL,
                    'data_sha256':sha,'retrieved_utc':datetime.now(timezone.utc).isoformat(),
                    **result}
            atomic_json(_point_file(dest,pt,plan_hash),record)
            successes.append({'point_id':pt['point_id'],'status':record['status'],
                              'lithology':record.get('lithology')})
        except (RuntimeError,ValueError,KeyError,TypeError,OSError) as exc:
            failures.append({'point_id':pt['point_id'],'error':str(exc)[:220]})
    return {'schema_version':'mars_analog_geology_fetch_v1.1',
            'status':'point_lithology_only_no_analog_rerank',
            'points_total':len(points),'cached_before':cached,'attempted':len(successes)+len(failures),
            'new_downloads':len(successes),'reused_from_compatible_plan':reused,'failures':failures,
            'total_cached':cached+len(successes),
            'pending':len(points)-cached-len(successes),
            'downloaded':successes,
            'note':'La clase litológica de cada punto NO representa proporciones de área ni confirma basalto.'}


def summarize(plan:Path,folder:Path,csv_path:Path,report:Path) -> dict:
    obj=read_geology_plan(plan)
    digest=sha256_file(plan)
    by_region={r['region_id']:[] for r in obj['regions']}
    for pt in obj['points']:
        rec=_read_cached(_point_file(folder,pt,digest),pt,digest)
        by_region[pt['region_id']].append(rec)
    rows=[]
    for region in obj['regions']:
        recs=by_region[region['region_id']]
        complete=[x for x in recs if x is not None]
        labeled=[x['lithology'] for x in complete if x['status']=='classified']
        counts=Counter(labeled)
        n=len(labeled)
        # Point-frequency summaries describe a deliberately selected sample ONLY.
        row={'region_id':region['region_id'],
             'topographic_rank':region['topographic_rank'],
             'center_lat':region['center_lat'],
             'center_lon_180':region['center_lon_180'],
             'sampled':len(recs),'retrieved':len(complete),
             'classified':n,'unmapped_or_unclassified':sum(x['status'] in ('unmapped','unclassified') for x in complete),
             'ambiguous':sum(x['status']=='ambiguous' for x in complete),
             'pending':len(recs)-len(complete),
             'basic_volcanic_sample_count':counts['Basic volcanic rocks'],
             'other_volcanic_sample_count':sum(counts[x] for x in VOLCANIC if x!='Basic volcanic rocks'),
             'basic_volcanic_sample_share_pct':round(100*counts['Basic volcanic rocks']/n,2) if n else '',
             'observed_lithology_classes':json.dumps(dict(sorted(counts.items())),ensure_ascii=False),
             'status':'all_queries_returned' if len(complete)==len(recs) else 'incomplete'}
        rows.append(row)
    fieldnames=list(rows[0])
    csv_path.parent.mkdir(parents=True,exist_ok=True)
    import os
    tmp=csv_path.with_suffix(csv_path.suffix+'.tmp')
    try:
        with tmp.open('w',encoding='utf-8',newline='') as f:
            w=csv.DictWriter(f,fieldnames=fieldnames)
            w.writeheader();w.writerows(rows)
        os.replace(tmp,csv_path)
    finally:
        tmp.unlink(missing_ok=True)
    all_records=[x for values in by_region.values() for x in values]
    retrieved=sum(x is not None for x in all_records)
    classified=sum(x is not None and x['status']=='classified' for x in all_records)
    report_obj={'schema_version':SCHEMA_REPORT,
                'status':'descriptive_point_lithology_only_no_mars_score',
                'source':LAYER_URL,'original_doi':ORIGINAL_DOI,
                'plan_sha256':digest,'selected_regions':len(rows),
                'selected_points':len(all_records),
                'retrieved_points':retrieved,'classified_points':classified,
                'pending_points':len(all_records)-retrieved,
                'regions_with_sampled_basic_volcanics':[
                    row['region_id'] for row in rows if row['basic_volcanic_sample_count']>0],
                'csv_file':str(csv_path),'csv_sha256':sha256_file(csv_path),
                'limitations':['No son porcentajes de superficie: muestras puntuales sesgadas por la grilla.',
                               'La categoría Basic volcanic rocks no demuestra basalto en el afloramiento exacto.',
                               'Generalización cartográfica e incertidumbre de límites de polígonos.',
                               'Fuente ArcGIS de terceros; citar Hartmann y Moosdorf (2012).',
                               'Elysium Planitia no es geológicamente homogénea; requiere referencia cartográfica USGS.',
                               'No se altera topography_ranking.csv.']}
    atomic_json(report,report_obj)
    return {'schema_version':SCHEMA_REPORT,'status':report_obj['status'],
            'selected_regions':len(rows),'selected_points':len(all_records),
            'retrieved_points':retrieved,'classified_points':classified,
            'pending_points':len(all_records)-retrieved,
            'regions_with_sampled_basic_volcanics':report_obj['regions_with_sampled_basic_volcanics'],
            'csv_file':str(csv_path),'report_file':str(report),
            'csv_sha256':sha256_file(csv_path)}
