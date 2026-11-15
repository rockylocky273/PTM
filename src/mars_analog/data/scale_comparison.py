"""V0.4: comparación exploratoria de ventanas de relieve a escala física nominal común.

Este módulo no define qué es un análogo de Marte ni produce un score.
La operación es exclusivamente un piloto Tierra (ETOPO regional) contra una
ventana marciana arbitraria. No reemplaza máscaras de tierra, validación MOLA
ni armonización de funciones de respuesta instrumentales.
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import xarray as xr

from .download import sha256_file
from .terrain_features import _physical_spacing, terrain_features


def _check_axis(values: np.ndarray, label: str) -> float:
    vals = np.asarray(values, dtype=float)
    if vals.ndim != 1 or len(vals) < 3 or not np.all(np.isfinite(vals)):
        raise ValueError(f"{label}: se requieren >=3 coordenadas finitas")
    dif = np.diff(vals)
    if (not np.all(dif > 0) and not np.all(dif < 0)) or not np.allclose(
        np.abs(dif), abs(dif[0]), rtol=1e-4, atol=1e-7
    ):
        raise ValueError(f"{label}: eje no regular o no monótono")
    return float(np.median(np.abs(dif)))


def grid_step_km(latitude: np.ndarray, longitude: np.ndarray, planet: str,
                 at_lat: float | None = None) -> tuple[float, float]:
    """Distancia aproximada entre centros: norte-sur y este-oeste (km)."""
    dlat = np.deg2rad(_check_axis(latitude, 'latitude'))
    lon_vals=np.asarray(longitude, dtype=float)
    # Unwrap la malla martiana al cruzar 360 -> 0; no altera las coordenadas originales.
    if planet.lower()=='mars':
        lon_vals = np.rad2deg(np.unwrap(np.deg2rad(lon_vals)))
    dlon = np.deg2rad(_check_axis(lon_vals, 'longitude'))
    center = float(np.median(latitude)) if at_lat is None else at_lat
    meridional, zonal = _physical_spacing(np.asarray([center]), planet)
    return float(dlat * meridional[0] / 1000), float(dlon * zonal[0] / 1000)


def coarsen_earth_to_km(ds: xr.Dataset, target_km: float = 15.0,
                        valid_fraction: float = 0.8) -> tuple[xr.Dataset, dict]:
    """Promedio de bloques rectangulares (no interpolación de altitudes inventadas).

    Solo sirve para mallas regionales regulares en lat/lon; la escala es nominal
    al centro del dominio. No intenta una re-malla mundial uniforme en km.
    """
    if not (5 <= target_km <= 100):
        raise ValueError('target_km debe estar entre 5 y 100 para este piloto')
    if not (0 < valid_fraction <= 1):
        raise ValueError('valid_fraction debe estar en (0, 1]')
    if not str(ds.attrs.get('dataset', '')).startswith('ETOPO_'):
        raise ValueError('Se requiere ETOPO normalizado con metadatos de origen')
    if 'elevation_m' not in ds or ds.elevation_m.dims != ('latitude', 'longitude'):
        raise ValueError('Se requiere elevation_m(latitude,longitude)')
    if ds.elevation_m.attrs.get('units') != 'm':
        raise ValueError('Las elevaciones deben estar en metros')
    lat = np.asarray(ds.latitude.values, dtype=float)
    lon = np.asarray(ds.longitude.values, dtype=float)
    north, east = grid_step_km(lat, lon, 'earth')
    if north > target_km * 1.15 or east > target_km * 1.15:
        raise ValueError('ETOPO ya tiene celdas mayores que la escala objetivo')
    b_lat = max(1, int(np.rint(target_km / north)))
    b_lon = max(1, int(np.rint(target_km / east)))
    nlat, nlon = len(lat) // b_lat, len(lon) // b_lon
    if nlat < 7 or nlon < 7:
        raise ValueError('ETOPO demasiado pequeño: se requieren al menos 7x7 celdas coarsened; reducí target_km o descargá un área mayor')

    # Recorte simétrico de sobrantes para preservar la ventana central.
    lat0 = (len(lat) - nlat * b_lat) // 2
    lon0 = (len(lon) - nlon * b_lon) // 2
    orig = np.asarray(ds.elevation_m.values, dtype=float)
    crop = orig[lat0:lat0 + nlat*b_lat, lon0:lon0+nlon*b_lon]
    blocks = crop.reshape(nlat,b_lat,nlon,b_lon)
    valid = np.isfinite(blocks)
    count = valid.sum(axis=(1,3))
    with np.errstate(invalid='ignore', divide='ignore'):
        z = np.where(valid,blocks,0).sum(axis=(1,3)) / np.maximum(count,1)
    z[count/(b_lat*b_lon) < valid_fraction] = np.nan
    lat_new = lat[lat0:lat0 + nlat*b_lat].reshape(nlat,b_lat).mean(axis=1)
    lon_new = lon[lon0:lon0 + nlon*b_lon].reshape(nlon,b_lon).mean(axis=1)
    out = xr.Dataset(
        {'elevation_m':(('latitude','longitude'),z.astype('float32'))},
        coords={'latitude':lat_new,'longitude':lon_new},
        attrs={**ds.attrs,
               'processing_version':'0.4.0',
               'coarsening':'block average of elevation, not interpolation',
               'coarsening_lat_factor':b_lat,
               'coarsening_lon_factor':b_lon,
               'valid_fraction_min':valid_fraction,
               'coarsening_warning':'Nominal grid footprint only; Mars and Earth source instrument footprints may differ'}
    )
    out.elevation_m.attrs.update({'units':'m', 'long_name':'Block-averaged elevation'})
    coarse_north,coarse_east=grid_step_km(lat_new,lon_new,'earth')
    return out, {
        'native_cell_km':{'north':north,'east':east},
        'block_shape':[b_lat,b_lon],
        'coarse_cell_km':{'north':coarse_north,'east':coarse_east},
        'grid_shape':[nlat,nlon],
        'valid_coarse_cells':int(np.isfinite(z).sum()),
        'discarded_edge_samples':[len(lat)-nlat*b_lat,len(lon)-nlon*b_lon],
    }


def _region_indices(size: int, center_idx: int, cells: int) -> np.ndarray:
    half = cells//2
    idx = np.arange(center_idx-half,center_idx+half+1)
    if idx[0] < 0 or idx[-1] >= size:
        raise ValueError('La ventana solicitada supera el dominio disponible')
    return idx


def _select_earth_roi(ds: xr.Dataset, cells: int) -> xr.Dataset:
    lat = _region_indices(ds.sizes['latitude'],ds.sizes['latitude']//2,cells)
    lon = _region_indices(ds.sizes['longitude'],ds.sizes['longitude']//2,cells)
    return ds.isel(latitude=lat,longitude=lon)


def _select_mars_roi(ds: xr.Dataset, cells: int, mars_lat: float,
                     mars_lon: float) -> xr.Dataset:
    if not np.isfinite(mars_lat) or abs(mars_lat) > 55:
        raise ValueError('Piloto restringido a |latitud marciana| <=55°, por anisotropía zonal')
    if not np.isfinite(mars_lon):
        raise ValueError('Longitud marciana inválida')
    if (ds.attrs.get('planet') != 'Mars' or
        ds.attrs.get('georeferenced') != 'true' or
        ds.sizes.get('latitude') != 720 or ds.sizes.get('longitude') != 1440):
        raise ValueError('Se requieren características MOLA de la malla global georreferenciada')
    for name in ['elevation_m','slope_deg','roughness_std3_m']:
        if name not in ds:
            raise ValueError(f'Falta variable MOLA {name}; ejecutá terrain-features --planet mars')
    latv = np.asarray(ds.latitude.values,dtype=float)
    lonv = np.asarray(ds.longitude.values,dtype=float)
    ci = int(np.argmin(np.abs(latv-mars_lat)))
    target = mars_lon % 360
    cj = int(np.argmin(np.abs(lonv-target)))
    ilat = _region_indices(len(latv),ci,cells)
    j = (np.arange(cj-cells//2,cj+cells//2+1) % len(lonv))
    # Conservar índices sin reajustar coordenadas al cruzar el meridiano 0.
    return ds.isel(latitude=ilat,longitude=j)


def _features_summary(ds: xr.Dataset) -> dict:
    def summary(v):
        x = np.asarray(ds[v].values,dtype=float)
        valid = x[np.isfinite(x)]
        if len(valid) < max(9,int(.8*x.size)):
            raise ValueError(f'Menos del 80% de muestras válidas para {v}')
        return valid
    z=summary('elevation_m')
    sl=summary('slope_deg')
    rough=summary('roughness_std3_m')
    return {
        'cell_count':int(z.size),
        'slope_median_deg':float(np.median(sl)),
        'slope_p90_deg':float(np.percentile(sl,90)),
        'roughness_std3_median_m':float(np.median(rough)),
        'roughness_std3_p90_m':float(np.percentile(rough,90)),
        'regional_relief_p90_p10_m':float(np.percentile(z,90)-np.percentile(z,10)),
    }


def compare_nominal_scale(earth: xr.Dataset, mars: xr.Dataset,
                          target_km: float = 15., cells: int = 5,
                          mars_lat: float = 0., mars_lon: float = 150.,
                          tolerance: float = .15) -> tuple[xr.Dataset,dict]:
    """Retorna ETOPO coarsened y diferencias descriptivas, NO un score de similitud."""
    if cells < 5 or cells%2 != 1:
        raise ValueError('cells debe ser impar y >=5')
    coarse,info=coarsen_earth_to_km(earth,target_km)
    if any(d < cells+2 for d in coarse.elevation_m.shape):
        raise ValueError('Se requiere una celda de margen alrededor de la ROI terrestre; reducí cells')
    # La derivación se hace sobre la malla coarsened completa para evitar bordes de la ROI.
    earth_feats,_ = terrain_features(coarse,'earth')
    e_roi=_select_earth_roi(earth_feats,cells)
    m_roi=_select_mars_roi(mars,cells,mars_lat,mars_lon)
    en,ee=grid_step_km(e_roi.latitude.values,e_roi.longitude.values,'earth')
    mn,me=grid_step_km(m_roi.latitude.values,m_roi.longitude.values,'mars')
    match={'north':abs(en-mn)/mn,'east':abs(ee-me)/me}
    if any(x > tolerance for x in match.values()):
        raise ValueError(f'Las escalas no coinciden dentro de {tolerance:.0%}: '
                         f'norte {match["north"]:.1%}, este {match["east"]:.1%}. '
                         'Probá una ROI marciana ecuatorial o modificá target_km.')
    er=_features_summary(e_roi)
    mr=_features_summary(m_roi)
    keys=['slope_median_deg','slope_p90_deg','roughness_std3_median_m',
          'roughness_std3_p90_m','regional_relief_p90_p10_m']
    difference={k:round(er[k]-mr[k],5) for k in keys}
    return coarse,{
        'experiment':'v0.4_nominal_scale_regional_pilot',
        'status':'descriptive_only_no_analog_ranking',
        'target_cell_km':target_km,
        'cells_per_axis':cells,
        'earth':{'center_lat':float(np.median(e_roi.latitude)),
                 'center_lon':float(np.median(e_roi.longitude)),
                 'nominal_cell_km':{'north':en,'east':ee},
                 'features':er},
        'mars':{'center_lat':float(np.median(m_roi.latitude)),
                'center_lon':float(np.rad2deg(np.angle(np.mean(np.exp(1j*np.deg2rad(m_roi.longitude.values))))) % 360),
                'nominal_cell_km':{'north':mn,'east':me},
                'features':mr,
                'region_note':'ROI arbitraria para pruebas; no se afirma que represente un entorno geológico concreto'},
        'scale_relative_error':match,
        'earth_minus_mars':difference,
        'earth_coarsening':info,
        'caveats':[
            'Solo piloto regional: la muestra ETOPO no representa todo el planeta',
            'Se comparan escalas geométricas nominales, no resolución instrumental efectiva idéntica',
            'No hay máscara de tierra, índice de calidad MOLA MEGC ni variables geológicas o climáticas',
            'Pendientes y rugosidades se derivan de una grilla de baja resolución; no son aptas para ingeniería de rovers',
            'Elevaciones absolutas no se comparan por sus referencias verticales planetarias distintas',
            'Una diferencia numérica pequeña NO implica analogía planetaria confirmada',
        ]
    }


def process_nominal_scale(earth_path: Path,mars_path: Path,
                          earth_output: Path,report_output: Path,
                          target_km: float = 15.,cells: int = 5,
                          mars_lat: float = 0.,mars_lon: float = 150.) -> dict:
    earth_path=Path(earth_path);mars_path=Path(mars_path)
    with xr.open_dataset(earth_path) as opened: e=opened.load()
    with xr.open_dataset(mars_path) as opened: m=opened.load()
    coarse,report=compare_nominal_scale(e,m,target_km,cells,mars_lat,mars_lon)
    earth_output=Path(earth_output);report_output=Path(report_output)
    earth_output.parent.mkdir(parents=True,exist_ok=True)
    report_output.parent.mkdir(parents=True,exist_ok=True)
    coarse.to_netcdf(earth_output)
    report['inputs']={
        'earth_file':str(earth_path),'earth_sha256':sha256_file(earth_path),
        'mars_file':str(mars_path),'mars_sha256':sha256_file(mars_path),
    }
    report['outputs']={'earth_coarse':str(earth_output),
                       'earth_coarse_sha256':sha256_file(earth_output),
                       'report':str(report_output)}
    report_output.write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    return report
