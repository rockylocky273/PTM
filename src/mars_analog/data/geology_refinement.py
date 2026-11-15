"""V1.1.1: Auditable GLiM polygon clips and local study-area definitions.

This does NOT assess Mars geologic polygons, physical outcrops, safe landing sites,
regolith properties, or rover traversability. The returned generalized polygon
geometry may distort boundaries. Small exploratory clips are visualization aids,
NOT a defensible regional area-fraction estimator.
"""
from __future__ import annotations

import csv
import hashlib
import json
import math
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import requests
from shapely.geometry import LinearRing, Point, Polygon, box, mapping
from shapely.ops import transform, unary_union

from .download import atomic_json, sha256_file
from .geology_glim import (
    LAYER_URL, ORIGINAL_DOI, SCHEMA_POINT, _point_file, _read_cached,
    read_geology_plan,
)

SCHEMA_CLIP = 'mars_analog_geologic_polygon_clip_v1.1.1'
SCHEMA_SUMMARY = 'mars_analog_geologic_polygon_report_v1.1.1'
USGS_ELYSIUM_MAP = 'https://pubs.usgs.gov/publication/i2147'
USGS_GLOBAL_MARS_MAP = 'https://pubs.usgs.gov/sim/3292/'
MAX_RESPONSE_BYTES = 8 * 1024 * 1024
MAX_RING_VERTICES = 150000


def candidate_volcanic_points(plan: Path, point_cache: Path, region_id: str | None = 'r026_c146') -> tuple[dict, list[dict]]:
    obj = read_geology_plan(plan)
    digest = sha256_file(plan)
    selected = []
    for pt in obj['points']:
        if region_id and pt['region_id'] != region_id:
            continue
        cache = _read_cached(_point_file(point_cache, pt, digest), pt, digest)
        if cache and cache['status'] == 'classified' and cache['lithology'] == 'Basic volcanic rocks':
            selected.append(pt)
    if region_id and region_id not in {r['region_id'] for r in obj['regions']}:
        raise ValueError(f'Región {region_id} ausente del plan geológico')
    return obj, selected


def _query_polygon(point: dict, timeout: float, session=None) -> tuple[dict, str]:
    """Only get features touching an already-verified point; no full-world query."""
    if not 5 <= timeout <= 240:
        raise ValueError('timeout debe estar entre 5 y 240 segundos')
    params = {
        'f': 'json', 'where': '1=1',
        'geometry': f"{point['lon']},{point['lat']}",
        'geometryType': 'esriGeometryPoint', 'inSR': 4326,
        'spatialRel': 'esriSpatialRelIntersects',
        'outFields': 'OBJECTID,xx_Description',
        'returnGeometry': 'true', 'outSR': 4326,
        'geometryPrecision': 5, 'maxAllowableOffset': 0.001,
        'resultRecordCount': 10,
    }
    client = session or requests
    try:
        response = client.get(LAYER_URL + '/query', params=params, timeout=(15, timeout))
        response.raise_for_status()
        raw = response.content
        if len(raw) > MAX_RESPONSE_BYTES:
            raise ValueError('Respuesta de polígonos demasiado grande (máx. 8 MB)')
        payload = response.json()
    except (requests.RequestException, ValueError) as exc:
        raise RuntimeError(f'Consulta de polígonos GLiM fallida: {type(exc).__name__}: {exc}') from exc
    if not isinstance(payload, dict):
        raise ValueError('Respuesta de polígonos no es un objeto')
    if 'error' in payload:
        error = payload['error']
        number = error.get('code', '?') if isinstance(error, dict) else '?'
        details = error.get('message', '') if isinstance(error, dict) else str(error)
        raise RuntimeError(f'GLiM ArcGIS HTTP/API {number}: {details[:180]}')
    if payload.get('exceededTransferLimit') is True:
        raise ValueError('Resultado de polígonos truncado; no se guardará geometría parcial')
    features = payload.get('features')
    if not isinstance(features, list) or not 1 <= len(features) <= 10:
        raise ValueError('Se esperaba entre 1 y 10 polígonos sin truncamiento')
    return payload, hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(',', ':')).encode()).hexdigest()


