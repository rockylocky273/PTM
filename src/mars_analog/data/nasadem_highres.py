"""V1.1.2: high-resolution NASADEM HGT workflow, entirely separate from Mars ranking.

NASADEM ~1 arcsec is NOT a survey-grade bare-earth DTM. GLiM generalized geology
clips are map units, not field-verified outcrops. 30 m grid slopes are NOT rover
trafficability, nor are connected low-slope patches safe habitat sites.
"""
from __future__ import annotations

import csv
import importlib.util
import json
import math
import os
import re
import zipfile
from pathlib import Path
from typing import Any

import numpy as np
import xarray as xr
from scipy.ndimage import label, uniform_filter
from shapely import contains_xy
from shapely.geometry import shape
from shapely.ops import unary_union

from .download import atomic_json, sha256_file
from .terrain_features import terrain_features, _physical_spacing

DATASET = 'NASADEM_HGT'
VERSION = '001'
PLAN_SCHEMA = 'mars_analog_nasadem_plan_v1.1.2'
SEARCH_SCHEMA = 'mars_analog_nasadem_search_v1.1.2'
REPORT_SCHEMA = 'mars_analog_local_volcanic_terrain_v1.1.2'
ROWS_PER_TILE = 3601
MAX_HGT_BYTES = ROWS_PER_TILE * ROWS_PER_TILE * 2
SOURCE_URL = 'https://doi.org/10.5067/MEaSUREs/NASADEM/NASADEM_HGT.001'
TILE_RE = re.compile(r'nasadem_hgt_[ns]\d{2}[ew]\d{3}', re.I)


def tile_name(lat: int, lon: int) -> str:
    if not -56 <= lat <= 59 or not -180 <= lon <= 179:
        raise ValueError('NASADEM soporta teselas entre 56° S y 60° N')
    return f'{"n" if lat >= 0 else "s"}{abs(lat):02d}{"e" if lon >= 0 else "w"}{abs(lon):03d}'


def required_tiles(bbox: list[float]) -> list[dict]:
    if len(bbox) != 4:
        raise ValueError('BBox requiere W,S,E,N')
    west, south, east, north = [float(a) for a in bbox]
    if not all(map(math.isfinite, (west, south, east, north))):
        raise ValueError('BBox con coordenadas no finitas')
    if not (-180 <= west < east <= 180 and -56 <= south < north <= 60):
        raise ValueError('BBox inválido o fuera de cobertura NASADEM')
    if (east - west) > 3 or (north - south) > 3:
        raise ValueError('BBox demasiado grande para análisis local (máximo 3°)')
    tiles = []
    for lat in range(math.floor(south), math.ceil(north)):
        for lon in range(math.floor(west), math.ceil(east)):
            name = tile_name(lat, lon)
            tiles.append({'name': name, 'south': lat, 'west': lon,
                          'filename': f'NASADEM_HGT_{name}.zip'})
    return tiles


def build_plan(roi_path: Path, output: Path) -> dict:
    source = json.loads(Path(roi_path).read_text(encoding='utf-8'))
    if not isinstance(source.get('areas'), list) or not source['areas']:
        raise ValueError('Se requiere geology-terrain-bboxes con areas')
    areas = []
    combined: dict[str, dict] = {}
    for area in source['areas']:
        pt = str(area['point_id'])
        box = area['bbox_W_S_E_N']
        tiles = required_tiles(box)
        if any(x['point_id'] == pt for x in areas):
            raise ValueError('Point ID repetido en las áreas')
        areas.append({'point_id': pt, 'region_id': source['region_id'],
                      'bbox_W_S_E_N': [float(v) for v in box],
                      'tile_names': [t['name'] for t in tiles]})
        for t in tiles:
            combined[t['name']] = t
    obj = {'schema_version': PLAN_SCHEMA, 'status': 'plan_only_no_download',
           'source_roi_file': str(roi_path), 'source_roi_sha256': sha256_file(roi_path),
           'dataset': DATASET, 'version': VERSION, 'doi': SOURCE_URL,
           'areas': areas, 'tiles': sorted(combined.values(), key=lambda t: t['name']),
           'limitations': [
               'NASADEM está derivado principalmente de radar SRTM de febrero de 2000 con rellenos auxiliares',
               'No es un DTM topográfico de campo ni permite resolver obstáculos individuales del rover',
               'Los polígonos GLiM son unidades cartográficas generalizadas, no afloramientos confirmados',
           ]}
    atomic_json(output, obj)
    return {'schema_version': PLAN_SCHEMA, 'status': obj['status'],
            'areas': len(areas), 'required_tiles': len(combined),
            'tiles': [t['name'] for t in obj['tiles']],
            'plan_file': str(output), 'plan_sha256': sha256_file(output)}


