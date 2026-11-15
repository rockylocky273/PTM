"""V1.3.0: auditable *non-compensatory* Mars/Earth evidence integration.

A workflow triage, not a physical analog score or scientific validation.
Only Earth NASA POWER climate is available: NEVER compare it to Mars climate.
Mars USGS map units and terrestrial GLiM classes have distinct taxonomies.
"""
from __future__ import annotations

import csv
import json
import math
from collections import Counter, defaultdict
from pathlib import Path

from .download import atomic_json, sha256_file
from .geology_glim import VOLCANIC
from .mars_domain_v122 import DOMAIN_SCHEMA, MATRIX_SCHEMA
from .mars_geology_v122 import SUMMARY_SCHEMA, SOURCE as MARS_SOURCE
from .mars_profiles_v12 import SCHEMA as SCREEN_SCHEMA

SCHEMA = 'mars_analog_multicriteria_evidence_v1.3.0'
ALLOWED_DOMAIN = frozenset({
    'within_sampled_earth_feature_ranges',
    'partial_reference_extrapolation',
    'strong_reference_extrapolation',
    'all_features_outside_sampled_earth_range',
})
CLIMATE_FIELDS = ('air_temp_mean_c', 'precip_annual_mean_mm',
                  'relative_humidity_mean_pct', 'seasonal_air_temp_range_c')


def _load_json(path, schema, label):
    path = Path(path)
    obj = json.loads(path.read_text(encoding='utf-8'))
    if obj.get('schema_version') != schema:
        raise ValueError(f'{label}: versión de esquema incompatible')
    return obj


def _read_csv(path, required, label):
    with Path(path).open(encoding='utf-8-sig', newline='') as f:
        reader = csv.DictReader(f)
        if reader.fieldnames is None or not set(required).issubset(reader.fieldnames):
            raise ValueError(f'{label}: faltan columnas requeridas')
        rows = list(reader)
    if not rows:
        raise ValueError(f'{label}: CSV vacío')
    return rows


def _verify_file(path, digest, label):
    if not isinstance(digest, str) or len(digest) != 64 or not Path(path).is_file():
        raise ValueError(f'{label}: falta archivo o SHA-256 declarado')
    if sha256_file(Path(path)) != digest:
        raise ValueError(f'{label}: SHA-256 incompatible; se detiene la integración')


def _finite_nonneg(raw, label):
    try:
        v = float(raw)
    except (TypeError, ValueError) as exc:
        raise ValueError(f'{label}: número inválido') from exc
    if not math.isfinite(v) or v < 0:
        raise ValueError(f'{label}: se esperaba número finito no negativo')
    return v


def _count(raw, label):
    try:
        val = int(raw)
        if str(raw).strip() not in (str(val),):
            raise ValueError()
    except (TypeError, ValueError) as exc:
        raise ValueError(f'{label}: entero inválido') from exc
    if val < 0: raise ValueError(f'{label}: entero negativo')
    return val


def _counts_json(raw, label):
    try:
        data = json.loads(raw) if isinstance(raw, str) else raw
    except (TypeError, ValueError) as exc:
        raise ValueError(f'{label}: JSON inválido') from exc
    if not isinstance(data, dict):
        raise ValueError(f'{label}: se requiere objeto de conteos')
    result = {}
    for k, v in data.items():
        if not isinstance(k, str) or not k:
            raise ValueError(f'{label}: código vacío')
        result[k] = _count(v, f'{label}.{k}')
    return result


def _unique_rows(rows, key, label):
    out = {}
    for r in rows:
        k = key(r)
        if k in out:
            raise ValueError(f'{label}: ID duplicado: {k}')
        out[k] = r
    return out


