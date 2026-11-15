"""V0.8: audit and stress-test topographic ranking V0.7 (no new downloads).

This module tests *numerical and parameter robustness*, NOT scientific validity
of analog sites. It never converts an algorithmic distance into a probability.
"""
from __future__ import annotations

import csv
import json
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

from .analog_screen import (
    FEATURES, OFFSET, WEIGHTS, diverse_top, distance_metrics,
)
from .download import atomic_json, sha256_file

GROUPS = ('slope', 'roughness', 'relief')
REQUIRED = ('rank', 'region_id', 'center_lat', 'center_lon_180',
            'mapped_land_fraction', 'sample_coverage', 'sample_count',
            *FEATURES, 'distance_total', 'distance_slope',
            'distance_roughness', 'distance_relief')


def _check_number(value, key: str, low=None, high=None):
    try:
        val = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f'Valor inválido {key}: {value!r}') from exc
    if not np.isfinite(val) or (low is not None and val < low) or (high is not None and val > high):
        raise ValueError(f'Valor fuera de rango {key}: {value!r}')
    return val


def load_screened_ranking(ranking_csv: Path, profile_file: Path, screen_report: Path):
    """Require complete V0.7 output, matching hashes and recomputed distances.

    We deliberately fail closed when the profile or CSV have changed since
    screening, instead of silently evaluating a mismatched candidate set.
    """
    profile_file = Path(profile_file)
    ranking_csv = Path(ranking_csv)
    screen_report = Path(screen_report)
    with profile_file.open(encoding='utf-8') as f:
        profile = json.load(f)
    with screen_report.open(encoding='utf-8') as f:
        screen = json.load(f)
    if profile.get('schema_version') != 'mars_analog_profile_v0.7' or profile.get('planet') != 'Mars':
        raise ValueError('Perfil marciano distinto de V0.7')
    if screen.get('schema_version') != 'mars_analog_topographic_screen_v0.7':
        raise ValueError('Se requiere reporte de analog-screen V0.7')
    if screen.get('status') != 'exploratory_topographic_distance_only_not_analog_confirmation':
        raise ValueError('Estado del reporte V0.7 inválido')
    if screen.get('profile_name') != profile.get('profile_name'):
        raise ValueError('No coincide el nombre del perfil')
    if screen.get('input_sha256', {}).get('mars_profile') != sha256_file(profile_file):
        raise ValueError('Hash de perfil distinto del experimento de cribado')
    if screen.get('csv_sha256') != sha256_file(ranking_csv):
        raise ValueError('Hash del ranking distinto del experimento de cribado')
    if screen.get('nominal_comparison', {}).get('weights') != WEIGHTS:
        raise ValueError('Pesos del experimento no coinciden con el motor V0.7')
    if screen.get('nominal_comparison', {}).get('regularizers') != OFFSET:
        raise ValueError('Regularizadores V0.7 incompatibles')

    with ranking_csv.open(newline='', encoding='utf-8-sig') as f:
        rdr = csv.DictReader(f)
        if not rdr.fieldnames or not set(REQUIRED).issubset(rdr.fieldnames):
            raise ValueError('Ranking CSV incompleto; columnas V0.7 faltantes')
        rows = list(rdr)
    if not rows or len(rows) != screen.get('counts', {}).get('ranked'):
        raise ValueError('Recuento del ranking distinto del reporte V0.7')
    if len({r['region_id'] for r in rows}) != len(rows):
        raise ValueError('IDs regionales duplicados')
    numeric_rows = []
    for k, r in enumerate(rows, 1):
        if int(r['rank']) != k:
            raise ValueError('La columna rank no es secuencial')
        if not r['region_id']:
            raise ValueError('region_id vacío')
        item = {'region_id': r['region_id'], 'rank': k,
                'center_lat': _check_number(r['center_lat'], 'center_lat', -90, 90),
                'center_lon_180': _check_number(r['center_lon_180'], 'center_lon_180', -180, 180),
                'mapped_land_fraction': _check_number(r['mapped_land_fraction'], 'mapped_land_fraction', 0, 1),
                'sample_coverage': _check_number(r['sample_coverage'], 'sample_coverage', 0, 1),
                'sample_count': int(r['sample_count'])}
        for key in FEATURES:
            item[key] = _check_number(r[key], key, 0)
        for key in ('distance_total', 'distance_slope', 'distance_roughness', 'distance_relief'):
            item[key] = _check_number(r[key], key, 0)
        recomputed = distance_metrics(item, profile['features'])
        for key, expected in recomputed.items():
            if not np.isclose(item[key], expected, atol=1e-7, rtol=1e-7):
                raise ValueError(f'Distancia almacenada inconsistente para {r["region_id"]} ({key})')
        numeric_rows.append(item)
    for prev, curr in zip(numeric_rows, numeric_rows[1:]):
        if prev['distance_total'] > curr['distance_total'] + 1e-10:
            raise ValueError('Ranking no está ordenado')
    return numeric_rows, profile, screen