def read_plan(path: Path) -> dict:
    obj = json.loads(Path(path).read_text(encoding='utf-8'))
    if obj.get('schema_version') != PLAN_SCHEMA:
        raise ValueError('Plan NASADEM inválido o incompatible')
    expected = {t['name'] for a in obj['areas'] for t in required_tiles(a['bbox_W_S_E_N'])}
    observed = {t['name'] for t in obj['tiles']}
    if expected != observed or len(obj['tiles']) != len(observed):
        raise ValueError('Plan NASADEM inconsistente: teselas no coinciden con áreas')
    return obj


def _granule_id(granule: Any) -> str:
    ids = []
    if isinstance(granule, dict):
        for src in ('umm', 'meta'):
            if isinstance(granule.get(src), dict):
                ids.extend(str(v) for v in granule[src].values() if isinstance(v, str))
    ids.append(str(granule))
    try:
        ids.extend(granule.data_links(access='external'))
    except (AttributeError, ValueError):
        pass
    return ' '.join(ids).lower()


def _find_granule_for_tile(tile: dict, earthaccess_client) -> Any:
    lon, lat = tile['west'], tile['south']
    granules = earthaccess_client.search_data(
        short_name=DATASET, version=VERSION,
        bounding_box=(lon + .1, lat + .1, lon + .9, lat + .9), count=20)
    expected = 'nasadem_hgt_' + tile['name'].lower()
    matches = [g for g in granules if expected in _granule_id(g)]
    if len(matches) != 1:
        raise RuntimeError(f'CMR: {tile["name"]} produjo {len(matches)} coincidencias exactas; '
                           'no elegiré una granula al azar')
    return matches[0]


def search_tiles(plan: Path, output: Path, earthaccess_client=None) -> dict:
    if earthaccess_client is None:
        import earthaccess as earthaccess_client
    obj = read_plan(plan)
    found, missing = [], []
    for tile in obj['tiles']:
        try:
            granule = _find_granule_for_tile(tile, earthaccess_client)
            links = granule.data_links(access='external')
            size_mb = getattr(granule, 'size', None)
            found.append({'tile': tile['name'], 'granule_name': f'NASADEM_HGT_{tile["name"]}',
                          'size_mb': float(size_mb) if size_mb is not None else None,
                          'links': [l for l in links if isinstance(l,str) and l.startswith('https://')][:5]})
        except Exception as exc:
            missing.append({'tile': tile['name'], 'reason': f'{type(exc).__name__}: {str(exc)[:150]}'})
    manifest = {'schema_version': SEARCH_SCHEMA, 'source_plan_sha256': sha256_file(plan),
                'dataset': DATASET, 'version': VERSION,
                'matched': found, 'unresolved': missing}
    atomic_json(output, manifest)
    return {'schema_version': SEARCH_SCHEMA,
            'status': 'complete' if not missing else 'partial_do_not_assume_availability',
            'resolved': len(found), 'unresolved': missing,
            'granules': found, 'manifest_file': str(output)}


