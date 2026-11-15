"""V1.3.3: scientific reference labels frozen independently from rankings."""
import csv
import json
from pathlib import Path

import pytest

from mars_analog.data.download import sha256_file
from mars_analog.data.mars_external_validation_v133 import (
    BENCHMARK_FILE, FROZEN_BENCHMARK_SHA256,
    _case_result, _validate_benchmark, build_external_validation, center_of_region,
    great_circle_km, region_from_latlon, review_external_validation)
from mars_analog.data.mars_profiles_v12 import SCHEMA as SCREEN_SCHEMA


PROFILE_IDS=('elysium_planitia','jezero_entorno','gale_entorno',
             'olympus_mons','meridiani_planum','syrtis_major_planum')


def _write_csv(file,columns,rows):
    file.parent.mkdir(parents=True,exist_ok=True)
    with file.open('w',encoding='utf-8',newline='') as f:
        w=csv.DictWriter(f,columns);w.writeheader();w.writerows(rows)


def _write_json(file,obj):
    file.write_text(json.dumps(obj,ensure_ascii=False,indent=2),encoding='utf-8')


def _fixture(tmp_path):
    bench=Path(__file__).resolve().parents[1]/'config'/'external_benchmarks_v1_3_3.json'
    cells=['r077_c171','r054_c102','r063_c014','r063_c121',
           'r066_c123','r062_c124']
    catalogue=tmp_path/'catalog.csv'
    _write_csv(catalogue,['region_id','status','center_lat','center_lon_180'],
               [dict(region_id=rid,status='land_candidate_unranked',
                     center_lat=center_of_region(rid)[0],center_lon_180=center_of_region(rid)[1])
                for rid in cells])
    manifest=tmp_path/'manifest.json'
    _write_json(manifest,dict(schema_version=SCREEN_SCHEMA,status='multi_profiles_built_topography_only',
                              profiles=[dict(id=p) for p in PROFILE_IDS]))
    entries=[]
    ranked_cells=[rid for rid in cells if rid!='r077_c171']
    for p in PROFILE_IDS:
        file=tmp_path/(p+'.csv')
        _write_csv(file,['region_id','rank','center_lat','center_lon_180'],[
            dict(region_id=rid,rank=i,center_lat=center_of_region(rid)[0],
                 center_lon_180=center_of_region(rid)[1])
            for i,rid in enumerate(ranked_cells,1)])
        entries.append(dict(id=p,ranking_csv=str(file),ranking_sha256=sha256_file(file),
                            ranked_count=len(ranked_cells)))
    screen=tmp_path/'screen.json'
    _write_json(screen,dict(schema_version=SCREEN_SCHEMA,
                 status='separate_topographic_rankings_not_mars_analog_confirmation',
                 manifest_sha256=sha256_file(manifest),earth_catalog_sha256=sha256_file(catalogue),
                 profiles=entries,settings={'max_abs_lat':65.}))
    domain_csv=tmp_path/'domain.csv'
    _write_csv(domain_csv,['profile','outside_catalog_minmax'],
               [dict(profile=p,outside_catalog_minmax=int(p=='olympus_mons')*5) for p in PROFILE_IDS])
    domain=tmp_path/'domain.json'
    _write_json(domain,dict(schema_version='mars_analog_reference_domain_audit_v1.2.2',
                  status='numeric_reference_coverage_not_validation',
                  csv_file=str(domain_csv),csv_sha256=sha256_file(domain_csv),
                  profiles=[dict(profile=p,domain_flag=('all_features_outside_sampled_earth_range' if p=='olympus_mons' else 'within_sampled_earth_feature_ranges'),
                                 outside_catalog_minmax=5 if p=='olympus_mons' else 0) for p in PROFILE_IDS]))
    scales_csv=tmp_path/'scales.csv'
    _write_csv(scales_csv,['scale','mars_profile','region_id','rank'],[
        dict(scale=scale,mars_profile=p,region_id=rid,rank=i)
        for scale in ('15km_17x17','30km_9x9','40km_7x7')
        for p in PROFILE_IDS for i,rid in enumerate(ranked_cells,1)])
    scales=tmp_path/'scales.json'
    _write_json(scales,dict(schema_version='mars_analog_profile_audit_v1.2.1',
         status='fixed_window_multiscale_experiment_no_reranking_of_historical_results',
         source_hashes={'v12_screen':sha256_file(screen),'v12_manifest':sha256_file(manifest)},
         files={'rankings':dict(file=str(scales_csv),sha256=sha256_file(scales_csv))}))
    return dict(benchmark=bench,screen=screen,manifest=manifest,catalog=catalogue,
                domain=domain,scales=scales,out_csv=tmp_path/'benchmark.csv',
                out_report=tmp_path/'benchmark.json',out_markdown=tmp_path/'benchmark.md',
                strict_catalog=False)


