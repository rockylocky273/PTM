"""Mars Analog Engine V1.2: perfiles marcianos y rankings separados por perfil.

Solo distancias topográficas: la nomenclatura USGS NO es una unidad geológica.
"""
from __future__ import annotations
import csv
import json
import math
from pathlib import Path
from datetime import datetime, timezone

import xarray as xr
from .analog_screen import (GlobalSampler, patch_features, distance_metrics,
                            diverse_top, FEATURES, OFFSET, WEIGHTS)
from .download import sha256_file, atomic_json

SCHEMA='mars_analog_multi_profiles_v1.2'
PROFILE_SCHEMA='mars_analog_profile_v0.7'
PROFILE_STATUS='topographic_profile_only_not_geologically_validated'
USGS_MAP='https://doi.org/10.3133/sim3292'

# Coordenadas USGS / IAU planetocéntricas, longitudes positivas Este 0..360.
# Para cráteres se estudia una ventana REGIONAL de 240 km, NO solo el cráter.
TARGETS=(
    ('elysium_planitia','Elysium Planitia',1.98,155.0,'https://planetarynames.wr.usgs.gov/Feature/1784','Planicie: centro del piloto V0.7; no equivale a una unidad volcánica','https://doi.org/10.3133/i2147'),
    ('jezero_entorno','Jezero (entorno regional)',18.41,77.69,'https://planetarynames.wr.usgs.gov/Feature/Jezero','Cráter ~47,5 km; ventana de 240 km incluye alrededores',USGS_MAP),
    ('gale_entorno','Gale (entorno regional)',-5.44,137.70,'https://planetarynames.wr.usgs.gov/Feature/Gale','Cráter ~155 km; ventana de 240 km incluye alrededores',USGS_MAP),
    ('olympus_mons','Olympus Mons',18.40,226.0,'https://planetarynames.wr.usgs.gov/Feature/4453','Ventana de 240 km no representa el volcán completo de >600 km',USGS_MAP),
    ('meridiani_planum','Meridiani Planum',0.20,357.50,'https://planetarynames.wr.usgs.gov/Feature/3854','Centro nominal de planicie; geología local sin validar',USGS_MAP),
    ('syrtis_major_planum','Syrtis Major Planum',8.40,69.50,'https://planetarynames.wr.usgs.gov/Feature/5796','Centro nominal; cartografía de unidades geológicas aún no superpuesta',USGS_MAP),
)
LOOKUP={t[0]:t for t in TARGETS}


def targets_catalog():
    return {'schema_version':SCHEMA,'status':'usgs_nomenclature_centers_only',
            'coordinate_system':'planetocentric latitude, positive East 0..360',
            'targets':[{'id':t[0],'name':t[1],'lat':t[2],'lon_east_0_360':t[3],
                        'gazetteer':t[4],'scope_warning':t[5],
                        'geology_reference':t[6]} for t in TARGETS],
            'note':'Las coordenadas de topónimos no constituyen identificación litológica.'}


def _select(spec):
    ids=[x.strip() for x in spec.split(',')] if spec.lower()!='all' else list(LOOKUP)
    if not ids or len(set(ids))!=len(ids) or any(x not in LOOKUP for x in ids):
        raise ValueError('IDs marcianos no válidos o duplicados; ejecutar mars-targets')
    return [LOOKUP[x] for x in ids]


def _sampling(spacing,samples):
    if not(math.isfinite(spacing) and 0<spacing<=100 and 5<=samples<=31 and samples%2):
        raise ValueError('spacing-km (0,100], samples impar [5,31]')


