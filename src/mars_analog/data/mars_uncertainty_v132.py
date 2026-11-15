"""V1.3.2 — balanced evidence audit for *selected* Mars/Earth process hypotheses.

No planetary similarity probability, area fractions, or independence assumptions.
Every contender is assessed with the SAME globally available observations:
9 GLiM points, MOLA/ETOPO 30-km rankings, 15/30/40-km sensitivity,
robust L2/percentile methods, and fixed seeded perturbations.
Argentina's optional NASADEM local detail is explicitly outside the comparison.
"""
from __future__ import annotations

import csv
import json
import math
from collections import Counter
from pathlib import Path

import numpy as np

from .download import atomic_json, sha256_file
from .geology_glim import VOLCANIC, ALLOWED, FILL
from .mars_geology_correspondence_v131 import (SCHEMA as CORR_SCHEMA,
    PLUTONIC, SEDIMENT)
from .mars_multicriteria_v130 import (_count, _counts_json, _load_json,
    _unique_rows, _verify_file)
from .mars_profiles_audit_v121 import (SCHEMA_AUDIT, W, F_KEYS, _signed, _groups,
    _ranks, _alternative_scores, _load_ranking_matrices)

SCHEMA = 'mars_analog_balanced_uncertainty_v1.3.2'
STATUS = 'matched_observation_sensitivity_no_analog_probability'
DEFAULT_IDS = ('r026_c146', 'r069_c067', 'r067_c038')
METHODS = ('original', 'robust_log_l2', 'empirical_percentile_l1')


def _families(counts):
    """Explicit mixed classes: metamorphics are never folded into sediments."""
    if set(counts) - ALLOWED:
        raise ValueError('Categoría GLiM desconocida')
    grouped = {
        'extrusive_volcanic_or_pyroclastic': sum(n for c,n in counts.items() if c in VOLCANIC),
        'plutonic_not_extrusive': sum(n for c,n in counts.items() if c in PLUTONIC),
        'metamorphic': counts.get('Metamorphics', 0),
        'sedimentary_or_unconsolidated': sum(n for c,n in counts.items() if c in SEDIMENT),
        'fill_not_a_rock': sum(n for c,n in counts.items() if c in FILL),
    }
    if sum(grouped.values()) != sum(counts.values()):
        raise ValueError('GLiM no se pudo clasificar completamente por familias')
    return grouped


def _observed_signature(counts):
    families = _families(counts)
    positive = [k for k,v in families.items() if v > 0]
    if not positive:
        return 'no_classified_lithology'
    if families['extrusive_volcanic_or_pyroclastic'] > 0:
        return ('volcanic_signal_with_other_lithologies' if len(positive)>1
                else 'volcanic_signal_only')
    return ('no_volcanic_sample_mixed_'+'_and_'.join(positive) if len(positive)>1
            else 'no_volcanic_sample_'+positive[0])


def _volcanic_leave_one_out(counts, classified):
    """Finite-sample *deletion* and subsampling sensitivity, NOT a population CI."""
    n = _count(classified, 'GLiM classified')
    if n != sum(counts.values()):
        raise ValueError('GLiM conteos no suman puntos clasificados')
    volcanic = sum(v for k,v in counts.items() if k in VOLCANIC)
    if n < 1:
        return {'classified': 0, 'volcanic_observed': 0, 'sampled_fraction_not_area': None,
                'leave_one_out_signal_preserved':None,
                'leave_one_out_trials':0, 'subsample_detection_given_observed_points':{}}
    # Number of the n leave-one-out subsamples containing >=1 volcanic observation.
    retained = sum((volcanic - int(remove_volcanic)) > 0
                   for remove_volcanic in ([True]*volcanic+[False]*(n-volcanic)))
    subsample = {}
    for k in (1,3,5,9):
        if k > n:continue
        # Exact finite-population probability from the *observed* n points,
        # assuming an equally likely subset of indices, not spatial independence.
        p = 1 - (math.comb(n-volcanic,k)/math.comb(n,k) if k<=n-volcanic else 0.)
        subsample[str(k)] = round(p, 8)
    return {'classified':n,'volcanic_observed':volcanic,
            'sampled_fraction_not_area':round(volcanic/n,8),
            'leave_one_out_signal_preserved':retained,
            'leave_one_out_trials':n,
            'subsample_detection_given_observed_points':subsample}