def test_frozen_cases_have_credible_structured_provenance():
    path=Path(__file__).resolve().parents[1]/'config'/'external_benchmarks_v1_3_3.json'
    assert sha256_file(path)==FROZEN_BENCHMARK_SHA256
    obj=_validate_benchmark(path)
    assert len(obj['cases'])==9
    assert sum(c['role']=='documented_direct_target_analogue' for c in obj['cases'])==4
    assert sum(c['role']=='process_scope_contrast_not_negative_site' for c in obj['cases'])==2


def test_geographic_cell_mapping_and_dateline():
    assert region_from_latlon(-37.,-67.67564)=='r026_c146'
    assert center_of_region('r026_c146')==(-37,-67)
    assert region_from_latlon(64.8498,-16.829975)=='r077_c171'
    assert region_from_latlon(19.475,-155.608)=='r054_c102'
    assert region_from_latlon(37.55,29.68)=='r063_c014'
    assert region_from_latlon(36.229805,-116.767413)=='r063_c121'
    assert region_from_latlon(5.0,179.999)=='r047_c089'
    assert region_from_latlon(5.0,-179.999)=='r047_c090'
    assert great_circle_km(0,179.9,0,-179.9)<25
    with pytest.raises(ValueError):region_from_latlon(91,23)
    with pytest.raises(ValueError):region_from_latlon(0,181)
    with pytest.raises(ValueError):center_of_region('r999_c001')


def test_full_external_benchmark_and_scope_controls(tmp_path):
    a=_fixture(tmp_path)
    r=build_external_validation(**a)
    assert r['summary']['external_cases']==9
    assert r['summary']['direct_target_process_analogues']==4
    assert r['summary']['direct_sites_represented_in_ranked_population']==3
    assert r['summary']['direct_sites_missing_from_ranked_population']==1
    assert r['summary']['direct_sites_with_mars_profile_out_of_domain']==1
    assert r['summary']['scope_contrasts_blocked']==2
    assert r['summary']['validated_analogs']==0
    doc=json.loads(a['out_report'].read_text())
    by={x['case_id']:x for x in doc['results']}
    assert by['holuhraun_elysium']['earth_region_id']=='r077_c171'
    assert by['holuhraun_elysium']['topographic_rank'] is None
    assert by['holuhraun_elysium']['evaluation_status']=='external_site_not_in_screened_population'
    assert by['mauna_loa_olympus']['evaluation_status']=='topography_outside_reference_domain'
    assert by['salda_jezero']['evaluation_status']=='topographic_retrieval_descriptor_only'
    assert by['salda_jezero']['scale_ranks']['30km_9x9']==by['salda_jezero']['topographic_rank']
    assert by['salda_olympus_scope_contrast']['topographic_rank'] is None
    assert by['salda_olympus_scope_contrast']['control_is_negative_geology_label'] is False
    assert by['atacama_out_of_scope']['earth_region_id'] is None
    assert all(not x['geological_analogy_proven_by_engine'] for x in doc['results'])
    assert review_external_validation(a['out_report'],'holuhraun_elysium')['cases'][0]['case_id']=='holuhraun_elysium'
    with pytest.raises(ValueError,match='no encontrado'):
        review_external_validation(a['out_report'],'unknown')


