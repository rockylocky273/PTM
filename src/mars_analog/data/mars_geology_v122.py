"""Mars V1.2.2 — USGS SIM 3292 derived geological point observations.

The ArcGIS layer is a public *republication* attributed to Tanaka et al. 2014,
not an official USGS API or mineralogical ground truth. Mars coordinates are
planetocentric/east-positive; the layer uses the custom 104971 spatial ref and
-180..180 longitudes. It is NEVER EPSG:4326.
"""
from __future__ import annotations

import csv
from collections import Counter
from datetime import datetime, timezone
import json
import math
from pathlib import Path
import re
import requests

from .download import atomic_json, sha256_file
from .mars_profiles_v12 import _load_profiles, SCHEMA, LOOKUP

SOURCE = ('https://services.arcgis.com/nzS0F0zdNLvs7nc8/ArcGIS/rest/'
          'services/Mars_Geology_feature_layer/FeatureServer/0')
MAP_DOI = 'https://doi.org/10.3133/sim3292'
CRS = 104971
MARS_RADIUS_KM = 3396.19
PLAN_SCHEMA = 'mars_geology_point_plan_v1.2.2'
POINT_SCHEMA = 'mars_geology_point_observation_v1.2.2'
SUMMARY_SCHEMA = 'mars_geology_point_summary_v1.2.2'
MAX_BODY = 512 * 1024


def _source_json(url, params, timeout=45, session=None):
    if not (5 <= timeout <= 240):
        raise ValueError('timeout debe estar entre 5 y 240 segundos')
    if not url.startswith(SOURCE):
        raise ValueError('URL fuera del servicio geológico autorizado')
    client = session if session is not None else requests
    try:
        response = client.get(url, params=params, timeout=(15, timeout))
        response.raise_for_status()
        if len(response.content) > MAX_BODY:
            raise ValueError('Respuesta ArcGIS superior al límite de 512 KiB')
        value = response.json()
    except requests.RequestException as exc:
        raise RuntimeError(f'Servicio geológico Mars no disponible ({type(exc).__name__}); revisá conexión y estado HTTP') from exc
    if not isinstance(value, dict):
        raise ValueError('ArcGIS no devolvió un objeto JSON')
    if 'error' in value:
        err = value['error']
        code = err.get('code', '?') if isinstance(err, dict) else '?'
        msg = err.get('message', '') if isinstance(err, dict) else str(err)
        raise RuntimeError(f'ArcGIS Mars error {code}: {str(msg)[:180]}')
    return value


def validate_metadata(meta):
    fields = {f.get('name') for f in meta.get('fields', []) if isinstance(f, dict)}
    if not {'OBJECTID', 'Unit', 'UnitDesc'}.issubset(fields):
        raise ValueError('La capa no expone los campos esperados OBJECTID,Unit,UnitDesc')
    if meta.get('geometryType') != 'esriGeometryPolygon':
        raise ValueError('La capa no es de polígonos')
    spatial = meta.get('extent', {}).get('spatialReference') or meta.get('spatialReference') or {}
    if CRS not in (spatial.get('wkid'), spatial.get('latestWkid')):
        raise ValueError('Referencia espacial distinta de Mars 104971; no consultar coordenadas')
    if meta.get('name') != 'Geology':
        raise ValueError('Capa inesperada; no se realizará una clasificación errónea')
    return True


def source_metadata(timeout=45, session=None):
    meta = _source_json(SOURCE, {'f': 'json'}, timeout, session)
    validate_metadata(meta)
    return {'status': 'metadata_verified_no_queries', 'layer': SOURCE,
            'fields': ['OBJECTID', 'Unit', 'UnitDesc'], 'mars_custom_crs': CRS,
            'geological_map_reference': MAP_DOI,
            'provenance': 'ArcGIS third-party hosted layer citing USGS SIM 3292 (2014)',
            'warning': 'Geo-códigos y descripciones no equivalen a mineralogía medida'}


