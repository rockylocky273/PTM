"""V1.2.1: independent numerical audit of V1.2 rankings and controlled scale tests.

Results are diagnostics of a topographic screening algorithm, not evidence that a
location is a physical Mars analogue. Does not change any earlier ranking.
"""
from __future__ import annotations

import csv
import json
import math
from itertools import combinations
from pathlib import Path

import numpy as np
import xarray as xr
from scipy.stats import kendalltau, spearmanr

from .analog_screen import (FEATURES, OFFSET, WEIGHTS, GlobalSampler,
                            patch_features, distance_metrics)
from .mars_profiles_v12 import (_load_profiles, _regions, LOOKUP, SCHEMA,
                                _sampling)
from .download import sha256_file, atomic_json

SCHEMA_AUDIT = 'mars_analog_profile_audit_v1.2.1'
F_KEYS = tuple(FEATURES)
G_NAMES = ('slope', 'roughness', 'relief')
EPS = np.array([OFFSET['slope']]*2+[OFFSET['roughness']]*2+
               [OFFSET['relief']], dtype=float)
W = np.array([WEIGHTS[k] for k in G_NAMES], dtype=float)


def _write_csv(path, fields, rows):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('w', newline='', encoding='utf-8') as out:
        wr = csv.DictWriter(out, fieldnames=list(fields))
        wr.writeheader()
        wr.writerows(rows)
    return {'file': str(path), 'sha256': sha256_file(path)}


def _verify_sources(screen_report, manifest):
    screen_report, manifest = Path(screen_report), Path(manifest)
    report = json.loads(screen_report.read_text(encoding='utf-8'))
    if (report.get('schema_version') != SCHEMA or
        report.get('status') != 'separate_topographic_rankings_not_mars_analog_confirmation'):
        raise ValueError('Se requiere reporte de búsqueda V1.2 válido')
    if report.get('manifest_sha256') != sha256_file(manifest):
        raise ValueError('El manifest no coincide con la búsqueda V1.2')
    m, profiles = _load_profiles(manifest)
    if {p['profile_name'] for p in profiles} != {p['id'] for p in report['profiles']}:
        raise ValueError('Perfiles de manifest y búsqueda inconsistentes')
    if not (report['settings']['weights'] == WEIGHTS and
            report['settings']['regularizers'] == OFFSET and
            math.isclose(report['settings']['spacing_km'], m['spacing_km']) and
            report['settings']['samples'] == m['samples']):
        raise ValueError('Parámetros del algoritmo histórico inconsistentes')
    return report, m, {p['profile_name']: p for p in profiles}


def _load_ranking_matrices(screen_report, manifest):
    report, m, profiles = _verify_sources(screen_report, manifest)
    names = [r['id'] for r in report['profiles']]
    ids = None
    rows_per_profile = {}
    for entry in report['profiles']:
        path = Path(entry['ranking_csv'])
        if sha256_file(path) != entry['ranking_sha256']:
            raise ValueError('SHA-256 del ranking inconsistente: '+entry['id'])
        with path.open(newline='', encoding='utf-8-sig') as f:
            rows = list(csv.DictReader(f))
        if len(rows) != entry['ranked_count'] or not rows:
            raise ValueError('Ranking incompleto: '+entry['id'])
        this_ids = [r['region_id'] for r in rows]
        if len(set(this_ids)) != len(this_ids) or not all(this_ids):
            raise ValueError('IDs terrestres repetidos o vacíos')
        if [int(r['rank']) for r in rows] != list(range(1,len(rows)+1)):
            raise ValueError('Posiciones no consecutivas')
        if ids is None:
            ids = sorted(this_ids)
        if set(this_ids) != set(ids):
            raise ValueError('Las listas V1.2 tienen distintos conjuntos terrestres')
        rows_per_profile[entry['id']] = {r['region_id']:r for r in rows}
    assert ids is not None
    baseline = rows_per_profile[names[0]]
    earth = np.array([[float(baseline[i][key]) for key in F_KEYS] for i in ids])
    coords = np.array([[float(baseline[i]['center_lat']),
                        float(baseline[i]['center_lon_180'])] for i in ids])
    if not np.isfinite(earth).all() or np.any(earth<0):
        raise ValueError('Características terrestres no finitas o negativas')
    if not np.isfinite(coords).all():
        raise ValueError('Coordenadas no finitas')
    rank_vectors={}
    for name in names:
        per = rows_per_profile[name]
        values=np.array([[float(per[i][k]) for k in F_KEYS] for i in ids])
        if not np.allclose(values,earth,atol=1e-7,rtol=1e-7):
            raise ValueError('Distintas características terrestres por perfil: '+name)
        mfeat=profiles[name]['features']
        for i in ids:
            expected=distance_metrics({k:float(per[i][k]) for k in F_KEYS},mfeat)
            for key,value in expected.items():
                if not np.isclose(float(per[i][key]),value,rtol=1e-7,atol=1e-7):
                    raise ValueError('Distancia V1.2 no reproducible: '+name+' '+i+' '+key)
        positions=np.array([int(per[i]['rank']) for i in ids], dtype=int)
        if not np.array_equal(np.sort(positions),np.arange(1,len(ids)+1)):
            raise ValueError('Ranking corrupto: '+name)
        rank_vectors[name]=positions
    return report,m,profiles,names,ids,earth,coords,rank_vectors