def _domain_gate(domain_row):
    flag = domain_row['domain_flag']
    if flag not in ALLOWED_DOMAIN:
        raise ValueError(f'Dominio desconocido: {flag}')
    if flag in ('all_features_outside_sampled_earth_range', 'strong_reference_extrapolation'):
        return 'blocked_reference_outside_range'
    if flag == 'partial_reference_extrapolation':
        return 'caution_partial_extrapolation'
    tails = _count(domain_row['extreme_one_sided_features_95pct'], 'colas')
    if tails >= 3:
        return 'caution_extreme_terrestrial_tail'
    if tails > 0:
        return 'within_minmax_with_tail_warning'
    return 'within_sampled_feature_ranges_only'


def _geology_signal(mars_profile, earth_counts, earth_classified):
    """Broad *textual* volcanic indicator only, NOT taxonomy matching."""
    unit_counts = _counts_json(mars_profile['unit_code_counts'], 'Unidades Marte')
    descriptions = json.loads(mars_profile['descriptions'])
    if not isinstance(descriptions, dict) or set(unit_counts) != set(descriptions):
        raise ValueError('Códigos y descripciones marcianas no coinciden')
    if sum(unit_counts.values()) != _count(mars_profile['mapped'], 'Muestras mapeadas Marte'):
        raise ValueError('Conteos geológicos de Marte incoherentes')
    volcanic_mars = sum(n for code, n in unit_counts.items()
                        if isinstance(descriptions[code], str) and 'volcanic' in descriptions[code].lower())
    terrestrial_volcanic = sum(n for lith, n in earth_counts.items() if lith in VOLCANIC)
    if sum(earth_counts.values()) != earth_classified:
        raise ValueError('Conteos GLiM no coinciden con muestras clasificadas')
    if not earth_classified or not _count(mars_profile['mapped'], 'Muestras mapeadas Marte'):
        signal = 'insufficient_mapped_geology'
    elif volcanic_mars and terrestrial_volcanic:
        signal = 'shared_broad_volcanic_mapping_signal'
    elif volcanic_mars:
        signal = 'volcanic_mars_not_observed_in_earth_points'
    elif terrestrial_volcanic:
        signal = 'volcanic_earth_no_mars_volcanic_keyword'
    else:
        signal = 'no_broad_volcanic_signal_established'
    return signal, volcanic_mars, terrestrial_volcanic


def _load_climate(report_path):
    """Optional terrestrial context, source-verified, never a Mars similarity."""
    if report_path is None or not Path(report_path).exists():
        return {}, {'status': 'not_available', 'note': 'NASA POWER no se usa como métrica de analogía climática'}
    obj = _load_json(report_path, 'mars_analog_environment_global_v1.0', 'NASA POWER')
    if obj.get('status') != 'descriptive_sampled_climate_not_global_census_or_mars_score':
        raise ValueError('NASA POWER: informe de entorno incompatible')
    source = obj['csv_file']
    _verify_file(source, obj.get('csv_sha256'), 'NASA POWER CSV')
    recs = _read_csv(source, ['region_id', 'status', *CLIMATE_FIELDS], 'NASA POWER CSV')
    rows = _unique_rows(recs, lambda r: r['region_id'], 'NASA POWER')
    if _count(obj['selected'], 'POWER seleccionados') != len(rows):
        raise ValueError('NASA POWER: longitud de muestra incoherente')
    for r in recs:
        if r['status'] not in ('complete', 'partial', 'not_downloaded'):
            raise ValueError('NASA POWER: estado no reconocido')
        if r['status'] == 'complete':
            for k in CLIMATE_FIELDS:
                raw = r[k]
                if not raw:
                    raise ValueError('NASA POWER completo pero sin variable: ' + k)
                val = float(raw)
                if not math.isfinite(val):
                    raise ValueError('NASA POWER: valor no finito')
                if k != 'air_temp_mean_c' and val < 0:
                    raise ValueError('NASA POWER: medida negativa no permitida')
                if k == 'relative_humidity_mean_pct' and val > 100:
                    raise ValueError('NASA POWER: humedad >100%')
    return rows, {'status': 'available_earth_context_only', 'report_sha256': sha256_file(report_path),
                  'csv_sha256': obj['csv_sha256'], 'years': obj.get('years'),
                  'sampled_earth_regions': len(recs), 'complete_earth_regions': sum(r['status']=='complete' for r in recs)}


