"""V0.8 regression tests for audit and parametric stability (synthetic data)."""
import csv
import json
from pathlib import Path

import numpy as np
import pytest

from mars_analog.data.analog_screen import distance_metrics, diverse_top
from mars_analog.data.analog_audit import (
    audit_ranking, component_distances, load_screened_ranking,
)
from mars_analog.data.download import sha256_file


def fixtures(tmp_path):
    mars={
        'slope_median_deg':0.10,
        'slope_p90_deg':0.40,
        'roughness_std3_median_m':50.,
        'roughness_std3_p90_m':130.,
        'relief_p90_p10_m':550.,
    }
    profile=tmp_path/'profile.json'
    profile.write_text(json.dumps({'schema_version':'mars_analog_profile_v0.7',
                                   'planet':'Mars','profile_name':'synthetic',
                                   'features':mars}),encoding='utf8')
    rows=[]
    for k in range(18):
        scale=0.60+k*.055
        vals={name:v*scale for name,v in mars.items()}
        r={'region_id':f'R{k:02}', 'center_lat':-45+k*5,
           'center_lon_180':-170+k*20,
           'mapped_land_fraction':1.,'sample_coverage':1.,
           'sample_count':81,**vals,**distance_metrics(vals,mars)}
        rows.append(r)
    rows.sort(key=lambda r:(r['distance_total'],r['region_id']))
    ranking=tmp_path/'ranking.csv'
    with ranking.open('w',newline='',encoding='utf8') as f:
        wr=csv.DictWriter(f,fieldnames=['rank',*rows[0].keys()])
        wr.writeheader()
        for i,row in enumerate(rows,1): wr.writerow({'rank':i,**row})
    report=tmp_path/'screen.json'
    report.write_text(json.dumps({
        'schema_version':'mars_analog_topographic_screen_v0.7',
        'status':'exploratory_topographic_distance_only_not_analog_confirmation',
        'profile_name':'synthetic',
        'nominal_comparison':{'weights':{'slope':.35,'roughness':.35,'relief':.3},
                              'regularizers':{'slope':.05,'roughness':10.,'relief':20.}},
        'counts':{'ranked':18},
        'input_sha256':{'mars_profile':sha256_file(profile)},
        'csv_sha256':sha256_file(ranking),
        'top_diverse':[],
    }),encoding='utf8')
    return profile,ranking,report


def test_component_nominal_matches_original_engine(tmp_path):
    profile,ranking,report=fixtures(tmp_path)
    rows, p, _=load_screened_ranking(ranking,profile,report)
    matrix=component_distances(rows,p['features'])
    for i,row in enumerate(rows):
        assert matrix[i].tolist() == pytest.approx([
            row['distance_slope'],row['distance_roughness'],row['distance_relief']],
            abs=1e-13)


def test_audit_reproducible_and_sources_preserved(tmp_path):
    profile,ranking,report=fixtures(tmp_path)
    output_a=tmp_path/'a.csv'
    a=audit_ranking(profile,ranking,report,output_a,tmp_path/'a.json',top=5,
                    min_separation_km=0,scenarios=9,seed=42)
    output_b=tmp_path/'b.csv'
    b=audit_ranking(profile,ranking,report,output_b,tmp_path/'b.json',top=5,
                    min_separation_km=0,scenarios=9,seed=42)
    assert output_a.read_bytes()==output_b.read_bytes()
    assert a['nominal_top_stability']==b['nominal_top_stability']
    assert a['stress_test']['random_scenarios']==9
    assert all(0<=r['top_frequency']<=1 for r in a['nominal_top_stability'])
    assert len(a['ablations'])==8
    assert a['base_ranked_count']==18
    assert a['status']=='parameter_sensitivity_only_not_scientific_validation'


def test_audit_rejects_mismatched_input_hash(tmp_path):
    profile,ranking,report=fixtures(tmp_path)
    profile.write_text(profile.read_text()+' ',encoding='utf8')
    with pytest.raises(ValueError,match='Hash de perfil'):
        audit_ranking(profile,ranking,report,tmp_path/'out.csv',tmp_path/'out.json')


def test_audit_rejects_falsified_distance_even_if_hash_updated(tmp_path):
    profile,ranking,report=fixtures(tmp_path)
    content=ranking.read_text()
    ranking.write_text(content.replace('R00','RAX',1).replace('R01','R00',1),encoding='utf8')
    obj=json.loads(report.read_text())
    obj['csv_sha256']=sha256_file(ranking)
    report.write_text(json.dumps(obj))
    # All distances remain numerically consistent here; test duplicate region detection separately.
    # Instead force a changed numeric value while preserving the updated SHA.
    with ranking.open(newline='') as f:
        rows=list(csv.DictReader(f))
        columns=list(rows[0].keys())
    rows[0]['distance_total']='123456'
    with ranking.open('w',newline='') as f:
        w=csv.DictWriter(f,fieldnames=columns);w.writeheader();w.writerows(rows)
    obj['csv_sha256']=sha256_file(ranking)
    report.write_text(json.dumps(obj))
    with pytest.raises(ValueError,match='Distancia almacenada'):
        load_screened_ranking(ranking,profile,report)


def test_audit_rejects_incomplete_or_bad_parameters(tmp_path):
    profile,ranking,report=fixtures(tmp_path)
    with pytest.raises(ValueError,match='Escenarios'):
        audit_ranking(profile,ranking,report,tmp_path/'o.csv',tmp_path/'r.json',scenarios=-1)
    with pytest.raises(ValueError,match='top o separación'):
        audit_ranking(profile,ranking,report,tmp_path/'o.csv',tmp_path/'r.json',top=0)


def test_audit_zero_scenarios_marks_frequency_unavailable(tmp_path):
    profile,ranking,report=fixtures(tmp_path)
    obj=audit_ranking(profile,ranking,report,tmp_path/'o.csv',tmp_path/'r.json',top=2,scenarios=0)
    assert all(item['top_frequency'] is None for item in obj['nominal_top_stability'])
    assert obj['stress_test']['average_top_overlap_fraction'] is None