def east_to_signed(lon):
    x = float(lon)
    if not math.isfinite(x) or not 0 <= x < 360:
        raise ValueError('Longitud marciana requiere Este en [0,360)')
    out = (x + 180.0) % 360.0 - 180.0
    return round(out, 8)


def _offset_point(lat, east_lon, north_km, east_km):
    lat_out = lat + north_km / (MARS_RADIUS_KM * math.pi / 180)
    if not (-80 <= lat_out <= 80):
        raise ValueError('Muestreo fuera del rango latitudinal seguro de este servicio')
    lon_out = (east_lon + east_km /
               (MARS_RADIUS_KM * math.pi / 180 * math.cos(math.radians(lat)))) % 360
    return round(lat_out, 8), round(lon_out, 8), east_to_signed(lon_out)


def plan_geology(manifest, output, per_target=9, radius_km=100):
    man, profiles = _load_profiles(Path(manifest))  # enforces V1.2 hashes
    if per_target not in (1, 5, 9) or not (10 <= radius_km <= 120):
        raise ValueError('points-per-profile admite 1,5,9; radio entre 10 y 120 km')
    offsets = [(0.,0.)]
    if per_target >= 5:
        offsets += [(radius_km,0),(-radius_km,0),(0,radius_km),(0,-radius_km)]
    if per_target == 9:
        offsets += [(radius_km,radius_km),(radius_km,-radius_km),
                    (-radius_km,radius_km),(-radius_km,-radius_km)]
    if radius_km > man['window_km']/2 + 0.0001:
        raise ValueError('Los puntos no deben superar la semiventana topográfica')
    points = []
    for p in profiles:
        name = p['profile_name']; lat = float(p['center_lat'])
        lon = float(p['center_lon_east_0_360'])
        if not -80 <= lat <= 80 or name not in LOOKUP:
            raise ValueError('Centro marciano fuera de la fuente aprobada')
        for n,(north,east) in enumerate(offsets):
            a,b,c = _offset_point(lat,lon,north,east)
            points.append({'point_id': f'{name}_p{n:02d}', 'profile_id': name,
                           'lat_planetocentric':a,'lon_east_0_360':b,
                           'lon_signed_for_arcgis':c,
                           'north_offset_km':north,'east_offset_km':east})
    output = Path(output)
    obj = {'schema_version':PLAN_SCHEMA,'status':'plan_only_no_geology_assertions',
           'source_manifest_sha256':sha256_file(Path(manifest)),
           'profile_ids':[p['profile_name'] for p in profiles],
           'sampling_half_width_km':man['window_km']/2,
           'offset_radius_km':radius_km,'points_per_profile':per_target,
           'sample_count':len(points),'layer':SOURCE,'mars_crs':CRS,
           'usgs_map':MAP_DOI,'points':points,
           'notes':['Muestras puntuales, NO porcentajes de área',
                    'La capa es una republicación que cita SIM 3292',
                    'Las coordenadas de ArcGIS son -180..180 bajo CRS 104971, NO WGS84']}
    atomic_json(output,obj)
    return {'status':obj['status'],'profiles':len(profiles),'samples':len(points),
            'file':str(output),'sha256':sha256_file(output),'layer':SOURCE}


def _read_plan(file):
    data = json.loads(Path(file).read_text(encoding='utf-8'))
    if data.get('schema_version') != PLAN_SCHEMA or data.get('layer') != SOURCE or data.get('mars_crs') != CRS:
        raise ValueError('Plan de geología marciana inválido')
    pts = data.get('points')
    if not isinstance(pts, list) or len(pts) != data.get('sample_count') or not pts or len(pts)>500:
        raise ValueError('Plan de puntos ausente o demasiado grande')
    ids = [p['point_id'] for p in pts]
    if len(ids) != len(set(ids)):
        raise ValueError('Puntos duplicados')
    for p in pts:
        if p['profile_id'] not in data['profile_ids'] or not -90<=float(p['lat_planetocentric'])<=90:
            raise ValueError('Coordenadas o perfil inválidos')
        if east_to_signed(p['lon_east_0_360']) != p['lon_signed_for_arcgis']:
            raise ValueError('Longitud 0..360 incongruente con -180..180')
    return data


