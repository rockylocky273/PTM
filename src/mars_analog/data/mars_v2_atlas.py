"""Offline topo atlas for presentation V2.0.1.

Draws ONLY elevation grids that already exist in the research data directory.
No guessed terrain, external map tiles or unsupported lithology inference.
"""
from __future__ import annotations

import math
import json
from pathlib import Path
from typing import Any

import numpy as np
import xarray as xr

from .download import sha256_file
from .mars_external_validation_v133 import center_of_region
from .mars_profiles_v12 import LOOKUP as MARS_TARGETS

GLOBAL_FILE = Path('processed/earth_global_land.nc')
MARS_FILE = Path('processed/mola_georeferenced.nc')
MARS_PROFILE_MANIFEST = Path('catalog/mars_profiles_v1_2.json')
LOCAL_FILES = {
    'r026_c146_p04': Path('processed/nasadem_argentina_p04.nc'),
    'r026_c146_p08': Path('processed/nasadem_argentina_p08.nc'),
}
SITE_COORDS = {
    'r026_c146_p04': (-37.0, -67.6756431),
    'r026_c146_p08': (-37.5395926, -67.6756431),
}
SITE_STATS = {
    'r026_c146_p04': dict(glim_clip_km2=1675.654, slope_median_deg=1.858, slope_p90_deg=3.6199, roughness_median_m=1.6911),
    'r026_c146_p08': dict(glim_clip_km2=798.531, slope_median_deg=1.4907, slope_p90_deg=3.0192, roughness_median_m=1.4303),
}


def _serialize_grid(lats: np.ndarray, lons: np.ndarray, z: np.ndarray,
                    *, mask: np.ndarray | None = None) -> dict:
    """Serialize sampled 2D elevation with geographic bounds, no invented pixels."""
    lats = np.asarray(lats, dtype=float)
    lons = np.asarray(lons, dtype=float)
    z = np.asarray(z, dtype=float)
    if z.ndim != 2 or z.shape != (len(lats), len(lons)):
        raise ValueError('Ejes de elevación del atlas inconsistentes')
    if len(lats) < 3 or len(lons) < 3:
        return {'status': 'insufficient_grid_samples'}
    if not np.all(np.isfinite(lats)) or not np.all(np.isfinite(lons)):
        raise ValueError('Coordenadas inválidas en la grilla topográfica')
    ii = np.argsort(lats)
    jj = np.argsort(lons)
    lats, lons = lats[ii], lons[jj]
    z = z[np.ix_(ii, jj)]
    if mask is not None:
        mask = np.asarray(mask)[np.ix_(ii, jj)]
        if mask.shape != z.shape:
            raise ValueError('Máscara geológica incompatible')
    valid = np.isfinite(z)
    if int(valid.sum()) < 9:
        return {'status': 'insufficient_valid_elevations'}
    # Use a local median to avoid heavy float serialization while keeping
    # original grid elevation units in metres. Each datum is rounded to 1 m.
    heights = [[int(round(float(v))) if math.isfinite(float(v)) else None for v in row] for row in z]
    good = z[valid]
    result = {
        'status': 'available',
        'bounds': [round(float(lons[0]), 8), round(float(lats[0]), 8),
                   round(float(lons[-1]), 8), round(float(lats[-1]), 8)],
        'shape': [len(lats), len(lons)],
        'elevation': heights,
        'elevation_min_m': round(float(good.min()), 1),
        'elevation_max_m': round(float(good.max()), 1),
        'elevation_p02_m': round(float(np.percentile(good, 2)), 1),
        'elevation_p98_m': round(float(np.percentile(good, 98)), 1),
        'valid_samples': int(valid.sum()),
    }
    if mask is not None:
        result['volcanic_mask'] = [[int(v) for v in row] for row in mask]
    return result


def _read_global_map(ds: xr.Dataset, lat: float, lon: float) -> dict:
    # ~9° longitude × 7° latitude context, centered on the 2° research cell.
    # At the historical 10' ETOPO grid this is only ~54×42 values.
    half_lat, half_lon = 3.5, 4.5
    lat_sl = slice(max(-89.8, lat-half_lat), min(89.8, lat+half_lat))
    geo = ds['land_elevation_m']
    # ETOPO V0.6 coordinate longitude is [-180,180), ascending.
    low, high = lon-half_lon, lon+half_lon
    if low < -180 or high > 180:
        left = geo.sel(latitude=lat_sl).where(
            (geo.longitude >= ((low+180)%360-180)) | (geo.longitude <= ((high+180)%360-180)), drop=True)
        lonvals = np.asarray(left.longitude.values, dtype=float)
        # Local unwrapped longitude around the selected center, even when
        # the requested window crosses -180/180. Never span 360° on the map.
        lonvals = lon + ((lonvals - lon + 180) % 360 - 180)
        return _serialize_grid(left.latitude.values, lonvals, left.values)
    out = geo.sel(latitude=lat_sl, longitude=slice(low, high))
    return _serialize_grid(out.latitude.values, out.longitude.values, out.values)