def component_distances(rows: list[dict], mars_features: dict,
                        offset_factor: float = 1.0) -> np.ndarray:
    """Compute (n,3) values. Match V0.7 exactly when factor is 1."""
    if not (0.1 <= offset_factor <= 10):
        raise ValueError('offset_factor debe estar en [0.1,10]')
    features = np.array([[r[k] for k in FEATURES] for r in rows], dtype=float)
    mars = np.array([_check_number(mars_features[k], k, 0) for k in FEATURES])
    offs = np.array([OFFSET['slope'], OFFSET['slope'],
                     OFFSET['roughness'], OFFSET['roughness'], OFFSET['relief']]) * offset_factor
    diffs = np.abs(np.log((features+offs)/(mars[None,:]+offs)))
    return np.column_stack((diffs[:,0:2].mean(axis=1),
                            diffs[:,2:4].mean(axis=1), diffs[:,4]))


def _top_indices(rows: list[dict], scores: np.ndarray, n_top: int, separation: float):
    ids = np.asarray([r['region_id'] for r in rows])
    order = np.lexsort((ids, scores))
    selected = diverse_top([{'_i':int(i),'center_lat':rows[int(i)]['center_lat'],
                             'center_lon_180':rows[int(i)]['center_lon_180']}
                            for i in order],n_top,separation)
    return order, [x['_i'] for x in selected]


def _overlap(a: list[int], b: list[int]) -> dict:
    a_set,b_set=set(a),set(b)
    overlap=len(a_set & b_set)
    union=len(a_set | b_set)
    return {'intersection':overlap,
            'fraction_of_reference':round(overlap/max(len(a_set),1),6),
            'jaccard':round(overlap/max(union,1),6)}


