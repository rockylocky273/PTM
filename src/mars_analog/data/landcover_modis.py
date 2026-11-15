"""MCD12C1.061 IGBP majority-class context; no geological or Martian inference.

HDF4 is opened with optional pyhdf on Windows/Linux. The dataset is a global
lat/lon CMG grid of 0.05 degree (3600x7200), not a 500m local product.
"""
from __future__ import annotations
import csv
import json
import math
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

from .download import atomic_json, sha256_file
from .environment_global import _read_ranked

COLLECTION='MCD12C1'
VERSION='061'
SDS='Majority_Land_Cover_Type_1'
SCHEMA='mars_analog_modis_landcover_v1.0'
HDF4_MAGIC=b'\x0e\x03\x13\x01'
CLASS_NAMES={0:'water',1:'evergreen_needleleaf_forest',2:'evergreen_broadleaf_forest',
             3:'deciduous_needleleaf_forest',4:'deciduous_broadleaf_forest',
             5:'mixed_forest',6:'closed_shrublands',7:'open_shrublands',
             8:'woody_savannas',9:'savannas',10:'grasslands',11:'permanent_wetlands',
             12:'croplands',13:'urban_built_up',14:'cropland_natural_mosaic',
             15:'snow_ice',16:'barren_or_sparsely_vegetated'}


def search_modis_landcover(year:int=2024,ea=None) -> dict:
    if not 2001<=year<=2025: raise ValueError('Año MODIS inválido')
    if ea is None:
        from .earthdata import _ea
        ea=_ea()
    # One global annual granule per year. CMR may offer multiple records;
    # selection is explicit and user checks the result before download.
    items=ea.search_data(short_name=COLLECTION,version=VERSION,
                         temporal=(f'{year}-01-01',f'{year}-12-31'),count=10)
    out=[]
    for item in items:
        meta=item.get('meta',{});umm=item.get('umm',{})
        ident=umm.get('GranuleUR') or meta.get('native-id') or ''
        if f'A{year}001' not in ident: continue
        out.append({'concept_id':meta.get('concept-id'),'producer_granule_id':ident,
                    'size_mb':getattr(item,'size',None),
                    'links':item.data_links(access='external')})
    return {'schema_version':'mcd12c1_cmr_v1.0','dataset':COLLECTION,
            'version':VERSION,'year':year,'matches':out,
            'note':'CMR discover only; download requires NASA Earthdata login'}


def download_modis_landcover(year:int,dest:Path,max_mb:int=1000,ea=None) -> dict:
    if not 2001<=year<=2025 or not 1<=max_mb<=4096:
        raise ValueError('Año fuera de rango o límite de descarga [1,4096] MB')
    if ea is None:
        from .earthdata import _ea
        ea=_ea()
    matches=ea.search_data(short_name=COLLECTION,version=VERSION,
                           temporal=(f'{year}-01-01',f'{year}-12-31'),count=10)
    items=[item for item in matches if f'A{year}001' in (item.get('umm',{}).get('GranuleUR') or item.get('meta',{}).get('native-id') or '')]
    if len(items)!=1:
        raise ValueError(f'Se esperaba exactamente una gránula MCD12C1 para {year}; obtenidas {len(items)}')
    item=items[0]
    if getattr(item,'size',None) is None or not 0<float(item.size)<=max_mb:
        raise ValueError(f'Tamaño no informado o mayor que presupuesto {max_mb} MB')
    dest=Path(dest);dest.mkdir(parents=True,exist_ok=True)
    ea.login()
    files=ea.download(items,local_path=str(dest),threads=1,access='https')
    if len(files)!=1: raise RuntimeError('NASA no devolvió exactamente un archivo HDF4')
    path=Path(files[0])
    if not path.is_file() or not path.name.lower().endswith('.hdf'):
        raise RuntimeError('Descarga NASA no localizada o extensión inesperada')
    if path.stat().st_size > max_mb*1024**2:
        raise RuntimeError('Descarga final supera presupuesto máximo')
    with path.open('rb') as f:
        if f.read(4)!=HDF4_MAGIC: raise RuntimeError('Archivo sin firma HDF4 válida')
    out={'dataset':COLLECTION,'version':VERSION,'year':year,'file':str(path),
         'size_bytes':path.stat().st_size,'sha256':sha256_file(path),
         'retrieved_at_utc':datetime.now(timezone.utc).isoformat(),
         'source_concept_id':item.get('meta',{}).get('concept-id')}
    atomic_json(dest/f'mcd12c1_{year}_manifest.json',out)
    return out


def open_hdf4_igbp(path:Path) -> np.ndarray:
    try:
        from pyhdf.SD import SD,SDC
    except ImportError as exc:
        raise RuntimeError('Para leer HDF4 instalá: python -m pip install -e ".[landcover]"') from exc
    with Path(path).open('rb') as f:
        if f.read(4)!=HDF4_MAGIC: raise ValueError('No es un archivo HDF4')
    hdf=SD(str(path),SDC.READ)
    try:
        if SDS not in hdf.datasets():
            raise ValueError(f'No está {SDS} en HDF4; capas presentes: {list(hdf.datasets())[:12]}')
        layer=hdf.select(SDS)
        arr=np.asarray(layer.get())
        if arr.shape != (3600,7200):
            raise ValueError(f'Dimensiones inesperadas {arr.shape}; esperado 3600x7200')
        return arr
    finally:
        hdf.end()