def _read_nasadem_map(path: Path, site_id: str) -> dict:
    with xr.open_dataset(path, mask_and_scale=True) as ds:
        if ds.attrs.get('dataset') != 'NASADEM_HGT.001' or ds.attrs.get('point_id') != site_id:
            raise ValueError(f'NASADEM no corresponde al sector solicitado: {site_id}')
        for name in ('elevation_m','glim_basic_volcanic_mask','latitude','longitude'):
            if name not in ds:
                raise ValueError(f'NASADEM incompleto: {site_id}: {name}')
        # Subsample actual HGT elevations. Sampling gap is declared accurately;
        # *not* claimed to preserve 30m display fidelity.
        ny, nx = ds.elevation_m.shape
        step = max(1, int(math.ceil(max(ny / 210, nx / 250))))
        sub = ds.isel(latitude=slice(None,None,step),longitude=slice(None,None,step))
        result = _serialize_grid(sub.latitude.values, sub.longitude.values,
                                 sub.elevation_m.values,
                                 mask=sub.glim_basic_volcanic_mask.values)
        result['source'] = 'NASADEM_HGT.001'
        result['native_resolution_arcsec'] = 1.0
        result['display_stride'] = step
        result['display_resolution_arcsec_nominal'] = float(step)
        result['caption'] = (f'Elevaciones NASADEM muestreadas cada {step} celdas '
                             '(base nominal 1 segundo de arco). La máscara GLiM es cartografía generalizada.')
        return result


# Country label is derived from the center of the cell (Natural Earth low-resolution,
# point-in-polygon). Country names are a geographic index, not a claim that the
# entire 2° cell is located inside those borders.
_COUNTRY_INDEX = json.loads(Path(__file__).with_name('country_centers_v202.json').read_text(encoding='utf-8'))


def _region_label(rid: str, lat: float, lon: float) -> str:
    country = _COUNTRY_INDEX['countries'].get(rid, 'Región no identificada')
    qualifier = _COUNTRY_INDEX['descriptors'].get(rid)
    return country + (' · ' + qualifier if qualifier else '')


def _read_mars_map(ds: xr.Dataset, lat: float, lon_east: float, context_km: float=640.0) -> dict:
    """Read ONLY MOLA georeferenced elevations in a configurable context window.

    Longitudes are *Mars* 0..360 east-positive. Local unwrapping permits
    Meridiani to cross the 0° seam without showing a 360°-wide map.
    """
    z = ds['elevation_m']
    center_lon = lon_east % 360.0
    degrees = (context_km/2.0) / (3396.0 * math.pi / 180.0)
    half_lat = degrees
    half_lon = degrees / max(math.cos(math.radians(lat)), 0.15)
    lat_idx = np.flatnonzero(np.abs(np.asarray(z.latitude.values, dtype=float) - lat) <= half_lat)
    source_lon = np.asarray(z.longitude.values, dtype=float)
    unwrapped = center_lon + ((source_lon - center_lon + 180.0) % 360.0 - 180.0)
    lon_idx = np.flatnonzero(np.abs(unwrapped - center_lon) <= half_lon)
    if lat_idx.size < 3 or lon_idx.size < 3:
        return {'status':'insufficient_grid_samples', 'reason':'MOLA insuficiente en ventana regional'}
    patch = z.isel(latitude=lat_idx,longitude=lon_idx)
    out = _serialize_grid(patch.latitude.values,unwrapped[lon_idx],patch.values)
    out.update({'source':'NASA MOLA MEGDR', 'planet':'Mars',
                'longitude_convention':'planetocentric east-positive 0..360',
                'context_window_km':f'{int(context_km)} km aproximadamente, proyección local',
                'analysis_window_km':240.0,
                'center_lat':lat,'center_lon_east':center_lon,
                'caption':(f'Relieve MOLA real del entorno regional (~{int(context_km)} km de contexto). '
                           'Resolución de origen: 0,25° (~15 km en latitud). '
                           'La ventana de análisis estadístico tiene 240 km. '
                           'Altitudes relativas al datum marciano del producto, NO al nivel del mar terrestre.')})
    return out


