"""V1.3.3: Frozen, independently sourced planetary analog reference audit.

This is *not* trained/evaluated geologic classification. External published
analogies concern particular processes/places, while V1.2 rankings compare
240-km MOLA/ETOPO windows over 2-degree terrestrial catalog cells.
Never treat absence/poor rank as refutation or a high rank as validation.
"""
from __future__ import annotations

import csv
import json
import math
import re
from collections import Counter
from pathlib import Path

from .download import sha256_file, atomic_json
from .mars_profiles_v12 import SCHEMA as SCREEN_SCHEMA
from .mars_domain_v122 import DOMAIN_SCHEMA

SCHEMA = 'mars_analog_external_validation_v1.3.3'
STATUS = 'external_reference_retrieval_audit_not_analog_accuracy'
BENCHMARK_SCHEMA = 'mars_analog_external_benchmarks_v1.3.3'
BENCHMARK_FILE = Path('config/external_benchmarks_v1_3_3.json')
FROZEN_BENCHMARK_SHA256 = 'dd78507e3f14dbe3292361934c93cef8bb65940686553c1cd08b85c909fe91a2'
ROLES = {
    'documented_direct_target_analogue',
    'planetary_process_reference_only',
    'process_scope_contrast_not_negative_site',
    'environmental_reference_not_topographic_truth',
}
GRID_ID = re.compile(r'^r\d{3}_c\d{3}$')
SCALES = ('15km_17x17','30km_9x9','40km_7x7')


def _read_json(path):
    return json.loads(Path(path).read_text(encoding='utf-8'))


def _verified(path, sha, description):
    if not isinstance(sha,str) or not re.fullmatch('[a-f0-9]{64}',sha) or not Path(path).is_file():
        raise ValueError(f'{description}: falta archivo o SHA-256 válido')
    if sha256_file(Path(path)) != sha:
        raise ValueError(f'{description}: SHA-256 inconsistente')


def _csv(path, fields, description):
    with Path(path).open(encoding='utf-8-sig',newline='') as f:
        rdr=csv.DictReader(f)
        if not rdr.fieldnames or not set(fields).issubset(rdr.fieldnames):
            raise ValueError(f'{description}: columnas faltantes')
        return list(rdr)


def region_from_latlon(lat, lon):
    """Canonical 2° catalogue cell, *not* nearest-ranked-region selection.

    No generic nearest-neighbor fallback: that could attribute an analog to a
    different volcanic or sedimentary province many km away.
    """
    if (not isinstance(lat,(float,int)) or not isinstance(lon,(float,int)) or
        not math.isfinite(lat) or not math.isfinite(lon) or not (-90 <= lat < 90) or
        not (-180 <= lon <= 180)):
        raise ValueError('Coordenadas terrestres inválidas o fuera de [-180,180]')
    row=int(math.floor((lat+90)/2))
    col=int(math.floor((lon%360)/2))
    if not (0<=row<90 and 0<=col<180):raise ValueError('Celda 2 grados fuera de rango')
    return f'r{row:03d}_c{col:03d}'


def center_of_region(region_id):
    if not isinstance(region_id,str) or not GRID_ID.fullmatch(region_id):
        raise ValueError('ID de celda geográfica inválido')
    r=int(region_id[1:4]); c=int(region_id[6:9])
    if r>=90 or c>=180:raise ValueError('Índice de celda fuera de rango')
    center_lon=(2*c+1+180)%360-180
    return (-89+2*r,center_lon)


def great_circle_km(a,b,c,d):
    """Earth spherical great circle; only describes proxy-center separation."""
    lat1,lat2=math.radians(a),math.radians(c)
    dlat=math.radians(c-a)
    dlon=math.radians((d-b+180)%360-180)
    x=math.sin(dlat/2)**2+math.cos(lat1)*math.cos(lat2)*math.sin(dlon/2)**2
    return 6371.0088*2*math.atan2(math.sqrt(max(0,x)),math.sqrt(max(0,1-x)))