def _classify(features):
    if not isinstance(features,list) or len(features)>20:
        raise ValueError('ArcGIS devolvió geometrías inesperadas')
    items=[]
    for f in features:
        a=f.get('attributes') if isinstance(f,dict) else None
        if not isinstance(a,dict) or not all(k in a for k in ('OBJECTID','Unit','UnitDesc')):
            raise ValueError('Respuesta sin atributos geológicos requeridos')
        code, desc = a['Unit'], a['UnitDesc']
        if not isinstance(code,str) or not code.strip() or not (desc is None or isinstance(desc,str)):
            raise ValueError('Código/descripcion de unidad inesperado')
        items.append({'feature_objectid':a['OBJECTID'], 'unit_code':code,
                      'unit_description':desc})
    if not items:
        return 'no_map_coverage', None, None, 0
    if len(items)>1:
        return 'ambiguous_multiple_polygons',None,None,len(items)
    return 'mapped_unit',items[0]['unit_code'],items[0]['unit_description'],1


def _cache_file(folder, point):
    return Path(folder)/(point['point_id']+'.json')


def _validated_cached(path, point, plan_sha):
    if not path.exists():
        return None
    d=json.loads(path.read_text(encoding='utf-8'))
    if (d.get('schema_version') != POINT_SCHEMA or d.get('plan_sha256') != plan_sha or
        d.get('point') != point or d.get('source') != SOURCE or
        d.get('query_crs') != CRS or d.get('status') not in
        ('mapped_unit','no_map_coverage','ambiguous_multiple_polygons')):
        raise ValueError('Caché geológico incompatible: '+str(path))
    return d


def fetch_geology(plan, directory, limit=10, timeout=45, verify_service=True, session=None):
    if not (1 <= limit <= 500):
        raise ValueError('--limit entre 1 y 500')
    plan=Path(plan); src=_read_plan(plan); plan_sha=sha256_file(plan)
    directory=Path(directory)
    cache_count=0;pending=[]
    for p in src['points']:
        if _validated_cached(_cache_file(directory,p),p,plan_sha) is not None:
            cache_count+=1
        else:
            pending.append(p)
    if verify_service and pending:
        source_metadata(timeout,session=session)
    output=[];failures=[]
    for p in pending[:limit]:
        geom={'x':p['lon_signed_for_arcgis'],'y':p['lat_planetocentric'],
              'spatialReference':{'wkid':CRS}}
        params={'f':'json','where':'1=1','geometry':json.dumps(geom,separators=(',',':')),
                'geometryType':'esriGeometryPoint','inSR':str(CRS),
                'spatialRel':'esriSpatialRelIntersects',
                'outFields':'OBJECTID,Unit,UnitDesc','returnGeometry':'false',
                'resultRecordCount':'10'}
        try:
            response=_source_json(SOURCE+'/query',params,timeout,session)
            if response.get('exceededTransferLimit'):
                raise ValueError('Exceso de polígonos; punto ambiguo')
            status,code,description,matches=_classify(response.get('features'))
            saved={'schema_version':POINT_SCHEMA,'point':p,'plan_sha256':plan_sha,
                   'source':SOURCE,'usgs_map':MAP_DOI,'query_crs':CRS,
                   'status':status,'unit_code':code,'unit_description':description,
                   'polygon_matches':matches,
                   'retrieved_utc':datetime.now(timezone.utc).isoformat()}
            path=_cache_file(directory,p)
            atomic_json(path,saved)
            output.append({'point_id':p['point_id'],'status':status,'unit_code':code,
                           'unit_description':description})
        except (RuntimeError,ValueError,requests.RequestException) as exc:
            failures.append({'point_id':p['point_id'],'error':str(exc)[:200]})
    after=cache_count+len(output)
    return {'schema_version':POINT_SCHEMA,'status':'partial_or_complete_sampling_no_geological_rank',
            'selected':len(src['points']),'cached_before':cache_count,
            'attempted':len(output)+len(failures),'new_queries':len(output),
            'cached_after':after,'pending':len(src['points'])-after,
            'failures':failures,'queried':output,'source':SOURCE}