def build_mars_topographic_atlas(data_root: Path, profiles: list[dict], *, context_km: float=640.0) -> dict:
    data_root = Path(data_root)
    source = data_root / MARS_FILE
    manifest_file = data_root / MARS_PROFILE_MANIFEST
    maps, detail, sources = {}, {}, {}
    manifest = None
    if manifest_file.is_file():
        manifest = json.loads(manifest_file.read_text(encoding='utf-8'))
        if manifest.get('schema_version') != 'mars_analog_multi_profiles_v1.2':
            raise ValueError('Manifiesto MOLA V1.2 inválido')
        sources['mars_profiles_manifest']={'path':str(manifest_file),'sha256':sha256_file(manifest_file)}
    for p in profiles:
        rid = p['id']
        if rid not in MARS_TARGETS:
            raise ValueError('Perfil marciano desconocido: '+rid)
        t = MARS_TARGETS[rid]
        features = None
        if manifest is not None:
            record = next((r for r in manifest.get('profiles', []) if r.get('id')==rid), None)
            if record is None:
                raise ValueError('El manifiesto no incluye: '+rid)
            # Stored paths are relative to project parent, not data/.
            path = Path(record['profile_file'])
            if not path.is_absolute(): path=data_root.parent/path
            if not path.is_file() or sha256_file(path) != record['sha256']:
                raise ValueError('Perfil marciano alterado o ausente: '+rid)
            profile = json.loads(path.read_text(encoding='utf-8'))
            if profile.get('profile_name') != rid or profile.get('planet')!='Mars':
                raise ValueError('Perfil MOLA incorrecto: '+rid)
            features = profile.get('features')
        detail[rid]={'id':rid,'name':p['name'], 'center_lat':t[2],
                     'center_lon_east':t[3], 'features':features,
                     'scope_note':t[5], 'usgs_url':t[4],
                     'geology_units':p['units'], 'domain_flag':p['domain_flag']}
        maps[rid]={'status':'unavailable','reason':'Falta data/processed/mola_georeferenced.nc'}
    if source.is_file():
        with xr.open_dataset(source,mask_and_scale=True) as ds:
            if ds.attrs.get('planet')!='Mars' or str(ds.attrs.get('georeferenced')).lower()!='true':
                raise ValueError('El mosaico indicado no es MOLA georreferenciado de Marte')
            if 'elevation_m' not in ds or ds.elevation_m.dims!=('latitude','longitude'):
                raise ValueError('MOLA: ejes latitude/longitude o elevación ausentes')
            if (len(ds.latitude)<3 or len(ds.longitude)<3 or
                not np.all(np.diff(ds.longitude.values)>0) or
                not np.all(np.isfinite(ds.longitude.values))):
                raise ValueError('Coordenadas MOLA no válidas')
            # Cross-check source from signed previous run to avoid silent swapping.
            if manifest is not None and sha256_file(source)!=manifest['source_mola_sha256']:
                raise ValueError('MOLA no coincide con el manifiesto científico V1.2')
            for rid, d in detail.items():
                maps[rid]=_read_mars_map(ds,d['center_lat'],d['center_lon_east'],context_km)
        sources['mola_georeferenced']={'path':str(source),'sha256':sha256_file(source)}
    return {'profiles':detail,'maps':maps,'sources':sources,
            'source_note':'Coordenadas MARCIANAS planetocéntricas en longitud Este 0–360°, sin transformación WGS84 terrestre. Mapas generados de datos MOLA históricos del usuario.'}