def build_profiles(mars:Path, ids='all',spacing=30.,samples=9,
                   output_dir=Path('data/profiles/v1_2'),
                   manifest=Path('data/catalog/mars_profiles_v1_2.json')):
    _sampling(spacing,samples)
    selected=_select(ids); mars=Path(mars)
    with xr.open_dataset(mars) as ds:
        sampler=GlobalSampler(ds,'Mars')
        patches=[sampler.sample(t[2],t[3],spacing,samples) for t in selected]
    source_hash=sha256_file(mars)
    records=[]
    footprint_features=[]
    for t,patch in zip(selected,patches):
        feat=patch_features(patch,spacing)
        if feat is None or feat['sample_coverage']<.9:
            raise ValueError('Perfil insuficiente: '+t[0])
        profile={'schema_version':PROFILE_SCHEMA,'status':PROFILE_STATUS,
                 'profile_name':t[0],'planet':'Mars','center_lat':t[2],
                 'center_lon_east_0_360':t[3], 'spacing_km':float(spacing),
                 'samples_per_axis':samples,'window_extent_center_to_center_km':(samples-1)*spacing,
                 'features':feat,'mars_file_sha256':source_hash,
                 'reference_source':'MOLA MEGDR topography, 4 pixels/degree, PDS',
                 'usgs_nomenclature_url':t[4], 'usgs_geology_reference_url':t[6],
                 'geology_verification':'not_performed',
                 'interpretation_warning':t[5],
                 'limitations':['Solo topografía, NO litología ni composición mineralógica',
                                'Muestreo métrico nominal, no iguala resolución instrumental',
                                'No permite clasificar terrenos aptos para rovers o hábitats']}
        path=Path(output_dir)/(t[0]+'.json')
        atomic_json(path,profile)
        records.append({'id':t[0],'name':t[1], 'profile_file':str(path),
                        'sha256':sha256_file(path),'usgs_url':t[4]})
        # El perímetro representa las posiciones EXTREMAS de muestreo.
        # Es un rectángulo métrico local, NO un límite oficial geológico.
        half=(samples//2)*spacing
        deg_lat=half/(3396.0*math.pi/180.)
        deg_lon=deg_lat/math.cos(math.radians(t[2]))
        south,north=t[2]-deg_lat,t[2]+deg_lat
        west,east=t[3]-deg_lon,t[3]+deg_lon
        boundary=[[west,south],[east,south],[east,north],[west,north],[west,south]]
        footprint_features.append({'type':'Feature','properties':{
            'profile_id':t[0],'name':t[1],'planet':'Mars',
            'geometry_semantics':'approximate_sampling_window_not_geological_unit',
            'spacing_km':spacing,'samples_per_axis':samples,
            'usgs_nomenclature_url':t[4]},
            'geometry':{'type':'Polygon','coordinates':[boundary]}})
    footprints_path=Path(output_dir)/'mars_sampling_footprints.geojson'
    atomic_json(footprints_path,{'type':'FeatureCollection','features':footprint_features,
              'coordinate_system':'Mars planetocentric, east-positive 0..360',
              'warning':'These rectangles are approximate sample extents, NOT geology or IAU feature boundaries'})
    obj={'schema_version':SCHEMA,'status':'multi_profiles_built_topography_only',
         'source_mola_sha256':source_hash,'source_mola_file':str(mars),
         'spacing_km':float(spacing),'samples':samples,
         'window_km':(samples-1)*spacing, 'profiles':records,
         'sampling_footprints_geojson':str(footprints_path),
         'sampling_footprints_sha256':sha256_file(footprints_path),
         'sources':{'nomenclature':'https://planetarynames.wr.usgs.gov/',
                    'global_mars_geology':USGS_MAP,
                    'mola':'https://pds-geosciences.wustl.edu/missions/mgs/megdr.html'},
         'notes':['No se asignaron unidades geológicas de Marte',
                  'Ventanas con centros de cráter incluyen sus alrededores']}
    atomic_json(Path(manifest),obj)
    return {**obj,'manifest_file':str(manifest),'manifest_sha256':sha256_file(Path(manifest))}


def _load_profiles(path):
    path=Path(path)
    obj=json.loads(path.read_text(encoding='utf-8'))
    if obj.get('schema_version')!=SCHEMA or obj.get('status')!='multi_profiles_built_topography_only':
        raise ValueError('Manifest de V1.2 no válido')
    _sampling(float(obj['spacing_km']),int(obj['samples']))
    footprint_path=Path(obj['sampling_footprints_geojson'])
    if sha256_file(footprint_path)!=obj['sampling_footprints_sha256']:
        raise ValueError('SHA256 de polígonos de muestreo no coincide')
    if not math.isclose(obj['window_km'],(obj['samples']-1)*obj['spacing_km']):
        raise ValueError('Escala de ventana inconsistente')
    rows=obj['profiles']
    if not rows or len({r['id'] for r in rows})!=len(rows):
        raise ValueError('Perfiles ausentes o duplicados')
    loaded=[]
    for item in rows:
        file=Path(item['profile_file'])
        if sha256_file(file)!=item['sha256']:
            raise ValueError('SHA256 del perfil no coincide: '+item['id'])
        profile=json.loads(file.read_text(encoding='utf-8'))
        if (profile.get('schema_version')!=PROFILE_SCHEMA or
            profile.get('status')!=PROFILE_STATUS or profile.get('planet')!='Mars' or
            profile.get('profile_name')!=item['id'] or
            profile.get('mars_file_sha256')!=obj['source_mola_sha256'] or
            profile.get('geology_verification')!='not_performed' or
            profile['samples_per_axis']!=obj['samples'] or
            not math.isclose(profile['spacing_km'],obj['spacing_km']) or
            not all(k in profile['features'] for k in FEATURES)):
            raise ValueError('Perfil inconsistente: '+item['id'])
        loaded.append(profile)
    return obj,loaded


def _regions(path):
    with Path(path).open(newline='',encoding='utf-8') as f:
        rows=list(csv.DictReader(f))
    if len(rows)!=16200 or len({r['region_id'] for r in rows})!=len(rows):
        raise ValueError('Se requiere catálogo mundial V0.6 de 16200 regiones únicas')
    return [r for r in rows if r['status']=='land_candidate_unranked']


CSV_COLUMNS=['rank','region_id','center_lat','center_lon_180','mapped_land_fraction',
             'sample_coverage','sample_count',*FEATURES,'distance_total',
             'distance_slope','distance_roughness','distance_relief']


def screen_profiles(manifest:Path,earth:Path,catalog:Path,output_dir:Path,
                    report:Path,top=25,min_separation=250.,max_lat=65.,min_coverage=.95):
    if not(1<=top<=500 and 0<=min_separation<=5000 and 0<max_lat<=65 and .9<=min_coverage<=1):
        raise ValueError('Parámetros de screening fuera de rango')
    m,profiles=_load_profiles(manifest)
    regions=_regions(catalog)
    results={p['profile_name']:[] for p in profiles}
    excluded_lat=excluded_cover=0
    with xr.open_dataset(earth) as ds:
        sampler=GlobalSampler(ds,'Earth')
        for region in regions:
            lat=float(region['center_lat']);lon=float(region['center_lon_180'])
            if abs(lat)>max_lat:
                excluded_lat+=1;continue
            patch=sampler.sample(lat,lon,m['spacing_km'],m['samples'])
            features=patch_features(patch,m['spacing_km'])
            if features is None or features['sample_coverage']<min_coverage:
                excluded_cover+=1;continue
            shared={'region_id':region['region_id'],'center_lat':lat,
                    'center_lon_180':lon,
                    'mapped_land_fraction':float(region['land_fraction_area_approx']),
                    **features}
            for p in profiles:
                results[p['profile_name']].append({**shared,**distance_metrics(features,p['features'])})
    if not results or not next(iter(results.values())):
        raise ValueError('No hay candidatos evaluables')
    output_dir=Path(output_dir);output_dir.mkdir(parents=True,exist_ok=True)
    records=[]
    for p in profiles:
        name=p['profile_name']
        rows=sorted(results[name],key=lambda x:(x['distance_total'],x['region_id']))
        selected=diverse_top(rows,top,min_separation)
        positions={r['region_id']:i for i,r in enumerate(rows,1)}
        dest=output_dir/f'{name}_ranking.csv'
        with dest.open('w',newline='',encoding='utf-8') as f:
            writer=csv.DictWriter(f,fieldnames=CSV_COLUMNS);writer.writeheader()
            writer.writerows({'rank':i,**r} for i,r in enumerate(rows,1))
        records.append({'id':name,'ranking_csv':str(dest),
                        'ranking_sha256':sha256_file(dest),'ranked_count':len(rows),
                        'profile_sha256':next(r['sha256'] for r in m['profiles'] if r['id']==name),
                        'top_diverse':[{'rank_in_all':positions[r['region_id']],**r} for r in selected]})
    output={'schema_version':SCHEMA,'status':'separate_topographic_rankings_not_mars_analog_confirmation',
            'profiles':records,'manifest_sha256':sha256_file(Path(manifest)),
            'earth_surface_sha256':sha256_file(Path(earth)),
            'earth_catalog_sha256':sha256_file(Path(catalog)),
            'counts':{'land_candidates':len(regions),'excluded_latitude':excluded_lat,
                      'excluded_coverage_or_derivatives':excluded_cover,
                      'ranked_per_profile':len(next(iter(results.values())))},
            'settings':{'spacing_km':m['spacing_km'],'samples':m['samples'],
                        'max_abs_lat':max_lat,'min_patch_coverage':min_coverage,
                        'min_geographic_separation_km':min_separation,
                        'weights':WEIGHTS,'regularizers':OFFSET},
            'limitations':['No equivale a geología ni a propiedades ambientales comparables',
                           'No se puede interpretar la distancia como probabilidad o porcentaje',
                           'El píxel ETOPO es más grueso que el MOLA global utilizado',
                           'Los cráteres se comparan con sus alrededores, no su interior aislado',
                           'Selección mundial filtra costas, océanos y latitudes extremas',
                           'Sin validación externa ni seguridad de rovers/hábitats'],
            'created_at_utc':datetime.now(timezone.utc).isoformat()}
    atomic_json(Path(report),output)
    return {**output,'report_file':str(report),'report_sha256':sha256_file(Path(report))}


def compare_profiles(screen_report:Path,out_csv:Path,out_report:Path,
                     watch='r026_c146,r068_c061',top_n=25):
    if not 1<=top_n<=100:
        raise ValueError('top-n fuera de rango 1..100')
    src=Path(screen_report)
    report=json.loads(src.read_text(encoding='utf-8'))
    if report.get('schema_version')!=SCHEMA or report.get('status')!='separate_topographic_rankings_not_mars_analog_confirmation':
        raise ValueError('Reporte multirregión no válido')
    ids=[v.strip() for v in watch.split(',') if v.strip()]
    if not ids or len(set(ids))!=len(ids):
        raise ValueError('IDs terrestres duplicados o vacíos')
    by_profile={}; observations=[]
    for p in report['profiles']:
        path=Path(p['ranking_csv'])
        if sha256_file(path)!=p['ranking_sha256']:
            raise ValueError('Ranking alterado: '+p['id'])
        with path.open(newline='',encoding='utf-8') as f:
            records=list(csv.DictReader(f))
        if len(records)!=p['ranked_count'] or len(records)<top_n:
            raise ValueError('Ranking incompleto: '+p['id'])
        if len({r['region_id'] for r in records})!=len(records):
            raise ValueError('IDs terrestres duplicados')
        by_profile[p['id']]=set(r['region_id'] for r in records[:top_n])
        lookup={r['region_id']:r for r in records}
        for key in ids:
            item=lookup.get(key)
            observations.append({'mars_profile':p['id'],'earth_region_id':key,
                                 'rank':item['rank'] if item else '',
                                 'distance_total':item['distance_total'] if item else '',
                                 'status':'ranked' if item else 'excluded'})
    out_csv=Path(out_csv);out_csv.parent.mkdir(parents=True,exist_ok=True)
    with out_csv.open('w',newline='',encoding='utf-8') as f:
        writer=csv.DictWriter(f,fieldnames=['mars_profile','earth_region_id','rank',
                                            'distance_total','status'])
        writer.writeheader();writer.writerows(observations)
    names=list(by_profile)
    pairwise=[]
    for i,a in enumerate(names):
        for b in names[i+1:]:
            shared=len(by_profile[a]&by_profile[b])
            pairwise.append({'profile_a':a,'profile_b':b,'shared_top_n':shared,
                             'top_n':top_n,'jaccard':round(shared/(2*top_n-shared),6)})
    result={'schema_version':SCHEMA,'status':'profile_rank_comparison_no_joint_score',
            'source_report_sha256':sha256_file(src),'watch_csv':str(out_csv),
            'watch_csv_sha256':sha256_file(out_csv),'watched_regions':ids,
            'pairwise_top_n_overlap':pairwise,
            'limitations':['Solamente rankings topográficos independientes',
                           'No hay puntuación conjunta ni interpretación mineralógica']}
    atomic_json(Path(out_report),result)
    return {**result,'report_file':str(out_report)}
