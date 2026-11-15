"""Offline whole-Earth relief from historical NOAA ETOPO land elevations.

A compact RGB PNG displays shaded relief; another lossless RGB PNG encodes
signed metre heights (32768 offset, 65535 no data). No remote tiles, invented
measurements or additional Python dependencies are required.
"""
from __future__ import annotations

import base64
import struct
import zlib
from pathlib import Path

import numpy as np
import xarray as xr

from .download import sha256_file
from .mars_v2_atlas import GLOBAL_FILE

SCHEMA = 'mars_analog_continuous_earth_v2.0.5'


def _png_rgb(rgb: np.ndarray) -> bytes:
    a = np.ascontiguousarray(rgb, dtype=np.uint8)
    if a.ndim != 3 or a.shape[2] != 3 or min(a.shape[:2]) < 2:
        raise ValueError('PNG requiere matriz RGB 2D')
    h, w, _ = a.shape
    def chunk(tag: bytes, payload: bytes) -> bytes:
        body = tag + payload
        return struct.pack('>I', len(payload)) + body + struct.pack('>I', zlib.crc32(body) & 0xffffffff)
    rows = b''.join(b'\x00' + a[y].tobytes() for y in range(h))
    return (b'\x89PNG\r\n\x1a\n' + chunk(b'IHDR', struct.pack('>IIBBBBB', w, h, 8, 2, 0, 0, 0))
            + chunk(b'IDAT', zlib.compress(rows, 6)) + chunk(b'IEND', b''))


def _height_image(z: np.ndarray) -> np.ndarray:
    finite = np.isfinite(z)
    if np.any(finite & ((z < -32768) | (z >= 32767))):
        raise ValueError('Altitud ETOPO excede int16')
    code = np.full(z.shape, 65535, dtype=np.uint16)
    code[finite] = np.rint(z[finite]).astype(np.int32) + 32768
    out = np.zeros((*z.shape, 3), dtype=np.uint8)
    out[...,0] = (code >> 8).astype(np.uint8)
    out[...,1] = (code & 255).astype(np.uint8)
    return out


def _relief_image(z: np.ndarray) -> np.ndarray:
    valid = np.isfinite(z)
    levels = np.array([-400., 0., 180., 600., 1200., 2200., 3500., 5400., 9000.])
    palette = np.array([[53,106,94],[66,132,108],[120,162,119],[178,186,141],
                        [206,190,150],[186,160,125],[156,133,112],[210,202,188],[244,241,235]],float)
    zz = np.where(valid,z,0)
    rgb = np.stack([np.interp(zz,levels,palette[:,k]) for k in range(3)],axis=-1)
    left=np.roll(zz,1,axis=1);right=np.roll(zz,-1,axis=1)
    up=np.concatenate([zz[:1],zz[:-1]],axis=0)
    down=np.concatenate([zz[1:],zz[-1:]],axis=0)
    dx=np.where(valid & np.roll(valid,1,axis=1) & np.roll(valid,-1,axis=1),right-left,0)
    dy=np.where(valid & np.concatenate([valid[:1],valid[:-1]],axis=0)
                   & np.concatenate([valid[1:],valid[-1:]],axis=0),down-up,0)
    rgb *= np.clip(1.0+.21*np.tanh((-dx+dy)/500.0),.79,1.21)[...,None]
    rgb[~valid] = [27,65,90]  # Ocean = not measured in land-only source.
    return np.rint(np.clip(rgb,0,255)).astype(np.uint8)


def _uniform_global(lat: np.ndarray, lon: np.ndarray) -> float:
    if len(lat)<12 or len(lon)<24 or not np.isfinite(lat).all() or not np.isfinite(lon).all():
        raise ValueError('Grilla global ETOPO insuficiente')
    dy=np.diff(lat);dx=np.diff(lon)
    if (not (dy>0).all() or not (dx>0).all() or
        not np.allclose(dy,dy[0],rtol=0,atol=5e-5) or
        not np.allclose(dx,dx[0],rtol=0,atol=5e-5) or
        not np.isclose(dx[0],dy[0],atol=5e-5) or
        not np.isclose(dx[0]*len(lon),360,atol=.01) or
        not np.isclose(dy[0]*len(lat),180,atol=.01) or
        abs(lon[0]-(-180+dx[0]/2))>dx[0]+.001 or
        abs(lat[0]-(-90+dy[0]/2))>dy[0]+.001):
        raise ValueError('ETOPO no forma retícula global regular 180° × 360°')
    return float(dx[0])


def build_continuous_earth(data_root: Path) -> dict:
    source=Path(data_root)/GLOBAL_FILE
    base={'schema_version':SCHEMA,'source':'NOAA ETOPO 2022 land_elevation_m',
          'status':'unavailable','reason':'No se encontró processed/earth_global_land.nc',
          'texture_data_uri':None,'height_data_uri':None,'source_sha256':None,
          'nominal_resolution_arcmin':None,'grid_shape':None,'land_elevation_cells':0}
    if not source.is_file():return base
    with xr.open_dataset(source,mask_and_scale=True) as ds:
        if ds.attrs.get('planet')!='Earth' or ds.attrs.get('schema')!='global_land_surface_v0.6':
            raise ValueError('Mosaico mundial no verificado como ETOPO terrestre histórico')
        if ('land_elevation_m' not in ds or ds.land_elevation_m.dims!=('latitude','longitude')):
            raise ValueError('ETOPO sin grilla terrestre latitude/longitude')
        delta=_uniform_global(np.asarray(ds.latitude.values,float),np.asarray(ds.longitude.values,float))
        ds_lon_west=float(ds.longitude.values[0]-delta/2)
        ds_lat_north=float(ds.latitude.values[-1]+delta/2)
        z=np.asarray(ds.land_elevation_m.values,float)[::-1,:]
    finite=np.isfinite(z)
    if not np.any(finite):return {**base,'reason':'ETOPO sin celdas terrestres válidas'}
    shaded=_png_rgb(_relief_image(z));height=_png_rgb(_height_image(z))
    uri=lambda b:'data:image/png;base64,'+base64.b64encode(b).decode('ascii')
    return {**base,'status':'available','reason':None,'source_sha256':sha256_file(source),
            'source_path':str(source),'nominal_resolution_arcmin':round(delta*60,5),
            'grid_shape':list(map(int,z.shape)),'land_elevation_cells':int(finite.sum()),
            'raster_lon_west_edge_deg':round(float(ds_lon_west),9),
            'raster_lat_north_edge_deg':round(float(ds_lat_north),9),
            'texture_data_uri':uri(shaded),'height_data_uri':uri(height),
            'texture_png_bytes':len(shaded),'height_png_bytes':len(height),
            'caption':('Relieve mundial continuo ETOPO. La resolución de elevación no aumenta con zoom. '
                       'Océanos sin altura en este mosaico enmascarado. Solo p04 y p08 poseen NASADEM local.')}
