"""V1.2.2: explicit validity gates and evidence tables, no analog score."""
from __future__ import annotations
import csv
import json
from pathlib import Path
from collections import defaultdict

from .download import atomic_json, sha256_file
from .mars_geology_v122 import SUMMARY_SCHEMA, SOURCE, MAP_DOI
from .mars_profiles_v12 import SCHEMA

DOMAIN_SCHEMA='mars_analog_reference_domain_audit_v1.2.2'
MATRIX_SCHEMA='mars_analog_evidence_matrix_v1.2.2'


def _csv(path):
    with Path(path).open(encoding='utf-8-sig',newline='') as f:
        return list(csv.DictReader(f))


def evaluate_domain(audit_report, out_csv, out_json):
    audit_report=Path(audit_report)
    audit=json.loads(audit_report.read_text(encoding='utf-8'))
    if audit.get('schema_version')!='mars_analog_profile_audit_v1.2.1':
        raise ValueError('Se requiere auditoría mars-audit-rankings de V1.2.1')
    filemeta=audit.get('files',{}).get('feature_saturation',{})
    source=Path(filemeta.get('file',''))
    if not source.is_file() or sha256_file(source)!=filemeta.get('sha256'):
        raise ValueError('CSV de saturación ausente o SHA-256 incompatible')
    observations=_csv(source)
    if not observations:raise ValueError('No existen características topográficas')
    grouped=defaultdict(list)
    for r in observations:
        if r.get('profile') not in audit.get('profiles',[]):
            raise ValueError('Perfil inesperado en el diagnóstico de V1.2.1')
        value=float(r['mars_value']); low=float(r['earth_min']); high=float(r['earth_max'])
        above=float(r['earth_fraction_above_mars']);below=float(r['earth_fraction_below_mars'])
        if not (0<=low<=high and 0<=value and 0<=above<=1 and 0<=below<=1):
            raise ValueError('Estadísticas de saturación imposibles')
        grouped[r['profile']].append({'feature':r['feature'],'mars_value':value,
           'earth_min':low,'earth_max':high,'fraction_above':above,
           'fraction_below':below,
           'outside_empirical_minmax':bool(value<low or value>high),
           'outside_95pct_one_sided':max(above,below)>=.95})
    rows=[]
    for profile in audit['profiles']:
        feats=grouped[profile]
        if len(feats)!=5 or len(set(v['feature'] for v in feats))!=5:
            raise ValueError('Se requieren 5 características independientes por perfil')
        outside=sum(v['outside_empirical_minmax'] for v in feats)
        tails=sum(v['outside_95pct_one_sided'] for v in feats)
        domain=('all_features_outside_sampled_earth_range' if outside==5 else
                'strong_reference_extrapolation' if outside>=3 else
                'partial_reference_extrapolation' if outside>0 else
                'within_sampled_earth_feature_ranges')
        tail_flag=('concentrated_extreme_tails' if tails>=3 else
                   'some_extreme_tail_features' if tails>0 else 'no_extreme_tail_features')
        rows.append({'profile':profile,'features':5,'outside_catalog_minmax':outside,
                     'extreme_one_sided_features_95pct':tails,
                     'domain_flag':domain,'tail_flag':tail_flag,
                     'ranking_allowed_as_verified_analog':False})
    out_csv=Path(out_csv);out_csv.parent.mkdir(parents=True,exist_ok=True)
    with out_csv.open('w',newline='',encoding='utf-8') as f:
        w=csv.DictWriter(f,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)
    obj={'schema_version':DOMAIN_SCHEMA,'status':'numeric_reference_coverage_not_validation',
         'source_v121_audit_sha256':sha256_file(audit_report),
         'source_feature_saturation_sha256':sha256_file(source),
         'evaluated_profiles':len(rows),'profiles':rows,'features_detail':grouped,
         'csv_file':str(out_csv),'csv_sha256':sha256_file(out_csv),
         'warnings':['El universo de 2617 regiones procede de un filtro terrestre selectivo',
                     'Dentro del rango min-max no significa analogía científicamente validada',
                     'Los percentiles y rangos dependen del catálogo ETOPO y la escala de 30km',
                     'Los cinco valores están correlacionados; no son cinco pruebas independientes',
                     'No reemplaza el ranking de V1.2 ni modifica su función de distancia']}
    atomic_json(Path(out_json),obj)
    return {k:v for k,v in obj.items() if k!='features_detail'} | {
        'report_file':str(out_json),'report_sha256':sha256_file(Path(out_json))}


