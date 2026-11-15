"""V2.0.3 individualized evidence ledger for 25 preselected terrestrial cells.

Never promotes missing evidence to a negative site or claims that selected
regions have undergone the three-way V1.3.2 sensitivity experiment.
"""
from __future__ import annotations
from collections import Counter


def build_audits(entries:list[dict],correspondence:list[dict],climate:dict)->list[dict]:
    by_region={}
    for r in correspondence:
        by_region.setdefault(r['earth_region_id'],[]).append(r)
    results=[]
    for e in entries:
        rid=e['id'];ranks=by_region.get(rid,[])
        if not ranks:raise ValueError('Candidato sin correspondencia: '+rid)
        rank=e['topographic_rank']
        lit=e['lithology_counts'];observed=sum(int(x) for x in lit.values())
        leaders=sorted(lit.items(),key=lambda pair:(-int(pair[1]),pair[0]))
        base=e['climate_earth_context']
        descriptions=[]
        if rank is not None:
            descriptions.append(f'Puesto {rank} en 2.617 regiones terrestres respecto a Elysium Planitia, con la función topográfica histórica.')
        if e['relief_context_m'] is not None:
            descriptions.append(f'Diferencia P98–P02 del mapa ETOPO regional: {e["relief_context_m"]:,.0f} m (ventana de visualización, no puntuación del algoritmo).')
        if leaders:
            descriptions.append(f'Litología GLiM más frecuente entre {observed} observaciones: {leaders[0][0]} ({leaders[0][1]} puntos).')
        if e['volcanic_points']:
            descriptions.append(f'Se observaron {e["volcanic_points"]} puntos de clases volcánicas o piroclásticas, sin estimar proporciones de superficie.')
        else:
            descriptions.append('No se registraron clases volcánicas en las observaciones GLiM; no descarta vulcanismo fuera de los puntos muestreados.')
        if base:
            descriptions.append('Contexto meteorológico del centro de la celda: '+base['climate_descriptor']+'.')
        else:
            descriptions.append('Clima del centro de la celda pendiente de la fuente NASA POWER.')
        if e['scale_ranks']:
            vals=list(e['scale_ranks'].values())
            descriptions.append('Sensibilidad de escala evaluada para este candidato: '+', '.join(str(x) for x in vals)+'.')
        else:
            descriptions.append('No se realizó auditoría multiescala individual para esta celda; no extrapolar la estabilidad de los tres candidatos estudiados.')
        if e.get('sensitivity_full_v204'):
            methods=e['method_ranks']
            descriptions.append(f"Sensibilidad de método: original {methods['original']}, Log-L2 {methods['robust_log_l2']}, percentil L1 {methods['empirical_percentile_l1']}.")
            descriptions.append(f"Perturbación de pesos: en el top 25 en {e['weight_top25_of_60']}/60 escenarios; puesto mediano {e['weight_rank_median']}.")
            descriptions.append(f"Prueba leave-one-out de GLiM: señal volcánica conservada en {e['glim_leave_one_out_preserved']}/{observed} retiradas de una observación; no mide proporción de área.")
        other=[{'profile':r['mars_profile'],'rank':r.get('topographic_rank'),
                'triage':r.get('research_triage'),'process_relation':r.get('broad_process_relation')}
               for r in ranks]
        results.append({'id':rid,'label':e['label'],'country':e['country'],
          'center_lat':e['center_lat'],'center_lon':e['center_lon'],
          'topographic_rank_elysium':rank,'topo_status':e['relief_context_m'] is not None,
          'relief_context_m':e['relief_context_m'],'elevation_range_m':e['elevation_range_m'],
          'lithology_counts':lit,'sampled_glim_points':observed,'volcanic_observed_points':e['volcanic_points'],
          'geological_observation':'broad_volcanic_observed' if e['volcanic_points'] else 'volcanic_not_observed_in_sample',
          'climate_status':base['status'] if base else 'missing',
          'climate':base,'individual_multiscale_tested':e['scale_ranks'] is not None,
          'scale_ranks':e['scale_ranks'],'method_ranks':e['method_ranks'],
          'sensitivity_full_v204':bool(e.get('sensitivity_full_v204')),
          'weight_top25_of_60':e.get('weight_top25_of_60'),
          'glim_leave_one_out_preserved':e.get('glim_leave_one_out_preserved'),
          'mars_profiles_available':len(other),'six_mars_profiles':other,'findings':descriptions,
          'audit_scope':'individual_summary_of_existing_evidence_not_external_geologic_validation'})
    return results