def _signed(earth, mars):
    return np.log((earth+EPS)/(np.asarray(mars,dtype=float)+EPS))


def _groups(signed):
    return np.stack((np.abs(signed[...,0:2]).mean(axis=-1),
                     np.abs(signed[...,2:4]).mean(axis=-1),
                     np.abs(signed[...,4])), axis=-1)


def _ranks(scores, ids):
    """1..n deterministic ranks (tie breaking always by region_id)."""
    arr = np.asarray(scores, dtype=float)
    if not np.isfinite(arr).all():
        raise ValueError('Distancia no finita')
    order=np.lexsort((np.asarray(ids),arr))
    rank=np.empty(len(ids),dtype=int)
    rank[order]=np.arange(1,len(ids)+1)
    return rank


def _pairwise(ranks,names,ks):
    n=len(next(iter(ranks.values())))
    output=[]
    for a,b in combinations(names,2):
        ra,rb=ranks[a],ranks[b]
        sp=float(spearmanr(ra,rb).statistic)
        kd=float(kendalltau(ra,rb).statistic)
        record={'profile_a':a,'profile_b':b,'common_candidates':n,
                'spearman_full':round(sp,8),'kendall_full':round(kd,8),
                'identical_full_order':bool(np.array_equal(ra,rb))}
        for k in ks:
            shared=int(np.sum((ra<=k)&(rb<=k)))
            record[f'overlap_top{k}']=shared
            record[f'jaccard_top{k}']=round(shared/(2*k-shared),8)
            record[f'independent_random_expected_overlap_top{k}']=round(k*k/n,5)
        output.append(record)
    return output


def _alternative_scores(signed,earth):
    # Robust feature-scale standardization in log space, positive scale floor.
    x=np.log(earth+EPS)
    mad=1.4826*np.median(np.abs(x-np.median(x,axis=0)),axis=0)
    scale=np.maximum(mad,0.15)  # fixed floor prevents division by zero
    standardized=signed/scale
    robust=np.sqrt((W[0]*np.mean(standardized[:,0:2]**2,axis=1)+
                    W[1]*np.mean(standardized[:,2:4]**2,axis=1)+
                    W[2]*standardized[:,4]**2))
    # Empirical terrestrial CDF; Mars values beyond observed range clamp at 0 or 1.
    pct=np.empty_like(signed)
    for j in range(earth.shape[1]):
        col=np.sort(earth[:,j])
        p_earth=(np.searchsorted(col,earth[:,j],side='right')-0.5)/len(col)
        # signed = log((earth_j+eps)/(mars_j+eps)); recover identical mars value.
        mars_val=np.exp(np.log(earth[0,j]+EPS[j])-signed[0,j])-EPS[j]
        p_mars=np.searchsorted(col,mars_val,side='right')/len(col)
        pct[:,j]=np.abs(p_earth-p_mars)
    percentile=np.sum(_groups(pct)*W,axis=1)
    return robust,percentile,scale


