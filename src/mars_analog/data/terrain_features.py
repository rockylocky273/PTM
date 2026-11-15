"""Características topográficas reproducibles sobre mallas geográficas regulares.

V0.3: pendiente geográfica (grados), rugosidad de elevación local (std m, 3x3),
relieve p90-p10 y métricas de cobertura. Sin aplicar máscara de tierra ficticia.
Las métricas locales son DEL TAMAÑO DE CELDA ACTUAL y no comparables entre
ETOPO y MOLA hasta normalizar escalas físicas en siguientes versiones.
"""
from pathlib import Path
import numpy as np
import xarray as xr
from scipy.ndimage import uniform_filter
from .download import sha256_file

A_EARTH = 6378137.0
E2_EARTH = 6.69437999014e-3
R_MARS = 3396000.0


def _physical_spacing(lat_degrees: np.ndarray, planet: str) -> tuple[np.ndarray, np.ndarray]:
    phi=np.deg2rad(lat_degrees)
    if planet.lower()=='earth':
        sin2 = np.sin(phi)**2
        meridional = A_EARTH*(1-E2_EARTH)/(1-E2_EARTH*sin2)**1.5
        zonal=A_EARTH/np.sqrt(1-E2_EARTH*sin2)*np.cos(phi)
        return meridional,zonal
    if planet.lower()=='mars':
        return np.full_like(phi,R_MARS), R_MARS*np.cos(phi)
    raise ValueError(f'Planeta no soportado: {planet}')


def _local_roughness(z: np.ndarray, periodic_lon: bool) -> np.ndarray:
    """Desviación estándar local de elevación (m), ventana 3x3, solo válidos.

    Los puntos cercanos a huecos deben tener al menos 5 valores válidos;
    los bordes latitudinales replican filas, y Mars wrappea longitudes.
    """
    valid=np.isfinite(z)
    v=np.where(valid,z,0.0)
    modes=('nearest','wrap' if periodic_lon else 'nearest')
    k=3*3
    weights=uniform_filter(valid.astype(float),size=(3,3),mode=modes)*k
    mean=uniform_filter(v,size=(3,3),mode=modes)*k/np.maximum(weights,1)
    squared=uniform_filter(v*v,size=(3,3),mode=modes)*k/np.maximum(weights,1)
    rough=np.sqrt(np.maximum(0.0,squared-mean*mean))
    rough[(weights<5)|~valid]=np.nan
    return rough


