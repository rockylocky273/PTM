"""V1.0: auditable environmental comparison without creating a Mars similarity score."""
from __future__ import annotations
import csv
import json
import math
from collections import Counter, defaultdict
from pathlib import Path
from .download import sha256_file, atomic_json
from .environment_global import read_plan


def _load(path:Path,key:str='region_id') -> dict:
    with Path(path).open(encoding='utf-8',newline='') as f: rows=list(csv.DictReader(f))
    if not rows:raise ValueError(f'CSV vacío: {path}')
    d={}
    for row in rows:
        ident=row.get(key)
        if not ident or ident in d: raise ValueError(f'Identificador faltante/duplicado: {ident}')
        d[ident]=row
    return d


def _num(row:dict,key:str):
    try:
        v=float(row.get(key,''))
        return v if math.isfinite(v) else None
    except (TypeError,ValueError):return None


def produce_diagnostic(plan_path:Path, climate_csv:Path, landcover_csv:Path,
                       output_csv:Path, report:Path) -> dict:
    plan=read_plan(plan_path)
    climate=_load(climate_csv)
    cover=_load(landcover_csv) if landcover_csv.exists() else {}
    planned={r['region_id'] for r in plan['candidates']}
    if not planned.issubset(climate):
        raise ValueError('CSV climático no contiene todos los candidatos del plan')
    if cover and len(cover)<len(planned.intersection(cover)):
        raise ValueError('Datos de cobertura incompletos')
    rows=[]
    for site in plan['candidates']:
        ident=site['region_id']; c=climate[ident];v=cover.get(ident,{})
        if int(c.get('topographic_rank',-1))!=site['topographic_rank']:
            raise ValueError('Climate CSV y plan tienen rankings diferentes')
        if v and int(v.get('topographic_rank',-1))!=site['topographic_rank']:
            raise ValueError('Landcover CSV y plan tienen rankings diferentes')
        precip=_num(c,'precip_annual_mean_mm') if c.get('status')=='complete' else None
        humid=_num(c,'relative_humidity_mean_pct') if c.get('status')=='complete' else None
        barren=_num(v,'class16_bare_sparsely_vegetated_pct')
        urban=_num(v,'urban_majority_pct')
        # Illustrative *Earth* climate grouping, not a planetary similarity score.
        aridity='not_evaluable' if precip is None else ('very_low_precipitation' if precip<100 else
               'low_precipitation' if precip<250 else 'intermediate_or_wet')
        rows.append({'region_id':ident,'topographic_rank':site['topographic_rank'],
                     'selection':site['selection'],'rank_quintile':site['rank_quintile'],
                     'center_lat':site['center_lat'],'center_lon_180':site['center_lon_180'],
                     'climate_status':c.get('status'),'air_temp_mean_c':c.get('air_temp_mean_c'),
                     'precip_annual_mean_mm':c.get('precip_annual_mean_mm'),
                     'relative_humidity_mean_pct':c.get('relative_humidity_mean_pct'),
                     'seasonal_air_temp_range_c':c.get('seasonal_air_temp_range_c'),
                     'precipitation_context':aridity,
                     'landcover_status':'available' if v else 'not_loaded',
                     'class16_bare_sparsely_vegetated_pct':barren,
                     'urban_majority_pct':urban,
                     'flag_low_precip_and_low_humidity': bool(precip<250 and humid<50) if precip is not None and humid is not None else None})
    output_csv=Path(output_csv);output_csv.parent.mkdir(parents=True,exist_ok=True)
    tmp=output_csv.with_name(output_csv.name+'.tmp')
    try:
        with tmp.open('w',encoding='utf-8',newline='') as f:
            w=csv.DictWriter(f,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)
        tmp.replace(output_csv)
    finally:tmp.unlink(missing_ok=True)
    counts=Counter(row['precipitation_context'] for row in rows)
    by_q=defaultdict(lambda:{'n':0,'climate_complete':0,'low_precip_and_low_humidity':0})
    for r in rows:
        s=by_q[str(r['rank_quintile'])];s['n']+=1
        s['climate_complete']+=r['climate_status']=='complete'
        s['low_precip_and_low_humidity']+=r['flag_low_precip_and_low_humidity'] is True
    obj={'schema_version':'mars_analog_environment_diagnostic_v1.0',
         'status':'contextual_analysis_no_martian_analog_score',
         'sample_size':len(rows),'climate_complete':sum(r['climate_status']=='complete' for r in rows),
         'landcover_available':sum(r['landcover_status']=='available' for r in rows),
         'precipitation_context_counts':dict(counts),'rank_quintile_counts':dict(by_q),
         'illustrative_cutoffs':{'very_low_precipitation_mm_year':'<100',
                                'low_precipitation_mm_year':'<250',
                                'low_relative_humidity_pct':'<50'},
         'source_sha256':{'plan':sha256_file(plan_path),'climate_csv':sha256_file(climate_csv),
                          'landcover_csv':sha256_file(landcover_csv) if landcover_csv.exists() else None},
         'csv_file':str(output_csv),'csv_sha256':sha256_file(output_csv),
         'limitations':['Contexto ambiental de una muestra seleccionada, no censo climático global',
                        'Criterios de sequedad son ilustrativos, no umbrales de NASA ni Mars',
                        'Aún no existe un perfil ambiental físico de Marte',
                        'El ranking topográfico permanece intacto'],
         'report_file':str(report)}
    atomic_json(report,obj)
    return obj
