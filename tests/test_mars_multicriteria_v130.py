"""V1.3.0: integration tests offline and scientific guardrails."""
import csv
import json
from pathlib import Path

import pytest

from mars_analog.data.download import atomic_json, sha256_file
from mars_analog.data.mars_multicriteria_v130 import (
    _domain_gate, _geology_signal, _load_climate, build_multicriteria,
    review_multicriteria)
from mars_analog.data.mars_domain_v122 import evaluate_domain, evidence_matrix
from mars_analog.data.mars_geology_v122 import plan_geology, fetch_geology, summarize_geology
from mars_analog.data.mars_profiles_v12 import build_profiles, screen_profiles
from mars_analog.data.mars_profiles_audit_v121 import audit_rankings
from test_mars_profiles_v12 import create_mars, create_earth_and_catalog
from test_mars_geology_v122 import FakeSession


@pytest.fixture
def inputs(tmp_path):
    mars = tmp_path/'mars.nc'
    create_mars(mars)
    manifest=tmp_path/'manifest.json'
    build_profiles(mars,'all',30,9,tmp_path/'profiles',manifest)
    gp=tmp_path/'mars_geology_plan.json'
    plan_geology(manifest,gp,1,50)
    cache=tmp_path/'cache'
    assert fetch_geology(gp,cache,6,session=FakeSession())['pending']==0
    mars_report=tmp_path/'mars_summary.json'
    summarize_geology(gp,cache,tmp_path/'mars_summary.csv',mars_report)
    earth,catalog=create_earth_and_catalog(tmp_path)
    screen=tmp_path/'screen.json'
    screen_profiles(manifest,earth,catalog,tmp_path/'rankings',screen,top=5,min_separation=0)
    audit_dir=tmp_path/'audit'
    audit_rankings(screen,manifest,audit_dir,ks=(5,8,10),scenarios=3,watch=('r00000',))
    domain=tmp_path/'domain.json'
    evaluate_domain(audit_dir/'rank_audit_report.json',tmp_path/'domain.csv',domain)
    glim=tmp_path/'glim.csv'
    with glim.open('w',encoding='utf-8',newline='') as f:
        writer=csv.DictWriter(f,fieldnames=['region_id','classified','basic_volcanic_sample_count',
                                           'observed_lithology_classes'])
        writer.writeheader()
        writer.writerow({'region_id':'r00000','classified':9,'basic_volcanic_sample_count':2,
                         'observed_lithology_classes':'{"Basic volcanic rocks": 2, "Unconsolidated sediments": 7}'})
    matrix=tmp_path/'matrix.json'
    evidence_matrix(mars_report,domain,glim,screen,tmp_path/'matrix.csv',matrix,watch='r00000')
    climate_csv=tmp_path/'environment.csv'
    with climate_csv.open('w',encoding='utf-8',newline='') as f:
        writer=csv.DictWriter(f,fieldnames=['region_id','status','air_temp_mean_c',
              'precip_annual_mean_mm','relative_humidity_mean_pct','seasonal_air_temp_range_c'])
        writer.writeheader();writer.writerow({'region_id':'r00000','status':'complete',
              'air_temp_mean_c':-5.3,'precip_annual_mean_mm':340,
              'relative_humidity_mean_pct':58,'seasonal_air_temp_range_c':19.9})
    climate=tmp_path/'climate.json'
    atomic_json(climate,{'schema_version':'mars_analog_environment_global_v1.0',
        'status':'descriptive_sampled_climate_not_global_census_or_mars_score',
        'csv_file':str(climate_csv),'csv_sha256':sha256_file(climate_csv),
        'selected':1,'years':[2015,2024]})
    return {'matrix_report':matrix,'domain_report':domain,'geology_report':mars_report,
            'glim_csv':glim,'screen_report':screen,'climate_report':climate,
            'audit_report':audit_dir/'rank_audit_report.json','tmp':tmp_path}