def _geometries(feature: dict):
    """Convert ArcGIS exterior/interior rings; reject pathological geometries."""
    geom = feature.get('geometry') if isinstance(feature, dict) else None
    if not isinstance(geom, dict) or not isinstance(geom.get('rings'), list):
        raise ValueError('GLiM no devolvió anillos de polígonos')
    rings = geom['rings']
    if not rings or len(rings) > 200:
        raise ValueError('Cantidad de anillos no válida')
    exteriors, holes = [], []
    count_vertices = 0
    for ring in rings:
        if not isinstance(ring, list) or len(ring) < 4:
            raise ValueError('Anillo incompleto')
        count_vertices += len(ring)
        if count_vertices > MAX_RING_VERTICES:
            raise ValueError('Demasiados vértices en geometría')
        coords = []
        for c in ring:
            if not isinstance(c, (list, tuple)) or len(c) < 2:
                raise ValueError('Coordenada geológica inválida')
            x, y = float(c[0]), float(c[1])
            if not (math.isfinite(x) and math.isfinite(y) and -180 <= x <= 180 and -90 <= y <= 90):
                raise ValueError('El servicio no devolvió geometría WGS84 plausible')
            coords.append((x, y))
        if coords[0] != coords[-1]:
            raise ValueError('Anillo sin cierre')
        try:
            outline = LinearRing(coords)
            poly = Polygon(coords)
        except Exception as exc:
            raise ValueError(f'Anillo inválido: {exc}') from exc
        if not poly.is_valid:
            # Reject invalid source geometry: never invent a polygon by silent repair.
            raise ValueError('Polígono GLiM inválido o auto-intersectado')
        (holes if outline.is_ccw else exteriors).append(poly)
    if not exteriors and holes:
        # Some republished services may reverse ring winding; only one ring is safe.
        if len(holes) == 1:
            exteriors, holes = holes, []
        else:
            raise ValueError('No se pudo identificar el exterior de la geometría')
    if not exteriors:
        raise ValueError('No hay anillos exteriores')
    union = unary_union(exteriors)
    if holes:
        union = union.difference(unary_union(holes))
    if not union.is_valid or union.is_empty:
        raise ValueError('Polígono GLiM inválido')
    return union


def _to_km(geometry, latitude: float, lon0: float, lat0: float):
    scale_x = 111.195 * math.cos(math.radians(latitude))
    if scale_x < 1e-6:
        raise ValueError('Latitud demasiado polar')
    return transform(lambda x, y, z=None: ((x-lon0) * scale_x, (y-lat0) * 111.195), geometry)


def _to_wgs84(geometry, latitude: float, lon0: float, lat0: float):
    scale_x = 111.195 * math.cos(math.radians(latitude))
    return transform(lambda x, y, z=None: (x / scale_x + lon0, y / 111.195 + lat0), geometry)


def clip_one(point: dict, payload: dict, payload_hash: str, plan_hash: str,
             radius_km: float) -> dict:
    if not (5 <= radius_km <= 80 and math.isfinite(radius_km)):
        raise ValueError('radius-km debe estar entre 5 y 80')
    lat, lon = float(point['lat']), float(point['lon'])
    if abs(lat) > 70 or abs(lon) > 175:
        raise ValueError('El recorte local no admite latitudes >70° ni antimeridiano')
    roi = Point(0, 0).buffer(radius_km, quad_segs=64)
    collection = []
    areas = []
    for feat in payload['features']:
        attrs = feat.get('attributes') if isinstance(feat, dict) else None
        if not isinstance(attrs, dict) or attrs.get('xx_Description') != 'Basic volcanic rocks':
            # Do not silently merge non-volcanic units into the volcanic clip.
            continue
        raw = _geometries(feat)
        localized = _to_km(raw, lat, lon, lat)
        clipped = localized.intersection(roi)
        if clipped.is_empty or clipped.area <= 1e-12:
            continue
        if not clipped.is_valid:
            raise ValueError('Intersección produjo un polígono inválido')
        areas.append(clipped)
        collection.append({
            'type': 'Feature',
            'geometry': mapping(_to_wgs84(clipped, lat, lon, lat)),
            'properties': {
                'point_id': point['point_id'],
                'region_id': point['region_id'],
                'GLiM_class': 'Basic volcanic rocks',
                'source_objectid': attrs.get('OBJECTID'),
                'clipped_approx_area_km2': round(clipped.area, 3),
                'geometry_generalized': True,
            },
        })
    if not collection:
        raise ValueError('No hay geometría volcánica básica recortable; revisar servicio GLiM')
    # Union avoids double-counting overlaps between returned polygons.
    approx_area = unary_union(areas).area
    return {
        'type': 'FeatureCollection',
        'metadata': {
            'schema_version': SCHEMA_CLIP,
            'point_id': point['point_id'], 'region_id': point['region_id'],
            'plan_sha256': plan_hash, 'source_response_sha256': payload_hash,
            'center_lat': lat, 'center_lon': lon, 'radius_km': radius_km,
            'source_layer': LAYER_URL,
            'approximate_clipped_volcanic_area_km2': round(approx_area, 3),
            'roi_approximate_area_km2': round(roi.area, 3),
            'geometry_method': 'generalized server geometry, WGS84; local equirectangular clip; NOT survey-grade',
            'retrieved_utc': datetime.now(timezone.utc).isoformat(),
            'limitations': [
                'Área aproximada de una unidad cartográfica generalizada, no superficie de afloramiento verificada',
                'No interpretar como porcentaje volcánico de toda la región',
                'El buffer local es de radio específico y NO cubre la ventana topográfica original',
                'La generalización ArcGIS puede alterar límites, tamaño y contactos litológicos',
                'No se valida basalto, edad, accesibilidad, rególito ni condiciones de hábitat',
            ],
        },
        'features': collection,
    }