def _load_audit(audit_report, screen_sha):
    if audit_report is None or not Path(audit_report).exists():
        return {}, {'status': 'not_available'}, {}
    obj = _load_json(audit_report, 'mars_analog_profile_audit_v1.2.1', 'Auditoría V1.2.1')
    if obj.get('source_screen_sha256') != screen_sha:
        raise ValueError('Auditoría V1.2.1 y búsqueda V1.2 no coinciden')
    wr = obj.get('files', {}).get('watched_candidates', {})
    _verify_file(wr.get('file', ''), wr.get('sha256'), 'Rangos alternativos V1.2.1')
    candidates = _unique_rows(_read_csv(wr['file'], ['profile','region_id','method','rank'], 'Rangos alternativos'),
                              lambda r: (r['profile'],r['region_id'],r['method']), 'Rangos alternativos')
    return candidates, {'status':'available_diagnostic_only','report_sha256':sha256_file(audit_report),
                        'csv_sha256':wr['sha256']}, obj.get('weight_stability', {})


def _load_scales(scales_report, screen_sha):
    if scales_report is None or not Path(scales_report).exists():
        return {}, {'status':'not_available'}, []
    obj = _load_json(scales_report, 'mars_analog_profile_audit_v1.2.1', 'Auditoría multiescala')
    if obj.get('status') != 'fixed_window_multiscale_experiment_no_reranking_of_historical_results':
        raise ValueError('Auditoría multiescala con estado incompatible')
    if obj.get('source_hashes', {}).get('v12_screen') != screen_sha:
        raise ValueError('Auditoría multiescala y búsqueda V1.2 no coinciden')
    f = obj['files']['rankings']
    _verify_file(f['file'], f['sha256'], 'Rankings multiescala')
    recs = _read_csv(f['file'], ['scale','mars_profile','region_id','rank'], 'Rankings multiescala')
    d = _unique_rows(recs, lambda r:(r['scale'],r['mars_profile'],r['region_id']), 'Rankings multiescala')
    scales = sorted({r['scale'] for r in recs})
    if '30km_9x9' not in scales or len(scales)<2:
        raise ValueError('Multiescala: falta referencia 30km_9x9')
    return d, {'status':'available_diagnostic_only','report_sha256':sha256_file(scales_report),
               'csv_sha256':f['sha256'],'scales':scales}, scales


def _read_sources(matrix_report, domain_report, geology_report, glim, screen_report):
    m = _load_json(matrix_report, MATRIX_SCHEMA, 'Matriz V1.2.2')
    if m.get('status') != 'independent_evidence_matrix_without_joint_score':
        raise ValueError('La matriz V1.2.2 debe carecer de puntuación conjunta')
    d = _load_json(domain_report, DOMAIN_SCHEMA, 'Dominio V1.2.2')
    g = _load_json(geology_report, SUMMARY_SCHEMA, 'Geología marciana V1.2.2')
    s = _load_json(screen_report, SCREEN_SCHEMA, 'Búsqueda topográfica V1.2')
    if g.get('source') != MARS_SOURCE or g.get('pending_points') != 0:
        raise ValueError('Geología marciana incompleta o fuente no permitida')
    if s.get('status') != 'separate_topographic_rankings_not_mars_analog_confirmation':
        raise ValueError('Reporte de búsqueda V1.2 inválido')
    for p, expected, label in (
        (domain_report, m['source_domain_report_sha256'], 'Dominio'),
        (geology_report, m['source_mars_geology_sha256'], 'Geología marciana'),
        (glim, m['earth_glim_sha256'], 'GLiM terrestre'),
        (screen_report, m['source_screen_sha256'], 'Ranking V1.2'),
    ):
        _verify_file(p, expected, label)
    for path, digest, label in ((m['csv_file'],m['csv_sha256'],'Matriz CSV'),
                                 (d['csv_file'],d['csv_sha256'],'Dominio CSV'),
                                 (g['csv_file'],g['csv_sha256'],'Geología CSV')):
        _verify_file(path, digest, label)
    return m,d,g,s