def build_topographic_atlas(data_root: Path, summary: dict[str, Any]) -> dict:
    """Make a complete 25-region clickable atlas using existing Earth grids.

    Map data are optional. Missing/invalid sources never become synthetic terrain.
    Existing V1.3.3 reports remain the provenance spine.
    """
    data_root = Path(data_root)
    priority = {x['id']: x for x in summary['candidates']}
    anchors = sorted(summary['elysium_anchors'],
                     key=lambda r: (r.get('topographic_rank') is None,
                                    r.get('topographic_rank') or 10**8))
    entries, maps, source_files = [], {}, {}
    for r in anchors:
        rid = r['earth_region_id']
        lat, lon = center_of_region(rid)
        lith = r.get('earth_glim_lithology_counts', {})
        if not isinstance(lith, dict): lith = {}
        is_priority = rid in priority
        entries.append({
            'id': rid, 'label': _region_label(rid, lat, lon),
            'country':_COUNTRY_INDEX['countries'].get(rid, 'Sin país determinado'),
            'geographic_descriptor':_COUNTRY_INDEX['descriptors'].get(rid),
            'center_lat': lat, 'center_lon': lon,
            'cell_bounds': [lon-1, lat-1, lon+1, lat+1],
            'topographic_rank': r['topographic_rank'],
            'lithology_counts': lith,
            'volcanic_points': sum(int(v) for k,v in lith.items() if
                                   'volcanic' in k.lower() or 'pyroclast' in k.lower()),
            'process_relation': r.get('broad_process_relation'),
            'is_priority': is_priority,
            'is_argentina': rid == 'r026_c146',
            'scale_ranks': priority[rid]['scale_ranks'] if is_priority else None,
            'method_ranks': priority[rid]['method_ranks'] if is_priority else None,
            'weight_summary': priority[rid]['weight_summary'] if is_priority else None,
        })
        maps[rid] = {'status': 'unavailable', 'reason': 'Falta grilla ETOPO terrestre histórica'}
    earth_path = data_root / GLOBAL_FILE
    if earth_path.is_file():
        with xr.open_dataset(earth_path, mask_and_scale=True) as ds:
            if ds.attrs.get('schema') != 'global_land_surface_v0.6' or ds.attrs.get('planet') != 'Earth':
                raise ValueError('El NetCDF global del atlas no pertenece a ETOPO terrestre V0.6')
            for name in ('latitude','longitude','land_elevation_m'):
                if name not in ds:
                    raise ValueError('Falta variable en la fuente global ETOPO: '+name)
            if set(ds.land_elevation_m.dims) != {'latitude','longitude'}:
                raise ValueError('ETOPO global con dimensiones incorrectas')
            if not np.all(np.diff(ds.latitude.values)>0) or not np.all(np.diff(ds.longitude.values)>0):
                raise ValueError('ETOPO global requiere coordenadas ascendentes')
            for item in entries:
                m = _read_global_map(ds, item['center_lat'], item['center_lon'])
                m['source'] = 'NOAA ETOPO 2022 / máscara terrestre Natural Earth'
                m['nominal_resolution'] = '10 minutos de arco (mosaico histórico del proyecto)'
                m['caption'] = ('Topografía regional ETOPO; centro de celda de 2° indicado. '
                                'Es contexto topográfico, no imagen del afloramiento volcánico.')
                maps[item['id']] = m
        source_files['global_etopo'] = {'path': str(earth_path), 'sha256': sha256_file(earth_path)}
    # Per-region factual terrain context from the regional ETOPO display; missing
    # maps remain missing rather than fabricated.
    for item in entries:
        m=maps[item['id']]
        item['relief_context_m'] = round(m['elevation_p98_m']-m['elevation_p02_m'],1) if m.get('status')=='available' else None
        item['elevation_range_m'] = [m['elevation_min_m'],m['elevation_max_m']] if m.get('status')=='available' else None
    sites = []
    for site_id, filename in LOCAL_FILES.items():
        lat, lon = SITE_COORDS[site_id]
        entry = {'id':site_id,'parent_id':'r026_c146',
                 'label': 'Argentina · p04' if site_id.endswith('p04') else 'Argentina · p08',
                 'lat':lat,'lon':lon,'metrics':SITE_STATS[site_id]}
        site_file = data_root / filename
        if site_file.is_file():
            maps[site_id] = _read_nasadem_map(site_file, site_id)
            source_files[site_id] = {'path':str(site_file),'sha256':sha256_file(site_file)}
        else:
            maps[site_id] = {'status':'unavailable','reason':'No se encontró NetCDF NASADEM de este sector'}
        sites.append(entry)
    return {'entries':entries,'maps':maps,'local_sites':sites,
            'sources':source_files,
            'map_source_status':'global_etopo_available' if 'global_etopo' in source_files else 'etopo_not_found',
            'source_note':'ETOPO 10 arcmin regional; NASADEM 1 arcsec de origen en p04/p08 con submuestreo para pantalla. Centros de celdas no son ubicaciones exactas de afloramientos.'}
