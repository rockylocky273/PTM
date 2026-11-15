"""Local synthetic tests: no NASA downloads or field-groundtruth claims."""
import csv
import json
import zipfile
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest
from shapely.geometry import Polygon, mapping

from mars_analog.data.download import atomic_json, sha256_file
from mars_analog.data.nasadem_highres import (
    DATASET, MAX_HGT_BYTES, PLAN_SCHEMA, _geometry_mask, _spatial_metrics,
    build_plan, download_tiles, mosaic_bbox, read_plan, required_tiles,
    search_tiles, tile_name, verify_zip,
)


def plan(tmp_path):
    roi = tmp_path/'rois.json'
    atomic_json(roi, {'schema_version':'mars_analog_local_terrain_roi_plan_v1.1.1',
                      'region_id':'r026_c146', 'areas':[
                          {'point_id':'r026_c146_p04',
                           'bbox_W_S_E_N':[-68.01346,-37.2698,-67.33782,-36.7302]},
                          {'point_id':'r026_c146_p08',
                           'bbox_W_S_E_N':[-68.01589,-37.80939,-67.33539,-37.2698]}]})
    output=tmp_path/'nasadem.json'
    build_plan(roi,output)
    return output


def test_required_tiles_and_coverage():
    assert tile_name(-38,-69)=='s38w069'
    assert tile_name(0,0)=='n00e000'
    assert [t['name'] for t in required_tiles([-68.1,-37.5,-67.9,-37.1])] == [
        's38w069','s38w068']
    with pytest.raises(ValueError):
        required_tiles([-68,-65,-67,-64])
    with pytest.raises(ValueError):
        required_tiles([177,0,-179,1])


def test_plan_all_four_tiles_and_hash(tmp_path):
    src = plan(tmp_path)
    obj=read_plan(src)
    assert obj['schema_version']==PLAN_SCHEMA
    assert len(obj['tiles'])==4
    assert {r['name'] for r in obj['tiles']} == {
        's37w068','s37w069','s38w068','s38w069'}
    assert len(obj['areas'])==2
    doc=json.loads(src.read_text())
    doc['tiles'].pop()
    atomic_json(src,doc)
    with pytest.raises(ValueError, match='inconsistente'):
        read_plan(src)


class Granule(dict):
    size = 8.0
    def __init__(self,name):
        super().__init__(umm={'GranuleUR': f'NASADEM_HGT_{name}.zip'})
        self.name=name
    def data_links(self,access='external'):
        assert access=='external'
        return [f'https://example.nasa.gov/NASADEM_HGT_{self.name}.zip']


class FakeEA:
    def __init__(self):
        self.queried=[]
        self.downloaded=[]
        self.logged_in=0
    def search_data(self, **kwargs):
        self.queried.append(kwargs)
        assert kwargs['short_name']==DATASET
        bbox=kwargs['bounding_box']
        lat,lon=int(np.floor(bbox[1])),int(np.floor(bbox[0]))
        return [Granule(tile_name(lat,lon))]
    def login(self,*,strategy,persist):
        self.logged_in+=1
        assert strategy=='all' and persist is False
        return SimpleNamespace(authenticated=True)
    def download(self, granules, directory, threads, show_progress):
        self.downloaded.extend(granules)
        folder=Path(directory)
        for g in granules:
            create_zip(folder/g['umm']['GranuleUR'],g.name)
        return [str(folder/g['umm']['GranuleUR']) for g in granules]


def create_zip(path:Path, name:str, value:int=400):
    arr=np.full((3601,3601),value,dtype='>i2')
    with zipfile.ZipFile(path,'w',compression=zipfile.ZIP_DEFLATED) as fd:
        fd.writestr(f'{name}.hgt',arr.tobytes())


