"""V0.7: primera búsqueda EXPLORATORIA de similitud TOPOGRÁFICA Tierra/Marte.

No realiza inferencia geológica, climática ni evaluación de seguridad de aterrizaje.
No usa elevaciones absolutas, evita falsear una puntuación de probabilidad.
La comparación utiliza *rejillas métricas nominales*, no resolución instrumental
real idéntica; no pretende resolver rasgos de tamaño inferior al píxel original.
"""
from __future__ import annotations

import csv
import json
import math
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import xarray as xr
from scipy.ndimage import map_coordinates, uniform_filter

from .download import sha256_file, atomic_json

RADIUS_KM = {'Earth': 6371.0088, 'Mars': 3396.0}
FEATURES = ('slope_median_deg','slope_p90_deg',
            'roughness_std3_median_m','roughness_std3_p90_m',
            'relief_p90_p10_m')
# Tolerancias metodológicas EXPLORATORIAS: NO estimadas por entrenamiento.
OFFSET = {'slope': 0.05, 'roughness': 10.0, 'relief': 20.0}
WEIGHTS = {'slope':0.35,'roughness':0.35,'relief':0.30}
USGS_ELYSIUM_URL = 'https://planetarynames.wr.usgs.gov/Feature/1784'


def _require_grid(dataset: xr.Dataset, planet: str):
    if 'elevation_m' not in dataset:
        raise ValueError('Falta elevación en metros')
    elevation = dataset['elevation_m']
    if elevation.dims != ('latitude', 'longitude') or elevation.attrs.get('units') != 'm':
        raise ValueError('Se requiere elevation_m(latitude,longitude), unidad m')
    if planet == 'Earth':
        if dataset.attrs.get('schema') != 'global_land_surface_v0.6':
            raise ValueError('Earth: se requiere earth_global_land.nc validado V0.6')
        if 'land_mask' not in dataset:
            raise ValueError('Falta la máscara de superficie terrestre')
    elif planet == 'Mars':
        if (dataset.attrs.get('planet') != 'Mars' or
            dataset.attrs.get('georeferenced') != 'true' or
            dataset.attrs.get('longitude_range') != '0_360'):
            raise ValueError('Mars: se requiere mola_georeferenced.nc validado')
    else:
        raise ValueError('Planeta no soportado')
    lat = np.asarray(dataset.latitude.values, dtype=np.float64)
    lon = np.asarray(dataset.longitude.values, dtype=np.float64)
    if lat.size < 3 or lon.size < 3 or not np.all(np.isfinite(lat)) or not np.all(np.isfinite(lon)):
        raise ValueError('Coordenadas incompletas')
    dlat = np.diff(lat)
    dlon = np.diff(lon)
    if not (np.all(dlat>0) or np.all(dlat<0)) or not np.all(dlon>0):
        raise ValueError('Ejes lat/lon deben ser monótonos')
    if not (np.allclose(dlat,dlat[0],atol=5e-6) and np.allclose(dlon,dlon[0],atol=5e-6)):
        raise ValueError('Se requieren ejes uniformes para interpolación')
    if not np.isclose(len(lon)*dlon[0],360.0,atol=1e-3):
        raise ValueError('La rejilla debe cubrir 360° de longitud para usar wrapping')
    if elevation.shape != (len(lat),len(lon)):
        raise ValueError('Dimensiones inconsistentes')
    return lat,lon


