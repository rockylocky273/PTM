"""V1.3.1: process-level *hypotheses*, never lithologic/planetary equivalence.

USGS SIM3292 records cartographic units (Mars), GLiM records sampled
lithology (Earth). Keywords and classes are weak evidence of related broad
process families, not proof of the same material/process, and absence in nine
points is not counterevidence of absence in the surrounding area.
"""
from __future__ import annotations

import csv
import json
from collections import Counter, defaultdict
from pathlib import Path

from .download import atomic_json, sha256_file
from .geology_glim import ALLOWED, VOLCANIC, FILL
from .mars_geology_v122 import SOURCE as MARS_SOURCE, SUMMARY_SCHEMA
from .mars_domain_v122 import DOMAIN_SCHEMA
from .mars_profiles_v12 import SCHEMA as SCREEN_SCHEMA
from .mars_multicriteria_v130 import (
    SCHEMA as MULTI_SCHEMA, _load_json, _read_csv, _verify_file,
    _counts_json, _count, _finite_nonneg, _domain_gate, _unique_rows,
    _geology_signal,
)

SCHEMA = 'mars_analog_process_correspondence_v1.3.1'
LOCAL_SCHEMA = 'mars_analog_local_volcanic_terrain_v1.1.2'
MARS_VOLCANIC_WORDS = ('volcanic', 'volcanism')
MARS_IMPACT_WORDS = ('impact',)
MARS_UNDETERMINED = ('undivided', 'transition', 'highland', 'lowland')
PLUTONIC = frozenset({'Acid plutonic rocks', 'Basic plutonic rocks',
                       'Intermediate plutonic rocks'})
SEDIMENT = frozenset({'Carbonate sedimentary rocks', 'Evaporites',
                      'Mixed sedimentary rocks', 'Siliciclastic sedimentary rocks',
                      'Unconsolidated sediments'})


def _load_sources(multicriteria_report, geology_report, domain_report, glim_csv, screen_report):
    multi = _load_json(multicriteria_report, MULTI_SCHEMA, 'V1.3.0 multicriterio')
    if multi.get('status') != 'noncompensatory_evidence_triage_no_joint_similarity_score':
        raise ValueError('V1.3.0: estado desconocido')
    _verify_file(multi['csv_file'], multi['csv_sha256'], 'CSV V1.3.0')
    if multi.get('markdown_sha256') is not None:
        _verify_file(multi['markdown_file'], multi['markdown_sha256'], 'Markdown V1.3.0')
    binding = [
        ('v122_mars_geology_report', geology_report),
        ('v122_domain_report', domain_report),
        ('earth_glim_csv', glim_csv),
        ('v12_screen_report', screen_report),
    ]
    for key, path in binding:
        meta = multi.get('sources', {}).get(key, {})
        if not meta or Path(meta.get('file','')) != Path(path):
            raise ValueError(f'Fuente {key}: ruta distinta del registro V1.3.0')
        _verify_file(path, meta.get('sha256'), f'Fuente V1.3.0: {key}')
    geology = _load_json(geology_report, SUMMARY_SCHEMA, 'Geología Mars V1.2.2')
    domain = _load_json(domain_report, DOMAIN_SCHEMA, 'Dominio V1.2.2')
    screen = _load_json(screen_report, SCREEN_SCHEMA, 'Rankings V1.2')
    if geology.get('source') != MARS_SOURCE or geology.get('pending_points') != 0:
        raise ValueError('Geología marciana incompleta o procedencia inesperada')
    if screen.get('status') != 'separate_topographic_rankings_not_mars_analog_confirmation':
        raise ValueError('Rankings V1.2 con estado incompatible')
    for obj, label in ((geology, 'Geología Marte'), (domain, 'Dominio')):
        _verify_file(obj['csv_file'], obj['csv_sha256'], label + ' CSV')
    return multi, geology, domain, screen


def _mars_process_units(profile):
    counts = _counts_json(profile['unit_code_counts'], 'Conteos SIM3292')
    descriptions = profile['descriptions']
    try:
        descriptions = json.loads(descriptions) if isinstance(descriptions, str) else descriptions
    except (ValueError, TypeError) as exc:
        raise ValueError('Descripciones de Marte malformadas') from exc
    if not isinstance(descriptions, dict) or set(counts) != set(descriptions):
        raise ValueError('Descripciones y códigos marcianos no coinciden')
    if sum(counts.values()) != _count(profile['mapped'], 'Muestras Marte clasificadas'):
        raise ValueError('Conteo de muestras marcianas inconsistente')
    families = defaultdict(list)
    for code in sorted(counts):
        desc = descriptions[code]
        if not isinstance(desc, str):
            raise ValueError('Descripción geológica no textual')
        low = desc.lower()
        if any(word in low for word in MARS_VOLCANIC_WORDS):
            family = 'volcanic_cartographic_unit'
        elif any(word in low for word in MARS_IMPACT_WORDS):
            family = 'impact_cartographic_unit'
        else:
            # Other units cannot be assigned a material/process purely by name.
            family = 'not_process_diagnostic_from_unit_name'
        families[family].append({'unit_code': code, 'unit_description': desc,
                                 'point_observations': counts[code]})
    return dict(families), counts