def _verify_correspondence(path):
    doc=_load_json(path,CORR_SCHEMA,'Correspondencia V1.3.1')
    if doc.get('status')!='process_hypotheses_and_contrasts_no_geological_equivalence_score':
        raise ValueError('Correspondencia geológica V1.3.1 incompleta')
    _verify_file(doc['csv_file'],doc['csv_sha256'],'Correspondencia V1.3.1 CSV')
    _verify_file(doc['markdown_file'],doc['markdown_sha256'],'Correspondencia V1.3.1 Markdown')
    for name,entry in doc['source_files'].items():
        _verify_file(entry['path'],entry['sha256'],'Fuente correspondencia '+name)
    if doc['pairs'] != len(doc['rows']):
        raise ValueError('Conteo de pares V1.3.1 no coincide')
    return doc


def _read_scale_positions(report_path, screen_hash, manifest_hash, ids, profile, base_ranks):
    doc=_load_json(report_path,SCHEMA_AUDIT,'Escalas V1.2.1')
    if doc.get('status')!='fixed_window_multiscale_experiment_no_reranking_of_historical_results':
        raise ValueError('Experimento multiescala incorrecto')
    hashes=doc['source_hashes']
    if hashes.get('v12_screen')!=screen_hash or hashes.get('v12_manifest')!=manifest_hash:
        raise ValueError('Fuentes de escalas difieren de rankings V1.2')
    for name,entry in doc['files'].items():
        _verify_file(entry['file'],entry['sha256'],'Archivo de escalas '+name)
    # Read all rows and explicitly reject duplicate (scale, profile, region).
    # The stored file contains approx. 47k rows; it is not a re-download.
    lookup={}
    scale_total=Counter()
    with Path(doc['files']['rankings']['file']).open(encoding='utf-8-sig',newline='') as f:
        rdr=csv.DictReader(f)
        required={'scale','mars_profile','region_id','rank'}
        if not rdr.fieldnames or not required.issubset(rdr.fieldnames):
            raise ValueError('CSV multiescala sin columnas requeridas')
        for r in rdr:
            if r['mars_profile']!=profile: continue
            key=(r['scale'],r['region_id'])
            if key in lookup:raise ValueError('CSV multiescala: fila duplicada')
            v=_count(r['rank'],'Puesto en escala')
            if v<1:raise ValueError('Puesto en escala inválido')
            lookup[key]=v
            scale_total[r['scale']]+=1
    scales=('15km_17x17','30km_9x9','40km_7x7')
    if set(scale_total)!=set(scales):
        raise ValueError('Faltan escalas 15, 30 o 40 km')
    if scale_total['30km_9x9']!=len(base_ranks):
        raise ValueError('Escala de referencia distinta del ranking V1.2')
    for rid,base in base_ranks.items():
        if lookup.get(('30km_9x9',rid))!=base:
            raise ValueError('30km no reproduce el ranking original: '+rid)
    # Never conflate absence of data at one scale with rank > top-k.
    return {rid:{s:lookup.get((s,rid)) for s in scales} for rid in ids}, dict(scale_total)


