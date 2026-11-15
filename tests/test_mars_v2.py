"""V2.0 synthetic contract tests. Real historic outputs remain on user's PC."""
import csv
import json
from pathlib import Path

import pytest

from mars_analog.data.download import sha256_file
from mars_analog.data.mars_v2 import build_v2, SCHEMA, INPUTS, PROFILES


def _json(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding='utf-8')


def _csv(path):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('w',newline='',encoding='utf-8') as f:
        w=csv.writer(f);w.writerow(['region_id','rank']);w.writerow(['r026_c146',6])


def fixture(tmp_path):
    root=tmp_path
    data=root/'data'
    paths={k:data/rel for k,rel in INPUTS.items()}
    ranks={'r026_c146':6,'r069_c067':8,'r067_c038':19}
    dom=[];geol=[]
    for pid in PROFILES:
        dom.append(dict(profile=pid,outside_catalog_minmax=5 if pid=='olympus_mons' else 0,
                        extreme_one_sided_features_95pct=5 if pid=='olympus_mons' else 0,
                        domain_flag='all_features_outside_sampled_earth_range' if pid=='olympus_mons' else 'within_sampled_earth_feature_ranges'))
        geol.append(dict(profile_id=pid,sampled=9,mapped=9,status='complete',unit_code_counts='{"lAv":9}'))
    doc={
        'domain':{'schema_version':'mars_analog_reference_domain_audit_v1.2.2',
                  'status':'numeric_reference_coverage_not_validation','profiles':dom},
        'mars_geology':{'schema_version':'mars_geology_point_summary_v1.2.2',
                        'status':'cartographic_point_observations_no_area_fraction_or_mineralogy','profiles':geol},
        'multicriteria':{'schema_version':'mars_analog_multicriteria_evidence_v1.3.0',
                         'status':'noncompensatory_evidence_triage_no_joint_similarity_score'},
        'correspondence':{'schema_version':'mars_analog_process_correspondence_v1.3.1',
                          'status':'process_hypotheses_and_contrasts_no_geological_equivalence_score',
                          'glim_sampled_regions':3,'pairs':3,'rows':[{
                          'mars_profile':'elysium_planitia','earth_region_id':rid,
                          'topographic_rank':rank,'broad_process_relation':'broad_volcanic_cartography_and_lithology_signal',
                          'inference_strength':'process_hypothesis_only','research_triage':'targeted_volcanic_process_hypothesis_followup',
                          'analog_validated':False} for rid,rank in ranks.items()]},
        'uncertainty':{'schema_version':'mars_analog_balanced_uncertainty_v1.3.2',
                       'status':'matched_observation_sensitivity_no_analog_probability','profile':'elysium_planitia',
                       'candidates':[dict(earth_region_id=rid,topographic_rank_original=rank,
                       scale_ranks={'15km_17x17':rank-1,'30km_9x9':rank,'40km_7x7':rank+5},
                       method_ranks={'original':rank,'robust_log_l2':rank-1,'empirical_percentile_l1':rank+1},
                       weight_perturbation_ranks={'min':rank-1,'median':rank,'max':rank+5,'scenarios':60},
                       top_k_membership={'25':{'scales_present':3}},
                       volcanic_point_diagnostics={'classified':9,'volcanic_observed':2 if rank!=19 else 1,
                                                   'leave_one_out_signal_preserved':9 if rank!=19 else 8,
                                                   'leave_one_out_trials':9},
                       lithology_counts={'Basic volcanic rocks':2},analog_validated=False)
                       for rid,rank in ranks.items()]},
        'benchmark':{'schema_version':'mars_analog_external_validation_v1.3.3',
                     'status':'external_reference_retrieval_audit_not_analog_accuracy',
                     'summary':{'external_cases':9,'direct_target_process_analogues':4,
                                'direct_sites_missing_from_ranked_population':3,
                                'validated_analogs':0,'accuracy_or_auc':None},
                     'results':[dict(case_id='site_'+str(i),site_name=('Sede adversarial </script><script>alert(1)</script>' if i==0 else 'Sitio '+str(i)),
                                  mars_profile='elysium_planitia',earth_region_id='r026_c146',
                                  role='documented_direct_target_analogue' if i<4 else 'planetary_process_reference_only',
                                  topographic_rank=166 if i==3 else None,
                                  evaluation_status='external_site_not_in_screened_population' if i<3 else 'topography_outside_reference_domain',
                                  validation_outcome='inconclusive_on_geological_analogy') for i in range(9)]}}
    for k,d in doc.items():
        _json(paths[k],d)
    # Supporting file and SHA verification for each report, including the source graph.
    for k in doc:
        csvpath=data/'results'/f'{k}.csv';_csv(csvpath)
        doc[k]['csv_file']=str(csvpath)
        doc[k]['csv_sha256']=sha256_file(csvpath)
    # Avoid cyclic hash: M (multicriteria) => correspondence => uncertainty,
    # while external benchmark independently links domain.
    _json(paths['domain'],doc['domain'])
    _json(paths['mars_geology'],doc['mars_geology'])
    _json(paths['multicriteria'],doc['multicriteria'])
    doc['correspondence']['source_files']={
        'v130':{'path':str(paths['multicriteria']),'sha256':sha256_file(paths['multicriteria'])},
        'domain':{'path':str(paths['domain']),'sha256':sha256_file(paths['domain'])},
        'mars_geology':{'path':str(paths['mars_geology']),'sha256':sha256_file(paths['mars_geology'])}}
    _json(paths['correspondence'],doc['correspondence'])
    doc['uncertainty']['sources']={'correspondence_v131':{'file':str(paths['correspondence']),
                      'sha256':sha256_file(paths['correspondence'])}}
    _json(paths['uncertainty'],doc['uncertainty'])
    doc['benchmark']['source_files']={'reference_domain':{'file':str(paths['domain']),
                      'sha256':sha256_file(paths['domain'])}}
    _json(paths['benchmark'],doc['benchmark'])
    return data,paths