def audit_ranking(profile_file: Path, ranking_csv: Path, screen_report: Path,
                  output_csv: Path, output_report: Path,
                  top: int = 25, min_separation_km: float = 250.0,
                  scenarios: int = 60, seed: int = 2026) -> dict:
    if not (1 <= top <= 200) or not (0 <= min_separation_km <= 5000):
        raise ValueError('top o separación inválidos')
    if not (0 <= scenarios <= 500) or not (0 <= seed < 2**32):
        raise ValueError('Escenarios [0,500], semilla [0,2^32)')
    rows, profile, report = load_screened_ranking(ranking_csv, profile_file, screen_report)
    nominal = np.array([WEIGHTS[g] for g in GROUPS])
    base_components = component_distances(rows, profile['features'])
    nominal_scores = base_components @ nominal
    base_order, base_top = _top_indices(rows, nominal_scores, top, min_separation_km)
    orig_ids = [r['region_id'] for r in report.get('top_diverse', [])]
    comp_ids = [rows[i]['region_id'] for i in base_top]
    if len(orig_ids) == top and orig_ids != comp_ids:
        raise ValueError('Top diverso no coincide con el informe V0.7')

    # Seven pre-declared deterministic ablations / single-family controls.
    controls = {
        'solo_pendiente':(np.array([1.,0.,0.]),1.),
        'solo_rugosidad':(np.array([0.,1.,0.]),1.),
        'solo_relieve':(np.array([0.,0.,1.]),1.),
        'sin_pendiente':(np.array([0.,.35,.30])/.65,1.),
        'sin_rugosidad':(np.array([.35,0.,.30])/.65,1.),
        'sin_relieve':(np.array([.35,.35,0.])/.70,1.),
        'regularizadores_mitad':(nominal,.5),
        'regularizadores_dobles':(nominal,2.),
    }
    control_report = {}
    for name, (weights,factor) in controls.items():
        comps=component_distances(rows,profile['features'],factor)
        _,chosen = _top_indices(rows,comps @ weights,top,min_separation_km)
        control_report[name]=_overlap(base_top,chosen)

    rng=np.random.default_rng(seed)
    presence=np.zeros(len(rows),dtype=np.int64)
    ranks_for_baseline=np.zeros((scenarios,len(base_top)),dtype=np.int32)
    overlaps=[]
    sampled=[]
    base_index=np.array(base_top,dtype=int)
    for t in range(scenarios):
        weights = rng.dirichlet(16*nominal)
        factor = float(rng.choice([.5,1.,2.]))
        comp=component_distances(rows,profile['features'],factor)
        order, chosen=_top_indices(rows,comp @ weights,top,min_separation_km)
        presence[chosen]+=1
        ranks=np.empty(len(rows),dtype=int)
        ranks[order]=np.arange(1,len(rows)+1)
        ranks_for_baseline[t]=ranks[base_index]
        overlaps.append(_overlap(base_top,chosen)['fraction_of_reference'])
        sampled.append({'weights':[round(float(x),4) for x in weights],
                        'offset_factor':factor})

    stability=[]
    for k, idx in enumerate(base_top):
        d=rows[idx]
        rank_samples=ranks_for_baseline[:,k].tolist() if scenarios else []
        stability.append({
            'region_id':d['region_id'], 'center_lat':d['center_lat'],
            'center_lon_180':d['center_lon_180'],
            'rank_original':d['rank'],
            'distance_original':round(float(nominal_scores[idx]),10),
            'top_frequency':round(float(presence[idx]/scenarios),6) if scenarios else None,
            'median_full_rank':round(float(np.median(rank_samples)),2) if rank_samples else None,
            'min_full_rank':int(min(rank_samples)) if rank_samples else None,
            'max_full_rank':int(max(rank_samples)) if rank_samples else None,
            'slope_median_deg':d['slope_median_deg'],
            'roughness_std3_median_m':d['roughness_std3_median_m'],
            'relief_p90_p10_m':d['relief_p90_p10_m']})
    output_csv=Path(output_csv)
    output_csv.parent.mkdir(parents=True, exist_ok=True)
    with output_csv.open('w',newline='',encoding='utf-8') as f:
        w=csv.DictWriter(f,fieldnames=list(stability[0].keys()))
        w.writeheader()
        w.writerows(stability)
    output_report=Path(output_report)
    result={
        'schema_version':'mars_analog_ranking_audit_v0.8',
        'status':'parameter_sensitivity_only_not_scientific_validation',
        'source_profile':profile.get('profile_name'),
        'base_ranked_count':len(rows),
        'top_diverse_count':len(base_top),
        'top':top,
        'min_separation_km':min_separation_km,
        'base_weights':WEIGHTS,
        'base_regularizers':OFFSET,
        'ablations':control_report,
        'stress_test':{
            'random_scenarios':scenarios,
            'seed':seed,
            'weight_distribution':'Dirichlet(alpha=16*[0.35,0.35,0.30])',
            'regularizer_factors':[.5,1.,2.],
            'average_top_overlap_fraction':round(float(np.mean(overlaps)),6) if overlaps else None,
            'minimum_top_overlap_fraction':round(float(np.min(overlaps)),6) if overlaps else None,
            'random_unstructured_expected_overlap_count':round(top*top/len(rows),3),
            'interpretation':'Exploración de pesos, NO intervalo de confianza ni evaluación de precisión',
        },
        'nominal_top_stability':stability,
        'input_sha256':{
            'profile':sha256_file(Path(profile_file)),
            'ranking':sha256_file(Path(ranking_csv)),
            'screen_report':sha256_file(Path(screen_report)),
        },
        'outputs':{'csv':str(output_csv),'csv_sha256':sha256_file(output_csv)},
        'limitations':[
            'El ranking fue generado sin variables geológicas, climáticas o mineralógicas',
            'No se efectuó validación externa de análogos; estos controles solo miden estabilidad numérica',
            'Las regiones geográficamente próximas no constituyen observaciones independientes',
            'La selección previa excluyó regiones polares y candidatos con datos insuficientes',
            'Los escenarios se eligieron como pruebas de estrés, no como distribución de incertidumbre física',
            'Este módulo no puede detectar sesgos presentes en los datos ETOPO/MOLA originales',
        ],
        'created_at_utc':datetime.now(timezone.utc).isoformat(),
    }
    atomic_json(output_report,result)
    result['report_file']=str(output_report)
    return result