def _read_audit(path, screen_hash, manifest_hash, profile, rank_profile_hash):
    obj=_load_json(path,SCHEMA_AUDIT,'Auditoría V1.2.1')
    if obj.get('status')!='numerical_rank_diagnostics_only_no_analog_validation':
        raise ValueError('Auditoría de pesos incorrecta')
    if (obj.get('source_screen_sha256')!=screen_hash or
        obj.get('source_manifest_sha256')!=manifest_hash or
        obj.get('source_rankings',{}).get(profile)!=rank_profile_hash):
        raise ValueError('Auditoría V1.2.1 no coincide con V1.2')
    for name,entry in obj['files'].items():
        _verify_file(entry['file'],entry['sha256'],'Archivo de auditoría '+name)
    seed=_count(obj['seed'],'Semilla auditoría')
    scenarios=_count(obj['scenarios'],'Escenarios auditoría')
    if not 1<=scenarios<=2000 or seed>2**32-1:
        raise ValueError('Escenarios o semilla inválidos')
    return obj,seed,scenarios


def build_uncertainty(correspondence_report, screen_report, manifest, audit_report,
                      scales_report, out_csv, out_report, out_markdown,
                      profile='elysium_planitia', candidates=DEFAULT_IDS, top_ks=(10,25,50)):
    candidates=tuple(candidates)
    if len(candidates)<2 or len(set(candidates))!=len(candidates) or any(not x for x in candidates):
        raise ValueError('Se requieren al menos dos candidatos terrestres distintos')
    if (not top_ks or len(set(top_ks))!=len(top_ks) or
        any(not isinstance(k,int) or k<1 for k in top_ks)):
        raise ValueError('top-k inválidos o repetidos')
    corr=_verify_correspondence(correspondence_report)
    if sha256_file(screen_report)!=corr['source_files']['v12_screen']['sha256']:
        raise ValueError('Ranking V1.2 distinto del usado en V1.3.1')
    report,m,profiles,names,ids,earth,coords,rank_vectors=_load_ranking_matrices(screen_report,manifest)
    if profile not in names:raise ValueError('Perfil MOLA no encontrado')
    if max(top_ks)>len(ids):raise ValueError('top-k supera regiones disponibles')
    ordered_ids=set(ids)
    if not set(candidates).issubset(ordered_ids):
        raise ValueError('Candidato fuera del catálogo topográfico')
    group=_unique_rows([r for r in corr['rows'] if r['mars_profile']==profile],
                       lambda r:r['earth_region_id'],'Correspondencias del perfil')
    if not set(candidates).issubset(group):
        raise ValueError('Faltan candidatos con evidencia GLiM en V1.3.1')
    screen_hash=sha256_file(screen_report); manifest_hash=sha256_file(manifest)
    ranked_map=dict(zip(ids, (int(x) for x in rank_vectors[profile])))
    sc_pos,scale_counts=_read_scale_positions(scales_report,screen_hash,manifest_hash,
                                       candidates,profile,ranked_map)
    entry=next(p for p in report['profiles'] if p['id']==profile)
    audit,seed,scenarios=_read_audit(audit_report,screen_hash,manifest_hash,
                                    profile,entry['ranking_sha256'])
    target=np.array([profiles[profile]['features'][f] for f in F_KEYS],dtype=float)
    signed=_signed(earth,target)
    groups=_groups(signed)
    alt_l2,alt_pct,_=_alternative_scores(signed,earth)
    method_ranks={
        'original': ranked_map,
        'robust_log_l2':dict(zip(ids,map(int,_ranks(alt_l2,ids)))),
        'empirical_percentile_l1':dict(zip(ids,map(int,_ranks(alt_pct,ids)))),
    }
    # Reproduce published watched-candidate values, if present, to catch drift.
    with Path(audit['files']['watched_candidates']['file']).open(encoding='utf-8-sig',newline='') as f:
        for row in csv.DictReader(f):
            if row['profile']==profile and row['region_id'] in candidates:
                key=row['method']
                if key not in method_ranks or method_ranks[key][row['region_id']]!=_count(row['rank'],'Puesto watch'):
                    raise ValueError('Función alternativa no reproduce auditoría V1.2.1')
    rng=np.random.default_rng(seed)
    draws=rng.dirichlet(W*35,size=scenarios)
    weight_positions={rid:[] for rid in candidates}
    idpos={rid:i for i,rid in enumerate(ids)}
    for weights in draws:
        ranks=_ranks(groups@weights,ids)
        for rid in candidates:
            weight_positions[rid].append(int(ranks[idpos[rid]]))
    # Geographic compare is not allowed to convert p04/p08 local detail into points.
    outputs=[]
    for rid in candidates:
        old=group[rid]
        original=ranked_map[rid]
        if old['topographic_rank']!=original:
            raise ValueError('Puesto V1.3.1 no coincide con V1.2 para '+rid)
        if old['topographic_domain_gate']=='blocked_reference_outside_range':
            gate='blocked_out_of_domain'
        elif str(old['topographic_domain_gate']).startswith('caution_'):
            gate='extrapolation_caution'
        else:
            gate='within_sampled_ranges_not_validated'
        lith=_counts_json(old['earth_glim_lithology_counts'],'GLiM '+rid)
        classified=_count(old['earth_classified_points'],'Puntos GLiM')
        sampled=_count(old['earth_sampled_points'],'Puntos GLiM muestreados')
        if classified!=9 or sampled!=9:
            raise ValueError('Comparación equilibrada exige nueve puntos GLiM clasificados por candidato; '+rid)
        obs=_volcanic_leave_one_out(lith,classified)
        scale=sc_pos[rid]
        weights=weight_positions[rid]
        row={
            'earth_region_id':rid,'mars_profile':profile,'topographic_rank_original':original,
            'topographic_gate':gate, 'glim_classified_points':classified,
            'lithology_counts':lith,'earth_lithology_families':_families(lith),
            'refined_lithology_observation':_observed_signature(lith),
            'broad_process_relation_v131':old['broad_process_relation'],
            'volcanic_point_diagnostics':obs,
            'method_ranks':{m:int(v[rid]) for m,v in method_ranks.items()},
            'scale_ranks':scale,
            'top_k_membership':{
                str(k):{'methods_present':sum(method_ranks[m][rid]<=k for m in METHODS),
                        'methods_evaluated':len(METHODS),
                        'scales_present':sum(v is not None and v<=k for v in scale.values()),
                        'scales_evaluated':sum(v is not None for v in scale.values()),
                        'scales_missing':[s for s,v in scale.items() if v is None],
                        'weight_draws_present':sum(r<=k for r in weights),
                        'weight_draws_total':scenarios}
                for k in top_ks},
            'weight_perturbation_ranks':{
                'min':min(weights),'median':float(np.median(weights)),
                'max':max(weights), 'seed':seed,'scenarios':scenarios},
            'sampled_lithology_not_area':True,
            'spatial_independence_not_established':True,
            'local_nasadem_comparison_excluded':'only_Argentina_had_local_nasadem',
            'combined_similarity_score':None,'analog_validated':False,
        }
        outputs.append(row)
    # All 25 anchor records get corrected descriptive labels, including metamorphics.
    controls=[]
    for rid,old in group.items():
        counts=_counts_json(old['earth_glim_lithology_counts'],'GLiM control '+rid)
        if sum(counts.values())!=_count(old['earth_classified_points'],'GLiM control clasificados'):
            raise ValueError('GLiM control inconsistente')
        controls.append({'region_id':rid,'topographic_rank':old['topographic_rank'],
                         'refined_lithology_observation':_observed_signature(counts),
                         'glim_lithology_families':_families(counts),
                         'previous_v131_relation':old['broad_process_relation']})
    controls.sort(key=lambda x:(x['topographic_rank'] is None,x['topographic_rank'] or 10**10,x['region_id']))
    controls_csv=Path(out_csv).with_name(Path(out_csv).stem+'_anchor_controls.csv')
    controls_csv.parent.mkdir(parents=True,exist_ok=True)
    with controls_csv.open('w',encoding='utf-8',newline='') as f:
        wr=csv.DictWriter(f,fieldnames=['region_id','topographic_rank',
            'refined_lithology_observation','glim_lithology_families','previous_v131_relation'])
        wr.writeheader()
        for row in controls:
            wr.writerow({k:(json.dumps(v,ensure_ascii=False,sort_keys=True) if isinstance(v,dict) else v)
                         for k,v in row.items()})
    out_csv=Path(out_csv);out_csv.parent.mkdir(parents=True,exist_ok=True)
    columns=('earth_region_id','mars_profile','topographic_rank_original','topographic_gate',
             'glim_classified_points','refined_lithology_observation','volcanic_observed',
             'leave_one_out_retained','method_ranks','scale_ranks','top_k_membership',
             'weight_perturbation_ranks','combined_similarity_score','analog_validated')
    with out_csv.open('w',encoding='utf-8',newline='') as f:
        wr=csv.DictWriter(f,fieldnames=columns);wr.writeheader()
        for row in outputs:
            v=row['volcanic_point_diagnostics']
            record={**row,'volcanic_observed':v['volcanic_observed'],
                    'leave_one_out_retained':f"{v['leave_one_out_signal_preserved']}/{v['leave_one_out_trials']}"}
            wr.writerow({k:(json.dumps(record[k],ensure_ascii=False,sort_keys=True)
                           if isinstance(record[k],dict) else record[k]) for k in columns})
    source_files={
        'correspondence_v131':str(correspondence_report),
        'screen_v12':str(screen_report),'manifest_v12':str(manifest),
        'audit_v121':str(audit_report),'scales_v121':str(scales_report),
    }
    limitations=[
        f'{len(candidates)} candidatos preseleccionados, no son una muestra aleatoria de regiones terrestres',
        'Nueve puntos GLiM muestreados no describen distribución areal ni independencia espacial',
        'Submuestreo combinatorio y leave-one-out solo reordenan los puntos ya conocidos',
        'Las diferencias entre clases volcánicas básicas, piroclastos e intermedias impiden equivalencia mineralógica',
        'La cartografía USGS SIM3292 y GLiM tienen resolución y taxonomías diferentes',
        '15km re-muestrea datos ETOPO cuya resolución efectiva puede ser mayor',
        'La estabilidad a 60 pesos no demuestra validez geológica ni precisión instrumental',
        'NASADEM local existe para Argentina, NO para ambos rivales: no se usa para compararlos',
        'No se inventa score integrado, probabilidad de similitud, área volcánica ni lugar seguro para misión',
    ]
    doc={
        'schema_version':SCHEMA,'status':STATUS,'profile':profile,
        'candidate_ids':list(candidates),'candidates':outputs,
        'anchor_refined_lithology_controls':controls,
        'common_observation_protocol':{
            'earth_glim':'same 9-point anchor protocol per region, classified counts checked',
            'mars_geology':'same SIM3292 profile-wide point observations for all candidates, not area',
            'topography':'same V1.2 ranking + V1.2.1 alt methods & scale windows',
            'local_nasadem':'excluded from fair three-way comparison',
        },
        'top_ks':list(top_ks),'multiscale_profile_population_counts':scale_counts,
        'weight_draws':{'seed':seed,'scenarios':scenarios,'distribution':'Dirichlet(W*35), historical audit'},
        'sources':{name:{'file':file,'sha256':sha256_file(Path(file))} for name,file in source_files.items()},
        'csv_file':str(out_csv),'csv_sha256':sha256_file(out_csv),
        'anchor_controls_csv':str(controls_csv),'anchor_controls_csv_sha256':sha256_file(controls_csv),
        'limitations':limitations,
    }
    # No ranked "winner" and no one-dimensional priority score.
    md=['# V1.3.2 — Comparación equilibrada de hipótesis geológicas', '',
        '**Diagnóstico descriptivo, NO evaluación de analogía validada.**', '',
        f'Perfil: `{profile}`. Candidatos: {", ".join(candidates)}.', '',
        'Los mismos datos de muestreo y métodos se aplican a todos los candidatos.', '',
        '| Candidato | Puesto 30 km | L2 | Percentil | 15 km | 40 km | Volcánicos GLiM | Leave-one-out |',
        '|---|---:|---:|---:|---:|---:|---|---|']
    for r in outputs:
        pos=r['scale_ranks'];obs=r['volcanic_point_diagnostics']
        fmt=lambda v: str(v) if v is not None else 'sin datos'
        md.append('| '+' | '.join([r['earth_region_id'],str(r['topographic_rank_original']),
            str(r['method_ranks']['robust_log_l2']),str(r['method_ranks']['empirical_percentile_l1']),
            fmt(pos['15km_17x17']),fmt(pos['40km_7x7']),
            f"{obs['volcanic_observed']}/{obs['classified']}",
            f"{obs['leave_one_out_signal_preserved']}/{obs['leave_one_out_trials']}"])+ ' |')
    md.extend(['','## Controles de clasificación GLiM', '',
               'Estos rótulos **corrigen la descripción** de litologías mixtas sin reescribir V1.3.1.', '',
               '| Región | Puesto | Observación refinada |','|---|---:|---|'])
    md.extend(f"| {r['region_id']} | {r['topographic_rank']} | {r['refined_lithology_observation']} |"
              for r in controls)
    md.extend(['','## Interpretación y límites','',*('- '+x for x in limitations),''])
    out_markdown=Path(out_markdown);out_markdown.parent.mkdir(parents=True,exist_ok=True)
    out_markdown.write_text('\n'.join(md),encoding='utf-8')
    doc['markdown_file']=str(out_markdown)
    doc['markdown_sha256']=sha256_file(out_markdown)
    atomic_json(Path(out_report),doc)
    return {'schema_version':SCHEMA,'status':STATUS,'profile':profile,
            'candidates_evaluated':len(outputs),'anchor_controls':len(controls),
            'weight_scenarios':scenarios,'scale_counts':scale_counts,
            'comparison':[{'region_id':r['earth_region_id'],
                           'rank_original':r['topographic_rank_original'],
                           'method_ranks':r['method_ranks'], 'scale_ranks':r['scale_ranks'],
                           'volcanic_glim_points':r['volcanic_point_diagnostics']['volcanic_observed'],
                           'leave_one_out_signal_preserved':r['volcanic_point_diagnostics']['leave_one_out_signal_preserved']}
                          for r in outputs],
            'csv_file':str(out_csv),'anchor_controls_csv':str(controls_csv),'report_file':str(out_report),
            'markdown_file':str(out_markdown),'report_sha256':sha256_file(out_report)}