def run(inputs, **kw):
    base={k:inputs[k] for k in ('matrix_report','domain_report','geology_report','glim_csv','screen_report')}
    base.update({'out_csv':inputs['tmp']/'multi.csv','out_json':inputs['tmp']/'multi.json',
                 'out_markdown':inputs['tmp']/'multi.md','shortlist_top':5,
                 'climate_report':inputs['climate_report'],'audit_report':inputs['audit_report'],
                 'scales_report':None})
    base.update(kw)
    return build_multicriteria(**base)


def test_end_to_end_evidence_and_review(inputs):
    result=run(inputs)
    assert result['rows']==6 and result['profiles']==6
    assert result['climate']=='available_earth_context_only'
    assert result['alternative_rank_diagnostics']=='available_diagnostic_only'
    assert result['multiscale_diagnostics']=='not_available'
    doc=json.loads((inputs['tmp']/'multi.json').read_text())
    assert doc['status']=='noncompensatory_evidence_triage_no_joint_similarity_score'
    assert len(doc['candidates'])==6
    for rec in doc['candidates']:
        assert rec['mars_volcanic_keyword_points']==1
        assert rec['earth_volcanic_point_count']==2
        assert rec['geological_signal']=='shared_broad_volcanic_mapping_signal'
        assert rec['mars_climate_similarity']=='NOT_EVALUATED'
        assert rec['combined_similarity_score'] is None
        assert rec['earth_nasa_power_climate']['air_temp_mean_c']==-5.3
        assert rec['climate_status']=='complete'
        assert rec['analog_validated'] is False
    assert 'No es un ranking combinado' in (inputs['tmp']/'multi.md').read_text()
    view=review_multicriteria(inputs['tmp']/'multi.json','elysium_planitia')
    assert len(view['rows'])==1 and view['rows'][0]['mars_profile']=='elysium_planitia'
    with pytest.raises(ValueError,match='no encontrado'):
        review_multicriteria(inputs['tmp']/'multi.json','spirit_rover')


def test_without_optional_environment_or_audit(inputs):
    result=run(inputs,climate_report=None,audit_report=None,scales_report=None)
    assert result['rows']==6
    assert result['climate']=='not_available'
    assert result['alternative_rank_diagnostics']=='not_available'
    doc=json.loads((inputs['tmp']/'multi.json').read_text())
    assert all(r['climate_status']=='not_available' for r in doc['candidates'])
    assert all(r['combined_similarity_score'] is None for r in doc['candidates'])


def test_multiscale_candidate_positions(inputs):
    s=json.loads(inputs['screen_report'].read_text())
    r=next(x for x in s['profiles'] if x['id']=='elysium_planitia')
    first=list(csv.DictReader(open(r['ranking_csv'],encoding='utf-8')))
    rank=next(int(x['rank']) for x in first if x['region_id']=='r00000')
    sc_csv=inputs['tmp']/'scale.csv'
    with sc_csv.open('w',encoding='utf-8',newline='') as f:
        wr=csv.DictWriter(f,fieldnames=['scale','mars_profile','region_id','rank'])
        wr.writeheader()
        for p in s['profiles']:
            rows=list(csv.DictReader(open(p['ranking_csv'],encoding='utf-8')))
            rnk=next(int(x['rank']) for x in rows if x['region_id']=='r00000')
            for scale,value in [('15km_17x17',1),('30km_9x9',rnk),('40km_7x7',rnk)]:
                wr.writerow({'scale':scale,'mars_profile':p['id'],'region_id':'r00000','rank':value})
    scale_json=inputs['tmp']/'scales.json'
    atomic_json(scale_json,{'schema_version':'mars_analog_profile_audit_v1.2.1',
        'status':'fixed_window_multiscale_experiment_no_reranking_of_historical_results',
        'source_hashes':{'v12_screen':sha256_file(inputs['screen_report'])},
        'files':{'rankings':{'file':str(sc_csv),'sha256':sha256_file(sc_csv)}}})
    result=run(inputs,scales_report=scale_json)
    assert result['multiscale_diagnostics']=='available_diagnostic_only'
    doc=json.loads((inputs['tmp']/'multi.json').read_text())
    elysium=next(x for x in doc['candidates'] if x['mars_profile']=='elysium_planitia')
    assert elysium['scale_ranks']['30km_9x9']==rank
    assert elysium['scale_ranks']['15km_17x17']==1
    assert elysium['scale_shortlist_stability'] in ('in_shortlist_all_scales','shortlist_changes_with_scale')