def _validate_benchmark(path, verify_frozen=True):
    if verify_frozen and sha256_file(Path(path)) != FROZEN_BENCHMARK_SHA256:
        raise ValueError('SHA-256 del benchmark congelado no coincide; NO modificar las etiquetas')
    bench=_read_json(path)
    if bench.get('schema_version')!=BENCHMARK_SCHEMA or bench.get('freeze_date')!='2026-11-14':
        raise ValueError('Esquema o fecha del benchmark incorrectos')
    ks=bench.get('protocol',{}).get('predefined_top_ks')
    if ks!=[25,100,250]:raise ValueError('Top-K del protocolo externo alterado')
    cases=bench.get('cases')
    if not isinstance(cases,list) or not cases or len({r.get('case_id') for r in cases})!=len(cases):
        raise ValueError('Casos externos ausentes o repetidos')
    for c in cases:
        if c.get('role') not in ROLES or not isinstance(c.get('case_id'),str) or not c['case_id']:
            raise ValueError('Caso externo con rol/ID incorrecto')
        urls=c.get('sources')
        if not isinstance(urls,list) or not urls or any(not isinstance(u,str) or not u.startswith('https://') for u in urls):
            raise ValueError('Caso externo sin fuentes verificables')
        lat,lon=c.get('site_lat'),c.get('site_lon')
        if (lat is None)!=(lon is None):raise ValueError('Coordenadas incompletas')
        if lat is not None:region_from_latlon(lat,lon)
        if c['role']=='documented_direct_target_analogue' and (lat is None or not c.get('mars_profile')):
            raise ValueError('Una referencia directa requiere lugar y perfil de Marte')
        if c['role']=='environmental_reference_not_topographic_truth' and (lat is not None or c.get('mars_profile')):
            raise ValueError('Analogía ambiental extensa no tiene centro ni perfil topográfico')
    return bench


def _read_screen(screen_path, manifest_path, catalog_path, strict_catalog=True):
    screen=_read_json(screen_path)
    if (screen.get('schema_version')!=SCREEN_SCHEMA or
        screen.get('status')!='separate_topographic_rankings_not_mars_analog_confirmation'):
        raise ValueError('Reporte V1.2 incorrecto')
    _verified(manifest_path,screen['manifest_sha256'],'Manifest MOLA V1.2')
    manifest=_read_json(manifest_path)
    if manifest.get('schema_version')!=SCREEN_SCHEMA or manifest.get('status')!='multi_profiles_built_topography_only':
        raise ValueError('Manifest multirregión V1.2 incorrecto')
    _verified(catalog_path,screen['earth_catalog_sha256'],'Catálogo terrestre V0.6')
    regions=_csv(catalog_path,{'region_id','status','center_lat','center_lon_180'},'Catálogo terrestre')
    if strict_catalog and len(regions)!=16200:
        raise ValueError('Catálogo terrestre debe contener 16200 celdas')
    catalogue={}
    for r in regions:
        rid=r['region_id']
        if rid in catalogue:raise ValueError('Celda terrestre duplicada')
        lat,lon=center_of_region(rid)
        if abs(float(r['center_lat'])-lat)>1e-4 or abs((float(r['center_lon_180'])-lon+180)%360-180)>1e-4:
            raise ValueError('Centros del catálogo no coinciden con su ID: '+rid)
        catalogue[rid]=r
    ranked={}
    identities=[r['id'] for r in screen['profiles']]
    if len(set(identities))!=len(identities) or set(identities)!={r['id'] for r in manifest['profiles']}:
        raise ValueError('Perfiles V1.2 inconsistentes')
    for entry in screen['profiles']:
        p=Path(entry['ranking_csv'])
        _verified(p,entry['ranking_sha256'],'Ranking '+entry['id'])
        rows=_csv(p,{'region_id','rank','center_lat','center_lon_180'},'Ranking '+entry['id'])
        if len(rows)!=entry['ranked_count'] or [int(r['rank']) for r in rows]!=list(range(1,len(rows)+1)):
            raise ValueError('Ranking incompleto o posiciones no consecutivas')
        index={}
        for r in rows:
            rid=r['region_id']
            if rid in index or rid not in catalogue:raise ValueError('Región del ranking inválida o repetida')
            lat,lon=center_of_region(rid)
            if abs(float(r['center_lat'])-lat)>1e-4 or abs((float(r['center_lon_180'])-lon+180)%360-180)>1e-4:
                raise ValueError('Ranking con coordenadas terrestres inconsistentes: '+rid)
            index[rid]=int(r['rank'])
        ranked[entry['id']]=index
    return screen,manifest,catalogue,ranked


