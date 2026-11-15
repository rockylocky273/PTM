"""Natural Earth 1:50m land polygons: máscaras geográficas por centros de píxel.

Representa tierra cartográfica aproximada, NO agua dulce, línea litoral
precisa, hielo, habitabilidad ni categoría geológica. No usa z>0.
"""
from __future__ import annotations
import io
from pathlib import Path
from zipfile import ZipFile, BadZipFile

import numpy as np
import shapefile
from shapely.geometry import GeometryCollection, shape
from shapely import contains_xy, prepare

from .download import fetch_file, sha256_file

NE_VERSION = "Natural Earth 1:50m land, physical vectors 4.0.0"
NE_URL = "https://naturalearth.s3.amazonaws.com/50m_physical/ne_50m_land.zip"
NE_BASENAME = "ne_50m_land"


def download_landmask(destination: Path, max_mb: int = 15) -> dict:
    """Descarga limitada, con cache SHA-256; valida la estructura del ZIP."""
    rec = fetch_file(NE_URL, Path(destination), "natural_earth_50m_land", max_mb=max_mb)
    try:
        polygons = _read_shapes(Path(destination))
    except (BadZipFile, ValueError, OSError, shapefile.ShapefileException) as exc:
        raise ValueError(f"Máscara Natural Earth inválida: {exc}") from exc
    return {**rec, "polygon_geometries": len(polygons), "landmask_version": NE_VERSION,
            "warning": "Polígonos generalizados, no resuelven bien costas, lagos ni islas pequeñas."}


def _read_shapes(path: Path):
    path=Path(path)
    if not path.is_file():
        raise FileNotFoundError(f"Falta máscara: {path}. Ejecutá landmask-download")
    with ZipFile(path) as archive:
        files={Path(name).name.lower(): name for name in archive.namelist()
               if not name.endswith('/')}
        required=[f"{NE_BASENAME}.{s}" for s in ('shp','shx','dbf')]
        if not all(k in files for k in required):
            raise ValueError("El ZIP no contiene ne_50m_land.{shp,shx,dbf}.")
        # Freno a bombas ZIP y archivos de estructura no esperada.
        payload={}
        for key in required:
            info=archive.getinfo(files[key])
            if info.file_size > 50 * 1024 * 1024:
                raise ValueError(f"Componente de ZIP excesivamente grande: {key}")
            payload[key.split('.')[-1]]=io.BytesIO(archive.read(files[key]))
    reader=shapefile.Reader(shp=payload['shp'], shx=payload['shx'], dbf=payload['dbf'])
    geoms=[]
    for s in reader.iterShapes():
        geom=shape(s.__geo_interface__)
        if not geom.is_empty:
            if not geom.is_valid:
                raise ValueError("Geometría de tierra inválida: no repararemos silenciosamente")
            geoms.append(geom)
    if not geoms:
        raise ValueError("La máscara no tiene geometrías terrestres")
    return geoms


def land_centers_mask(lat: np.ndarray, lon_0_360: np.ndarray, zip_file: Path,
                      chunk_rows: int = 64) -> np.ndarray:
    """Clasifica centros; salida booleana lat×lon; longitudes NOAA 0..360."""
    lat=np.asarray(lat,dtype=np.float64)
    lon=np.asarray(lon_0_360,dtype=np.float64)
    if lat.ndim!=1 or lon.ndim!=1 or not (1<=chunk_rows<=2048):
        raise ValueError("Coordenadas 1D y chunk_rows válido requeridos")
    if not (np.all(np.isfinite(lat)) and np.all(np.isfinite(lon)) and
            np.all(np.diff(lat)>0) and np.all(np.diff(lon)>0) and
            np.all((-90<=lat)&(lat<=90)) and np.all((0<=lon)&(lon<360))):
        raise ValueError("Coordenadas globales NOAA inválidas")
    geom=GeometryCollection(_read_shapes(zip_file))
    prepare(geom)
    x=(lon+180.0)%360.0-180.0
    out=np.zeros((len(lat),len(lon)),dtype=bool)
    for first in range(0,len(lat),chunk_rows):
        yy,xx=np.meshgrid(lat[first:first+chunk_rows],x,indexing='ij')
        out[first:first+chunk_rows,:]=contains_xy(geom,xx,yy)
    return out