def _hgt_member(zfile: zipfile.ZipFile, name: str) -> zipfile.ZipInfo:
    """Locate exactly one elevation grid in a NASADEM tile ZIP.

    NASADEM_HGT_<tile>.zip normally contains <tile>.hgt, <tile>.num and
    <tile>.swb. Some test/legacy bundles use NASADEM_HGT_<tile>.hgt.
    Match only the exact tile basename (not substrings) and fail on
    ambiguity, missing elevation, or unexpected uncompressed raster size.
    Do not extract arbitrary ZIP paths onto disk.
    """
    expected = {f'{name.lower()}.hgt', f'nasadem_hgt_{name.lower()}.hgt'}
    matches = [z for z in zfile.infolist()
               if not z.is_dir()
               and z.filename.replace('\\', '/').rsplit('/', 1)[-1].lower() in expected]
    if len(matches) != 1:
        available = [z.filename for z in zfile.infolist()
                     if not z.is_dir() and z.filename.lower().endswith('.hgt')][:10]
        raise ValueError(f'Se esperaba exactamente un archivo {name}.hgt en el ZIP; '
                         f'coincidencias={len(matches)}, HGT_disponibles={available}')
    info = matches[0]
    if info.file_size != MAX_HGT_BYTES:
        raise ValueError(f'Tamaño HGT inesperado en {name}: {info.file_size} bytes '
                         f'(esperados {MAX_HGT_BYTES})')
    return info


def verify_zip(path: Path, name: str) -> dict:
    if not Path(path).is_file() or not zipfile.is_zipfile(path):
        raise ValueError(f'ZIP NASADEM no válido: {path}')
    with zipfile.ZipFile(path) as z:
        info = _hgt_member(z,name)
        if info.compress_size <= 0 or info.compress_size > 150 * 1024 * 1024:
            raise ValueError('Compresión NASADEM sospechosa')
        # Test CRC without extracting anything (no path traversal).
        with z.open(info) as fp:
            while fp.read(1024*1024):
                pass
    return {'file': str(path), 'sha256': sha256_file(path), 'bytes': path.stat().st_size,
            'HGT_member': info.filename}


def download_tiles(plan: Path, manifest: Path, directory: Path, *, limit: int = 1,
                   max_mb: float = 60, earthaccess_client=None) -> dict:
    if not 1 <= limit <= 10 or not 5 <= max_mb <= 150:
        raise ValueError('limit debe estar entre 1 y 10; max-mb entre 5 y 150')
    obj = read_plan(plan)
    indexed = json.loads(Path(manifest).read_text(encoding='utf-8'))
    if indexed.get('schema_version') != SEARCH_SCHEMA or indexed.get('source_plan_sha256') != sha256_file(plan):
        raise ValueError('Primero ejecutá nasadem-search con este mismo plan')
    lookup = {r['tile']: r for r in indexed['matched']}
    if any(t['name'] not in lookup for t in obj['tiles']):
        raise ValueError('CMR no resolvió todas las teselas; revisar nasadem-search')
    directory.mkdir(parents=True, exist_ok=True)
    cached, pending = [], []
    for tile in obj['tiles']:
        p = directory / tile['filename']
        if p.exists():
            cached.append(verify_zip(p,tile['name']))
        else:
            pending.append(tile)
    if not pending:
        return {'status': 'complete_from_cache', 'cached_before': len(cached),
                'new_downloads': 0, 'pending': 0, 'failures': [], 'downloads': []}
    if earthaccess_client is None:
        import earthaccess as earthaccess_client
    # No credentials are persisted by this function.
    auth = earthaccess_client.login(strategy='all', persist=False)
    if getattr(auth, 'authenticated', True) is False:
        raise RuntimeError('Earthdata rechazó la autenticación')
    failures, done = [], []
    for tile in pending[:limit]:
        try:
            size = lookup[tile['name']]['size_mb']
            if size is not None and size > max_mb:
                raise ValueError(f'Tesela anunciada de {size:.1f} MB supera --max-mb')
            granule = _find_granule_for_tile(tile, earthaccess_client)
            # Reject network calls if a returned granule exceeds the configured limit.
            reported = getattr(granule,'size',None)
            if reported is not None and float(reported)>max_mb:
                raise ValueError(f'Archivo de {float(reported):.1f} MB supera --max-mb')
            files = earthaccess_client.download([granule], str(directory), threads=1,
                                                show_progress=True)
            target = directory / tile['filename']
            if not target.exists():
                raise ValueError(f'NASADEM no dejó el archivo esperado {target.name}; archivos: {files}')
            if target.stat().st_size > max_mb * 1024 * 1024:
                target.unlink(missing_ok=True)
                raise ValueError('Archivo descargado excede max-mb; descartado')
            done.append({'tile':tile['name'], **verify_zip(target,tile['name'])})
        except Exception as exc:
            failures.append({'tile':tile['name'], 'error': f'{type(exc).__name__}: {str(exc)[:200]}'})
    return {'status':'download_subset_done', 'cached_before':len(cached),
            'attempted':min(len(pending),limit), 'new_downloads':len(done),
            'pending':len(pending)-len(done), 'failures':failures,
            'downloads':done, 'note':'Sin descarga automática de teselas fuera del plan'}