class GlobalSampler:
    """Bilineal métrica local, longitude wrap y latitud sin wrap.

    El peso válido evita mezclar batimetría con elevaciones terrestres en costa.
    """
    def __init__(self, ds: xr.Dataset, planet: str):
        self.planet=planet
        self.lat,self.lon=_require_grid(ds,planet)
        z=np.asarray(ds.elevation_m.values,dtype=np.float64)
        finite=np.isfinite(z)
        if planet=='Earth':
            finite &= np.asarray(ds.land_mask.values,dtype=bool)
        self.values=np.pad(np.where(finite,z,0.),((0,0),(1,1)),mode='wrap')
        self.valid=np.pad(finite.astype(float),((0,0),(1,1)),mode='wrap')
        self.lat_step=float(self.lat[1]-self.lat[0])
        self.lon_step=float(self.lon[1]-self.lon[0])

    def sample(self, center_lat: float, center_lon: float, spacing_km: float=30., samples: int=9):
        """Malla local centrada en km, aproximación tangente a latitud central.

        Los puntos faltantes o interpolados con tierra/océano mezclados se invalidan.
        """
        if not (-90 < center_lat < 90) or not np.isfinite(center_lon):
            raise ValueError('Centro planetario no válido')
        if not (0 < spacing_km <= 100) or not (5 <= samples <= 31 and samples%2):
            raise ValueError('spacing_km: (0,100], samples impar entre 5 y 31')
        radius=RADIUS_KM[self.planet]
        km_per_lat=radius*np.pi/180
        km_per_lon=km_per_lat*np.cos(np.deg2rad(center_lat))
        if km_per_lon<5.:
            raise ValueError('Latitud demasiado cercana al polo para esta proyección local')
        offsets=(np.arange(samples)-samples//2)*spacing_km
        yy,xx=np.meshgrid(offsets,offsets,indexing='ij')
        lat_target=center_lat+yy/km_per_lat
        lon_target=center_lon+xx/km_per_lon
        row=(lat_target-self.lat[0])/self.lat_step
        col=np.mod((lon_target-self.lon[0])/self.lon_step,len(self.lon))+1
        coords=np.array([row.ravel(),col.ravel()])
        # Las coordenadas fuera de la extensión latitudinal son inválidas.
        # La longitud posee columnas de contorno replicadas periódicamente.
        weights=map_coordinates(self.valid,coords,order=1,mode='constant',cval=0.,prefilter=False)
        weighted=map_coordinates(self.values,coords,order=1,mode='constant',cval=0.,prefilter=False)
        points=np.where(weights>0.999999,weighted,np.nan).reshape(samples,samples)
        return points


def patch_features(patch: np.ndarray,spacing_km: float) -> dict | None:
    """Magnitudes de relieve independientes de datum vertical.

    Requiere 90% de píxeles válidos y 16 celdas interiores con pendientes
    calculadas sin atravesar valores nulos. Devuelve None si no hay soporte.
    """
    h=np.asarray(patch,dtype=float)
    if h.ndim!=2 or min(h.shape)<5 or not (spacing_km>0):
        raise ValueError('patch debe ser rejilla >=5x5 con spacing positivo')
    good=np.isfinite(h)
    coverage=float(good.mean())
    if coverage<0.9:
        return None
    # Las operaciones derivativas preservan NaN en límites de tierra y océano.
    dy,dx=np.gradient(h,spacing_km*1000.,edge_order=1)
    with np.errstate(invalid='ignore'):
        slopes=np.degrees(np.arctan(np.hypot(dx,dy)))
    interior_slopes=slopes[1:-1,1:-1]
    s=interior_slopes[np.isfinite(interior_slopes)]
    clean=np.where(good,h,0.)
    count=uniform_filter(good.astype(float),size=3,mode='constant',cval=0.)*9
    avg=uniform_filter(clean,size=3,mode='constant',cval=0.)*9/np.maximum(count,1)
    var=uniform_filter(clean**2,size=3,mode='constant',cval=0.)*9/np.maximum(count,1)-avg**2
    std=np.sqrt(np.maximum(0,var))
    r=std[1:-1,1:-1][(count[1:-1,1:-1]>8.999)]
    if s.size<16 or r.size<16:
        return None
    e=h[good]
    return {
        'sample_coverage':round(coverage,6),
        'sample_count':int(e.size),
        'slope_median_deg':float(np.median(s)),
        'slope_p90_deg':float(np.percentile(s,90)),
        'roughness_std3_median_m':float(np.median(r)),
        'roughness_std3_p90_m':float(np.percentile(r,90)),
        'relief_p90_p10_m':float(np.percentile(e,90)-np.percentile(e,10)),
    }


def distance_metrics(earth: dict,mars: dict) -> dict:
    """Distancia logarítmica equilibrada, NO una probabilidad de analogía."""
    for key in FEATURES:
        if key not in earth or key not in mars:
            raise ValueError(f'Falta característica {key}')
        if not all(np.isfinite([float(earth[key]),float(mars[key])])):
            raise ValueError('Características no finitas')
        if earth[key]<0 or mars[key]<0:
            raise ValueError('Características deben ser no negativas')
    def diff(key,eps):
        return abs(math.log((float(earth[key])+eps)/(float(mars[key])+eps)))
    slope=(diff('slope_median_deg',OFFSET['slope'])+
           diff('slope_p90_deg',OFFSET['slope']))/2
    rough=(diff('roughness_std3_median_m',OFFSET['roughness'])+
           diff('roughness_std3_p90_m',OFFSET['roughness']))/2
    relief=diff('relief_p90_p10_m',OFFSET['relief'])
    return {'distance_total':float(WEIGHTS['slope']*slope + WEIGHTS['roughness']*rough + WEIGHTS['relief']*relief),
            'distance_slope':float(slope), 'distance_roughness':float(rough),
            'distance_relief':float(relief)}


def create_mars_profile(mars_file: Path, output: Path, name: str,
                        lat: float,lon: float,spacing_km: float=30.,samples: int=9) -> dict:
    if not name or not all(c.isalnum() or c in '_-' for c in name):
        raise ValueError('name solo acepta letras, números, _ y -')
    with xr.open_dataset(mars_file) as ds:
        sample=GlobalSampler(ds,'Mars')
    if abs(lat)>65:
        raise ValueError('Prototipo V0.7 restringe el centro del perfil a |lat| <= 65°')
    patch=sample.sample(lat,lon,spacing_km,samples)
    features=patch_features(patch,spacing_km)
    if features is None:
        raise ValueError('No hay cobertura suficiente en el perfil marciano')
    result={'schema_version':'mars_analog_profile_v0.7',
            'status':'topographic_profile_only_not_geologically_validated',
            'profile_name':name,'planet':'Mars',
            'center_lat':float(lat),'center_lon_east_0_360':float(lon%360),
            'spacing_km':float(spacing_km),'samples_per_axis':int(samples),
            'window_extent_center_to_center_km':(samples-1)*spacing_km,
            'reference_source':'MOLA MEGDR 4 pix/degree; user-specified center',
            'usgs_elysium_reference_url':USGS_ELYSIUM_URL if name.startswith('elysium') else None,
            'features':features,'mars_file_sha256':sha256_file(Path(mars_file)),
            'limitations':['No se evaluó composición mineralógica ni clima',
                           'Resolución de producto MOLA 4 pix/deg; no resolución rover',
                           'Malla tangente local nominal, no igual resolución instrumental'],
            'created_at_utc':datetime.now(timezone.utc).isoformat()}
    atomic_json(Path(output),result)
    result['output_file']=str(output)
    return result


def _haversine_km(lat1,lon1,lat2,lon2):
    p1,p2=np.deg2rad([lat1,lat2])
    dl=np.deg2rad(lat2-lat1)
    dn=np.deg2rad((lon2-lon1+180)%360-180)
    a=np.sin(dl/2)**2+np.cos(p1)*np.cos(p2)*np.sin(dn/2)**2
    return float(2*RADIUS_KM['Earth']*np.arcsin(min(1.,np.sqrt(a))))


def diverse_top(ranked:list[dict],top:int,min_distance_km:float) -> list[dict]:
    """Evita informar muchas regiones vecinas como descubrimientos distintos."""
    result=[]
    for item in ranked:
        if len(result)>=top:
            break
        if all(_haversine_km(item['center_lat'],item['center_lon_180'],
                             old['center_lat'],old['center_lon_180'])>=min_distance_km
               for old in result):
            result.append(item)
    return result


def screen_earth(profile_file:Path,earth_file:Path,regions_csv:Path,
                 output_csv:Path,report_file:Path,top:int=25,
                 min_separation_km:float=250,max_abs_lat:float=65.,
                 min_patch_coverage:float=0.95) -> dict:
    """Ordena únicamente regiones terrestres de clase land_candidate_unranked.

    La comparación usa el *mismo espaciado métrico nominal* y tamaño de ventana
    para ambos mundos; no presume igualdad de resolución efectiva.
    """
    with Path(profile_file).open(encoding='utf-8') as f:
        profile=json.load(f)
    if (profile.get('schema_version')!='mars_analog_profile_v0.7' or
        profile.get('planet')!='Mars' or profile.get('status')!='topographic_profile_only_not_geologically_validated'):
        raise ValueError('Perfil marciano inválido o de otra versión')
    if not (1<=top<=500) or not(0<=min_separation_km<=5000) or not(0<max_abs_lat<=65) or not(0.9<=min_patch_coverage<=1):
        raise ValueError('Parámetros fuera de rango: top[1,500], separación[0,5000], lat(0,65], cobertura[0.9,1]')
    records=[]
    with Path(regions_csv).open(newline='',encoding='utf-8') as f:
        for row in csv.DictReader(f):
            records.append(row)
    if len(records)!=16200 or len({r['region_id'] for r in records})!=len(records):
        raise ValueError('Se requiere catálogo global de 16.200 regiones únicas, V0.6')
    candidates=[r for r in records if r.get('status')=='land_candidate_unranked']
    mars=profile['features']
    spacing_km=float(profile['spacing_km'])
    samples=int(profile['samples_per_axis'])
    counted={'land_candidates':len(candidates),'excluded_latitude':0,
             'excluded_coverage_or_derivatives':0,'ranked':0}
    output=[]
    with xr.open_dataset(earth_file) as ds:
        sampler=GlobalSampler(ds,'Earth')
        if ds.attrs.get('schema')!='global_land_surface_v0.6':
            raise ValueError('Earth no contiene la máscara validada')
        for candidate in candidates:
            lat=float(candidate['center_lat'])
            lon=float(candidate['center_lon_180'])
            if abs(lat)>max_abs_lat:
                counted['excluded_latitude']+=1
                continue
            patch=sampler.sample(lat,lon,spacing_km,samples)
            vals=patch_features(patch,spacing_km)
            if vals is None or vals['sample_coverage']<min_patch_coverage:
                counted['excluded_coverage_or_derivatives']+=1
                continue
            dist=distance_metrics(vals,mars)
            output.append({
                'region_id':candidate['region_id'],'center_lat':lat,
                'center_lon_180':lon,
                'mapped_land_fraction':float(candidate['land_fraction_area_approx']),
                **vals,**dist})
    output.sort(key=lambda x:(x['distance_total'],x['region_id']))
    counted['ranked']=len(output)
    selections=diverse_top(output,top,min_separation_km)
    output_csv=Path(output_csv)
    output_csv.parent.mkdir(parents=True,exist_ok=True)
    if output:
        with output_csv.open('w',newline='',encoding='utf-8') as f:
            wr=csv.DictWriter(f,fieldnames=['rank',*output[0].keys()])
            wr.writeheader()
            wr.writerows({'rank':i,**r} for i,r in enumerate(output,1))
    else:
        raise ValueError('Ninguna región evaluable: revisar cobertura y máscara')
    report={'schema_version':'mars_analog_topographic_screen_v0.7',
            'status':'exploratory_topographic_distance_only_not_analog_confirmation',
            'profile_name':profile['profile_name'],
            'mars_center':[profile['center_lat'],profile['center_lon_east_0_360']],
            'nominal_comparison':{'spacing_km':spacing_km,'samples_per_axis':samples,
                                 'window_extent_center_to_center_km':profile['window_extent_center_to_center_km'],
                                 'distance_metric':'weighted absolute log-ratio, lower is closer',
                                 'weights':WEIGHTS,'regularizers':OFFSET},
            'counts':counted,'latitude_limit_abs_deg':float(max_abs_lat),
            'min_patch_coverage':float(min_patch_coverage),
            'min_geographic_separation_km':float(min_separation_km),
            'top_diverse':[{'rank_in_all':output.index(row)+1,**row} for row in selections],
            'input_sha256':{'mars_profile':sha256_file(Path(profile_file)),
                            'earth_surface':sha256_file(Path(earth_file)),
                            'earth_regions':sha256_file(Path(regions_csv))},
            'csv_file':str(output_csv),
            'csv_sha256':sha256_file(output_csv),
            'limitations':[
                'La distancia no expresa probabilidad, porcentaje de similitud ni validación geológica',
                'Una sola ventana de Marte no caracteriza la totalidad de Elysium Planitia',
                'No se incluyeron clima, litología, mineralogía, ni acceso logístico',
                'Se excluyen regiones costeras, latitudes polares y celdas con cobertura insuficiente',
                'La interpolación iguala escalas geométricas nominales, NO el contenido espectral efectivo',
                'Las ventanas pueden solaparse y los candidatos no son muestras independientes',
                'Relieve ETOPO de ~18.5 km NS y MOLA ~14.8 km; no aptos para planificación de rovers',
                'Comparación sin verificación independiente: requiere sensibilidad y referencias de control'
            ],
            'created_at_utc':datetime.now(timezone.utc).isoformat()}
    atomic_json(Path(report_file),report)
    report['report_file']=str(report_file)
    return report