def test_search_and_download_does_not_store_credentials(tmp_path):
    p=plan(tmp_path)
    api=FakeEA()
    m=tmp_path/'manifest.json'
    r=search_tiles(p,m,earthaccess_client=api)
    assert r['resolved']==4 and r['unresolved']==[]
    assert api.logged_in==0
    d=tmp_path/'dem'
    result=download_tiles(p,m,d,limit=1,earthaccess_client=api)
    assert result['new_downloads']==1
    assert result['pending']==3
    assert api.logged_in==1
    result=download_tiles(p,m,d,limit=10,earthaccess_client=api)
    assert result['cached_before']==1
    assert result['pending']==0
    result=download_tiles(p,m,d,limit=1,earthaccess_client=api)
    assert result['status']=='complete_from_cache'
    assert api.logged_in==2
    assert 'password' not in m.read_text()


def test_verify_zip_rejects_wrong_hgt(tmp_path):
    bad=tmp_path/'NASADEM_HGT_s38w068.zip'
    with zipfile.ZipFile(bad,'w') as fp:
        fp.writestr('NASADEM_HGT_s38w068.hgt',b'not the full raster')
    with pytest.raises(ValueError,match='Tamaño HGT inesperado'):
        verify_zip(bad,'s38w068')


def test_mosaic_stitches_two_tiles_and_uses_correct_order(tmp_path):
    # longitude crosses -68 W, latitude lies inside one 1-degree tile.
    west=-68-2.1/3600
    east=-68+2.1/3600
    south=-37.5-2.1/3600
    north=-37.5+2.1/3600
    tiles=required_tiles([west,south,east,north])
    for t in tiles:
        create_zip(tmp_path/t['filename'],t['name'],400 if t['west']==-69 else 800)
    lat,lon,z,provenance=mosaic_bbox([west,south,east,north],tiles,tmp_path)
    assert z.shape==(5,5)
    assert np.all(np.diff(lat)<0) and np.all(np.diff(lon)>0)
    assert z[2,0]==400 and z[2,-1]==800
    assert len(provenance)==2


def test_slope_and_roughness_on_synthetic_plane():
    lat=np.array([-37+j/3600 for j in range(19,-20,-1)],dtype=float)
    # Row-index increases southward; linear height difference 1 m per 1 arcsec east.
    z=np.tile(np.arange(39,dtype=np.float32)[None,:],(39,1))
    slope,rough=_spatial_metrics(lat,z)
    assert slope.shape==z.shape
    assert np.all(np.isfinite(slope[12:20,12:20]))
    assert 1.5 < float(np.median(slope[12:20,12:20])) < 4
    assert np.allclose(rough[12:20,12:20],np.sqrt(10),atol=1e-3)
    # A void must remain void and cannot be silently interpolated.
    z[14,15] = np.nan
    slope, rough = _spatial_metrics(lat,z)
    assert np.isnan(slope[14,15])


def test_polygon_mask_and_boundaries():
    lat=np.array([-37.,-37.001,-37.002])
    lon=np.array([-68.,-67.999,-67.998])
    geom=Polygon([(-68.0005,-37.0005),(-67.9985,-37.0005),
                  (-67.9985,-37.0015),(-68.0005,-37.0015)])
    m=_geometry_mask(geom,lat,lon)
    assert m.shape==(3,3)
    assert m[1,0] and m[1,1] and not m[1,2]
    assert not m[0,:].any() and not m[2,:].any()


def test_analysis_requires_existing_glim_clips(tmp_path):
    from mars_analog.data.nasadem_highres import analyze_area
    with pytest.raises(ValueError,match='no aparece'):
        analyze_area(plan(tmp_path),tmp_path,tmp_path/'unavailable.csv',
                     'nonexistent', tmp_path/'out.nc',tmp_path/'out.json')


