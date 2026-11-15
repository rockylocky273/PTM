"""V2.0.4: complete *equal-method* sensitivity for all GLiM anchor cells.

Re-uses the exact 3-method, 3-scale, historical 60-weight and nine-point
leave-one-out protocol from V1.3.2, without retuning or downloading data.
This is sensitivity of a *preselected* group, not planetary validation.
"""
from __future__ import annotations

import csv
import json
import os
from contextlib import contextmanager
from pathlib import Path

from .download import sha256_file, atomic_json
from .mars_uncertainty_v132 import build_uncertainty, review_uncertainty
from .mars_multicriteria_v130 import _load_json
from .mars_geology_correspondence_v131 import SCHEMA as CORR_SCHEMA

SCHEMA = 'mars_analog_all_anchor_sensitivity_v2.0.4'
STATUS = 'all_glim_anchors_equal_sensitivity_not_external_validation'
SCALES = ('15km_17x17', '30km_9x9', '40km_7x7')
METHODS = ('original', 'robust_log_l2', 'empirical_percentile_l1')


@contextmanager
def _in_folder(folder: Path):
    previous = Path.cwd()
    os.chdir(folder)
    try:
        yield
    finally:
        os.chdir(previous)


def _order_correspondence(corr: dict, profile: str):
    rows = [r for r in corr['rows'] if r['mars_profile'] == profile]
    if len(rows) != corr['glim_sampled_regions'] or len({r['earth_region_id'] for r in rows}) != len(rows):
        raise ValueError('Conjunto GLiM del perfil incompleto o duplicado')
    if any(r.get('topographic_rank') is None for r in rows):
        raise ValueError('Alguna celda GLiM no está en la población topográfica; no se puede auditar por igual')
    return sorted(rows, key=lambda r: (r['topographic_rank'], r['earth_region_id']))


def _legacy_comparison(new_doc: dict, old_doc: dict) -> int:
    previous = {r['earth_region_id']:r for r in old_doc['candidates']}
    current = {r['earth_region_id']:r for r in new_doc['candidates']}
    for rid, old in previous.items():
        if rid not in current:
            raise ValueError('Falta candidato de la auditoría V1.3.2: '+rid)
        now = current[rid]
        for key in ('topographic_rank_original', 'method_ranks', 'scale_ranks',
                    'top_k_membership', 'weight_perturbation_ranks',
                    'volcanic_point_diagnostics', 'lithology_counts'):
            if now[key] != old[key]:
                raise ValueError('V2.0.4 no reproduce V1.3.2 para '+rid+' campo '+key)
    return len(previous)


def _summary_row(row: dict) -> dict:
    obs = row['volcanic_point_diagnostics']
    methods, scales, top = row['method_ranks'], row['scale_ranks'], row['top_k_membership']
    weights = row['weight_perturbation_ranks']
    x = {
        'earth_region_id':row['earth_region_id'],
        'topographic_rank_original':row['topographic_rank_original'],
        'rank_log_l2':methods['robust_log_l2'],
        'rank_percentile_l1':methods['empirical_percentile_l1'],
        'rank_15km':scales['15km_17x17'], 'rank_30km':scales['30km_9x9'],
        'rank_40km':scales['40km_7x7'],
        'all_methods_top25':all(methods[m]<=25 for m in METHODS),
        'all_scales_top25':all(scales[s] is not None and scales[s]<=25 for s in SCALES),
        'scales_missing':','.join(s for s in SCALES if scales[s] is None),
        'weight_top10_of_60':top.get('10',{}).get('weight_draws_present'),
        'weight_top25_of_60':top.get('25',{}).get('weight_draws_present'),
        'weight_top50_of_60':top.get('50',{}).get('weight_draws_present'),
        'weight_rank_min':weights['min'],'weight_rank_median':weights['median'],
        'weight_rank_max':weights['max'],
        'glim_volcanic_points':obs['volcanic_observed'],
        'glim_sampled_points':obs['classified'],
        'glim_leave_one_out_preserved':obs['leave_one_out_signal_preserved'],
        'glim_leave_one_out_trials':obs['leave_one_out_trials'],
        'topographic_gate':row['topographic_gate'],
        'analog_validated':False,
    }
    return x


