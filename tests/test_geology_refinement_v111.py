"""Deterministic GLiM API fixtures: not a live ArcGIS or field validation."""
import json

import pytest
from shapely.geometry import Polygon

from mars_analog.data.download import atomic_json, sha256_file
from mars_analog.data.geology_glim import build_plan, fetch_points
from mars_analog.data.geology_refinement import (
    _query_polygon, candidate_volcanic_points, clip_one, fetch_boundary_clips,
    summarize_boundary_clips, terrain_bboxes,
)


class Reply:
    def __init__(self, data):
        self.data = data
        self.content = json.dumps(data).encode()
    def raise_for_status(self):
        pass
    def json(self):
        return self.data


class FakeAPI:
    def __init__(self, replies):
        self.replies = list(replies)
        self.calls = []
    def get(self, url, params, timeout):
        self.calls.append((url, params, timeout))
        return Reply(self.replies.pop(0))


def envplan(tmp):
    p = tmp/'env.json'
    atomic_json(p, {'schema_version': 'mars_analog_environment_plan_v1.0',
                    'source_ranking_sha256': 'abc', 'sample_size': 2,
                    'candidates': [
                        {'region_id': 'r063_c140', 'center_lat': 37., 'center_lon_180': -79., 'topographic_rank': 1, 'selection': 'anchor_topography'},
                        {'region_id': 'r026_c146', 'center_lat': -37., 'center_lon_180': -67., 'topographic_rank': 6, 'selection': 'stratified_exploration'},
                    ]})
    return p


def lithology(value):
    return {'features': [{'attributes': {'xx_Description': value}}]}


def volcanic_polygon():
    # clockwise exterior, as emitted by ArcGIS feature-layer polygon geometries
    return {'features': [{'attributes': {'OBJECTID': 20, 'xx_Description': 'Basic volcanic rocks'},
                          'geometry': {'rings': [[[-67.25, -37.25], [-67.25, -36.75],
                                                  [-66.75, -36.75], [-66.75, -37.25],
                                                  [-67.25, -37.25]]]}}]}


def prepare(tmp):
    plan = tmp/'geology.json'
    build_plan(envplan(tmp), plan, limit=1, region_ids='r026_c146', points_per_region=1)
    cache = tmp/'geo_raw'
    result = fetch_points(plan, cache, limit=1, session=FakeAPI([lithology('Basic volcanic rocks')]))
    assert result['new_downloads'] == 1
    return plan, cache


def test_point_selection_and_clip_geometries(tmp_path):
    plan, cache = prepare(tmp_path)
    obj, pts = candidate_volcanic_points(plan, cache)
    assert len(pts) == 1 and pts[0]['point_id'] == 'r026_c146_p00'
    clipped = clip_one(pts[0], volcanic_polygon(), 'digest', sha256_file(plan), 25.)
    assert clipped['type'] == 'FeatureCollection'
    a = clipped['metadata']['approximate_clipped_volcanic_area_km2']
    assert 500 < a < 2000
    assert clipped['features'][0]['properties']['GLiM_class'] == 'Basic volcanic rocks'


def test_boundary_fetch_cache_summary_and_study_bboxes(tmp_path):
    plan, cache = prepare(tmp_path)
    f = FakeAPI([volcanic_polygon()])
    first = fetch_boundary_clips(plan, cache, tmp_path/'clips',
                                 limit=2, radius_km=25., session=f)
    assert first['new_downloads'] == 1 and first['pending'] == 0
    assert f.calls[0][1]['returnGeometry'] == 'true'
    assert f.calls[0][1]['outSR'] == 4326
    assert f.calls[0][1]['maxAllowableOffset'] == 0.001
    assert f.calls[0][1]['geometry'] == '-67.0,-37.0'
    assert (tmp_path/'clips').exists()
    second = fetch_boundary_clips(plan, cache, tmp_path/'clips', session=FakeAPI([]))
    assert second['cached_before'] == 1 and second['new_downloads'] == 0
    summ = summarize_boundary_clips(plan, cache, tmp_path/'clips',
                                    tmp_path/'out.csv', tmp_path/'out.json')
    assert summ['clipped'] == 1 and summ['pending'] == 0
    roi = terrain_bboxes(plan, cache, tmp_path/'roi.json')
    assert len(roi['areas']) == 1
    assert roi['areas'][0]['bbox_W_S_E_N'][0] < -67
    assert '--stride 1' in roi['areas'][0]['powershell_command']
    assert roi['status'] == 'download_instructions_only_no_high_resolution_rover_DTM'