def _earth_class_families(counts, classified):
    if sum(counts.values()) != classified:
        raise ValueError('GLiM: conteos no coinciden con puntos clasificados')
    unknown = set(counts) - ALLOWED
    if unknown:
        raise ValueError(f'GLiM: etiquetas no reconocidas: {sorted(unknown)}')
    families = defaultdict(list)
    for label in sorted(counts):
        if label in VOLCANIC:
            family = 'volcanic_or_pyroclastic_lithology'
        elif label in PLUTONIC:
            family = 'plutonic_lithology_not_eruption_evidence'
        elif label in SEDIMENT:
            family = 'sedimentary_or_unconsolidated_lithology'
        elif label in FILL:
            family = 'non_geological_fill'
        else:
            family = 'other_lithology'
        families[family].append({'glim_class':label,'point_observations': counts[label]})
    return dict(families)


def _relation(mars_fam, earth_fam, mars_n, earth_n):
    mvol = bool(mars_fam.get('volcanic_cartographic_unit'))
    mimpact = bool(mars_fam.get('impact_cartographic_unit'))
    evol = bool(earth_fam.get('volcanic_or_pyroclastic_lithology'))
    eplut = bool(earth_fam.get('plutonic_lithology_not_eruption_evidence'))
    esed = bool(earth_fam.get('sedimentary_or_unconsolidated_lithology'))
    cautions = ['map_taxonomies_and_geologic_ages_not_equivalent',
                'point_frequencies_not_area_fractions']
    if mimpact:
        cautions.append('martian_impact_origin_cannot_be_checked_from_glim_lithology')
    if mvol and eplut:
        cautions.append('plutonic_rock_class_must_not_be_interpreted_as_eruptive_volcanism')
    if not mars_n or not earth_n:
        return 'insufficient_point_observations', 'missing_evidence_not_negative', cautions
    if mvol and evol:
        return 'broad_volcanic_cartography_and_lithology_signal', 'process_hypothesis_only', cautions
    if mvol and not evol:
        if eplut:
            return 'martian_volcanic_earth_plutonic_only_or_other', 'eruptive_process_not_established', cautions
        if esed:
            return 'martian_volcanic_earth_sediment_observed_only', 'volcanism_not_observed_not_disproved', cautions
        return 'martian_volcanic_not_observed_in_earth_samples', 'unknown_not_incompatible', cautions
    if not mvol and evol:
        return 'earth_volcanic_mars_volcanic_unit_not_sampled', 'mars_process_unresolved', cautions
    return 'no_broad_shared_process_demonstrated', 'unknown_not_incompatible', cautions