def build_multicriteria(matrix_report, domain_report, geology_report, glim_csv, screen_report,
                        out_csv, out_json, out_markdown, shortlist_top=25,
                        climate_report='data/reports/environment_sample.json',
                        audit_report='data/reports/mars_audit_v1_2_1/rank_audit_report.json',
                        scales_report='data/reports/mars_audit_v1_2_1/scales/multiscale_audit_report.json'):
    if not 1 <= shortlist_top <= 500:
        raise ValueError('shortlist-top debe estar entre 1 y 500')
    m,d,g,s = _read_sources(matrix_report,domain_report,geology_report,glim_csv,screen_report)
    matrix = _read_csv(m['csv_file'], ['mars_profile','earth_region_id','topographic_rank_v12',
                       'topographic_distance_v12','mars_domain_flag','mars_units_sampled',
                       'mars_unit_codes','earth_glim_sampled','earth_observed_glim_classes',
                       'earth_basic_volcanic_sample_count'], 'Matriz V1.2.2 CSV')
    if _count(m['rows'],'Matriz filas') != len(matrix):
        raise ValueError('Matriz V1.2.2: cantidad de filas inconsistente')
    _unique_rows(matrix,lambda r:(r['mars_profile'],r['earth_region_id']),'Matriz V1.2.2')
    geol = _unique_rows(g['profiles'],lambda r:r['profile_id'],'Perfiles geología marciana')
    domain = _unique_rows(d['profiles'],lambda r:r['profile'],'Perfiles dominio')
    earth = _unique_rows(_read_csv(glim_csv,['region_id','classified','observed_lithology_classes',
                                            'basic_volcanic_sample_count'],'GLiM terrestre'),
                         lambda r:r['region_id'],'GLiM terrestre')
    if set(geol) != set(domain):
        raise ValueError('Perfiles dominio y geología marciana no coinciden')
    screen = _unique_rows(s['profiles'],lambda r:r['id'],'Perfiles búsqueda V1.2')
    if set(screen) != set(geol):
        raise ValueError('Perfiles de búsqueda y geología no coinciden')
    ranks={}
    for name, p in screen.items():
        _verify_file(p['ranking_csv'],p['ranking_sha256'],'Ranking '+name)
        arr=_read_csv(p['ranking_csv'],['rank','region_id','distance_total'],'Ranking '+name)
        ranks[name] = _unique_rows(arr,lambda r:r['region_id'],'Ranking '+name)
        if len(arr)!=_count(p['ranked_count'],'Conteo ranking'):
            raise ValueError('Conteo de ranking inconsistente: '+name)
    climate, climate_meta = _load_climate(climate_report)
    alternatives, audit_meta, weights = _load_audit(audit_report, sha256_file(screen_report))
    scales, scale_meta, scale_names = _load_scales(scales_report, sha256_file(screen_report))
    ledger=[]
    for v in matrix:
        profile, region = v['mars_profile'],v['earth_region_id']
        if profile not in geol or region not in earth or region not in ranks[profile]:
            raise ValueError('Candidato matricial no respaldado por las fuentes originales')
        pd,pg,eg,orank = domain[profile],geol[profile],earth[region],ranks[profile][region]
        if v['mars_domain_flag'] != pd['domain_flag']:
            raise ValueError('Matriz y diagnóstico de dominio difieren')
        if (_count(v['topographic_rank_v12'],'Puesto matriz') != _count(orank['rank'],'Puesto original') or
            abs(_finite_nonneg(v['topographic_distance_v12'],'Distancia matriz') -
                _finite_nonneg(orank['distance_total'],'Distancia ranking'))>1e-9):
            raise ValueError('Matriz y ranking topográfico difieren')
        mcounts = _counts_json(v['mars_unit_codes'],'Matriz geología Marte')
        if mcounts != _counts_json(pg['unit_code_counts'],'Resumen geología Marte') or \
            _count(v['mars_units_sampled'],'Muestras Marte matriz') != _count(pg['mapped'],'Muestras Marte resumen'):
            raise ValueError('Matriz no coincide con las observaciones marcianas')
        ecounts = _counts_json(v['earth_observed_glim_classes'],'Matriz GLiM')
        if ecounts != _counts_json(eg['observed_lithology_classes'],'CSV GLiM') or \
            _count(v['earth_glim_sampled'],'Clasificados matriz') != _count(eg['classified'],'Clasificados GLiM') or \
            _count(v['earth_basic_volcanic_sample_count'],'Volcánica básica matriz') != \
                _count(eg['basic_volcanic_sample_count'],'Volcánica básica GLiM'):
            raise ValueError('Matriz no coincide con las observaciones GLiM')
        if _count(eg['basic_volcanic_sample_count'],'Volcánica básica') != ecounts.get('Basic volcanic rocks', 0):
            raise ValueError('GLiM: recuento volcánico incoherente')
        rank = _count(orank['rank'],'Rank');
        if rank < 1:
            raise ValueError('Ranking debe ser mayor que cero')
        gate=_domain_gate(pd)
        signal, nmars, nearth = _geology_signal(pg,ecounts,_count(eg['classified'],'GLiM total'))
        if gate=='blocked_reference_outside_range': triage='hold_reference_domain'
        elif gate.startswith('caution_'): triage='review_topographic_extrapolation_first'
        elif signal=='insufficient_mapped_geology':triage='collect_missing_geology'
        elif signal=='shared_broad_volcanic_mapping_signal' and rank<=shortlist_top:
            triage='candidate_for_targeted_geological_validation'
        elif signal=='shared_broad_volcanic_mapping_signal':triage='secondary_volcanic_hypothesis_only'
        else:triage='topography_only_no_geological_match_established'
        climate_record = climate.get(region)
        climate_status = (climate_record['status'] if climate_record is not None else
                          'not_sampled' if climate_meta['status']!='not_available' else 'not_available')
        climate_metrics = {k:(float(climate_record[k]) if climate_status=='complete' else None)
                           for k in CLIMATE_FIELDS} if climate_record is not None else {k:None for k in CLIMATE_FIELDS}
        alternative_ranks={}
        for method in ('original','robust_log_l2','empirical_percentile_l1'):
            v2=alternatives.get((profile,region,method))
            alternative_ranks[method] = _count(v2['rank'],'Puesto alternativo') if v2 is not None else None
        if alternative_ranks['original'] is not None and alternative_ranks['original'] != rank:
            raise ValueError('Auditoría y ranking original no coinciden')
        scale_ranks={}
        for scale in scale_names:
            entry=scales.get((scale,profile,region))
            scale_ranks[scale]=_count(entry['rank'],'Puesto por escala') if entry else None
        if scale_ranks.get('30km_9x9') is not None and scale_ranks['30km_9x9'] != rank:
            raise ValueError('Auditoría multiescala y ranking original no coinciden')
        alternatives_known=sum(v is not None for v in alternative_ranks.values())
        scale_avail=sum(v is not None for v in scale_ranks.values())
        if not scale_names or scale_avail < len(scale_names): scale_state='not_fully_evaluated'
        elif all(x<=shortlist_top for x in scale_ranks.values()):scale_state='in_shortlist_all_scales'
        elif any(x<=shortlist_top for x in scale_ranks.values()):scale_state='shortlist_changes_with_scale'
        else:scale_state='outside_shortlist_all_scales'
        ledger.append({
            'mars_profile':profile,'earth_region_id':region,'topographic_rank_v12':rank,
            'topographic_distance_v12':_finite_nonneg(orank['distance_total'],'distancia'),
            'topographic_shortlist_at_n':rank<=shortlist_top,
            'topographic_domain_flag':pd['domain_flag'],'topographic_gate':gate,
            'topographic_extreme_tail_features':_count(pd['extreme_one_sided_features_95pct'],'colas'),
            'mars_geology_mapped_points':_count(pg['mapped'],'mapped'),
            'mars_geology_units':mcounts,'mars_volcanic_keyword_points':nmars,
            'earth_geology_classified_points':_count(eg['classified'],'classified'),
            'earth_glim_classes':ecounts,'earth_volcanic_point_count':nearth,
            'geological_signal':signal,'climate_status':climate_status,
            'earth_nasa_power_climate':climate_metrics,'alternative_method_ranks':alternative_ranks,
            'alternative_rank_coverage':alternatives_known,'scale_ranks':scale_ranks,
            'scale_shortlist_stability':scale_state,'weight_stability_profile':weights.get(profile),
            'workflow_triage':triage,'analog_validated':False,
            'mars_climate_similarity':'NOT_EVALUATED',
            'geological_equivalence':'NOT_EVALUATED',
            'combined_similarity_score':None,
        })
    if len(ledger)!=len(matrix):
        raise ValueError('Error interno: filas no conservadas')
    ledger.sort(key=lambda r:(r['mars_profile'],r['topographic_rank_v12'],r['earth_region_id']))
    out_csv=Path(out_csv);out_csv.parent.mkdir(parents=True,exist_ok=True)
    flat=[]
    for r in ledger:
        flat.append({k:(json.dumps(v,ensure_ascii=False,sort_keys=True) if isinstance(v,(dict,list)) else v)
                     for k,v in r.items()})
    with out_csv.open('w',encoding='utf-8',newline='') as f:
        wr=csv.DictWriter(f,fieldnames=list(flat[0]));wr.writeheader();wr.writerows(flat)
    report={
        'schema_version':SCHEMA,'status':'noncompensatory_evidence_triage_no_joint_similarity_score',
        'shortlist_threshold_exploratory':shortlist_top,
        'rows':len(ledger),'mars_profiles':len(geol),
        'earth_regions':sorted({r['earth_region_id'] for r in ledger}),
        'triage_counts':dict(sorted(Counter(r['workflow_triage'] for r in ledger).items())),
        'domain_gate_counts':dict(sorted(Counter(r['topographic_gate'] for r in ledger).items())),
        'geology_signal_counts':dict(sorted(Counter(r['geological_signal'] for r in ledger).items())),
        'sources':{'v122_matrix_report':{'file':str(matrix_report),'sha256':sha256_file(matrix_report),
                                        'csv_sha256':m['csv_sha256']},
                   'v122_domain_report':{'file':str(domain_report),'sha256':sha256_file(domain_report)},
                   'v122_mars_geology_report':{'file':str(geology_report),'sha256':sha256_file(geology_report)},
                   'earth_glim_csv':{'file':str(glim_csv),'sha256':sha256_file(glim_csv)},
                   'v12_screen_report':{'file':str(screen_report),'sha256':sha256_file(screen_report)},
                   'nasa_power':climate_meta,'v121_audit':audit_meta,'v121_scales':scale_meta},
        'csv_file':str(out_csv),'csv_sha256':sha256_file(out_csv),'candidates':ledger,
        'limitations':[
            'Triage describe próximas acciones; no cuantifica similitud Tierra-Marte ni probabilidades',
            'El top N es un umbral exploratorio configurable, no una regla de validez física',
            'Unidades USGS SIM 3292 y clases GLiM no son taxonomías equivalentes',
            'Volcanic es una palabra de la descripción cartográfica marciana, NO análisis mineralógico',
            'Ausencia de señal volcánica en nueve puntos NO demuestra incompatibilidad geológica',
            'Las frecuencias de puntos no son porcentajes de superficie',
            'NASA POWER caracteriza condiciones terrestres históricas; NO evalúa clima marciano',
            'Los cinco parámetros topográficos están correlacionados y dependen de la escala',
            'Puestos alternativos y multiescala son pruebas de sensibilidad, NO verdad de campo',
            'Ninguna fila ha superado una validación científica externa de analogía',
        ]}
    md=['# Mars Analog Discovery Engine V1.3.0 — Matriz de evidencias',
        '', '**No es un ranking combinado ni un porcentaje de similitud.**',
        '',f'Perfiles: {len(geol)}. Comparaciones: {len(ledger)}. Umbral exploratorio top {shortlist_top}.','']
    for profile in sorted(geol):
        md += [f'## {profile}', '',
               '| Tierra | Puesto topográfico | Dominio | Señal geológica | Clima Tierra | Estabilidad multiescala | Próximo paso |',
               '|---|---:|---|---|---|---|---|']
        for r in ledger:
            if r['mars_profile']!=profile:continue
            vals=[r['earth_region_id'],str(r['topographic_rank_v12']),r['topographic_gate'],
                  r['geological_signal'],r['climate_status'],r['scale_shortlist_stability'],r['workflow_triage']]
            md.append('| '+' | '.join(v.replace('|','/') for v in vals)+' |')
        md += ['']
    md += ['## Interpretación y límites','',*('- '+x for x in report['limitations']),'',
           'Consultar JSON para los metadatos SHA-256, las unidades USGS y las clases GLiM.', '']
    markdown_path=Path(out_markdown);markdown_path.parent.mkdir(parents=True,exist_ok=True)
    markdown_path.write_text('\n'.join(md),encoding='utf-8')
    report['markdown_file']=str(markdown_path)
    report['markdown_sha256']=sha256_file(markdown_path)
    atomic_json(Path(out_json),report)
    return {'schema_version':SCHEMA,'status':report['status'],'rows':len(ledger),
            'profiles':len(geol),'earth_regions':report['earth_regions'],
            'triage_counts':report['triage_counts'], 'climate':climate_meta['status'],
            'alternative_rank_diagnostics':audit_meta['status'], 'multiscale_diagnostics':scale_meta['status'],
            'csv_file':str(out_csv),'report_file':str(out_json),'markdown_file':str(markdown_path),
            'report_sha256':sha256_file(Path(out_json))}


def review_multicriteria(report_path, profile='all'):
    src=_load_json(report_path,SCHEMA,'Motor multicriterio V1.3.0')
    if src.get('status')!='noncompensatory_evidence_triage_no_joint_similarity_score':
        raise ValueError('Informe multicriterio incorrecto')
    _verify_file(src['csv_file'],src['csv_sha256'],'CSV multicriterio')
    if profile!='all' and profile not in {r['mars_profile'] for r in src['candidates']}:
        raise ValueError('Perfil no encontrado; usar --profile all o mars-targets')
    rows=[{'mars_profile':r['mars_profile'],'earth_region_id':r['earth_region_id'],
           'topographic_rank':r['topographic_rank_v12'],'topographic_gate':r['topographic_gate'],
           'geological_signal':r['geological_signal'],'earth_climate_status':r['climate_status'],
           'scale_stability':r['scale_shortlist_stability'],'triage':r['workflow_triage']}
          for r in src['candidates'] if profile=='all' or r['mars_profile']==profile]
    return {'schema_version':SCHEMA,'status':'evidence_review_no_joint_score',
            'source_sha256':sha256_file(report_path),'profile_filter':profile,'rows':rows}