def _load_domain(path, names):
    if path is None:
        return {},{}
    doc=_read_json(path)
    if doc.get('schema_version')!=DOMAIN_SCHEMA or doc.get('status')!='numeric_reference_coverage_not_validation':
        raise ValueError('Diagnóstico de dominio V1.2.2 inválido')
    _verified(doc['csv_file'],doc['csv_sha256'],'CSV de dominio')
    domains={r['profile']:r for r in doc['profiles']}
    if set(domains)!=set(names):raise ValueError('Dominio no corresponde a los seis perfiles')
    for x in domains.values():
        if not isinstance(x.get('outside_catalog_minmax'),int) or not 0<=x['outside_catalog_minmax']<=5:
            raise ValueError('Número de características fuera de dominio inválido')
    return domains,{'file':str(path),'sha256':sha256_file(path)}


def _load_scales(path, screen_sha, manifest_sha, sites, profile_names):
    if path is None:return {},{}
    doc=_read_json(path)
    if (doc.get('schema_version')!='mars_analog_profile_audit_v1.2.1' or
        doc.get('status')!='fixed_window_multiscale_experiment_no_reranking_of_historical_results' or
        doc.get('source_hashes',{}).get('v12_screen')!=screen_sha or
        doc['source_hashes'].get('v12_manifest')!=manifest_sha):
        raise ValueError('Auditoría multiescala no corresponde a datos V1.2')
    for entry in doc['files'].values():
        _verified(entry['file'],entry['sha256'],'Archivo de escalas')
    target={(profile,rid) for profile,rid in sites if profile in profile_names}
    lookup={}; seen=set(); n=Counter()
    for r in _csv(doc['files']['rankings']['file'],{'scale','mars_profile','region_id','rank'},'Escalas'):
        scale=r['scale'];profile=r['mars_profile'];rid=r['region_id']
        if scale not in SCALES:raise ValueError('Escala desconocida: '+scale)
        n[scale,profile]+=1
        if (profile,rid) in target:
            key=(scale,profile,rid)
            if key in seen:raise ValueError('Posición multiescala repetida')
            seen.add(key)
            value=int(r['rank'])
            if value<1:raise ValueError('Puesto multiescala inválido')
            lookup[key]=value
    for profile in profile_names:
        if any(n[scale,profile]<1 for scale in SCALES):
            raise ValueError('Una escala no contiene el perfil '+profile)
    return lookup,{'file':str(path),'sha256':sha256_file(path)}


def _screening_cause(rid, catalogue, screen):
    row=catalogue.get(rid)
    if row is None:return 'cell_absent_from_earth_catalog'
    if row['status']!='land_candidate_unranked':return 'excluded_by_earth_land_catalog'
    lat,_=center_of_region(rid)
    if abs(lat)>float(screen['settings']['max_abs_lat']):return 'excluded_by_latitude_threshold'
    return 'excluded_by_earth_patch_coverage_or_derivatives'


def _case_result(case, catalogue, ranked, domain, scales, screen):
    role=case['role'];profile=case.get('mars_profile')
    record={
        'case_id':case['case_id'], 'site_name':case['site_name'],
        'role':role,'process_scope':case['process_scope'],
        'mars_profile':profile,'external_sources':case['sources'],
        'site_lat':case.get('site_lat'),'site_lon':case.get('site_lon'),
        'reference_statement':case['reference_statement'],
        'external_claim_independent_of_ranking':True,
        'geological_analogy_proven_by_engine':False,
        'site_scale_matches_240km_screen':False,
        'validation_outcome':'inconclusive_on_geological_analogy',
    }
    if role=='environmental_reference_not_topographic_truth':
        record.update(evaluation_status='out_of_scope_environmental_reference',
                      earth_region_id=None,topographic_rank=None)
        return record
    rid=region_from_latlon(case['site_lat'],case['site_lon'])
    clat,clon=center_of_region(rid)
    record.update(earth_region_id=rid,cell_center_lat=clat,
                  cell_center_lon_180=clon,
                  site_to_cell_center_km=round(great_circle_km(case['site_lat'],case['site_lon'],clat,clon),3),
                  earth_catalog_cell_status=catalogue.get(rid,{}).get('status','missing'))
    if role=='process_scope_contrast_not_negative_site':
        record.update(evaluation_status='blocked_process_scope_contrast',
                      topographic_rank=None,control_is_negative_geology_label=False)
        return record
    if role=='planetary_process_reference_only':
        record.update(evaluation_status='reference_without_specific_mars_profile',
                      topographic_rank=None)
        return record
    if profile not in ranked:raise ValueError('Perfil externo no disponible: '+str(profile))
    found=ranked[profile].get(rid)
    d=domain.get(profile)
    record.update(
        topographic_rank=found,
        compared_earth_regions=len(ranked[profile]),
        domain_flag=d['domain_flag'] if d else 'domain_report_not_supplied',
        outside_catalog_minmax=d['outside_catalog_minmax'] if d else None,
        top_k={str(k):(found<=k if found is not None else None) for k in screen.get('external_top_ks',(25,100,250))},
        within_profile_percentile_approx=round(100*found/len(ranked[profile]),4) if found is not None else None,
        screening_exclusion_reason=_screening_cause(rid,catalogue,screen) if found is None else None,
    )
    rank_scale={s:scales.get((s,profile,rid)) for s in SCALES} if scales else {}
    if rank_scale and found is not None and rank_scale['30km_9x9']!=found:
        raise ValueError('Escala 30km no reproduce el puesto para sitio externo '+case['case_id'])
    record['scale_ranks']=rank_scale
    if found is None:
        record['evaluation_status']='external_site_not_in_screened_population'
    elif d and d['outside_catalog_minmax']>0:
        record['evaluation_status']='topography_outside_reference_domain'
    else:
        record['evaluation_status']='topographic_retrieval_descriptor_only'
    return record