def build_correspondences(multicriteria_report, geology_report, domain_report, glim_csv,
                          screen_report, out_csv, out_json, out_markdown, top_n=25):
    """All GLiM-sampled anchors x six MOLA profiles, not a global census."""
    if not 1 <= top_n <= 500:
        raise ValueError('top-n debe estar entre 1 y 500')
    multi, geology, domain, screen = _load_sources(
        multicriteria_report, geology_report, domain_report, glim_csv, screen_report)
    mars = _unique_rows(geology['profiles'],lambda p:p['profile_id'],'Perfiles Marte')
    gates = _unique_rows(domain['profiles'],lambda p:p['profile'],'Perfiles dominio')
    if set(mars) != set(gates):
        raise ValueError('Perfiles geológicos y dominio incompatibles')
    glims = _unique_rows(_read_csv(glim_csv, ['region_id','classified',
        'observed_lithology_classes','basic_volcanic_sample_count'], 'GLiM muestreos'),
        lambda r:r['region_id'],'Muestras GLiM')
    if len(glims) > 10000:
        raise ValueError('Demasiados candidatos GLiM para una auditoría puntual')
    historical = _unique_rows(multi['candidates'],
        lambda r:(r['mars_profile'],r['earth_region_id']), 'Registros V1.3.0')
    profiles = _unique_rows(screen['profiles'],lambda r:r['id'],'Rankings perfil')
    if set(profiles) != set(mars):
        raise ValueError('Perfiles de rankings difieren de los de geología')
    entries=[]
    for pid in sorted(mars):
        geo, gate = mars[pid], gates[pid]
        m_families,mcounts = _mars_process_units(geo)
        gd = _domain_gate(gate)
        p = profiles[pid]
        _verify_file(p['ranking_csv'],p['ranking_sha256'],'Ranking '+pid)
        ranking = _unique_rows(_read_csv(p['ranking_csv'],
            ['region_id','rank','distance_total'], 'Ranking '+pid),
            lambda r:r['region_id'],'Ranking '+pid)
        if len(ranking)!=_count(p['ranked_count'],'Ranking: cantidad'):
            raise ValueError('Ranking original: cantidad inválida: '+pid)
        ids = [_count(r['rank'],'Ranking puesto') for r in ranking.values()]
        if sorted(ids)!=list(range(1,len(ids)+1)):
            raise ValueError('Rankings no consecutivos o puestos duplicados: '+pid)
        for rid in sorted(glims):
            e=glims[rid]
            ec=_counts_json(e['observed_lithology_classes'],'GLiM '+rid)
            n=_count(e['classified'],'GLiM clasificados')
            sampled=_count(e.get('sampled') or e['classified'],'GLiM muestreados')
            if n>sampled or _count(e['basic_volcanic_sample_count'],'GLiM básicas')!=ec.get('Basic volcanic rocks',0):
                raise ValueError('GLiM: muestras y volcánicas básicas no coinciden')
            ef=_earth_class_families(ec,n)
            er=ranking.get(rid)
            original=historical.get((pid,rid))
            if er is None:
                if original is not None:
                    raise ValueError('Registro V1.3.0 sin candidato en ranking V1.2')
                rank=None; distance=None; in_shortlist=False
            else:
                rank = _count(er['rank'],'Puesto topográfico')
                distance = _finite_nonneg(er['distance_total'],'Distancia topográfica')
                in_shortlist = rank <= top_n
            if original is not None:
                if (rank is None or original['topographic_rank_v12']!=rank or
                    abs(original['topographic_distance_v12']-distance)>1e-9 or
                    original['topographic_gate']!=gd or
                    original['earth_glim_classes']!=ec or
                    original['mars_geology_units']!=mcounts or
                    original['geological_signal'] != _geology_signal(geo,ec,n)[0]):
                    raise ValueError('La evidencia V1.3.0 difiere del recálculo V1.3.1: '+pid+'/'+rid)
            relation, proof, warnings = _relation(m_families,ef,
                    _count(geo['mapped'],'Muestras de Marte'),n)
            if gd == 'blocked_reference_outside_range':
                triage='hold_martian_topographic_reference_domain'
            elif gd.startswith('caution_'):
                triage='review_topographic_reference_extrapolation'
            elif rank is None:
                triage='not_ranked_or_excluded_from_topographic_catalog'
            elif in_shortlist and relation == 'broad_volcanic_cartography_and_lithology_signal':
                triage='targeted_volcanic_process_hypothesis_followup'
            elif in_shortlist:
                triage='topographic_shortlist_geology_requires_independent_validation'
            elif relation == 'broad_volcanic_cartography_and_lithology_signal':
                triage='volcanic_signal_outside_topographic_shortlist'
            else:
                triage='not_prioritized_under_current_evidence'
            entries.append({
                'mars_profile':pid,'earth_region_id':rid,
                'topographic_rank':rank,'topographic_distance':distance,
                'topographic_domain_gate':gd,'top_n_threshold':top_n,
                'in_top_n':in_shortlist,'mars_mapped_points':_count(geo['mapped'],'Muestras Marte'),
                'mars_unit_counts':mcounts,'mars_units_by_process_label':m_families,
                'earth_sampled_points':sampled,'earth_classified_points':n,
                'earth_glim_lithology_counts':ec,'earth_classes_by_lithology_family':ef,
                'broad_process_relation':relation,'inference_strength':proof,
                'interpretation_limits':warnings,
                'research_triage':triage,
                'previously_examined_v130':original is not None,
                'v130_workflow_triage': original['workflow_triage'] if original else None,
                'v130_scale_shortlist_stability': original['scale_shortlist_stability'] if original else None,
                'hard_geologic_incompatibility_confirmed':False,
                'rock_mineralogy_equivalence':'NOT_TESTED',
                'geologic_age_equivalence':'NOT_TESTED',
                'areal_unit_coverage':'NOT_MEASURED',
                'analog_validated':False,'combined_similarity_score':None,
            })
    emitted_pairs={(r['mars_profile'],r['earth_region_id']) for r in entries}
    for pair in historical:
        if pair not in emitted_pairs:
            raise ValueError('Falta una combinación previamente examinada en V1.3.0')
    entries.sort(key=lambda e:(e['mars_profile'], e['topographic_rank'] is None,
                               e['topographic_rank'] if e['topographic_rank'] is not None else 10**8,
                               e['earth_region_id']))
    dest=Path(out_csv);dest.parent.mkdir(parents=True,exist_ok=True)
    fieldnames=['mars_profile','earth_region_id','topographic_rank','topographic_distance',
                'topographic_domain_gate','in_top_n','mars_mapped_points','mars_unit_counts',
                'earth_classified_points','earth_glim_lithology_counts',
                'broad_process_relation','inference_strength','research_triage',
                'previously_examined_v130','hard_geologic_incompatibility_confirmed',
                'analog_validated','combined_similarity_score']
    with dest.open('w',encoding='utf-8',newline='') as f:
        wr=csv.DictWriter(f,fieldnames=fieldnames);wr.writeheader()
        for row in entries:
            wr.writerow({k: json.dumps(row[k],ensure_ascii=False,sort_keys=True)
                        if isinstance(row[k],dict) else row[k] for k in fieldnames})
    report={
        'schema_version':SCHEMA,
        'status':'process_hypotheses_and_contrasts_no_geological_equivalence_score',
        'profiles':len(mars),'glim_sampled_regions':len(glims),
        'pairs':len(entries),'prior_v130_pairs':len(historical),'top_n':top_n,
        'triage_counts':dict(sorted(Counter(r['research_triage'] for r in entries).items())),
        'process_relation_counts':dict(sorted(Counter(r['broad_process_relation'] for r in entries).items())),
        'source_files':{
            'v130': {'path':str(multicriteria_report),'sha256':sha256_file(multicriteria_report)},
            'mars_geology': {'path':str(geology_report),'sha256':sha256_file(geology_report)},
            'earth_glim': {'path':str(glim_csv),'sha256':sha256_file(glim_csv)},
            'domain': {'path':str(domain_report),'sha256':sha256_file(domain_report)},
            'v12_screen': {'path':str(screen_report),'sha256':sha256_file(screen_report)},
        },'csv_file':str(dest),'csv_sha256':sha256_file(dest),
        'rows':entries,
        'limitations':[
            'GLiM son 25 (u otra cantidad) anclas muestreadas, NO censo global ni top25 literal',
            'Nueve puntos marcianos y terrestres NO representan proporciones de superficie',
            'El mapa USGS SIM 3292 no determina composición mineralógica de cada punto',
            'Clases litológicas GLiM y unidades marcianas no son categorías equivalentes',
            'Ausencia de una categoría en puntos no demuestra incompatibilidad del terreno',
            'Plutónico no se interpreta como volcánico eruptivo',
            'Una unidad de impacto no implica lithología específica bajo GLiM',
            'No existe score geológico ni similitud total; no hay validación independiente',
            'Sin evaluación climática marciana, operabilidad, seguridad de rover o hábitat',
        ]}
    md=['# V1.3.1 — Correspondencia geológica por hipótesis de procesos', '',
        '**Sin porcentaje de similitud; sin equivalencia mineralógica ni certificación de análogo.**', '',
        f'Perfiles: {len(mars)}; anclas GLiM: {len(glims)}; comparaciones: {len(entries)}.', '',
        'No hay contradicción geológica *demostrada* por la sola ausencia de una clase en muestreos.', '']
    for pid in sorted(mars):
        md.extend([f'## {pid}','','| Tierra | Puesto | Dominio | Relación cartográfica | Siguiente revisión |',
                   '|---|---:|---|---|---|'])
        for row in entries:
            if row['mars_profile'] != pid: continue
            md.append('| '+' | '.join(str(item).replace('|','/') for item in (
                row['earth_region_id'],row['topographic_rank'] or 'sin ranking',
                row['topographic_domain_gate'],row['broad_process_relation'],
                row['research_triage'])) + ' |')
        md.append('')
    md.extend(['## Límites', '',*('- '+x for x in report['limitations']),''])
    out_markdown=Path(out_markdown);out_markdown.parent.mkdir(parents=True,exist_ok=True)
    out_markdown.write_text('\n'.join(md),encoding='utf-8')
    report['markdown_file']=str(out_markdown)
    report['markdown_sha256']=sha256_file(out_markdown)
    atomic_json(Path(out_json),report)
    return {'schema_version':SCHEMA,'status':report['status'],
            'profiles':report['profiles'],'glim_sampled_regions':report['glim_sampled_regions'],
            'pairs':report['pairs'],'previously_examined_pairs':report['prior_v130_pairs'],
            'triage_counts':report['triage_counts'],'process_relation_counts':report['process_relation_counts'],
            'csv_file':str(dest),'report_file':str(out_json),
            'markdown_file':str(out_markdown),'report_sha256':sha256_file(out_json)}


