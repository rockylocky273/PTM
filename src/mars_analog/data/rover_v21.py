"""V2.1: physically dimensioned local rover *reconnaissance* grids.

This is deliberately separate from planetary analog rankings and never creates
sub-pixel terrain. The historical NASADEM 1-arcsec raster is the only bundled
source suitable for exploratory local traversal planning. MOLA / LOLA / ETOPO
regional grids are NOT sufficiently resolved for rover obstacle detection.
"""
from __future__ import annotations

from pathlib import Path
import math
import numpy as np
import xarray as xr

from .download import sha256_file
from .mars_v2_atlas import LOCAL_FILES, SITE_COORDS

SCHEMA = "mars_analog_rover_terrain_v2.1"


def _finite_grid(a: np.ndarray) -> list[list[float | None]]:
    if a.ndim != 2:
        raise ValueError('La elevación del rover debe ser una matriz bidimensional')
    return [[round(float(v), 2) if math.isfinite(float(v)) else None for v in row] for row in a]


def _sample_site(path: Path, site_id: str, center: tuple[float, float], *, size: int = 128) -> dict:
    """Read native DEM cells nearest the study point; no 0-100 normalization."""
    with xr.open_dataset(path, mask_and_scale=True) as ds:
        if ds.attrs.get('dataset') != 'NASADEM_HGT.001' or ds.attrs.get('point_id') != site_id:
            raise ValueError(f'Fuente NASADEM no coincide con sector: {site_id}')
        if 'elevation_m' not in ds or 'latitude' not in ds or 'longitude' not in ds:
            raise ValueError('Elevaciones NASADEM o coordenadas ausentes')
        z = ds['elevation_m']
        if z.dims != ('latitude', 'longitude'):
            raise ValueError(f'Ejes incompatibles para NASADEM: {z.dims}')
        lats = np.asarray(ds.latitude.values, dtype=float)
        lons = np.asarray(ds.longitude.values, dtype=float)
        if lats.ndim != 1 or lons.ndim != 1 or len(lats) < 12 or len(lons) < 12:
            raise ValueError('La fuente no tiene suficiente cobertura para un rover')
        if not np.all(np.isfinite(lats)) or not np.all(np.isfinite(lons)):
            raise ValueError('Coordenadas corruptas en fuente de elevación')
        if len(np.unique(lats)) != len(lats) or len(np.unique(lons)) != len(lons):
            raise ValueError('Coordenadas duplicadas en NASADEM')
        lat0, lon0 = center
        iy = int(np.argmin(abs(lats - lat0)))
        ix = int(np.argmin(abs(lons - lon0)))
        w = min(size, len(lons))
        h = min(size, len(lats))
        x0 = min(max(0,ix-w//2),len(lons)-w)
        y0 = min(max(0,iy-h//2),len(lats)-h)
        raw = np.asarray(z.isel(latitude=slice(y0,y0+h),longitude=slice(x0,x0+w)).values,dtype=float)
        ly = lats[y0:y0+h]
        lx = lons[x0:x0+w]
        # Explicit north-up ordering for JS: row 0 is the northernmost row.
        sy = np.argsort(-ly)
        sx = np.argsort(lx)
        grid = raw[np.ix_(sy,sx)]
        ly, lx = ly[sy], lx[sx]
        spacing_y = abs(float(np.median(np.diff(ly)))) * 111_132.0
        spacing_x = abs(float(np.median(np.diff(lx)))) * 111_320.0 * math.cos(math.radians(float(np.median(ly))))
        if not (0.1 < spacing_x < 100000 and 0.1 < spacing_y < 100000):
            raise ValueError('Separación física inválida entre píxeles NASADEM')
        finite = np.isfinite(grid)
        if int(finite.sum()) < 60 or float(finite.mean()) < .5:
            return {'id': site_id, 'status':'insufficient_valid_elevations',
                    'valid_fraction':round(float(finite.mean()),5)}
        # Store native physical elevations, rather than height normalization.
        return {
            'id':site_id, 'status':'available', 'planet':'Earth',
            'display_name':'Argentina · '+site_id.split('_')[-1].upper(),
            'source':'NASA NASADEM_HGT.001 · processed local HGT mosaic',
            'source_sha256':sha256_file(path),
            'coordinate_system':'WGS84 geographic',
            'lat_north_deg':float(ly[0]),'lon_west_deg':float(lx[0]),
            'cell_size_x_m':round(spacing_x,3),'cell_size_y_m':round(spacing_y,3),
            'width':int(w),'height':int(h),
            'elevation_m':_finite_grid(grid),
            'valid_fraction':round(float(finite.mean()),5),
            'min_elevation_m':round(float(np.nanmin(grid)),2),
            'max_elevation_m':round(float(np.nanmax(grid)),2),
            'local_extent_km':[round(spacing_x*(w-1)/1000,2),round(spacing_y*(h-1)/1000,2)],
            'nominal_native_resolution_arcsec':1.0,
            'simulation_level':'regional_reconnaissance_only',
            'obstacles_below_cell_resolution':'not_observable',
        }


def build_rover_terrain(data_root: Path, *, size: int = 128) -> dict:
    if not 32 <= size <= 256:
        raise ValueError('El tamaño de la ventana del rover debe estar entre 32 y 256')
    root = Path(data_root)
    sites = []
    for site_id,rel in LOCAL_FILES.items():
        path = root / rel
        if not path.is_file():
            sites.append({'id':site_id, 'status':'missing_dem',
                          'source':str(rel), 'message':'Falta el NetCDF local NASADEM original'})
            continue
        sites.append(_sample_site(path,site_id,SITE_COORDS[site_id],size=size))
    return {
        'schema_version':SCHEMA,
        'status':'exploratory_route_planning_not_rover_safety_certification',
        'sites':sites,
        'available_sites':sum(s['status']=='available' for s in sites),
        'resolution_warning':'A 30 m por celda no se observan rocas, zanjas, obstáculos de 0,3 m ni microtopografía. Rutas orientativas, no transitabilidad certificada.',
        'mars_warning':'MOLA regional (~15 km por celda) no permite simular movilidad de rover. Se necesitan DEM marcianos locales de resolución métrica o submétrica para ese caso.',
        'provenance':'Solo archivos NASADEM HGT procesados ya presentes en la instalación. Sin terreno sintético sustituto.',
        'physical_model':'heuristic_distance_slope_ascent_cost_not_joules',
    }