def _read_hgt(zip_path: Path, tile: dict) -> np.ndarray:
    with zipfile.ZipFile(zip_path) as z:
        info = _hgt_member(z,tile['name'])
        with z.open(info) as fd:
            data = fd.read(MAX_HGT_BYTES+1)
    if len(data) != MAX_HGT_BYTES:
        raise ValueError(f'HGT truncado/extendido: {tile["name"]}')
    return np.frombuffer(data, dtype='>i2').reshape((ROWS_PER_TILE,ROWS_PER_TILE))


def mosaic_bbox(bbox: list[float], tiles: list[dict], directory: Path,
                max_cells: int = 8_000_000) -> tuple[np.ndarray,np.ndarray,np.ndarray,list[dict]]:
    _ = required_tiles(bbox)
    west,south,east,north = bbox
    west_i, east_i = math.ceil(west*3600), math.floor(east*3600)
    south_i, north_i = math.ceil(south*3600), math.floor(north*3600)
    nx, ny = east_i-west_i+1, north_i-south_i+1
    if nx<3 or ny<3 or nx*ny>max_cells:
        raise ValueError(f'Recorte de tamaño {nx}x{ny} fuera del límite {max_cells} celdas')
    out = np.full((ny,nx),np.nan,dtype=np.float32)
    used = []
    for tile in tiles:
        y, x = int(tile['south'])*3600, int(tile['west'])*3600
        L,R = max(west_i,x),min(east_i,x+3600)
        B,T = max(south_i,y),min(north_i,y+3600)
        if L>R or B>T: continue
        path=directory/tile['filename']
        if not path.exists():
            raise FileNotFoundError(f'Falta tesela NASADEM: {path.name}')
        src = _read_hgt(path,tile)
        block = src[(y+3600-T):(y+3600-B+1), (L-x):(R-x+1)].astype(np.float32)
        block[block<=-32767] = np.nan
        dst = out[(north_i-T):(north_i-B+1), (L-west_i):(R-west_i+1)]
        dst[np.isnan(dst)] = block[np.isnan(dst)]
        used.append({'tile': tile['name'], 'sha256': sha256_file(path)})
    if not np.isfinite(out).any():
        raise ValueError('NASADEM sin píxeles válidos')
    lat = np.arange(north_i,south_i-1,-1,dtype=np.float64)/3600
    lon = np.arange(west_i,east_i+1,dtype=np.float64)/3600
    return lat,lon,out,used


def _spatial_metrics(lat: np.ndarray, z: np.ndarray) -> tuple[np.ndarray,np.ndarray]:
    if len(lat)<3 or z.shape[1]<3:
        raise ValueError('Malla DEM demasiado pequeña')
    meridional, zonal = _physical_spacing(lat, 'earth')
    dy = (np.pi/180)/3600*meridional
    dx = (np.pi/180)/3600*zonal
    # 1 arc second grid in descending latitude, ascending longitude
    dz_drow = np.gradient(z.astype(float),axis=0,edge_order=2)
    dz_dcol = np.gradient(z.astype(float),axis=1,edge_order=2)
    slope = np.degrees(np.arctan(np.hypot(dz_drow/dy[:,None], dz_dcol/dx[:,None])))
    finite = np.isfinite(z)
    count = uniform_filter(finite.astype(np.float32),size=11,mode='constant')*121
    val=np.where(finite,z,0.).astype(np.float64)
    mean=uniform_filter(val,size=11,mode='constant')*121 / np.maximum(count,1)
    meansq=uniform_filter(val*val,size=11,mode='constant')*121 / np.maximum(count,1)
    rough=np.sqrt(np.maximum(0,meansq-mean**2))
    rough[count<110] = np.nan
    # edge derivative not reliable; no buffer-based interpolation across nodata
    slope[~finite] = np.nan
    rough[~finite] = np.nan
    return slope.astype(np.float32),rough.astype(np.float32)