def review_correspondences(report_path, profile='elysium_planitia', region='all', limit=25):
    if limit < 1 or limit>250:
        raise ValueError('--limit entre 1 y 250')
    doc = _load_json(report_path,SCHEMA,'Correspondencia V1.3.1')
    if doc.get('status') != 'process_hypotheses_and_contrasts_no_geological_equivalence_score':
        raise ValueError('V1.3.1: estado inválido')
    _verify_file(doc['csv_file'],doc['csv_sha256'],'CSV V1.3.1')
    _verify_file(doc['markdown_file'],doc['markdown_sha256'],'Markdown V1.3.1')
    known = {row['mars_profile'] for row in doc['rows']}
    if profile!='all' and profile not in known:
        raise ValueError('Perfil no encontrado')
    hits = [r for r in doc['rows'] if (profile=='all' or r['mars_profile']==profile)
            and (region=='all' or r['earth_region_id']==region)]
    if region!='all' and not hits:
        raise ValueError('Región no encontrada en perfil solicitado')
    out=[]
    for r in hits[:limit]:
        out.append({k:r[k] for k in ('mars_profile','earth_region_id','topographic_rank',
            'topographic_domain_gate','mars_unit_counts','earth_glim_lithology_counts',
            'broad_process_relation','inference_strength','research_triage',
            'previously_examined_v130','v130_scale_shortlist_stability','analog_validated')})
    return {'schema_version':SCHEMA,'status':'interpretive_process_review_no_rank_combination',
            'source_sha256':sha256_file(report_path),'profile':profile,'region':region,
            'matches':len(hits),'returned':len(out),'rows':out}


