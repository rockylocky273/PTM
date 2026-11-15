"""V1.3.2: equal sampling, full-source checks and numerical sensitivities."""
from __future__ import annotations
import csv
import json
from pathlib import Path

import pytest

from mars_analog.data.mars_uncertainty_v132 import (
    _families, _observed_signature, _volcanic_leave_one_out,
    build_uncertainty, review_uncertainty)
from mars_analog.data.mars_domain_v122 import evidence_matrix
from mars_analog.data.mars_geology_correspondence_v131 import build_correspondences
from mars_analog.data.mars_profiles_audit_v121 import audit_scales
from mars_analog.data.download import sha256_file
from test_mars_multicriteria_v130 import inputs, run


def test_glim_metamorphic_and_sedimentary_not_conflated():
    c={'Metamorphics':7,'Siliciclastic sedimentary rocks':2}
    fam=_families(c)
    assert fam['metamorphic']==7
    assert fam['sedimentary_or_unconsolidated']==2
    assert _observed_signature(c)==('no_volcanic_sample_mixed_'
        'metamorphic_and_sedimentary_or_unconsolidated')
    with pytest.raises(ValueError,match='desconocida'):
        _families({'unidentified extraterrestrial':1})


def test_one_point_vs_two_point_signal_fragility():
    two=_volcanic_leave_one_out({'Basic volcanic rocks':2,'Unconsolidated sediments':7},9)
    one=_volcanic_leave_one_out({'Intermediate volcanic rocks':1,'Unconsolidated sediments':8},9)
    assert two['leave_one_out_signal_preserved']==9
    assert one['leave_one_out_signal_preserved']==8
    assert two['subsample_detection_given_observed_points']['1']==pytest.approx(2/9)
    assert one['subsample_detection_given_observed_points']['3']==pytest.approx(1/3)
    assert two['subsample_detection_given_observed_points']['9']==1
    assert _volcanic_leave_one_out({'Unconsolidated sediments':9},9)['leave_one_out_signal_preserved']==0
    with pytest.raises(ValueError,match='no suman'):
        _volcanic_leave_one_out({'Basic volcanic rocks':2},9)


def _full_synthetic(inputs):
    root=inputs['tmp']
    # Three candidates from exactly the same 9-point sample protocol; all
    # already exist among the 18 V1.2-ranked terrestrial regions.
    glim=inputs['glim_csv']
    with glim.open('a',encoding='utf-8',newline='') as f:
        w=csv.writer(f)
        w.writerow(['r00001',9,0,'{"Pyroclastics": 2, "Mixed sedimentary rocks": 7}'])
        w.writerow(['r00002',9,0,'{"Intermediate volcanic rocks": 1, "Unconsolidated sediments": 8}'])
        w.writerow(['r00003',9,0,'{"Metamorphics": 7, "Siliciclastic sedimentary rocks": 2}'])
    evidence_matrix(inputs['geology_report'],inputs['domain_report'],glim,
        inputs['screen_report'],root/'matrix.csv',inputs['matrix_report'],watch='r00000')
    run(inputs)
    build_correspondences(root/'multi.json',inputs['geology_report'],
        inputs['domain_report'],glim,inputs['screen_report'],
        root/'corr.csv',root/'corr.json',root/'corr.md',top_n=5)
    audit_scales(inputs['screen_report'],root/'manifest.json',root/'earth.nc',
        root/'mars.nc',root/'regions.csv',root/'scales',top_k=5)
    return dict(correspondence_report=root/'corr.json',screen_report=inputs['screen_report'],
        manifest=root/'manifest.json',audit_report=inputs['audit_report'],
        scales_report=root/'scales/multiscale_audit_report.json',
        out_csv=root/'uncertainty.csv',out_report=root/'uncertainty.json',
        out_markdown=root/'uncertainty.md',profile='elysium_planitia',
        candidates=('r00000','r00001','r00002'),top_ks=(5,10))


def test_integration_balanced_3_way_and_review(inputs):
    args=_full_synthetic(inputs)
    result=build_uncertainty(**args)
    assert result['candidates_evaluated']==3
    assert result['anchor_controls']==4
    assert result['weight_scenarios']==3
    doc=json.loads(args['out_report'].read_text(encoding='utf-8'))
    assert doc['multiscale_profile_population_counts']['30km_9x9']==18
    assert all(r['combined_similarity_score'] is None for r in doc['candidates'])
    assert all(r['analog_validated'] is False for r in doc['candidates'])
    a,b,c=doc['candidates']
    assert a['volcanic_point_diagnostics']['volcanic_observed']==2
    assert b['volcanic_point_diagnostics']['volcanic_observed']==2
    assert c['volcanic_point_diagnostics']['volcanic_observed']==1
    assert c['volcanic_point_diagnostics']['leave_one_out_signal_preserved']==8
    assert set(a['method_ranks'])=={'original','robust_log_l2','empirical_percentile_l1'}
    assert set(a['scale_ranks'])=={'15km_17x17','30km_9x9','40km_7x7'}
    assert a['scale_ranks']['30km_9x9']==a['topographic_rank_original']
    assert all(r['local_nasadem_comparison_excluded'] for r in doc['candidates'])
    metam=next(x for x in doc['anchor_refined_lithology_controls'] if x['region_id']=='r00003')
    assert 'metamorphic_and_sedimentary' in metam['refined_lithology_observation']
    view=review_uncertainty(args['out_report'],'r00002')
    assert len(view['rows'])==1 and view['rows'][0]['earth_region_id']=='r00002'
    with pytest.raises(ValueError,match='no encontrado'):
        review_uncertainty(args['out_report'],'r99999')


def test_modified_scale_file_is_rejected(inputs):
    args=_full_synthetic(inputs)
    multiscale=Path(args['scales_report'])
    info=json.loads(multiscale.read_text())
    with Path(info['files']['rankings']['file']).open('a',encoding='utf-8') as f:
        f.write('\nmodified')
    with pytest.raises(ValueError,match='SHA-256'):
        build_uncertainty(**args)
    assert not args['out_report'].exists()


def test_modified_correspondence_is_rejected(inputs):
    args=_full_synthetic(inputs)
    corr=json.loads(Path(args['correspondence_report']).read_text())
    with Path(corr['csv_file']).open('a',encoding='utf-8') as f:
        f.write('\nmodified')
    with pytest.raises(ValueError,match='SHA-256'):
        build_uncertainty(**args)


def test_invalid_candidates_rejected(inputs):
    args=_full_synthetic(inputs)
    args['candidates']=('r00000','r00000')
    with pytest.raises(ValueError,match='distintos'):
        build_uncertainty(**args)


def test_no_external_score_and_reviewer_verifies_hashes(inputs):
    args=_full_synthetic(inputs)
    build_uncertainty(**args)
    with args['out_markdown'].open('a',encoding='utf-8') as f:f.write('\nTAMPER')
    with pytest.raises(ValueError,match='SHA-256'):
        review_uncertainty(args['out_report'])