def test_tamper_matrix_csv_fails_closed(inputs):
    with open(inputs['tmp']/'matrix.csv','a',encoding='utf-8') as f:f.write('\ntamper')
    with pytest.raises(ValueError,match='SHA-256'):
        run(inputs)
    assert not (inputs['tmp']/'multi.json').exists()


def test_tamper_climate_fails_closed(inputs):
    with open(inputs['tmp']/'environment.csv','a',encoding='utf-8') as f:f.write('\ntamper')
    with pytest.raises(ValueError,match='SHA-256'):
        run(inputs)


def test_tamper_ranking_fails_closed(inputs):
    s=json.loads(inputs['screen_report'].read_text())
    rank_file=Path(s['profiles'][0]['ranking_csv'])
    with rank_file.open('a') as f:f.write('\ntamper')
    with pytest.raises(ValueError,match='SHA-256'):
        run(inputs)


def test_mismatched_matrix_with_valid_new_checksum_fails(inputs):
    path=inputs['tmp']/'matrix.csv'
    with path.open(newline='',encoding='utf-8') as f:
        rows=list(csv.DictReader(f))
    rows[0]['topographic_rank_v12']='10000'
    with path.open('w',newline='',encoding='utf-8') as f:
        w=csv.DictWriter(f,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)
    m=json.loads(inputs['matrix_report'].read_text())
    m['csv_sha256']=sha256_file(path)
    atomic_json(inputs['matrix_report'],m)
    with pytest.raises(ValueError,match='ranking topográfico'):
        run(inputs)


@pytest.mark.parametrize('flag,tails,want',[
  ('within_sampled_earth_feature_ranges',0,'within_sampled_feature_ranges_only'),
  ('within_sampled_earth_feature_ranges',3,'caution_extreme_terrestrial_tail'),
  ('partial_reference_extrapolation',5,'caution_partial_extrapolation'),
  ('strong_reference_extrapolation',5,'blocked_reference_outside_range'),
  ('all_features_outside_sampled_earth_range',5,'blocked_reference_outside_range'),
])
def test_noncompensatory_domain_gates(flag,tails,want):
    assert _domain_gate({'domain_flag':flag,'extreme_one_sided_features_95pct':tails})==want


def test_geology_vocabulary_not_a_lithologic_match():
    mars={'mapped':3,'unit_code_counts':json.dumps({'AHtu':2,'eHv':1}),
          'descriptions':json.dumps({'AHtu':'Amazonian undivided unit','eHv':'Early Hesperian volcanic unit'})}
    signal,nm,ne=_geology_signal(mars,{'Basic volcanic rocks':2,'Mixed sedimentary rocks':7},9)
    assert signal=='shared_broad_volcanic_mapping_signal' and (nm,ne)==(1,2)
    assert _geology_signal(mars,{'Mixed sedimentary rocks':9},9)[0]=='volcanic_mars_not_observed_in_earth_points'
    assert _geology_signal(mars,{},0)[0]=='insufficient_mapped_geology'
    with pytest.raises(ValueError,match='Conteos'):
        _geology_signal(mars,{'Basic volcanic rocks':1},9)


def test_invalid_shortlist_rejected(inputs):
    with pytest.raises(ValueError,match='shortlist-top'):
        run(inputs,shortlist_top=0)


def test_read_only_review_detects_tamper(inputs):
    run(inputs)
    with (inputs['tmp']/'multi.csv').open('a') as f:f.write('modified')
    with pytest.raises(ValueError,match='SHA-256'):
        review_multicriteria(inputs['tmp']/'multi.json')
