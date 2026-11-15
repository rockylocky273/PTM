"""Lectura, estandarización y control QA de ETOPO NetCDF.

No se infiere una máscara terrestre solo del signo de la altitud. La
normalización de longitudes no cambia los valores observados.
"""
from pathlib import Path
from datetime import datetime, timezone

import numpy as np
import xarray as xr

from .download import sha256_file


def _range(values):
    arr = np.asarray(values, dtype=float)
    if arr.size == 0 or not np.isfinite(arr).any():
        raise ValueError("No hay valores válidos para calcular estadísticas.")
    return [float(np.nanmin(arr)), float(np.nanmax(arr))]


def normalize_etopo(filepath: Path) -> tuple[xr.Dataset, dict]:
    """Devuelve NetCDF normalizado y resumen, sin remuestreo espacial.

    Longitudes normalizadas a [-180,180); ordena ejes crecientes. Se exige
    explicitamente unidad en metros, no se inventa la unidad de una variable.
    """
    filepath = Path(filepath)
    if not filepath.is_file():
        raise FileNotFoundError(str(filepath))
    with xr.open_dataset(filepath, decode_cf=True, mask_and_scale=True) as opened:
        ds = opened.load()  # lectura limitada por el tamaño descargado en V0.1
    for name in ("latitude", "longitude", "z"):
        if name not in ds:
            raise ValueError(f"ETOPO inválido: falta coordenada/variable '{name}'.")
    z = ds['z']
    if set(z.dims) != {'latitude', 'longitude'} or z.ndim != 2:
        raise ValueError("La variable ETOPO z debe tener ejes latitude, longitude.")
    units = str(z.attrs.get('units', '')).strip().lower()
    if units not in ('m','meter','meters','metre','metres'):
        raise ValueError(f"Unidad de z no confirmada en metros: {units!r}. Revisá el archivo.")
    latitude = ds.latitude.values.astype(float)
    longitude = ds.longitude.values.astype(float)
    if (not np.all(np.isfinite(latitude)) or not np.all(np.isfinite(longitude))
        or not np.all((-90 <= latitude) & (latitude <= 90))
        or not np.all((-360 <= longitude) & (longitude <= 360))):
        raise ValueError("Coordenadas inválidas o fuera de rango.")
    wrapped = ((longitude + 180) % 360) - 180
    if len(np.unique(np.round(wrapped, 10))) != len(wrapped):
        raise ValueError("La normalización produjo longitudes duplicadas; dividir la malla.")
    normalized = ds[['z']].assign_coords(longitude=('longitude',wrapped))
    normalized = normalized.sortby('longitude').sortby('latitude')
    normalized = normalized.rename({'z':'elevation_m'})
    normalized['elevation_m'].attrs.update({'units':'m', 'long_name':'Elevation relative to ETOPO vertical reference; includes bathymetry'})
    normalized['latitude'].attrs.update({'units':'degrees_north'})
    normalized['longitude'].attrs.update({'units':'degrees_east'})
    normalized.attrs = {
        'dataset':'ETOPO_2022_ice_surface',
        'source_file': filepath.name,
        'source_sha256': sha256_file(filepath),
        'processing':'longitude normalized to [-180,180), coordinates sorted; no resampling',
        'vertical_reference_note':'Consult official ETOPO metadata; not automatically comparable to MOLA',
        'land_mask_applied':'false',
        'conventions_note':'Geographic coordinates; no spatial reprojection performed',
    }
    values = normalized['elevation_m'].values.astype(float)
    valid_count = int(np.isfinite(values).sum())
    if valid_count == 0: raise ValueError('ETOPO sin elevaciones válidas.')
    summary = {
        'dataset':'etopo_surface', 'source_file':str(filepath),
        'source_sha256':normalized.attrs['source_sha256'],
        'shape':[int(values.shape[0]),int(values.shape[1])],
        'samples':int(values.size),'valid_samples':valid_count,
        'missing_samples':int(values.size-valid_count),
        'latitude_range':_range(normalized.latitude.values),
        'longitude_range':_range(normalized.longitude.values),
        'elevation_min_m':float(np.nanmin(values)),
        'elevation_max_m':float(np.nanmax(values)),
        'elevation_mean_m':float(np.nanmean(values)),
        'elevation_median_m':float(np.nanmedian(values)),
        'land_mask_applied':False,
        'longitude_normalized':True,
        'note':'Rango no es pendiente ni rugosidad; 0 m no delimita una máscara de tierra fiable.',
    }
    return normalized,summary


def process_etopo(filepath: Path, output: Path | None = None) -> dict:
    normalized, summary = normalize_etopo(filepath)
    if output is not None:
        output = Path(output)
        output.parent.mkdir(parents=True,exist_ok=True)
        normalized.to_netcdf(output)
        summary['output_file'] = str(output)
        summary['output_sha256'] = sha256_file(output)
    return summary