def test_real_pipeline_synthetic_hgt_and_polygon(tmp_path):
    import xarray as xr
    from mars_analog.data.nasadem_highres import analyze_area, compare_areas
    region='r026_c146'
    point=region+'_p04'
    bbox=[-67.685,-37.015,-67.675,-37.005]
    roi=tmp_path/'roi.json'
    atomic_json(roi,{'region_id':region,'areas':[{'point_id':point,'bbox_W_S_E_N':bbox}]})
    plan_file=tmp_path/'plan.json'
    build_plan(roi,plan_file)
    plan_doc=read_plan(plan_file)
    assert len(plan_doc['tiles'])==1
    tile=plan_doc['tiles'][0]
    directory=tmp_path/'zip'
    directory.mkdir()
    create_zip(directory/tile['filename'],tile['name'],value=400)
    # Source GLiM polygon encloses this entire small test area.
    geo=tmp_path/'volcanic.geojson'
    polygon=Polygon([(-67.7,-37.03),(-67.66,-37.03),(-67.66,-37.0),(-67.7,-37.0)])
    atomic_json(geo,{'type':'FeatureCollection',
                     'metadata':{'point_id':point,'source_layer':'example_glim',
                                 'approximate_clipped_volcanic_area_km2':12.3},
                     'features':[{'type':'Feature',
                                  'properties':{'GLiM_class':'Basic volcanic rocks'},
                                  'geometry':mapping(polygon)}]})
    csv_path=tmp_path/'boundaries.csv'
    with csv_path.open('w',newline='',encoding='utf-8') as fd:
        writer=csv.DictWriter(fd,fieldnames=['point_id','status','geojson_file','geojson_sha256'])
        writer.writeheader()
        writer.writerow({'point_id':point,'status':'clipped','geojson_file':str(geo),
                         'geojson_sha256':sha256_file(geo)})
    out=tmp_path/'raster.nc'
    report=tmp_path/'report.json'
    result=analyze_area(plan_file,directory,csv_path,point,out,report)
    assert out.exists() and report.exists()
    assert result['valid_volcanic_clip_samples']>200
    assert result['slope_deg']['median']==0
    assert result['roughness_std11_m']['median'] == 0
    assert result['exploratory_low_slope']['fraction_within_valid_clipped_grid_pct']==100
    assert 0.1<result['mapped_clip_sampled_approx_area_km2']<2
    with xr.open_dataset(out) as ds:
        assert ds.attrs['dataset']=='NASADEM_HGT.001'
        assert ds.glim_basic_volcanic_mask.values.sum()>200
        assert ds.slope_deg.values.shape==ds.elevation_m.values.shape
    # Reject the wrong point ID in comparison (fail-closed on provenance).
    with pytest.raises(ValueError,match='Orden'):
        compare_areas(report,report,tmp_path/'compare.json')


def test_nasadem_standard_zip_includes_auxiliary_layers(tmp_path):
    """Regression for NASADEM_HGT ZIP: s37w068.hgt, .num, .swb."""
    tile='s37w068'
    archive=tmp_path/f'NASADEM_HGT_{tile}.zip'
    arr=np.full((3601,3601),273,dtype='>i2')
    with zipfile.ZipFile(archive,'w',compression=zipfile.ZIP_DEFLATED) as z:
        z.writestr(f'{tile}.num',b'provenance')
        z.writestr(f'{tile}.swb',b'water')
        z.writestr(f'{tile}.hgt',arr.tobytes())
    result=verify_zip(archive,tile)
    assert result['HGT_member']==f'{tile}.hgt'


def test_nasadem_zip_allows_legacy_prefixed_hgt(tmp_path):
    tile='s37w068'
    archive=tmp_path/f'NASADEM_HGT_{tile}.zip'
    arr=np.full((3601,3601),273,dtype='>i2')
    with zipfile.ZipFile(archive,'w',compression=zipfile.ZIP_DEFLATED) as z:
        z.writestr(f'NASADEM_HGT_{tile}.hgt',arr.tobytes())
    assert verify_zip(archive,tile)['HGT_member']==f'NASADEM_HGT_{tile}.hgt'


def test_nasadem_zip_fails_closed_on_duplicate_hgt(tmp_path):
    tile='s37w068'
    archive=tmp_path/f'NASADEM_HGT_{tile}.zip'
    arr=np.full((3601,3601),273,dtype='>i2')
    with zipfile.ZipFile(archive,'w',compression=zipfile.ZIP_DEFLATED) as z:
        z.writestr(f'{tile}.hgt',arr.tobytes())
        z.writestr(f'NASADEM_HGT_{tile}.hgt',arr.tobytes())
    with pytest.raises(ValueError,match='coincidencias=2'):
        verify_zip(archive,tile)