def test_failures_do_not_poison_cache(tmp_path):
    plan, cache = prepare(tmp_path)
    f = FakeAPI([{'error': {'code': 400, 'message': 'unavailable geometry'}}])
    first = fetch_boundary_clips(plan, cache, tmp_path/'clips', session=f)
    assert first['new_downloads'] == 0 and first['pending'] == 1
    assert '400' in first['failures'][0]['error']
    assert list((tmp_path/'clips').rglob('*.geojson')) == [] if (tmp_path/'clips').exists() else True
    summ = summarize_boundary_clips(plan, cache, tmp_path/'clips', tmp_path/'s.csv', tmp_path/'s.json')
    assert summ['clipped'] == 0 and summ['pending'] == 1


def test_not_faking_volcanic_when_service_disagrees(tmp_path):
    plan, cache = prepare(tmp_path)
    response = volcanic_polygon()
    response['features'][0]['attributes']['xx_Description'] = 'Unconsolidated sediments'
    failed = fetch_boundary_clips(plan, cache, tmp_path/'clips', session=FakeAPI([response]))
    assert failed['new_downloads'] == 0
    assert failed['pending'] == 1


def test_bad_geometry_and_invalid_scale_rejected(tmp_path):
    plan, cache = prepare(tmp_path)
    _, pts = candidate_volcanic_points(plan, cache)
    bad = volcanic_polygon()
    bad['features'][0]['geometry']['rings'][0] = [[-67, -37], [-67.1, -37.1]]
    with pytest.raises(ValueError):
        clip_one(pts[0], bad, 'digest', sha256_file(plan), 25)
    with pytest.raises(ValueError):
        clip_one(pts[0], volcanic_polygon(), 'digest', sha256_file(plan), 1000)
    with pytest.raises(ValueError):
        terrain_bboxes(plan, cache, tmp_path/'rois.json', half_width_km=100)


def test_reuse_unchanged_points_across_geology_plans(tmp_path):
    env = envplan(tmp_path)
    original = tmp_path/'plan_a.json'
    expanded = tmp_path/'plan_b.json'
    build_plan(env, original, limit=1, region_ids='r026_c146', points_per_region=1)
    build_plan(env, expanded, limit=2, points_per_region=1)
    dest = tmp_path/'geo'
    fetch_points(original, dest, limit=1, session=FakeAPI([lithology('Basic volcanic rocks')]))
    result = fetch_points(expanded, dest, limit=2,
                          session=FakeAPI([lithology('Metamorphics')]))
    assert result['reused_from_compatible_plan'] == 1
    assert result['new_downloads'] == 1
    assert result['cached_before'] == 1
    assert result['pending'] == 0
    # Changing point coordinates must prevent reuse, even with identical IDs.
    third = tmp_path/'plan_c.json'
    build_plan(env, third, limit=1, region_ids='r026_c146', points_per_region=1)
    model = json.loads(third.read_text())
    model['points'][0]['lat'] = -37.2
    atomic_json(third, model)
    result = fetch_points(third, dest, limit=1,
                          session=FakeAPI([lithology('Siliciclastic sedimentary rocks')]))
    assert result['reused_from_compatible_plan'] == 0
    assert result['new_downloads'] == 1


def test_source_polygon_query_must_not_be_truncated(tmp_path):
    plan, cache = prepare(tmp_path)
    _, pts = candidate_volcanic_points(plan, cache)
    with pytest.raises(ValueError, match='truncado'):
        _query_polygon(pts[0], timeout=20, session=FakeAPI([{'features': [], 'exceededTransferLimit': True}]))
