"""V1.3.1 integration: inherited synthetic data, taxonomy guardrails, tampering."""
import csv
import json
from pathlib import Path

import pytest

from mars_analog.data.download import atomic_json, sha256_file
from mars_analog.data.mars_domain_v122 import evidence_matrix
from mars_analog.data.mars_geology_correspondence_v131 import (
    _earth_class_families, _mars_process_units, _relation,
    build_correspondences, review_correspondences, review_local_nasadem,
)
from test_mars_multicriteria_v130 import inputs, run as run_multicriteria
from mars_analog.data.mars_multicriteria_v130 import build_multicriteria


def _build(inputs):
    run_multicriteria(inputs)
    root=inputs['tmp']
    return build_correspondences(root/'multi.json',inputs['geology_report'],
        inputs['domain_report'],inputs['glim_csv'],inputs['screen_report'],
        root/'correspondence.csv',root/'correspondence.json',root/'correspondence.md',5)


def test_correspondence_integration_and_review(inputs):
    result=_build(inputs)
    assert result['profiles']==6 and result['glim_sampled_regions']==1
    assert result['pairs']==6 and result['previously_examined_pairs']==6
    doc=json.loads((inputs['tmp']/'correspondence.json').read_text())
    assert all(row['combined_similarity_score'] is None for row in doc['rows'])
    assert all(row['hard_geologic_incompatibility_confirmed'] is False for row in doc['rows'])
    assert all(row['previously_examined_v130'] for row in doc['rows'])
    assert all(row['earth_classified_points']==9 for row in doc['rows'])
    view=review_correspondences(inputs['tmp']/'correspondence.json','elysium_planitia','r00000')
    assert view['returned']==view['matches']==1
    with pytest.raises(ValueError,match='no encontrado'):
        review_correspondences(inputs['tmp']/'correspondence.json','missing',limit=10)
    with pytest.raises(ValueError,match='Región no encontrada'):
        review_correspondences(inputs['tmp']/'correspondence.json','elysium_planitia','missing')


def test_add_new_glim_anchor_without_changing_old_v130_matrix(inputs):
    # Regenerate the older matrix and V1.3.0 after extending GLiM; legacy still
    # compares only r00000, while V1.3.1 evaluates two anchors per profile.
    glim=inputs['glim_csv']
    with glim.open('a',encoding='utf-8',newline='') as f:
        writer=csv.writer(f)
        writer.writerow(['r00001',9,0,'{"Acid plutonic rocks": 4, "Mixed sedimentary rocks": 5}'])
    root=inputs['tmp']
    evidence_matrix(inputs['geology_report'],inputs['domain_report'],glim,
                    inputs['screen_report'],root/'matrix.csv',inputs['matrix_report'],watch='r00000')
    result=_build(inputs)
    assert result['pairs']==12
    doc=json.loads((root/'correspondence.json').read_text())
    fresh=[r for r in doc['rows'] if r['earth_region_id']=='r00001']
    assert len(fresh)==6 and all(not x['previously_examined_v130'] for x in fresh)
    assert all(x['earth_glim_lithology_counts']['Acid plutonic rocks']==4 for x in fresh)
    assert all('plutonic_rock_class_must_not_be_interpreted_as_eruptive_volcanism' in x['interpretation_limits'] for x in fresh)


def test_glim_unknown_category_rejected():
    with pytest.raises(ValueError,match='etiquetas no reconocidas'):
        _earth_class_families({'Artificial volcano':1},1)


def test_no_negative_evidence_from_missing_points():
    a,b,c=_relation({'volcanic_cartographic_unit':[{'unit_code':'Ave'}]},
                    {'sedimentary_or_unconsolidated_lithology':[{'glim_class':'Unconsolidated sediments'}]},9,9)
    assert a=='martian_volcanic_earth_sediment_observed_only'
    assert b=='volcanism_not_observed_not_disproved'
    assert 'map_taxonomies_and_geologic_ages_not_equivalent' in c
    assert _relation({'volcanic_cartographic_unit':[{'unit_code':'Ave'}]}, {},9,0)[1]=='missing_evidence_not_negative'