def _outfile(dest: Path, plan_hash: str, point_id: str, radius_km: float) -> Path:
    # Keep caches immutable when geometry radius / plan changes.
    suffix = f'{radius_km:.2f}'.replace('.', 'p')
    return dest / plan_hash[:16] / f'{point_id}_r{suffix}km.geojson'


def fetch_boundary_clips(plan: Path, point_cache: Path, dest: Path,
                         region_id: str = 'r026_c146', limit: int = 2,
                         radius_km: float = 25, timeout: float = 120,
                         session=None) -> dict:
    _, selected = candidate_volcanic_points(plan, point_cache, region_id)
    if not (1 <= limit <= 30):
        raise ValueError('limit entre 1 y 30')
    if not (5 <= radius_km <= 80 and math.isfinite(radius_km)):
        raise ValueError('radius-km entre 5 y 80')
    digest = sha256_file(plan)
    cached, pending = [], []
    for pt in selected:
        path = _outfile(dest, digest, pt['point_id'], radius_km)
        if path.exists():
            obj = json.loads(path.read_text(encoding='utf-8'))
            meta = obj.get('metadata', {})
            if (meta.get('schema_version') != SCHEMA_CLIP or meta.get('point_id') != pt['point_id']
                or meta.get('plan_sha256') != digest or meta.get('radius_km') != radius_km
                or meta.get('center_lat') != pt['lat'] or meta.get('center_lon') != pt['lon']):
                raise ValueError(f'Caché de recorte obsoleto: {path}')
            cached.append(pt)
        else:
            pending.append(pt)
    successes, failures = [], []
    for pt in pending[:limit]:
        try:
            response, response_hash = _query_polygon(pt, timeout, session=session)
            clip = clip_one(pt, response, response_hash, digest, radius_km)
            path = _outfile(dest, digest, pt['point_id'], radius_km)
            atomic_json(path, clip)
            successes.append({'point_id': pt['point_id'], 'geojson_file': str(path),
                              'approximate_clipped_volcanic_area_km2': clip['metadata']['approximate_clipped_volcanic_area_km2']})
        except (RuntimeError, ValueError, KeyError, TypeError, OSError) as exc:
            failures.append({'point_id': pt['point_id'], 'error': str(exc)[:260]})
    return {
        'schema_version': SCHEMA_CLIP,
        'status': 'generalized_earth_polygon_clips_not_verified_outcrops',
        'selected_basic_volcanic_points': len(selected),
        'cached_before': len(cached), 'new_downloads': len(successes),
        'pending': len(selected) - len(cached) - len(successes),
        'failures': failures, 'downloaded': successes,
        'source': LAYER_URL,
        'warning': 'La superficie aproximada recortada NO constituye proporción volcánica de la región.',
    }