def audit_rankings(screen_report:Path,manifest:Path,out_dir:Path,
                   ks=(25,50,100),scenarios=60,seed=2026,
                   watch=('r026_c146','r068_c061')):
    if not (1<=scenarios<=2000):
        raise ValueError('scenarios debe ser 1..2000')
    if not (0<=seed<=2**32-1):
        raise ValueError('seed fuera de rango')
    report,m,profiles,names,ids,earth,coords,ranks=_load_ranking_matrices(screen_report,manifest)
    n=len(ids)
    if not ks or any(k<1 or k>n for k in ks) or len(set(ks))!=len(ks):
        raise ValueError('Los top-k deben ser únicos y estar en 1..n')
    if len(set(watch))!=len(watch):
        raise ValueError('watch contiene IDs duplicados')
    out_dir=Path(out_dir);out_dir.mkdir(parents=True,exist_ok=True)
    pairs=_pairwise(ranks,names,ks)
    pair_cols=list(pairs[0]) if pairs else []
    pair_file=_write_csv(out_dir/'pairwise_rank_correlations.csv',pair_cols,pairs)
    rng=np.random.default_rng(seed)
    draws=rng.dirichlet(W*35, size=scenarios)
    sat=[]; method_rows=[]; perturb=[]; watch_rows=[]
    for name in names:
        target=np.array([profiles[name]['features'][f] for f in F_KEYS])
        signed=_signed(earth,target)
        gd=_groups(signed)
        base=gd@W
        # Compare numeric scores; floating-point near-ties may be ordered
        # differently by BLAS versus Python's scalar evaluation.
        if not np.all(np.isfinite(base)):
            raise ValueError('Distancias base no finitas: '+name)
        rb,pc,scale=_alternative_scores(signed,earth)
        alternatives={'robust_log_l2':rb,'empirical_percentile_l1':pc}
        for key,scores in alternatives.items():
            r=_ranks(scores,ids)
            method_rows.append({'profile':name,'method':key,
                                'spearman_against_legacy':round(float(spearmanr(r,ranks[name]).statistic),8),
                                'kendall_against_legacy':round(float(kendalltau(r,ranks[name]).statistic),8),
                                'overlap_top25':int(np.sum((r<=min(25,n))&(ranks[name]<=min(25,n)))),
                                'n':n})
            for w in watch:
                if w in ids:
                    j=ids.index(w)
                    watch_rows.append({'profile':name,'region_id':w,'method':key,
                                       'rank':int(r[j]),'original_rank':int(ranks[name][j])})
        for j,key in enumerate(F_KEYS):
            below=np.mean(earth[:,j]<target[j]);above=np.mean(earth[:,j]>target[j])
            sat.append({'profile':name,'feature':key,'mars_value':float(target[j]),
                        'earth_min':float(np.min(earth[:,j])),
                        'earth_median':float(np.median(earth[:,j])),
                        'earth_max':float(np.max(earth[:,j])),
                        'earth_fraction_below_mars':round(float(below),6),
                        'earth_fraction_above_mars':round(float(above),6),
                        'uniform_sign_fraction':round(float(max(below,above)),6),
                        'robust_log_feature_scale':round(float(scale[j]),6)})
        dr=gd@draws.T
        r_original=ranks[name]
        watched=[(w,ids.index(w)) for w in watch if w in ids]
        top=min(25,n)
        for t in range(scenarios):
            r_new=_ranks(dr[:,t],ids)
            pert={'profile':name,'scenario':t,'top25_overlap':int(np.sum((r_new<=top)&(r_original<=top))),
                  'spearman_full':round(float(spearmanr(r_new,r_original).statistic),8),
                  'slope_weight':float(draws[t,0]),'roughness_weight':float(draws[t,1]),
                  'relief_weight':float(draws[t,2])}
            for w,j in watched:
                pert['rank_'+w]=int(r_new[j])
            perturb.append(pert)
        for w,j in watched:
            watch_rows.append({'profile':name,'region_id':w,'method':'original',
                               'rank':int(r_original[j]),'original_rank':int(r_original[j])})
    satfile=_write_csv(out_dir/'feature_saturation.csv',list(sat[0]),sat)
    methodfile=_write_csv(out_dir/'alternative_distance_methods.csv',list(method_rows[0]),method_rows)
    perfile=_write_csv(out_dir/'weight_perturbations.csv',list(perturb[0]),perturb)
    watchfile=_write_csv(out_dir/'watched_candidates.csv',list(watch_rows[0]),watch_rows)
    out={'schema_version':SCHEMA_AUDIT,'status':'numerical_rank_diagnostics_only_no_analog_validation',
         'source_screen_sha256':sha256_file(Path(screen_report)),
         'source_manifest_sha256':sha256_file(Path(manifest)),
         'source_rankings':{p['id']:p['ranking_sha256'] for p in report['profiles']},
         'profiles':names,'common_regions':n,'top_k':list(ks),'scenarios':scenarios,'seed':seed,
         'pairwise':pairs,
         'saturation_summary':{name:{
             'features_with_at_least_95pct_one_sided':sum(
                 r['uniform_sign_fraction']>=0.95 for r in sat if r['profile']==name),
             'features_fully_one_sided':sum(
                 r['uniform_sign_fraction']==1.0 for r in sat if r['profile']==name)}
             for name in names},
         'weight_stability':{name:{
             'mean_top25_overlap':round(float(np.mean([r['top25_overlap'] for r in perturb if r['profile']==name])),3),
             'minimum_top25_overlap':int(min(r['top25_overlap'] for r in perturb if r['profile']==name)),
             'mean_spearman_full':round(float(np.mean([r['spearman_full'] for r in perturb if r['profile']==name])),8)}
             for name in names},
         'files':{'pairwise':pair_file,'feature_saturation':satfile,
                                 'alternative_methods':methodfile,'weight_perturbations':perfile,
                                 'watched_candidates':watchfile},
         'limitations':['Las correlaciones y coincidencias no validan analogía geológica',
                        'El solapamiento aleatorio k²/n no contempla autocorrelación espacial',
                        'La función percentil pierde magnitud fuera del rango terrestre',
                        'Las funciones alternativas son diagnósticos y no reemplazan el ranking V1.2',
                        'La robustez de pesos no prueba capacidad predictiva independiente']}
    target=out_dir/'rank_audit_report.json'
    atomic_json(target,out)
    return {**out,'report_file':str(target),'report_sha256':sha256_file(target)}