def test_impact_map_not_glim_impact_proof():
    relation, strength, notes = _relation({'impact_cartographic_unit':[{'unit_code':'AHi'}]},
                {'sedimentary_or_unconsolidated_lithology':[{'glim_class':'Mixed sedimentary rocks'}]},9,9)
    assert 'impact_origin_not' not in strength
    assert 'martian_impact_origin_cannot_be_checked_from_glim_lithology' in notes
    assert relation=='no_broad_shared_process_demonstrated'


def test_martian_map_description_must_match_counts():
    with pytest.raises(ValueError,match='coinciden'):
        _mars_process_units({'mapped':2,'unit_code_counts':'{"Ave":2}', 'descriptions':'{"lAv":"Late Amazonian volcanic"}'})


def test_tampered_old_csv_rejected(inputs):
    _build(inputs)
    with (inputs['tmp']/'multi.csv').open('a',encoding='utf-8') as f:
        f.write('corrupted')
    with pytest.raises(ValueError,match='SHA-256'):
        build_correspondences(inputs['tmp']/'multi.json',inputs['geology_report'],
            inputs['domain_report'],inputs['glim_csv'],inputs['screen_report'],
            inputs['tmp']/'c2.csv',inputs['tmp']/'c2.json',inputs['tmp']/'c2.md')


def test_tampered_source_glim_rejected(inputs):
    _build(inputs)
    with inputs['glim_csv'].open('a',encoding='utf-8') as f:f.write('corrupted')
    with pytest.raises(ValueError,match='SHA-256'):
        build_correspondences(inputs['tmp']/'multi.json',inputs['geology_report'],
            inputs['domain_report'],inputs['glim_csv'],inputs['screen_report'],
            inputs['tmp']/'c2.csv',inputs['tmp']/'c2.json',inputs['tmp']/'c2.md')


def test_tampered_v131_csv_rejected(inputs):
    _build(inputs)
    with (inputs['tmp']/'correspondence.csv').open('a',encoding='utf-8') as f:
        f.write('corrupted')
    with pytest.raises(ValueError,match='SHA-256'):
        review_correspondences(inputs['tmp']/'correspondence.json')


def test_invalid_top_n_rejected(inputs):
    run_multicriteria(inputs)
    with pytest.raises(ValueError,match='top-n'):
        build_correspondences(inputs['tmp']/'multi.json',inputs['geology_report'],
            inputs['domain_report'],inputs['glim_csv'],inputs['screen_report'],
            inputs['tmp']/'c2.csv',inputs['tmp']/'c2.json',inputs['tmp']/'c2.md',top_n=0)


def test_local_context_rejects_wrong_site_or_damaged_netcdf(tmp_path):
    data=tmp_path/'tile.nc';data.write_bytes(b'a')
    polygon=tmp_path/'p04.geojson';polygon.write_text('{}')
    def create(label):
        polygon_loc=tmp_path/(label+'.geojson');polygon_loc.write_text('{}')
        src=tmp_path/(label+'.json')
        atomic_json(src,{'schema_version':'mars_analog_local_volcanic_terrain_v1.1.2',
            'status':'descriptive_nasadem_30m_within_glim_volcanic_clips_no_rover_safety_claim',
            'point_id':'r026_c146_'+label,'region_id':'r026_c146',
            'output_netcdf':str(data),'output_netcdf_sha256':sha256_file(data),
            'glim':{'geojson_file':str(polygon_loc),'geojson_sha256':sha256_file(polygon_loc),
                    'approx_glim_clipped_area_km2':150},
            'slope_deg':{'median':1.2,'p90':2.5},
            'roughness_std11_m':{'median':4.0,'p90':7.8}})
        return src
    p04=create('p04');p08=create('p08')
    assert len(review_local_nasadem(p04,p08,tmp_path/'local.json')['sites'])==2
    data.write_bytes(b'changed')
    with pytest.raises(ValueError,match='SHA-256'):
        review_local_nasadem(p04,p08,tmp_path/'local2.json')
    assert not (tmp_path/'local2.json').exists()