def test_tampered_ranking_is_rejected_before_outputs(tmp_path):
    a=_fixture(tmp_path)
    csv_file=tmp_path/'elysium_planitia.csv'
    csv_file.write_text(csv_file.read_text()+'\ncorrupt',encoding='utf-8')
    with pytest.raises(ValueError,match='SHA-256'):
        build_external_validation(**a)
    assert not a['out_report'].exists()


def test_tampered_frozen_reference_is_rejected(tmp_path):
    a=_fixture(tmp_path)
    bad=tmp_path/'modified_benchmark.json'
    src=json.loads(a['benchmark'].read_text())
    src['cases'][0]['reference_statement']='arbitrary new claim'
    _write_json(bad,src);a['benchmark']=bad
    with pytest.raises(ValueError,match='congelado'):
        build_external_validation(**a)


def test_mismatched_multiscale_hash_is_rejected(tmp_path):
    a=_fixture(tmp_path)
    doc=json.loads(a['scales'].read_text())
    doc['source_hashes']['v12_screen']='0'*64
    _write_json(a['scales'],doc)
    with pytest.raises(ValueError,match='no corresponde'):
        build_external_validation(**a)


def test_report_rejects_tampered_output_csv(tmp_path):
    a=_fixture(tmp_path)
    build_external_validation(**a)
    a['out_csv'].write_text(a['out_csv'].read_text()+'\ninjected',encoding='utf-8')
    with pytest.raises(ValueError,match='SHA-256'):
        review_external_validation(a['out_report'])


def test_earth_catalog_center_mismatch_rejected(tmp_path):
    a=_fixture(tmp_path)
    rows=list(csv.DictReader(a['catalog'].open()))
    rows[0]['center_lon_180']='0'
    _write_csv(a['catalog'],list(rows[0]),rows)
    scr=json.loads(a['screen'].read_text());scr['earth_catalog_sha256']=sha256_file(a['catalog']);_write_json(a['screen'],scr)
    with pytest.raises(ValueError,match='Centros'):
        build_external_validation(**a)


def test_incorrect_midscale_rank_is_rejected(tmp_path):
    a=_fixture(tmp_path)
    s_rows=list(csv.DictReader(a['scales'].with_name('scales.csv').open()))
    for r in s_rows:
        if r['scale']=='30km_9x9' and r['mars_profile']=='jezero_entorno' and r['region_id']=='r063_c014':
            r['rank']='99';break
    sc_csv=tmp_path/'scales.csv'
    _write_csv(sc_csv,list(s_rows[0]),s_rows)
    doc=json.loads(a['scales'].read_text());doc['files']['rankings']['sha256']=sha256_file(sc_csv)
    _write_json(a['scales'],doc)
    with pytest.raises(ValueError,match='30km'):
        build_external_validation(**a)


def test_old_cli_parser_coexists_with_new_commands():
    from mars_analog.data.cli import make_parser
    p=make_parser()
    assert p.parse_args(['mars-external-benchmark-build']).command=='mars-external-benchmark-build'
    assert p.parse_args(['mars-external-benchmark-review','--case','salda_jezero']).case=='salda_jezero'
    assert p.parse_args(['mars-uncertainty-review']).command=='mars-uncertainty-review'


def test_report_rejects_a_ranking_changed_after_build(tmp_path):
    a=_fixture(tmp_path)
    build_external_validation(**a)
    rankfile=tmp_path/'jezero_entorno.csv'
    rankfile.write_text(rankfile.read_text()+'\nchanged',encoding='utf-8')
    with pytest.raises(ValueError,match='SHA-256'):
        review_external_validation(a['out_report'])