def evidence_matrix(mars_report, domain_report, earth_glim_csv, screen_report,
                    out_csv, out_json, watch='r026_c146,r068_c061'):
    """Lists evidence side by side, never computes geological compatibility."""
    requested=[x.strip() for x in watch.split(',') if x.strip()]
    if not requested or len(set(requested))!=len(requested) or len(requested)>25:
        raise ValueError('watch vacío, duplicado o demasiado amplio')
    mp=Path(mars_report);mg=json.loads(mp.read_text(encoding='utf-8'))
    if mg.get('schema_version')!=SUMMARY_SCHEMA or mg.get('source')!=SOURCE:
        raise ValueError('Informe geológico marciano incorrecto')
    if int(mg.get('pending_points',-1)) != 0:
        raise ValueError('Completá todas las muestras geológicas antes de crear la matriz')
    if sha256_file(Path(mg['csv_file'])) != mg.get('csv_sha256'):
        raise ValueError('CSV de geología marciana alterado')
    gp=Path(domain_report);domain=json.loads(gp.read_text(encoding='utf-8'))
    if domain.get('schema_version')!=DOMAIN_SCHEMA:
        raise ValueError('Primero generar mars-domain-report')
    gp_csv=Path(domain.get('csv_file',''))
    if sha256_file(gp_csv)!=domain.get('csv_sha256'):
        raise ValueError('Informe de dominio modificado')
    earth_file=Path(earth_glim_csv);earth_all=_csv(earth_file)
    earth_rows={r['region_id']:r for r in earth_all}
    if len(earth_all)!=len(earth_rows):
        raise ValueError('Regiones terrestres duplicadas')
    missing=set(requested)-set(earth_rows)
    if missing: raise ValueError(f'Faltan candidatos GLiM de Tierra: {sorted(missing)}')
    screen_path=Path(screen_report);screen=json.loads(screen_path.read_text(encoding='utf-8'))
    if (screen.get('schema_version')!=SCHEMA or
        screen.get('status')!='separate_topographic_rankings_not_mars_analog_confirmation'):
        raise ValueError('Búsqueda V1.2 inválida')
    domain_profiles={x['profile']:x for x in domain['profiles']}
    mars_profiles={x['profile_id']:x for x in mg['profiles']}
    if not domain_profiles.keys()==mars_profiles.keys():
        raise ValueError('Perfiles de geología y diagnóstico de dominio no coinciden')
    ret=[]
    for record in screen['profiles']:
        profile=record['id']
        if profile not in domain_profiles: raise ValueError('Perfil del ranking no examinado')
        rcsv=Path(record['ranking_csv'])
        if sha256_file(rcsv)!=record['ranking_sha256']:
            raise ValueError('Ranking V1.2 modificado; aborto de integración')
        ranks={r['region_id']:r for r in _csv(rcsv)}
        mars_row=mars_profiles[profile]
        for reg in requested:
            e=earth_rows[reg];r=ranks.get(reg)
            if r is None: continue
            earth_observed=json.loads(e['observed_lithology_classes'])
            if not isinstance(earth_observed,dict):raise ValueError('Campo GLiM terrestre malformado')
            ret.append({'mars_profile':profile,'earth_region_id':reg,
                        'topographic_rank_v12':int(r['rank']),
                        'topographic_distance_v12':float(r['distance_total']),
                        'mars_domain_flag':domain_profiles[profile]['domain_flag'],
                        'mars_units_sampled':mars_row['mapped'],
                        'mars_unit_codes':mars_row['unit_code_counts'],
                        'earth_glim_sampled':e['classified'],
                        'earth_observed_glim_classes':json.dumps(earth_observed,ensure_ascii=False,sort_keys=True),
                        'earth_basic_volcanic_sample_count':e['basic_volcanic_sample_count'],
                        'geological_compatibility_score':'NOT_COMPUTED',
                        'scientific_validation':'NOT_VALIDATED'})
    if not ret:raise ValueError('No existen candidatos conjuntos con rankings')
    out_csv=Path(out_csv);out_csv.parent.mkdir(parents=True,exist_ok=True)
    with out_csv.open('w',newline='',encoding='utf-8') as f:
        w=csv.DictWriter(f,fieldnames=list(ret[0]));w.writeheader();w.writerows(ret)
    result={'schema_version':MATRIX_SCHEMA,'status':'independent_evidence_matrix_without_joint_score',
            'rows':len(ret),'profiles':len(mars_profiles),'earth_regions':requested,
            'earth_glim_sha256':sha256_file(earth_file),
            'source_mars_geology_sha256':sha256_file(mp),
            'source_domain_report_sha256':sha256_file(gp),
            'source_screen_sha256':sha256_file(screen_path),
            'source_usgs_sim3292_doi':MAP_DOI,
            'csv_file':str(out_csv),'csv_sha256':sha256_file(out_csv),
            'warnings':['Los códigos geológicos marcianos y clases GLiM terrestres NO son taxonomías equivalentes',
                        'Sin comprobación mineralógica, espacial ni estratigráfica de unidades análogas',
                        'No se modifica el ranking topográfico, no se crea score total',
                        'Muestras puntuales no representan cobertura por área ni un hábitat apto']}
    atomic_json(Path(out_json),result)
    return result | {'report_file':str(out_json),'report_sha256':sha256_file(Path(out_json))}