def _extract_2deg_window(grid:np.ndarray,lat:float,lon:float,deg:float=2.) -> np.ndarray:
    if not (grid.shape==(3600,7200) and deg==2 and -89<=lat<=89 and -179<=lon<=179):
        raise ValueError('Se requiere grilla MCD12C1 global con centros regionales de 2°')
    top=int(round((90.-(lat+1.))/0.05))
    left=int(round(((lon-1.)+180.)/0.05))
    if top<0 or top+40>3600 or left<0 or left+40>7200:
        raise ValueError('Ventana fuera de cobertura')
    return grid[top:top+40,left:left+40]


def summarize_igbp_window(values:np.ndarray, center_lat:float) -> dict:
    """Pixel-majority fractions; NOT the internal MODIS subpixel percentages."""
    a=np.asarray(values)
    if a.ndim!=2 or a.size==0: raise ValueError('Ventana vacía')
    valid=(a>=0)&(a<=16)
    land=valid & (a!=0)
    # Area weighting by latitude (each .05-degree cell has distinct area).
    nrows,ncols=a.shape
    lats=(center_lat + (nrows/2-np.arange(nrows)-0.5)*.05)
    weights=np.broadcast_to(np.cos(np.deg2rad(lats))[:,None],a.shape)
    den=float(weights.sum())
    valid_w=float(weights[valid].sum())
    land_w=float(weights[land].sum())
    def share(classes):
        return round(100*float(weights[land & np.isin(a,classes)].sum())/land_w,3) if land_w else None
    land_classes=[i for i in range(1,17)]
    counts={i:float(weights[land&(a==i)].sum()) for i in land_classes}
    dominant=max(counts,key=counts.get) if land_w else None
    return {'classification_coverage_pct':round(100*valid_w/den,3),
            'mapped_land_pct_among_valid':round(100*land_w/valid_w,3) if valid_w else None,
            'class16_bare_sparsely_vegetated_pct':share([16]),
            'forest_majority_pct':share([1,2,3,4,5]),
            'shrubland_majority_pct':share([6,7]),
            'cropland_majority_pct':share([12,14]),
            'urban_majority_pct':share([13]),
            'grassland_majority_pct':share([10]),
            'snow_ice_majority_pct':share([15]),
            'dominant_land_igbp_class':dominant,
            'dominant_land_igbp_name':CLASS_NAMES.get(dominant),
            'valid_pixels':int(valid.sum()),'total_pixels':int(a.size)}


def summarize_modis_landcover(hdf:Path,ranking:Path,csv_out:Path,report:Path,year:int=2024,
                               grid_override=None) -> dict:
    if not 2001<=year<=2025:raise ValueError('Año inválido')
    rows=_read_ranked(ranking)
    grid=np.asarray(grid_override) if grid_override is not None else open_hdf4_igbp(hdf)
    if grid.shape!=(3600,7200): raise ValueError('MCD12C1 necesita cuadrícula de 3600x7200')
    out=[]
    for site in rows:
        clip=_extract_2deg_window(grid,site['center_lat'],site['center_lon_180'])
        out.append({**site,**summarize_igbp_window(clip,site['center_lat'])})
    csv_out=Path(csv_out);csv_out.parent.mkdir(parents=True,exist_ok=True)
    temp=csv_out.with_name(csv_out.name+'.tmp')
    try:
        with temp.open('w',encoding='utf-8',newline='') as f:
            writer=csv.DictWriter(f,fieldnames=list(out[0]));writer.writeheader();writer.writerows(out)
        temp.replace(csv_out)
    finally: temp.unlink(missing_ok=True)
    obj={'schema_version':SCHEMA,'source':'NASA MODIS MCD12C1.061',
         'year':year,'source_hdf':str(hdf),
         'source_hdf_sha256':sha256_file(hdf) if grid_override is None else None,
         'ranking_sha256':sha256_file(ranking),'regions':len(out),
         'regions_without_valid_land':sum(r['mapped_land_pct_among_valid'] in (None,0) for r in out),
         'csv_file':str(csv_out),'csv_sha256':sha256_file(csv_out),
         'status':'independent_landcover_context_no_topographic_rerank',
         'limitations':['IGBP mayoría por píxel de ~5.6 km, NO fracción subpíxel de vegetación',
                        'La clase 16 incluye suelo desnudo O vegetación escasa',
                        'La clase 13 es superficie construida, NO distancia a ciudad',
                        'No se han obtenido litología ni mineralogía',
                        'No identifica por sí sola análogos marcianos'],
         'report_file':str(report)}
    atomic_json(report,obj)
    return obj
