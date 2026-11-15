"""V2.0.3 lunar atlas from *real* NASA PDS LRO LOLA LDEM_4 PDS3 data.

4 px/degree; regional context only. Do not turn it into a Mars/Earth
similarity score or claim to resolve the fine structure of crater walls.
"""
from __future__ import annotations
import math
from pathlib import Path
import numpy as np
from .download import sha256_file
from .mars_v2_atlas import _serialize_grid

URL='https://pds-geosciences.wustl.edu/lro/lro-l-lola-3-rdr-v1/lrolol_1xxx/data/lola_gdr/cylindrical/img/ldem_4.img'
REL=Path('raw/moon/ldem_4.img')
BYTES=1440*720*2
REGIONS=[
 {'id':'mare_imbrium','name':'Mare Imbrium','lat':32.8,'lon_east':344.0,'process':'Gran cuenca de impacto cubierta posteriormente por lavas basálticas'},
 {'id':'copernicus','name':'Cráter Copernicus','lat':9.62,'lon_east':339.92,'process':'Cráter de impacto con anillos, terrazas y depósitos de expulsión'},
 {'id':'tycho','name':'Cráter Tycho','lat':-43.31,'lon_east':348.64,'process':'Cráter de impacto con sistema de rayos de material expulsado'},
 {'id':'mare_tranquillitatis','name':'Mare Tranquillitatis','lat':8.5,'lon_east':31.4,'process':'Planicie de basaltos lunares; región del aterrizaje Apollo 11'},
 {'id':'oceanus_procellarum','name':'Oceanus Procellarum','lat':-5.0,'lon_east':305.0,'process':'Gran extensión de llanuras volcánicas basálticas'},
 {'id':'orientale','name':'Cuenca Orientale','lat':-19.4,'lon_east':265.0,'process':'Gran cuenca de impacto con estructura multianular'},
]


def acquire_lola(root:Path,*,fetch:bool=False,session=None)->dict:
    path=Path(root)/REL
    if path.exists():
        if path.stat().st_size!=BYTES:raise ValueError('LOLA LDEM_4 incompleto o de tamaño inesperado: '+str(path))
        return {'available':True,'path':str(path),'sha256':sha256_file(path),'downloaded':False}
    if not fetch:
        return {'available':False,'reason':'Descargá LDEM_4.IMG desde NASA PDS; iniciá con --fetch-lunar o con EJECUTAR_V2.ps1'}
    import requests
    get = session.get if session is not None else requests.get
    try:
        with get(URL,stream=True,timeout=(12,35)) as resp:
            resp.raise_for_status()
            total=0;path.parent.mkdir(parents=True,exist_ok=True)
            tmp=path.with_suffix('.img.part')
            try:
                with tmp.open('wb') as f:
                    for part in resp.iter_content(chunk_size=65536):
                        total+=len(part)
                        if total>BYTES:raise ValueError('LDEM_4 excede tamaño oficial')
                        f.write(part)
                if total!=BYTES:raise ValueError(f'LDEM_4 incompleto: {total} bytes, esperados {BYTES}')
                tmp.replace(path)
            finally:tmp.unlink(missing_ok=True)
    except (requests.RequestException, OSError, ValueError) as exc:
        return {'available':False,'reason':f'NASA PDS no respondió o archivo incompleto: {str(exc)[:160]}'}
    return {'available':True,'path':str(path),'sha256':sha256_file(path),'downloaded':True}


def _moon_map(dem:np.ndarray,lat:float,lon:float,context_km:float=1450)->dict:
    # Lunar radius 1737.4 km, longitude east 0..360; raw array ordered N->S.
    angular=(context_km/2)/(1737.4*math.pi/180)
    half_lat=angular
    half_lon=min(88.,angular/max(.3,math.cos(math.radians(lat))))
    lats=90-(np.arange(720,dtype=float)+.5)/4
    lons=(np.arange(1440,dtype=float)+.5)/4
    lon0=lon%360
    unwrap=lon0+(lons-lon0+180)%360-180
    rows=np.flatnonzero(abs(lats-lat)<=half_lat)
    cols=np.flatnonzero(abs(unwrap-lon0)<=half_lon)
    if len(rows)<3 or len(cols)<3:return {'status':'insufficient_grid_samples'}
    # PDS label: LSB_INTEGER, signed 16-bit, SCALING_FACTOR=0.5,
    # OFFSET=1737400 m is lunar reference sphere radius. Display *height above*
    # 1737.4 km reference sphere, so 0.5 * signed DN (NOT 1737400+DN*0.5).
    patch=dem[np.ix_(rows,cols)].astype(float)*.5
    patch[dem[np.ix_(rows,cols)] == -32768]=np.nan
    out=_serialize_grid(lats[rows],unwrap[cols],patch)
    out.update({'planet':'Moon','source':'NASA LRO LOLA LDEM_4 (PDS3)','context_km':context_km,
        'native_resolution':'4 píxeles por grado (~7,6 km/px en el ecuador)',
        'datum':'elevación sobre esfera lunar de radio 1737,4 km',
        'caption':'Mapa real LOLA LDEM_4; contexto regional amplio. No resuelve bloques pequeños ni seguridad de aterrizaje.'})
    return out


def build_lunar_atlas(root:Path,*,fetch:bool=False,session=None)->dict:
    status=acquire_lola(root,fetch=fetch,session=session)
    maps={r['id']:{'status':'unavailable','reason':status.get('reason','LDEM_4 no descargado')} for r in REGIONS}
    if status['available']:
        raw=np.fromfile(status['path'],dtype='<i2')
        if raw.size!=720*1440:raise ValueError('Archivo LOLA no tiene dimensiones 1440 × 720')
        dem=raw.reshape((720,1440))
        for r in REGIONS:
            maps[r['id']]=_moon_map(dem,r['lat'],r['lon_east'])
    return {'regions':REGIONS,'maps':maps,'source':{'url':URL,'file':status.get('path'),
             'sha256':status.get('sha256'),'availability':status['available'],
             'downloaded_now':status.get('downloaded',False),
             'reason':status.get('reason'),
             'pixel_interpretation':'signed int16 little endian; 0.5 m/count; height above lunar 1737.4 km sphere'},
             'note':'Atlas lunar educativo independiente, SIN comparación cuantitativa ni ranking lunar validado.'}