def _read_geometry(csv_path: Path, point_id: str):
    with Path(csv_path).open(newline='',encoding='utf-8') as fd:
        candidates=[r for r in csv.DictReader(fd) if r['point_id']==point_id]
    if len(candidates)!=1 or candidates[0]['status']!='clipped':
        raise ValueError(f'Recorte GLiM no encontrado o no completo para {point_id}')
    row=candidates[0]
    gp=Path(row['geojson_file'])
    if not gp.is_file():
        raise FileNotFoundError(str(gp))
    if sha256_file(gp) != row['geojson_sha256']:
        raise ValueError('GeoJSON GLiM modificado respecto de su SHA256 registrado')
    fc=json.loads(gp.read_text(encoding='utf-8'))
    if fc.get('metadata',{}).get('point_id') != point_id or not fc.get('features'):
        raise ValueError('GeoJSON GLiM no corresponde al sector solicitado')
    features=fc['features']
    if any(f.get('properties',{}).get('GLiM_class') != 'Basic volcanic rocks' for f in features):
        raise ValueError('GeoJSON contiene clases no volcánicas')
    polys=[shape(f['geometry']) for f in features]
    geom=unary_union(polys)
    if geom.is_empty or not geom.is_valid:
        raise ValueError('Geometría GLiM inválida')
    return geom, {'geojson_file':str(gp),'geojson_sha256':sha256_file(gp),
                  'source_glim':fc['metadata']['source_layer'],
                  'approx_glim_clipped_area_km2':fc['metadata']['approximate_clipped_volcanic_area_km2']}


def _geometry_mask(geom, lat: np.ndarray, lon: np.ndarray) -> np.ndarray:
    result=np.zeros((len(lat),len(lon)),dtype=bool)
    for k in range(0,len(lat),64):
        yy,xx=np.meshgrid(lat[k:k+64],lon,indexing='ij')
        result[k:k+64]=contains_xy(geom,xx,yy)
    return result


def _summary_values(arr:np.ndarray, mask:np.ndarray) -> dict:
    x=arr[mask & np.isfinite(arr)]
    if x.size==0:
        return {'samples':0, 'median':None,'p90':None}
    return {'samples':int(x.size),'median':round(float(np.median(x)),4),
            'p90':round(float(np.percentile(x,90)),4)}


def _etopo_info(path: Path, geom) -> dict:
    with xr.open_dataset(path) as ds:
        if ds.attrs.get('dataset') != 'ETOPO_2022_ice_surface':
            raise ValueError('ETOPO debe estar normalizado con etopo-inspect')
        processed, _ = terrain_features(ds.load(), 'earth')
    lat=np.asarray(processed.latitude.values)
    lon=np.asarray(processed.longitude.values)
    z=np.asarray(processed.elevation_m.values,dtype=float)
    mask=_geometry_mask(geom, lat, lon) & np.isfinite(z)
    return {'source_file':str(path),'source_sha256':sha256_file(path),
            'grid_shape':list(z.shape),'grid_sampled_inside_geologic_clip':int(mask.sum()),
            'slope_deg':_summary_values(np.asarray(processed.slope_deg.values),mask),
            'roughness_std3_m':_summary_values(np.asarray(processed.roughness_std3_m.values),mask),
            'roughness_footprint_note':'3x3 celdas ETOPO de ~1.85 km, NO comparable con NASADEM 11x11'}