def review_local_nasadem(p04, p08, out_json):
    """Retain spatially restricted *terrestrial* volcanic clipping context.

    Do not infer Mars/Earth lithologic equivalence from these measurements.
    """
    rows=[]
    for label,path in [('p04',p04),('p08',p08)]:
        obj=_load_json(path,LOCAL_SCHEMA,'NASADEM '+label)
        if obj.get('point_id')!='r026_c146_'+label or obj.get('region_id')!='r026_c146':
            raise ValueError('NASADEM: no corresponde al sector '+label)
        if not str(obj.get('status','')).startswith('descriptive_nasadem_30m_'):
            raise ValueError('NASADEM: estado no reconocido')
        _verify_file(obj['output_netcdf'],obj['output_netcdf_sha256'],'NetCDF NASADEM '+label)
        _verify_file(obj['glim']['geojson_file'],obj['glim']['geojson_sha256'],'GLiM polygon '+label)
        for field in ('median','p90'):
            _finite_nonneg(obj['slope_deg'][field],'Pendiente '+label)
            _finite_nonneg(obj['roughness_std11_m'][field],'Rugosidad '+label)
        area=_finite_nonneg(obj['glim']['approx_glim_clipped_area_km2'],'Área GLiM')
        rows.append({'region_id':'r026_c146','site':label,
                     'mapped_basic_volcanic_glim_clip_km2':area,
                     'nasadem_slope_median_deg':obj['slope_deg']['median'],
                     'nasadem_slope_p90_deg':obj['slope_deg']['p90'],
                     'nasadem_roughness_std11_median_m':obj['roughness_std11_m']['median'],
                     'nasadem_report_sha256':sha256_file(path),
                     'glim_geometry_sha256':obj['glim']['geojson_sha256'],
                     'nasadem_grid_sha256':obj['output_netcdf_sha256'],
                     'not_a_terrain_safety_claim':True})
    report={'schema_version':SCHEMA,'status':'terrestrial_local_geologic_terrain_context_only',
            'sites':rows,'notes':[
                'Los círculos recortados pueden superponerse; NO sumar áreas como terrenos independientes',
                'GLiM generalizado NO verifica afloramientos ni mineralogía de basaltos',
                'NASADEM no es certificación de tránsito, terreno o construcción de una base',
                'Son regiones terrestres: NO implica similitud con litología marciana',
            ]}
    atomic_json(Path(out_json),report)
    return {'schema_version':SCHEMA,'status':report['status'],'sites':rows,
            'report_file':str(out_json),'report_sha256':sha256_file(out_json)}