def _process_keyword(description):
    """Only a textual keyword hint, never a claim of basalt, mineralogy or processes."""
    if not description: return 'unspecified'
    d=description.lower()
    if re.search(r'volcani|lava',d): return 'volcanic_keyword_in_source_description'
    if re.search(r'fluvial|channel|alluvial|delta|fan',d): return 'transport_keyword_in_source_description'
    if re.search(r'crater|impact',d): return 'impact_keyword_in_source_description'
    if re.search(r'sediment|deposit|eolian|aeolian',d): return 'sediment_keyword_in_source_description'
    return 'not_inferred'


def summarize_geology(plan, directory, csv_path, report_path):
    plan=Path(plan); source=_read_plan(plan); hash_plan=sha256_file(plan)
    rows=[];samples=[]
    for profile_id in source['profile_ids']:
        ids=[p for p in source['points'] if p['profile_id']==profile_id]
        mapped=[];pending=0;no_coverage=0;ambiguous=0
        for p in ids:
            cached=_validated_cached(_cache_file(directory,p),p,hash_plan)
            if cached is None:
                pending+=1;continue
            samples.append({'point_id':p['point_id'],'profile_id':profile_id,
                            'lat':p['lat_planetocentric'],'lon_east':p['lon_east_0_360'],
                            'lon_arcgis':p['lon_signed_for_arcgis'],
                            'status':cached['status'],'unit_code':cached['unit_code'],
                            'unit_description':cached['unit_description'],
                            'process_hint':_process_keyword(cached['unit_description'])})
            if cached['status']=='mapped_unit':mapped.append(cached)
            elif cached['status']=='no_map_coverage':no_coverage+=1
            else:ambiguous+=1
        counts=Counter(x['unit_code'] for x in mapped)
        desc={x['unit_code']:x['unit_description'] for x in mapped}
        rows.append({'profile_id':profile_id,'sampled':len(ids),'mapped':len(mapped),
                     'no_map_coverage':no_coverage,'ambiguous':ambiguous,'pending':pending,
                     'unit_code_counts':json.dumps(dict(sorted(counts.items())),ensure_ascii=False),
                     'descriptions':json.dumps(desc,ensure_ascii=False,sort_keys=True),
                     'status':'complete' if not pending else 'partial'})
    csv_path=Path(csv_path);csv_path.parent.mkdir(parents=True,exist_ok=True)
    with csv_path.open('w',encoding='utf-8',newline='') as f:
        w=csv.DictWriter(f,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)
    report={'schema_version':SUMMARY_SCHEMA,
            'status':'cartographic_point_observations_no_area_fraction_or_mineralogy',
            'source':SOURCE,'usgs_sim3292_doi':MAP_DOI,
            'plan_sha256':hash_plan,'selected_profiles':len(rows),
            'selected_points':len(source['points']),
            'mapped_points':sum(r['mapped'] for r in rows),
            'pending_points':sum(r['pending'] for r in rows),
            'no_coverage_points':sum(r['no_map_coverage'] for r in rows),
            'ambiguous_points':sum(r['ambiguous'] for r in rows),
            'profiles':rows,'observations':samples,
            'csv_file':str(csv_path),'csv_sha256':sha256_file(csv_path),
            'limitations':['La capa alojada en ArcGIS cita a Tanaka 2014; no es una API oficial USGS',
                           'Nueve puntos no miden proporciones espaciales ni unidades internas de cráteres',
                           'UnitDesc se conserva literal y el campo process_hint sólo refleja palabras del texto',
                           'No se afirma basalto, antigüedad radiométrica ni similitud geológica planetaria']}
    atomic_json(Path(report_path),report)
    return {k:v for k,v in report.items() if k not in ('observations',)} | {'report_file':str(report_path),'report_sha256':sha256_file(Path(report_path))}