def test_integration_exports_offline_dashboard_and_csv(tmp_path):
    data,paths=fixture(tmp_path)
    outputs=tmp_path/'data/reports/mars_v2_0'
    obj=build_v2(data,outputs)
    assert obj['schema_version']==SCHEMA
    assert obj['mars_profiles']==6
    assert obj['earth_mars_correspondences']==3
    assert obj['candidates']==3
    assert obj['benchmark']['validated_analogs']==0
    assert obj['benchmark']['accuracy_or_auc'] is None
    page=(outputs/'mars_analog_dashboard_v2.html').read_text()
    assert 'Marte a la Tierra' in page
    assert 'data-view="reference"' in page
    assert '<script src=' not in page and '<link rel="stylesheet" href=' not in page
    assert '</script><script>alert' not in page
    assert '\\u003c/script\\u003e' in page
    assert "Mars Analog" in (outputs/'mars_analog_report_v2.md').read_text()
    result=json.loads((outputs/'mars_analog_report_v2.json').read_text())
    assert result['combined_similarity_score'] is None
    assert result['analog_accuracy'] is None
    assert result['three_way_elysium_candidates'][0]['id']=='r026_c146'
    assert all('sha256' in ref for ref in result['outputs'].values())
    for p in paths.values():
        assert p.is_file()


def test_mutated_historical_source_rejected_without_assembling_dashboard(tmp_path):
    data,paths=fixture(tmp_path)
    report=json.loads(paths['domain'].read_text())
    report['profiles'][0]['outside_catalog_minmax']=2
    _json(paths['domain'],report)
    out=data/'reports/mars_v2_0'
    with pytest.raises(ValueError,match='alterado|incompatibles'):
        build_v2(data,out)
    assert not (out/'mars_analog_dashboard_v2.html').exists()


def test_invalid_reference_accuracy_rejected(tmp_path):
    data,paths=fixture(tmp_path)
    benchmark=json.loads(paths['benchmark'].read_text())
    benchmark['summary']['validated_analogs']=2
    _json(paths['benchmark'],benchmark)
    with pytest.raises(ValueError,match='validación planetaria'):
        build_v2(data,data/'reports/mars_v2_0')


def test_wrong_topographic_rank_detected(tmp_path):
    data,paths=fixture(tmp_path)
    uncertainty=json.loads(paths['uncertainty'].read_text())
    uncertainty['candidates'][0]['topographic_rank_original']=500
    _json(paths['uncertainty'],uncertainty)
    with pytest.raises(ValueError,match='Puesto o correspondencia'):
        build_v2(data,data/'reports/mars_v2_0')


def test_missing_required_input_actionable_error(tmp_path):
    data,paths=fixture(tmp_path)
    paths['uncertainty'].unlink()
    with pytest.raises(ValueError,match='Falta uncertainty'):
        build_v2(data,data/'reports/mars_v2_0')