def analyze_area(plan_path: Path, directory: Path, boundaries_csv: Path, point_id: str,
                 output_nc: Path, report_path: Path, etopo:Path|None=None,
                 slope_threshold_deg: float=5.0) -> dict:
    if not 0.1<=slope_threshold_deg<=15:
        raise ValueError('Umbral descriptivo entre 0.1 y 15 grados')
    plan=read_plan(plan_path)
    areas=[a for a in plan['areas'] if a['point_id']==point_id]
    if len(areas)!=1:
        raise ValueError(f'Punto {point_id} no aparece una vez en el plan')
    area=areas[0]
    tile_lookup={t['name']:t for t in plan['tiles']}
    needed=[tile_lookup[t] for t in area['tile_names']]
    geom, provenance = _read_geometry(boundaries_csv,point_id)
    lat,lon,z,files=mosaic_bbox(area['bbox_W_S_E_N'], needed, directory)
    mask=_geometry_mask(geom,lat,lon)
    slope,rough=_spatial_metrics(lat,z)
    valid=mask & np.isfinite(z) & np.isfinite(slope)
    if not valid.any():
        raise ValueError('No hay píxeles válidos dentro del recorte volcánico')
    dy,dxx=_physical_spacing(lat,'earth')
    pix_m2 = (np.pi/180/3600)**2 * dy * dxx
    source_area = float((valid.sum(axis=1)*pix_m2).sum()/1e6)
    flat = valid & (slope <= slope_threshold_deg)
    regions, count = label(flat,structure=np.ones((3,3),dtype=np.uint8))
    if count:
        # Per-row cell areas are slightly latitude dependent. Sum per-component in m².
        sums=np.bincount(regions.ravel(),weights=np.broadcast_to(pix_m2[:,None],regions.shape).ravel(),
                         minlength=count+1)
        sums[0]=0
        largest=float(sums.max()/1e6)
    else:
        largest=0.0
    total_flat = float((flat.sum(axis=1)*pix_m2).sum()/1e6)
    etopo_out=_etopo_info(etopo,geom) if etopo is not None else None
    metrics={'schema_version':REPORT_SCHEMA,
             'status':'descriptive_nasadem_30m_within_glim_volcanic_clips_no_rover_safety_claim',
             'point_id':point_id,'region_id':area['region_id'],
             'bbox_W_S_E_N':area['bbox_W_S_E_N'],
             'grid_shape':[int(z.shape[0]),int(z.shape[1])],
             'grid_step_arcseconds':1.0,
             'vertical_datum_note':'NASADEM HGT geoid-referenced merged elevations (EGM96); ETOPO datum may differ',
             'source_nasadem_doi':SOURCE_URL,
             'source_tiles':files,'source_plan_sha256':sha256_file(plan_path),
             'glim':provenance,
             'valid_nasadem_grid_samples':int(np.isfinite(z).sum()),
             'volcanic_clip_mask_grid_samples':int(mask.sum()),
             'valid_volcanic_clip_samples':int(valid.sum()),
             'mapped_clip_sampled_approx_area_km2':round(source_area,3),
             'elevation_m':_summary_values(z,valid),
             'slope_deg':_summary_values(slope,valid),
             'roughness_std11_m':_summary_values(rough,valid),
             'exploratory_low_slope':{
                 'threshold_deg':slope_threshold_deg,
                 'flat_valid_grid_samples':int(flat.sum()),
                 'fraction_within_valid_clipped_grid_pct':round(float(flat.sum()/valid.sum()*100),2),
                 'total_grid_approx_area_km2':round(total_flat,3),
                 'largest_8_connected_grid_approx_area_km2':round(largest,3),
                 'interpretation':'morphometric patch only; not a safe or accessible site'},
             'etopo_context':etopo_out,
             'warnings':[
                 'NASADEM is based on 2000-era SRTM radar and auxiliary fills: vegetation/building bias possible',
                 'GLiM boundaries are generalized: pixel-scale boundaries at 30 m are NOT independently resolved',
                 'Slope/roughness neighborhoods at polygon edges can include adjacent nonvolcanic elevations',
                 'Extent is only within a 25 km radius GLiM geometry intersected by the ROI rectangular grid',
                 '30m slopes and 11x11 roughness cannot identify rocks, cracks or regolith bearing capacity',
                 'Slope and roughness from ETOPO and NASADEM are inherently resolution dependent',
                 'Only descriptive; no Mars/Lunar analog score and no rover/lander/habitat safety certification',
             ]}
    output_nc.parent.mkdir(parents=True, exist_ok=True)
    ds=xr.Dataset(
        {'elevation_m':(('latitude','longitude'),z.astype(np.float32)),
         'slope_deg':(('latitude','longitude'),slope.astype(np.float32)),
         'roughness_std11_m':(('latitude','longitude'),rough.astype(np.float32)),
         'glim_basic_volcanic_mask':(('latitude','longitude'),mask.astype(np.uint8))},
        coords={'latitude':lat,'longitude':lon},
        attrs={'dataset':'NASADEM_HGT.001', 'point_id':point_id,
               'source_plan_sha256':metrics['source_plan_sha256'],
               'geology_clip_sha256':provenance['geojson_sha256'],
               'warning':'Exploratory only; not a safe rover route or habitat location'})
    temp=output_nc.with_suffix('.tmp.nc')
    try:
        if importlib.util.find_spec('netCDF4') is not None:
            ds.to_netcdf(temp,encoding={k:{'zlib':True,'complevel':3} for k in ds.data_vars},engine='netcdf4')
            metrics['output_compression']='netCDF4 zlib level 3'
        else:
            # Tests / lightweight Python environments can fall back to NetCDF3; real install includes netCDF4.
            ds.to_netcdf(temp,engine='scipy')
            metrics['output_compression']='uncompressed NetCDF3 fallback'
        os.replace(temp,output_nc)
    finally:
        temp.unlink(missing_ok=True)
    metrics['output_netcdf']=str(output_nc)
    metrics['output_netcdf_sha256']=sha256_file(output_nc)
    metrics['report_file']=str(report_path)
    atomic_json(report_path,metrics)
    return metrics