def build_all_sensitivity(data_root: Path, output_dir: Path, *, profile='elysium_planitia',
                          required_regions=25, top_ks=(10,25,50)) -> dict:
    """Build audited sensitivity for all anchors; historical inputs remain unchanged.

    Paths stored in V1.2--V1.3 reports are relative to their historical project
    root; temporary cwd switch respects those checksums without copying gigabytes.
    """
    data_root = Path(data_root).resolve()
    output_dir = Path(output_dir).resolve()
    historical_root = data_root.parent
    correspond_path=data_root/'reports/mars_geology_correspondence_v1_3_1.json'
    legacy_path=data_root/'reports/mars_uncertainty_v1_3_2.json'
    corr=_load_json(correspond_path, CORR_SCHEMA, 'Correspondencia V1.3.1')
    ordered=_order_correspondence(corr,profile)
    if required_regions is not None and len(ordered)!=required_regions:
        raise ValueError(f'Se esperaban {required_regions} regiones auditables; hay {len(ordered)}')
    ids=[r['earth_region_id'] for r in ordered]
    output_dir.mkdir(parents=True,exist_ok=True)
    core_csv=output_dir/'candidate_sensitivity_core_v204.csv'
    core_json=output_dir/'candidate_sensitivity_core_v204.json'
    core_md=output_dir/'candidate_sensitivity_core_v204.md'
    with _in_folder(historical_root):
        # Check original three-way evidence before repeating anything.
        legacy_view=review_uncertainty(legacy_path)
        old_doc=json.loads(legacy_path.read_text(encoding='utf-8'))
        result=build_uncertainty(
            correspondence_report=Path('data/reports/mars_geology_correspondence_v1_3_1.json'),
            screen_report=Path('data/reports/mars_profiles_screen_v1_2.json'),
            manifest=Path('data/catalog/mars_profiles_v1_2.json'),
            audit_report=Path('data/reports/mars_audit_v1_2_1/rank_audit_report.json'),
            scales_report=Path('data/reports/mars_audit_v1_2_1/scales/multiscale_audit_report.json'),
            out_csv=core_csv,out_report=core_json,out_markdown=core_md,
            profile=profile,candidates=ids,top_ks=top_ks)
    doc=json.loads(core_json.read_text(encoding='utf-8'))
    old_verified=_legacy_comparison(doc,old_doc)
    if doc['candidate_ids']!=ids or len(doc['candidates'])!=len(ordered):
        raise ValueError('Resultados V2.0.4 no corresponden a las 25 anclas')
    if doc['weight_draws']['scenarios']!=60 or doc['weight_draws']['seed']!=2026:
        raise ValueError('Auditoría completa usa la semilla y 60 pesos históricos')
    records=[_summary_row(row) for row in doc['candidates']]
    for r in records:
        if r['rank_30km']!=r['topographic_rank_original']:
            raise ValueError('El ranking a 30 km difiere del original')
    csv_path=output_dir/'candidate_sensitivity_v204.csv'
    with csv_path.open('w',encoding='utf-8-sig',newline='') as f:
        writer=csv.DictWriter(f,fieldnames=list(records[0]))
        writer.writeheader();writer.writerows(records)
    counts={
        'all_methods_top25':sum(x['all_methods_top25'] for x in records),
        'all_scales_top25':sum(x['all_scales_top25'] for x in records),
        'top25_in_all_60_weight_scenarios':sum(x['weight_top25_of_60']==60 for x in records),
        'at_least_one_missing_scale':sum(bool(x['scales_missing']) for x in records),
        'volcanic_glim_observed':sum(x['glim_volcanic_points']>0 for x in records),
    }
    markdown=output_dir/'candidate_sensitivity_v204.md'
    lines=['# V2.0.4 — Sensibilidad individual de las regiones GLiM','','**Mismo protocolo V1.3.2 para todas las celdas seleccionadas. No mide precisión de analogía planetaria.**','',
        f'Perfil: {profile}; regiones auditadas: {len(records)}. Se reprodujeron {old_verified} resultados de V1.3.2 sin modificar.','',
        '| Región | Base | L2 | Percentil | 15 km | 30 km | 40 km | Top25/60 pesos | GLiM volcánico | Retirada 1 |',
        '|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|']
    for x in records:
        lines.append('| '+' | '.join(str(x[key]) if x[key] is not None else 'sin datos' for key in
            ('earth_region_id','topographic_rank_original','rank_log_l2','rank_percentile_l1',
            'rank_15km','rank_30km','rank_40km','weight_top25_of_60',
            'glim_volcanic_points','glim_leave_one_out_preserved'))+' |')
    lines.extend(['','## Indicadores de cobertura','','\n'.join(f'- {k}: {v}/{len(records)}' for k,v in counts.items()),'',
        '## Interpretación prudente','','- Comparación sobre 25 regiones preseleccionadas con 9 muestras GLiM cada una, NO sobre todas las regiones terrestres.',
        '- Las posiciones topográficas se calculan frente a la población global de cada escala; el denominador cambia entre 15, 30 y 40 km.',
        '- Las 60 perturbaciones comparten una semilla y pesos; no son 60 experimentos científicos independientes.',
        '- Que GLiM no registre rocas volcánicas en 9 puntos no demuestra ausencia de vulcanismo en la celda completa.',
        '- Sensibilidad topográfica interna no equivale a validación geológica, mineralógica ni de seguridad.', ''])
    markdown.write_text('\n'.join(lines),encoding='utf-8')
    report_path=output_dir/'candidate_sensitivity_v204.json'
    report={
        'schema_version':SCHEMA,'status':STATUS,'mars_profile':profile,
        'candidate_count':len(records),'candidate_ids':ids,'legacy_three_way_cases_reproduced':old_verified,
        'protocol':{'methods':list(METHODS),'scales':list(SCALES),'weight_draws':60,'seed':2026,
                    'glim_points_per_region':9,'top_k':list(top_ks),
                    'no_analog_accuracy':True,'local_nasadem_excluded_from_comparison':True},
        'counts':counts,'rows':records,
        'source_files':{
            'correspondence_v131':{'file':str(correspond_path),'sha256':sha256_file(correspond_path)},
            'historical_three_way_v132':{'file':str(legacy_path),'sha256':sha256_file(legacy_path)},
            'source_core_25':{'file':str(core_json),'sha256':sha256_file(core_json)},
        },
        'csv_file':str(csv_path),'csv_sha256':sha256_file(csv_path),
        'markdown_file':str(markdown),'markdown_sha256':sha256_file(markdown),
        'combined_similarity_score':None,'accuracy_or_auc':None,'analog_validated':False,
    }
    atomic_json(report_path,report)
    return {'schema_version':SCHEMA,'status':STATUS,'candidate_count':len(records),
            'legacy_cases_reproduced':old_verified,'weight_scenarios':60,'counts':counts,
            'report_file':str(report_path),'csv_file':str(csv_path),'markdown_file':str(markdown),
            'report_sha256':sha256_file(report_path)}