def review_uncertainty(report_path, region='all'):
    doc=_load_json(report_path,SCHEMA,'Incertidumbre V1.3.2')
    if doc.get('status') != STATUS:raise ValueError('Estado V1.3.2 incompatible')
    _verify_file(doc['csv_file'],doc['csv_sha256'],'V1.3.2 CSV')
    _verify_file(doc['anchor_controls_csv'],doc['anchor_controls_csv_sha256'],'V1.3.2 controles CSV')
    _verify_file(doc['markdown_file'],doc['markdown_sha256'],'V1.3.2 informe')
    for name,entry in doc['sources'].items():
        _verify_file(entry['file'],entry['sha256'],'V1.3.2 fuente '+name)
    rows=[r for r in doc['candidates'] if region=='all' or r['earth_region_id']==region]
    if not rows:raise ValueError('Candidato V1.3.2 no encontrado')
    return {'schema_version':SCHEMA,'status':'balanced_uncertainty_review_no_score',
            'source_sha256':sha256_file(report_path),'profile':doc['profile'],
            'rows':[{k:r[k] for k in ('earth_region_id','topographic_rank_original',
                'refined_lithology_observation','volcanic_point_diagnostics',
                'method_ranks','scale_ranks','top_k_membership','weight_perturbation_ranks',
                'analog_validated')} for r in rows]}