def compare_areas(p04_report: Path, p08_report: Path, output: Path) -> dict:
    """Descriptive side-by-side comparison, not a safety or global analog ranking."""
    a=json.loads(Path(p04_report).read_text(encoding='utf-8'))
    b=json.loads(Path(p08_report).read_text(encoding='utf-8'))
    if a.get('schema_version')!=REPORT_SCHEMA or b.get('schema_version')!=REPORT_SCHEMA:
        raise ValueError('Los dos informes deben proceder de nasadem-analyze V1.1.2')
    if a.get('point_id')!='r026_c146_p04' or b.get('point_id')!='r026_c146_p08':
        raise ValueError('Orden de los informes incorrecto: p04 seguido de p08')
    if a['exploratory_low_slope']['threshold_deg'] != b['exploratory_low_slope']['threshold_deg']:
        raise ValueError('Los umbrales de pendiente deben coincidir')
    def brief(x):
        return {key:x[key] for key in ('point_id','valid_volcanic_clip_samples',
                                       'mapped_clip_sampled_approx_area_km2','slope_deg',
                                       'roughness_std11_m','exploratory_low_slope','etopo_context')}
    comparison={
        'schema_version':'mars_analog_nasadem_compare_v1.1.2',
        'status':'descriptive_comparison_not_rover_or_habitat_site_selection',
        'p04':brief(a), 'p08':brief(b),
        'comparability_notes':[
            'Comparable high-resolution slope and roughness sampling footprints, but polygons and extents differ',
            'Area differences are about mapped GLiM units clipped to study areas, not verified basalt exposure',
            'Connected shallow-slope pixels are NOT an accessible route or construction-ready region',
            'ETOPO roughness and NASADEM roughness use different pixel sizes and window footprints',
            'No calibration with field topography, geology, solar radiation, dust, water or logistics',
        ],
        'sources':{'p04_report_sha256':sha256_file(p04_report),
                   'p08_report_sha256':sha256_file(p08_report)},
    }
    atomic_json(output,comparison)
    return {'schema_version':comparison['schema_version'],'status':comparison['status'],
            'report_file':str(output),'report_sha256':sha256_file(output),
            'p04_slope_median_deg':a['slope_deg']['median'],
            'p08_slope_median_deg':b['slope_deg']['median'],
            'p04_largest_connected_low_slope_km2':a['exploratory_low_slope']['largest_8_connected_grid_approx_area_km2'],
            'p08_largest_connected_low_slope_km2':b['exploratory_low_slope']['largest_8_connected_grid_approx_area_km2']}