def review_all_sensitivity(report_path:Path, region='all') -> dict:
    path=Path(report_path)
    doc=_load_json(path,SCHEMA,'Auditoría extendida V2.0.4')
    if doc.get('status')!=STATUS or doc.get('analog_validated') is not False:
        raise ValueError('Auditoría V2.0.4 incompleta')
    for field in ('csv','markdown'):
        p=Path(doc[field+'_file'])
        if not p.is_file() or sha256_file(p)!=doc[field+'_sha256']:
            raise ValueError('SHA-256 inválido en auditoría '+field)
    for label,src in doc['source_files'].items():
        p=Path(src['file'])
        if not p.is_file() or sha256_file(p)!=src['sha256']:
            raise ValueError('SHA-256 inválido en fuente '+label)
    rows=doc['rows'] if region=='all' else [r for r in doc['rows'] if r['earth_region_id']==region]
    if not rows:
        raise ValueError('Región no encontrada en V2.0.4: '+region)
    if len(set(r['earth_region_id'] for r in doc['rows']))!=doc['candidate_count']:
        raise ValueError('Regiones duplicadas o incompletas en informe V2.0.4')
    return {'schema_version':SCHEMA,'status':'verified_sensitivity_review_no_analog_accuracy',
            'profile':doc['mars_profile'],'count':len(rows),'rows':rows,
            'report_sha256':sha256_file(path)}