def terrain_features(ds: xr.Dataset, planet: str) -> tuple[xr.Dataset,dict]:
    planet=planet.lower()
    if planet not in ('earth','mars'):
        raise ValueError('planet debe ser earth o mars')
    if planet=='mars' and (ds.attrs.get('georeferenced')!='true' or
                           ds.attrs.get('planet')!='Mars'):
        raise ValueError('MOLA todavía no está georreferenciado: primero ejecutá mola-georef.')
    if planet=='earth' and not ds.attrs.get('dataset','').startswith('ETOPO_'):
        raise ValueError('Earth: se esperaba NetCDF ETOPO normalizado.')
    if 'elevation_m' not in ds or ds['elevation_m'].dims != ('latitude','longitude'):
        raise ValueError('Se requiere elevation_m(latitude,longitude).')
    if ds['elevation_m'].attrs.get('units') != 'm':
        raise ValueError('Unidades de elevación no verificadas (se requieren metros).')
    lat=np.asarray(ds.latitude.values,dtype=float)
    lon=np.asarray(ds.longitude.values,dtype=float)
    if lat.size<3 or lon.size<3 or not np.all(np.isfinite(lat)) or not np.all(np.isfinite(lon)):
        raise ValueError('Coordenadas inválidas o insuficientes (mínimo 3x3).')
    if np.any(abs(lat)>90) or not (np.all(np.diff(lat)>0) or np.all(np.diff(lat)<0)):
        raise ValueError('Latitudes inválidas o no monótonas.')
    if np.any(np.diff(lon)<=0):
        raise ValueError('Longitudes deben crecer estrictamente.')
    if planet == 'mars' and (ds['elevation_m'].shape != (720,1440) or
                             ds.attrs.get('longitude_range') != '0_360'):
        raise ValueError('MOLA debe ser la cuadrícula global 4 pixels/grado confirmada.')
    z=np.asarray(ds['elevation_m'].values,dtype=np.float64)
    valid=np.isfinite(z)
    latr=np.deg2rad(lat)
    lonr=np.deg2rad(lon)
    # Derivada vertical respecto a latitud, respetando el orden creciente/decreciente.
    dz_dphi=np.gradient(z,latr,axis=0,edge_order=2)
    if planet=='mars':
        # La cuadrícula global es periódica en longitud, incluir transición 359.875 -> 0.125.
        step=np.deg2rad(0.25)
        dz_dlambda=(np.roll(z,-1,axis=1)-np.roll(z,1,axis=1))/(2*step)
    else:
        dz_dlambda=np.gradient(z,lonr,axis=1,edge_order=2)
    m,n=_physical_spacing(lat,planet)
    with np.errstate(invalid='ignore',divide='ignore'):
        dy=dz_dphi/m[:,None]
        dx=dz_dlambda/n[:,None]
        slope=np.degrees(np.arctan(np.hypot(dx,dy)))
    # La cuadrícula MOLA de 4 px/deg no permite gradientes este-oeste
    # fiables cerca de los polos, donde converge el meridiano.
    if planet=='mars':
        slope[np.abs(lat)>=89.5,:]=np.nan
    slope[~valid]=np.nan
    rough=_local_roughness(z,periodic_lon=planet=='mars')
    out=xr.Dataset(
        {'elevation_m': (('latitude','longitude'), z.astype('float32')),
         'slope_deg': (('latitude','longitude'),slope.astype('float32')),
         'roughness_std3_m':(('latitude','longitude'),rough.astype('float32'))},
        coords={'latitude': lat,'longitude':lon},
        attrs={**ds.attrs,'planet': 'Mars' if planet=='mars' else 'Earth',
               'feature_version': '0.3.0',
               'slope_method':'central differences of height vs angular coordinates and planet-appropriate metric radii',
               'roughness_method':'3x3 elevation standard deviation in meters, not scale-normalized',
               'comparison_warning':'Earth/Mars derived features use different pixel footprints; not directly comparable until physical scale harmonization',
               'polar_warning':'Mars |latitude|>=89.5 degrees masked for slope reliability',
               'land_mask_applied':ds.attrs.get('land_mask_applied','false')})
    out['elevation_m'].attrs={'units':'m'}
    out['slope_deg'].attrs={'units':'degree','long_name':'Magnitude of topographic slope'}
    out['roughness_std3_m'].attrs={'units':'m','long_name':'Local 3x3 elevation standard deviation'}
    selected=z[valid]
    good_slope=slope[np.isfinite(slope)]
    good_rough=rough[np.isfinite(rough)]
    result={
        'planet':out.attrs['planet'], 'shape': list(z.shape),
        'valid_elevation_samples':int(valid.sum()),
        'valid_slope_samples':int(np.isfinite(slope).sum()),
        'valid_roughness_samples':int(np.isfinite(rough).sum()),
        'elevation_p10_m':float(np.percentile(selected,10)),
        'elevation_p90_m':float(np.percentile(selected,90)),
        'relief_p90_p10_m':float(np.percentile(selected,90)-np.percentile(selected,10)),
        'slope_median_deg':float(np.median(good_slope)) if len(good_slope) else None,
        'slope_p90_deg':float(np.percentile(good_slope,90)) if len(good_slope) else None,
        'roughness_median_m':float(np.median(good_rough)) if len(good_rough) else None,
        'roughness_p90_m':float(np.percentile(good_rough,90)) if len(good_rough) else None,
        'note':'Estadísticas de las muestras cargadas, no estimación global terrestre ni ranking de análogos.',
    }
    return out,result


def process_terrain_features(source: Path, output: Path, planet: str) -> dict:
    source,output=Path(source),Path(output)
    with xr.open_dataset(source) as opened:
        ds=opened.load()
    features,summary=terrain_features(ds,planet)
    output.parent.mkdir(parents=True,exist_ok=True)
    features.to_netcdf(output)
    summary['input_file']=str(source)
    summary['input_sha256']=sha256_file(source)
    summary['output_file']=str(output)
    summary['output_sha256']=sha256_file(output)
    return summary