def summarize_boundary_clips(plan: Path, point_cache: Path, directory: Path,
                             csv_path: Path, report: Path, region_id: str = 'r026_c146',
                             radius_km: float = 25) -> dict:
    _, selected = candidate_volcanic_points(plan, point_cache, region_id)
    digest = sha256_file(plan)
    rows = []
    for pt in selected:
        path = _outfile(directory, digest, pt['point_id'], radius_km)
        if not path.exists():
            rows.append({'region_id': pt['region_id'], 'point_id': pt['point_id'],
                         'lat': pt['lat'], 'lon': pt['lon'], 'status': 'pending',
                         'approximate_clipped_volcanic_area_km2': '', 'geojson_file': '', 'geojson_sha256': ''})
            continue
        obj = json.loads(path.read_text(encoding='utf-8'))
        md = obj.get('metadata', {})
        if (md.get('schema_version') != SCHEMA_CLIP or md.get('plan_sha256') != digest
            or md.get('radius_km') != radius_km or md.get('point_id') != pt['point_id']
            or md.get('center_lat') != pt['lat'] or md.get('center_lon') != pt['lon']):
            raise ValueError(f'Recorte geológico no corresponde al punto: {path}')
        rows.append({'region_id': pt['region_id'], 'point_id': pt['point_id'],
                     'lat': pt['lat'], 'lon': pt['lon'], 'status': 'clipped',
                     'approximate_clipped_volcanic_area_km2': md['approximate_clipped_volcanic_area_km2'],
                     'geojson_file': str(path), 'geojson_sha256': sha256_file(path)})
    csv_path.parent.mkdir(parents=True, exist_ok=True)
    cols = ['region_id', 'point_id', 'lat', 'lon', 'status',
            'approximate_clipped_volcanic_area_km2', 'geojson_file', 'geojson_sha256']
    temp = csv_path.with_suffix('.csv.tmp')
    try:
        with temp.open('w', newline='', encoding='utf-8') as fd:
            writer = csv.DictWriter(fd, fieldnames=cols)
            writer.writeheader()
            writer.writerows(rows)
        os.replace(temp, csv_path)
    finally:
        temp.unlink(missing_ok=True)
    full = {
        'schema_version': SCHEMA_SUMMARY,
        'status': 'earth_geology_local_clips_no_mars_analog_validation',
        'source_glim': LAYER_URL, 'glim_original_doi': ORIGINAL_DOI,
        'source_plan_sha256': digest, 'region_id': region_id,
        'radius_km': radius_km,
        'selected_volcanic_points': len(selected),
        'clipped': sum(x['status']=='clipped' for x in rows),
        'pending': sum(x['status']=='pending' for x in rows),
        'csv_file': str(csv_path), 'csv_sha256': sha256_file(csv_path),
        'mars_reference': {
            'usgs_elysium_map': USGS_ELYSIUM_MAP,
            'usgs_global_geologic_map': USGS_GLOBAL_MARS_MAP,
            'status': 'bibliographic_reference_only_not_mars_GIS_unit_sampling',
        },
        'limitations': [
            'Los recortes no caracterizan toda la región',
            'No se deducen porcentajes regionales a partir de muestras puntuales o recortes arbitrarios',
            'Áreas del recorte estimadas mediante proyección local aproximada y geometría generalizada',
            'La geología cartografiada necesita verificación local independiente',
            'Aún no hay superposición geológica cuantitativa con unidades de Marte',
        ],
    }
    atomic_json(report, full)
    return {'schema_version': SCHEMA_SUMMARY, 'status': full['status'],
            'selected_volcanic_points': full['selected_volcanic_points'],
            'clipped': full['clipped'], 'pending': full['pending'],
            'csv_file': str(csv_path), 'report_file': str(report)}


def terrain_bboxes(plan: Path, point_cache: Path, output: Path,
                    region_id: str = 'r026_c146', half_width_km: float = 30) -> dict:
    if not 5 <= half_width_km <= 70 or not math.isfinite(half_width_km):
        raise ValueError('half-width-km debe estar entre 5 y 70')
    _, pts = candidate_volcanic_points(plan, point_cache, region_id)
    areas = []
    for p in pts:
        lat, lon = p['lat'], p['lon']
        if abs(lat) > 70 or abs(lon)>175:
            raise ValueError('Recorte fuera de latitudes/longitudes admitidas')
        dy = half_width_km/111.195
        dx = half_width_km/(111.195*math.cos(math.radians(lat)))
        coords = [round(lon-dx, 5), round(lat-dy, 5), round(lon+dx, 5), round(lat+dy, 5)]
        bbox_arg = ','.join(f'{c:.5f}' for c in coords)
        areas.append({
            'point_id': p['point_id'], 'center_lat': lat, 'center_lon': lon,
            'bbox_W_S_E_N': coords,
            'powershell_command': f'.\\.venv\\Scripts\\python.exe -m mars_analog.data etopo --bbox={bbox_arg} --stride 1 --max-mb 40',
        })
    obj = {
        'schema_version': 'mars_analog_local_terrain_roi_plan_v1.1.1',
        'status': 'download_instructions_only_no_high_resolution_rover_DTM',
        'source': 'NOAA ETOPO 2022, ~1 arcminute; not a 30 m or 1 m DEM',
        'region_id': region_id, 'square_half_width_km': half_width_km,
        'areas': areas,
        'limitations': [
            'ETOPO ~1 arcminute NO sirve para medir obstáculos o transitabilidad de un rover',
            'Usar DEM local de decenas de metros para exploración operativa',
            'Los recortes pueden solaparse y no equivalen a mapas geológicos de afloramientos',
        ],
    }
    atomic_json(output,obj)
    return obj
