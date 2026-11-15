"""Optional V2.1: import an original GeoTIFF DEM without normalization.

Only native pixels are extracted. Units, CRS and pixel size are retained;
low-resolution pixels are never interpolated to claim higher fidelity.
"""
from __future__ import annotations

from pathlib import Path
import json
import math
import numpy as np

from .download import sha256_file


def import_rover_geotiff(input_file: Path, output_json: Path, *, size: int=128,
                         center_col: int|None=None, center_row: int|None=None,
                         cell_size_m: float|None=None) -> dict:
    try:
        import rasterio
        from rasterio.windows import Window
    except ImportError as exc:
        raise ValueError('Falta rasterio: instalá con pip install -e ".[rover]"') from exc
    source=Path(input_file)
    if not source.is_file():
        raise ValueError('No existe el GeoTIFF de entrada')
    if not 32<=size<=256:
        raise ValueError('--size debe estar entre 32 y 256 celdas')
    with rasterio.open(source) as ds:
        if ds.count<1 or ds.width<12 or ds.height<12:
            raise ValueError('GeoTIFF no contiene una banda DEM utilizable')
        if abs(ds.transform.b)>1e-10 or abs(ds.transform.d)>1e-10:
            raise ValueError('GeoTIFF rotado: reproyectá previamente a grilla norte-arriba, sin aumentar resolución')
        if ds.transform.a<=0 or ds.transform.e>=0:
            raise ValueError('GeoTIFF necesita columnas de oeste a este y filas de norte a sur')
        cx=ds.width//2 if center_col is None else int(center_col)
        cy=ds.height//2 if center_row is None else int(center_row)
        if not 0<=cx<ds.width or not 0<=cy<ds.height:
            raise ValueError('El centro solicitado cae fuera del raster')
        width=min(size,ds.width);height=min(size,ds.height)
        x0=min(max(0,cx-width//2),ds.width-width)
        y0=min(max(0,cy-height//2),ds.height-height)
        arr=ds.read(1,window=Window(x0,y0,width,height),masked=True)
        grid=np.asarray(arr.filled(np.nan),dtype=np.float64)
        values=grid[np.isfinite(grid)]
        if values.size<50 or values.size/(width*height)<.5:
            raise ValueError('GeoTIFF contiene demasiados píxeles sin elevación')
        if cell_size_m is not None:
            if not .25<=float(cell_size_m)<=2000:
                raise ValueError('--cell-size-m debe estar entre .25 y 2000')
            sx=sy=float(cell_size_m)
            scale_source='explicit_user_cell_spacing'
        elif ds.crs is not None and ds.crs.is_projected:
            # linear_units_factor is a tuple (unit name, factor to metres)
            units,scale=ds.crs.linear_units_factor
            if scale is None or not math.isfinite(scale):
                raise ValueError('No puedo resolver unidades lineales del GeoTIFF')
            sx=abs(ds.transform.a)*float(scale)
            sy=abs(ds.transform.e)*float(scale)
            scale_source='projected_crs_'+str(units)
        elif ds.crs is not None and ds.crs.is_geographic:
            # This conversion is for terrestrial geodetic DEMs only.
            center_y=ds.xy(cy,cx)[1]
            sy=abs(ds.transform.e)*111132.0
            sx=abs(ds.transform.a)*111320.0*math.cos(math.radians(center_y))
            scale_source='geographic_crs_earth_wgs84_approximation'
        else:
            raise ValueError('GeoTIFF sin unidades conocidas: indicá --cell-size-m para un raster de píxeles cuadrados')
        if not .25<=sx<=2000 or not .25<=sy<=2000:
            raise ValueError('Separación de celdas fuera del rango permitido (.25–2000 m)')
        xwest,ynorth=ds.xy(y0,x0)
        result={
            'schema_version':'mars_rover_dem_v2.1',
            'id':source.stem[:80], 'display_name':source.stem[:120],
            'source':'GeoTIFF DEM local: '+source.name,
            'source_sha256':sha256_file(source),
            'planet':'Earth_or_other_unspecified',
            'coordinate_system':str(ds.crs) if ds.crs is not None else 'unknown',
            'width':int(width),'height':int(height),
            'cell_size_x_m':round(float(sx),5),'cell_size_y_m':round(float(sy),5),
            'spacing_derivation':scale_source,
            'elevation_m':[[round(float(v),3) if math.isfinite(float(v)) else None for v in row] for row in grid],
            'valid_fraction':round(float(values.size/(height*width)),4),
            'max_elevation_m':round(float(values.max()),3),
            'min_elevation_m':round(float(values.min()),3),
            'original_resolution_preserved':True,
            'rover_safety_certified':False,
            'lat_north_deg':float(ynorth) if ds.crs and ds.crs.is_geographic else None,
            'lon_west_deg':float(xwest) if ds.crs and ds.crs.is_geographic else None,
        }
    output_json=Path(output_json);output_json.parent.mkdir(parents=True,exist_ok=True)
    output_json.write_text(json.dumps(result,ensure_ascii=False,separators=(',',':')),encoding='utf-8')
    return {'status':'dem_imported_without_resampling','json_file':str(output_json),
            'width':result['width'],'height':result['height'],
            'cell_size_m':[result['cell_size_x_m'],result['cell_size_y_m']],
            'source_sha256':result['source_sha256']}