def build_external_validation(benchmark,screen,manifest,catalog,domain,scales,
                              out_csv,out_report,out_markdown,verify_frozen=True,
                              strict_catalog=True):
    bench=_validate_benchmark(benchmark,verify_frozen=verify_frozen)
    src,m,earth,ranked=_read_screen(screen,manifest,catalog,strict_catalog=strict_catalog)
    known_profiles=set(ranked)
    for case in bench['cases']:
        if case.get('mars_profile') and case['mars_profile'] not in known_profiles:
            raise ValueError('Referencia no corresponde a perfil registrado: '+case['case_id'])
    domains,dref=_load_domain(domain,known_profiles)
    sites={(c['mars_profile'],region_from_latlon(c['site_lat'],c['site_lon'])) for c in bench['cases']
           if c['role']=='documented_direct_target_analogue'}
    scales_idx,sref=_load_scales(scales,sha256_file(screen),sha256_file(manifest),sites,known_profiles)
    source_records={'benchmark':{'file':str(benchmark),'sha256':sha256_file(benchmark)},
                    'screen_v12':{'file':str(screen),'sha256':sha256_file(screen)},
                    'manifest_v12':{'file':str(manifest),'sha256':sha256_file(manifest)},
                    'earth_catalog':{'file':str(catalog),'sha256':sha256_file(catalog)}}
    # Retain direct hashes for ranking CSVs too, not just the V1.2 screen
    # metadata.  The review command can therefore detect a ranking replaced
    # or edited after this report was created.
    for entry in src['profiles']:
        source_records['ranking_'+entry['id']]={
            'file':entry['ranking_csv'],'sha256':entry['ranking_sha256']}
    if dref:source_records['reference_domain']=dref
    if sref:source_records['multiscale_audit']=sref
    # No benchmarking of an ad-hoc modified reference list.
    src['external_top_ks']=tuple(bench['protocol']['predefined_top_ks'])
    rows=[_case_result(c,earth,ranked,domains,scales_idx,src) for c in bench['cases']]
    tallies=Counter(r['evaluation_status'] for r in rows)
    direct=[r for r in rows if r['role']=='documented_direct_target_analogue']
    summary={
        'external_cases':len(rows),'direct_target_process_analogues':len(direct),
        'direct_sites_represented_in_ranked_population':sum(x['topographic_rank'] is not None for x in direct),
        'direct_sites_missing_from_ranked_population':sum(x['topographic_rank'] is None for x in direct),
        'direct_sites_with_mars_profile_out_of_domain':sum(x.get('outside_catalog_minmax',0)>0 for x in direct),
        'scope_contrasts_blocked':tallies['blocked_process_scope_contrast'],
        'environmental_references_not_misused':tallies['out_of_scope_environmental_reference'],
        'per_status':dict(sorted(tallies.items())),
        'validated_analogs':0,
        'accuracy_or_auc':None,
    }
    # Write only after all source hashes and consistency checks succeed.
    out_csv=Path(out_csv);out_report=Path(out_report);out_markdown=Path(out_markdown)
    for p in (out_csv,out_report,out_markdown):p.parent.mkdir(parents=True,exist_ok=True)
    fields=['case_id','site_name','role','mars_profile','process_scope','earth_region_id',
            'site_to_cell_center_km','earth_catalog_cell_status','topographic_rank',
            'within_profile_percentile_approx','top_k','scale_ranks',
            'domain_flag','outside_catalog_minmax','screening_exclusion_reason',
            'evaluation_status','validation_outcome','geological_analogy_proven_by_engine']
    with out_csv.open('w',newline='',encoding='utf-8') as f:
        wr=csv.DictWriter(f,fieldnames=fields);wr.writeheader()
        for r in rows:
            wr.writerow({key:(json.dumps(r[key],ensure_ascii=False,sort_keys=True) if isinstance(r.get(key),dict)
                            else r.get(key)) for key in fields})
    notes=[
        'Las cuatro referencias directas fueron publicadas con propósitos de proceso/ambiente, NO para validar un algoritmo de ventanas de 240 km.',
        'La celda terrestre de 2 grados no equivale al sitio puntual; no se selecciona la celda elegible más cercana como sustituto.',
        'La ausencia del sitio en el catálogo puede deberse al filtro de costa, cobertura, latitud o resolución.',
        'Un ranking pobre no refuta las analogías citadas; un ranking alto no confirma equivalencia de litología, procesos ni mineralogía.',
        'Contrastes de procesos son negativos de alcance de una HIPÓTESIS, no sitios con geología negativa verificada.',
        'El catálogo externo es pequeño, selectivo y no aleatorio; se prohíben accuracy/AUC y tuning de pesos sobre estos casos.',
        'El control de extrapolación topográfica precede cualquier interpretación; Olympus Mons requiere escala y validación adicionales.',
        'No se calculan probabilidades, scores de similitud, ni certificación de terrenos para rover o hábitat.',
    ]
    out_markdown.write_text('\n'.join([
        '# V1.3.3 — Referencias externas registradas antes de ver sus puestos','',
        '> **Auditoría descriptiva de recuperación.** Ningún resultado valida o refuta científicamente la analogía publicada.','',
        '| Caso | Perfil | Celda 2° | Puesto | Estado |','|---|---|---|---:|---|',
        *[f"| {r['case_id']} | {r['mars_profile'] or 'no aplicable'} | {r.get('earth_region_id') or '—'} | {r.get('topographic_rank') or '—'} | {r['evaluation_status']} |" for r in rows],
        '','## Principales límites','',*('- '+n for n in notes),'',
        '## Registro de fuentes externas','',
        *[f"- **{r['case_id']}** — {r['reference_statement']}. Fuentes: "+', '.join(r['external_sources']) for r in rows],''
    ]),encoding='utf-8')
    report={
        'schema_version':SCHEMA,'status':STATUS,'benchmark_frozen_date':bench['freeze_date'],
        'benchmark_is_independent_external_claim_catalog':True,
        'results':rows,'summary':summary,'protocol':bench['protocol'],
        'source_files':source_records,
        'csv_file':str(out_csv),'csv_sha256':sha256_file(out_csv),
        'markdown_file':str(out_markdown),'markdown_sha256':sha256_file(out_markdown),
        'limitations':notes,'all_analogs_validated':False,
    }
    atomic_json(out_report,report)
    return {'schema_version':SCHEMA,'status':STATUS,'summary':summary,
            'report_file':str(out_report),'report_sha256':sha256_file(out_report),
            'csv_file':str(out_csv),'markdown_file':str(out_markdown)}


def review_external_validation(report,case_id='all'):
    doc=_read_json(report)
    if doc.get('schema_version')!=SCHEMA or doc.get('status')!=STATUS:
        raise ValueError('Informe V1.3.3 inválido')
    _verified(doc['csv_file'],doc['csv_sha256'],'CSV de referencia externa')
    _verified(doc['markdown_file'],doc['markdown_sha256'],'Markdown referencia externa')
    for k,meta in doc['source_files'].items():
        _verified(meta['file'],meta['sha256'],'Fuente externa '+k)
    if len({r['case_id'] for r in doc['results']})!=len(doc['results']):
        raise ValueError('Casos repetidos en el informe')
    filtered=doc['results'] if case_id=='all' else [r for r in doc['results'] if r['case_id']==case_id]
    if not filtered:raise ValueError('Caso externo no encontrado: '+case_id)
    return {'schema_version':SCHEMA,'status':'review_external_scientific_references_not_accuracy',
            'source_sha256':sha256_file(report), 'filter':case_id,'summary':doc['summary'],'cases':filtered}