def parse_scales(spec):
    result=[]
    for item in spec.split(','):
        parts=item.strip().split(':')
        if len(parts)!=2:
            raise ValueError('Formato de escala debe ser km:n,km:n')
        spacing=float(parts[0]); samples=int(parts[1]);_sampling(spacing,samples)
        if not math.isclose(spacing*(samples-1),240.,abs_tol=1e-8):
            raise ValueError('La auditoría exige ventanas constantes de 240 km')
        if any(math.isclose(spacing,x[0]) for x in result):
            raise ValueError('Escalas repetidas')
        result.append((spacing,samples))
    if len(result)<2 or (30.,9) not in result:
        raise ValueError('Incluir escala histórica 30:9 y al menos una alternativa')
    return result


def audit_scales(screen_report:Path,manifest:Path,earth_file:Path,mars_file:Path,
                 catalog:Path,out_dir:Path,scale_spec='15:17,30:9,40:7',
                 top_k=25):
    scales=parse_scales(scale_spec)
    report,m,profiles,names,ids,earth_baseline,coords,ranks_base=_load_ranking_matrices(screen_report,manifest)
    if (not math.isclose(m['spacing_km'],30) or m['samples']!=9 or
        not math.isclose(report['settings']['spacing_km'],30) or
        report['settings']['samples']!=9):
        raise ValueError('El experimento multiescala compara contra V1.2 a 30 km/9')
    for path,digest in [(earth_file,report['earth_surface_sha256']),
                        (catalog,report['earth_catalog_sha256']),
                        (mars_file,m['source_mola_sha256'])]:
        if sha256_file(Path(path))!=digest:
            raise ValueError('Fuente distinta a V1.2: '+str(path))
    if any(samples<7 for spacing,samples in scales):
        raise ValueError('Se necesitan al menos 7x7 celdas para 16 pendientes interiores válidas')
    region_rows=_regions(catalog)
    if not 1<=top_k<=len(ids):
        raise ValueError('top-k fuera de rango')
    out_dir=Path(out_dir);out_dir.mkdir(parents=True,exist_ok=True)
    matrices={}
    records=[]
    mars_feature_rows=[]
    for spacing,samples in scales:
        key=f'{spacing:g}km_{samples}x{samples}'
        with xr.open_dataset(mars_file) as ds:
            sample=GlobalSampler(ds,'Mars')
            mfeat={}
            for name in names:
                t=LOOKUP[name]
                feat=patch_features(sample.sample(t[2],t[3],spacing,samples),spacing)
                if feat is None or feat['sample_coverage']<.9:
                    raise ValueError('Perfil MOLA inválido a escala '+key+': '+name)
                mfeat[name]=feat
                mars_feature_rows.append({'scale':key,'profile':name,'spacing_km':spacing,'samples':samples,
                                          **{f:feat[f] for f in F_KEYS}})
        collected=[]
        excluded_lat=excluded_cover=0
        with xr.open_dataset(earth_file) as ds:
            sample=GlobalSampler(ds,'Earth')
            for region in region_rows:
                lat=float(region['center_lat']);lon=float(region['center_lon_180'])
                if abs(lat)>report['settings']['max_abs_lat']:
                    excluded_lat+=1; continue
                feat=patch_features(sample.sample(lat,lon,spacing,samples),spacing)
                if feat is None or feat['sample_coverage']<report['settings']['min_patch_coverage']:
                    excluded_cover+=1;continue
                collected.append((region['region_id'],feat,lat,lon))
        matched=[x[0] for x in collected]
        if spacing==30 and samples==9:
            if set(matched)!=set(ids):
                raise ValueError('La muestra 30:9 no reproduce los mismos IDs de V1.2')
            for rid,feat,_,_ in collected:
                baseline=earth_baseline[ids.index(rid)]
                if not np.allclose([feat[k] for k in F_KEYS],baseline,rtol=1e-8,atol=1e-7):
                    raise ValueError('Características 30:9 no reproducidas: '+rid)
        matrices[key]={}
        for name in names:
            scores=np.array([distance_metrics(feat,mfeat[name])['distance_total']
                             for _,feat,_,_ in collected])
            ranks=_ranks(scores,matched)
            if (spacing,samples)==(30,9):
                base_rank={rid:int(ranks_base[name][ids.index(rid)]) for rid in ids}
                if any(int(ranks[j])!=base_rank[rid] for j,rid in enumerate(matched)):
                    raise ValueError('30:9 no reproduce ranking: '+name)
            matrices[key][name]={rid:int(ranks[j]) for j,rid in enumerate(matched)}
            for j,(rid,feat,lat,lon) in enumerate(collected):
                records.append({'scale':key,'mars_profile':name,'region_id':rid,
                                'rank':int(ranks[j]),'distance_total':float(scores[j]),
                                'center_lat':lat,'center_lon_180':lon})
        matrices[key]['_counts']={'ranked':len(collected),'excluded_lat':excluded_lat,
                                  'excluded_cover':excluded_cover,'mars_features':mfeat}
    scale_file=_write_csv(out_dir/'multiscale_rankings.csv',list(records[0]),records)
    feature_file=_write_csv(out_dir/'multiscale_mars_features.csv',list(mars_feature_rows[0]),mars_feature_rows)
    comparative=[]
    base_key='30km_9x9'
    for key,profile_rank in matrices.items():
        if key==base_key:continue
        for name in names:
            rr=profile_rank[name]; orig=matrices[base_key][name]
            common=sorted(set(orig)&set(rr))
            a=np.array([orig[i] for i in common]);b=np.array([rr[i] for i in common])
            # Ranks are global within each scale. Spearman on common IDs still valid.
            rho=float(spearmanr(a,b).statistic) if len(common)>=3 else None
            # top-k overlaps are absolute ranks, not re-ranked common universe.
            a_top={rid for rid,v in orig.items() if v<=top_k}
            b_top={rid for rid,v in rr.items() if v<=top_k}
            comparative.append({'scale':key,'profile':name,'common_candidates':len(common),
                                'baseline_ranked':len(orig),'scale_ranked':len(rr),
                                'spearman_common':round(rho,8) if rho is not None else None,
                                'overlap_top_k':len(a_top&b_top),'top_k':top_k,
                                'only_baseline':len(set(orig)-set(rr)),
                                'only_scale':len(set(rr)-set(orig))})
    compare_file=_write_csv(out_dir/'multiscale_comparison.csv',list(comparative[0]),comparative)
    out={'schema_version':SCHEMA_AUDIT,'status':'fixed_window_multiscale_experiment_no_reranking_of_historical_results',
         'window_center_to_center_km':240.,'scale_specs':scale_spec,
         'source_hashes':{'v12_screen':sha256_file(Path(screen_report)),
                          'v12_manifest':sha256_file(Path(manifest)),
                          'earth':sha256_file(Path(earth_file)),
                          'mars':sha256_file(Path(mars_file)),
                          'catalog':sha256_file(Path(catalog))},
         'scale_counts':{key:entry['_counts'] | {'mars_features':None} for key,entry in matrices.items()},
         'comparisons':comparative,
         'files':{'rankings':scale_file,'comparison':compare_file,'mars_features':feature_file},
         'limitations':['Ventana física constante de 240 km entre centros, N de muestras variable',
                        '15 km puede ser más fino que la resolución efectiva del ETOPO terrestre y puede interpolar',
                        'Los gradientes y rugosidad no son directamente invariantes a escala',
                        'Diferencias de completitud pueden alterar la población de candidatos',
                        'No se modifican rankings V1.2 ni se atribuye litología o validez operativa']}
    output=out_dir/'multiscale_audit_report.json'
    atomic_json(output,out)
    return {**out,'report_file':str(output),'report_sha256':sha256_file(output)}
