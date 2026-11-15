"""V2.0.4 all-anchor sensitivity, historical regression, integrity and dashboard."""
import csv
import json
import shutil

import pytest

from mars_analog.data.download import sha256_file
from mars_analog.data.mars_sensitivity_v204 import (
    build_all_sensitivity, review_all_sensitivity, _summary_row, _order_correspondence)
from mars_analog.data.mars_uncertainty_v132 import build_uncertainty
from mars_analog.data.mars_v2 import build_v2
from test_mars_uncertainty_v132 import _full_synthetic
from test_mars_v2 import fixture
from test_mars_multicriteria_v130 import inputs, audit_rankings


def test_order_of_four_anchors_and_duplicates():
    corr={'glim_sampled_regions':2,'rows':[{'mars_profile':'elysium_planitia','earth_region_id':'B','topographic_rank':8},
                                         {'mars_profile':'elysium_planitia','earth_region_id':'A','topographic_rank':2}]}
    assert [x['earth_region_id'] for x in _order_correspondence(corr,'elysium_planitia')]==['A','B']
    corr['rows'].append(corr['rows'][0])
    with pytest.raises(ValueError,match='duplicado'):
        _order_correspondence(corr,'elysium_planitia')


def test_synthetic_four_anchor_full_batch_matches_historical_three(inputs):
    args=_full_synthetic(inputs)
    audit_rankings(inputs['screen_report'], inputs['tmp']/'manifest.json',
                   inputs['tmp']/'audit', ks=(5,8,10), scenarios=60, watch=('r00000',))
    build_uncertainty(**args)  # freeze the original three-way audit
    root=inputs['tmp']; data=root/'data'
    files={
        'reports/mars_geology_correspondence_v1_3_1.json':root/'corr.json',
        'reports/mars_uncertainty_v1_3_2.json':root/'uncertainty.json',
        'reports/mars_profiles_screen_v1_2.json':inputs['screen_report'],
        'catalog/mars_profiles_v1_2.json':root/'manifest.json',
        'reports/mars_audit_v1_2_1/rank_audit_report.json':inputs['audit_report'],
        'reports/mars_audit_v1_2_1/scales/multiscale_audit_report.json':args['scales_report'],
    }
    for name,src in files.items():
        dst=data/name;dst.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(src,dst)
    out=root/'v204'
    result=build_all_sensitivity(data,out,required_regions=4,top_ks=(5,10))
    assert result['candidate_count']==4
    assert result['legacy_cases_reproduced']==3
    doc=json.loads((out/'candidate_sensitivity_v204.json').read_text())
    assert doc['protocol']['weight_draws']==60
    assert doc['accuracy_or_auc'] is None
    assert all(x['rank_30km']==x['topographic_rank_original'] for x in doc['rows'])
    assert len(list(csv.DictReader((out/'candidate_sensitivity_v204.csv').open(encoding='utf-8-sig'))))==4
    assert review_all_sensitivity(out/'candidate_sensitivity_v204.json')['count']==4
    with pytest.raises(ValueError,match='Se esperaban 25'):
        build_all_sensitivity(data,out,required_regions=25,top_ks=(5,10))
    with pytest.raises(ValueError,match='Región no encontrada'):
        review_all_sensitivity(out/'candidate_sensitivity_v204.json','r99999')
    (out/'candidate_sensitivity_v204.csv').write_text('tampered',encoding='utf-8')
    with pytest.raises(ValueError,match='SHA-256'):
        review_all_sensitivity(out/'candidate_sensitivity_v204.json')


def test_v204_dashboard_expands_all_audits(tmp_path):
    data, paths=fixture(tmp_path)
    corresponding=json.loads(paths['correspondence'].read_text())['rows']
    rowdict=[]
    for row in corresponding:
        rid=row['earth_region_id'];rank=row['topographic_rank']
        rowdict.append(dict(earth_region_id=rid,topographic_rank_original=rank,
            rank_log_l2=rank-1,rank_percentile_l1=rank+1,
            rank_15km=rank-2,rank_30km=rank,rank_40km=rank+4,
            weight_top25_of_60=60,weight_top10_of_60=40,weight_rank_median=rank,
            glim_leave_one_out_preserved=9))
    import mars_analog.data.mars_sensitivity_v204 as m
    full=tmp_path/'all.json';src=dict(
        correspondence_v131={'file':str(paths['correspondence']),'sha256':sha256_file(paths['correspondence'])},
        historical_three_way_v132={'file':str(paths['uncertainty']),'sha256':sha256_file(paths['uncertainty'])})
    full.write_text(json.dumps({'schema_version':m.SCHEMA,'status':m.STATUS,
        'candidate_count':3,'rows':rowdict,'source_files':src,'analog_validated':False,'mars_profile':'elysium_planitia',
        'counts':{'all_methods_top25':3,'all_scales_top25':3},
        'csv_file':str(tmp_path/'a.csv'),'csv_sha256':sha256_file(paths['correspondence']),
        'markdown_file':str(tmp_path/'b.md'),'markdown_sha256':sha256_file(paths['uncertainty'])}),encoding='utf-8')
    # Read path/content must have correct verifiable SHA; copy exactly from known files.
    (tmp_path/'a.csv').write_bytes(paths['correspondence'].read_bytes())
    (tmp_path/'b.md').write_bytes(paths['uncertainty'].read_bytes())
    # Source entries may be empty for dashboard tests; report and CSV still verified.
    out=tmp_path/'v2expanded'
    result=build_v2(data,out,full_sensitivity_report=full)
    assert result['full_sensitivity_audits']==3
    audits=json.loads((out/'candidate_audits_v203.json').read_text())['audits']
    assert all(x['sensitivity_full_v204'] for x in audits)
    assert all(x['weight_top25_of_60']==60 for x in audits)
    assert all('Perturbación de pesos' in str(x['findings']) for x in audits)
    html=(out/'mars_analog_dashboard_v2.html').read_text(encoding='utf-8')
    assert 'V2.0.4' in html and 'Top25/pesos:' in html
    bad=json.loads(full.read_text());bad['source_files']['historical_three_way_v132']['sha256']='0'*64
    full.write_text(json.dumps(bad))
    with pytest.raises(ValueError,match='SHA-256|mezcla versiones'):
        build_v2(data,tmp_path/'bad',full_sensitivity_report=full)
