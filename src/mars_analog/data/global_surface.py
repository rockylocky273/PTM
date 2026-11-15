"""V0.6: reconstruir matriz global ETOPO, máscara de tierra y regiones 2°.

NO indexa H3, NO estima analogía con Marte, NO atribuye precisión 15km.
"""
from __future__ import annotations
import csv
from pathlib import Path

import numpy as np
import xarray as xr
from scipy.ndimage import minimum_filter, uniform_filter

from .download import sha256_file, atomic_json
from .global_tiles import load_plan, global_inventory, _target_path
from .landmask import land_centers_mask, NE_VERSION
from .terrain_features import _physical_spacing

R_EARTH_KM = 6371.0088


def assemble_global(plan_file: Path, tiles_directory: Path, output: Path) -> dict:
    """Combina tiles validados por SHA sin huecos, duplicaciones ni desorden."""
    plan=load_plan(Path(plan_file))
    stride=int(plan['stride'])
    tile_deg=int(plan['tile_deg'])
    if (tile_deg*60)%stride != 0 or (180*60)%stride != 0 or (360*60)%stride != 0:
        raise ValueError('El stride no divide exactamente la malla global')
    side=tile_deg*60//stride
    ny=180*60//stride
    nx=360*60//stride
    # El cálculo NO acepta datos sin metadata/caché correctos.
    audit=global_inventory(Path(plan_file),Path(tiles_directory),
                           Path('data/reports/global_inventory.json'))
    if not audit['complete']:
        raise ValueError(f"Catálogo incompleto/inválido: {audit['validated_tiles']}/{audit['total_tiles']}"
                         f" (inválidas: {audit['invalid_tiles']}). Ejecutá global-inventory.")
    z=np.full((ny,nx),np.nan,dtype=np.float32)
    occupied=np.zeros((ny,nx),dtype=bool)
    expected_lat=-90+1/120+np.arange(ny,dtype=float)*stride/60
    expected_lon=0+1/120+np.arange(nx,dtype=float)*stride/60
    for tile in plan['tiles']:
        path=_target_path(Path(tiles_directory),tile,stride)
        with xr.open_dataset(path,mask_and_scale=True) as ds:
            lat=np.asarray(ds.latitude.values,dtype=np.float64)
            lon=np.asarray(ds.longitude.values,dtype=np.float64)
            values=np.asarray(ds.z.values,dtype=np.float32)
        start_i=int((tile['south']+90)*60//stride)
        start_j=int(tile['west_0_360']*60//stride)
        i=slice(start_i,start_i+side)
        j=slice(start_j,start_j+side)
        if values.shape!=(side,side):
            raise ValueError(f"Tesela {tile['id']} de dimensiones inesperadas: {values.shape}")
        if not np.allclose(lat,expected_lat[i],rtol=0,atol=2e-4):
            raise ValueError(f"Coordenadas de latitud no alineadas: {tile['id']}")
        if not np.allclose(lon,expected_lon[j],rtol=0,atol=2e-4):
            raise ValueError(f"Coordenadas de longitud no alineadas: {tile['id']}")
        if occupied[i,j].any():
            raise ValueError(f"Solapamiento entre teselas: {tile['id']}")
        z[i,j]=values
        occupied[i,j]=True
    if not np.all(occupied):
        raise ValueError(f"Quedan {int((~occupied).sum())} celdas sin cobertura del catálogo")
    ds=xr.Dataset({'elevation_m':(('latitude','longitude'),z)},
                  coords={'latitude':expected_lat,'longitude':expected_lon},
                  attrs={'planet':'Earth','dataset':'ETOPO_2022_v1_60s',
                         'grid_longitude':'0_360 east positive',
                         'elevation_vertical_datum':'ETOPO EGM2008 height (ice surface)',
                         'mosaic_schema':'mars_analog_global_mosaic_v0.6',
                         'source_plan_sha256':sha256_file(Path(plan_file)),
                         'sampling_step_arcsec':60*stride,
                         'warning':'Incluye batimetría, tierra/agua aún NO clasificada.'})
    ds.elevation_m.attrs={'units':'m'}
    output=Path(output)
    output.parent.mkdir(parents=True,exist_ok=True)
    ds.to_netcdf(output)
    return {'status':'mosaic_validated_no_land_mask','shape':[ny,nx],
            'filled_grid_cells':int(occupied.sum()),
            'valid_elevations':int(np.isfinite(z).sum()),
            'longitude_range':[float(expected_lon[0]),float(expected_lon[-1])],
            'latitude_range':[float(expected_lat[0]),float(expected_lat[-1])],
            'source_plan_sha256':sha256_file(Path(plan_file)),
            'output_file':str(output),'output_sha256':sha256_file(output),
            'analogs_ranked':False}


def _masked_topography(z: np.ndarray, lat: np.ndarray, lon: np.ndarray, land: np.ndarray):
    """Pendiente y rugosidad *solo* en interiores terrestres 3x3.

    Costa excluida del cálculo de pendientes para no mezclar batimetría.
    Longitud periódica, latitud con bordes no periódicos, polos excluidos.
    """
    valid=np.isfinite(z)
    clean=np.where(valid,z,0.0).astype(float)
    phi=np.deg2rad(lat)
    lamb=np.deg2rad(lon)
    dz_dphi=np.gradient(clean,phi,axis=0,edge_order=2)
    if len(lon)<3:
        raise ValueError('Se necesitan al menos 3 columnas para el gradiente')
    dl=float(np.median(np.diff(lamb)))
    dz_dlambda=(np.roll(clean,-1,axis=1)-np.roll(clean,1,axis=1))/(2*dl)
    meridional,zonal=_physical_spacing(lat,'earth')
    with np.errstate(invalid='ignore',divide='ignore'):
        slope=np.degrees(np.arctan(np.hypot(dz_dphi/meridional[:,None],
                                            dz_dlambda/zonal[:,None])))
    mean=uniform_filter(clean,size=3,mode=('nearest','wrap'))
    sq=uniform_filter(clean*clean,size=3,mode=('nearest','wrap'))
    rough=np.sqrt(np.maximum(0.0,sq-mean*mean))
    interior=minimum_filter((land&valid).astype(np.uint8),size=3,
                            mode=('constant','wrap'),cval=0).astype(bool)
    interior &= (np.abs(lat) < 89.0)[:,None]
    return np.where(interior,slope,np.nan).astype('float32'),\
           np.where(interior,rough,np.nan).astype('float32'),interior


def _stats(values):
    values=np.asarray(values,dtype=float)
    values=values[np.isfinite(values)]
    if values.size==0:
        return None,None,None,None
    return (float(np.percentile(values,10)), float(np.median(values)),
            float(np.percentile(values,90)), float(np.percentile(values,90)-np.percentile(values,10)))


def _regions(lat, lon, elev, land, slope, rough, region_deg, minimum_land_fraction):
    if not (isinstance(region_deg,int) and region_deg in (1,2,5,10)):
        raise ValueError('region_deg permitido: 1, 2, 5, 10')
    step=round(float(np.median(np.diff(lat))),8)
    n_float=region_deg/step
    per=int(round(n_float))
    if abs(per-n_float)>1e-5 or len(lat)%per or len(lon)%per:
        raise ValueError('El tamaño regional no es múltiplo de la malla muestreada')
    if not (0.0<minimum_land_fraction<=1):
        raise ValueError('minimum_land_fraction debe ser >0 y <=1')
    nrow=len(lat)//per
    ncol=len(lon)//per
    rows=[]
    for ir in range(nrow):
        sl=slice(ir*per,(ir+1)*per)
        lats=lat[sl]
        weight=np.cos(np.deg2rad(lats))[:,None]
        for jc in range(ncol):
            sc=slice(jc*per,(jc+1)*per)
            here=land[sl,sc]
            zv=elev[sl,sc]
            sv=slope[sl,sc]
            rv=rough[sl,sc]
            fraction=float((here*weight).sum()/(weight.sum()*per))
            ok=here & np.isfinite(zv)
            count=int(ok.sum())
            validfrac=count/max(1,int(here.sum()))
            p10,p50,p90,relief=_stats(zv[ok])
            _,s50,s90,_=_stats(sv)
            _,r50,r90,_=_stats(rv)
            if not np.any(here):
                status='ocean_or_not_mapped_land'
            elif fraction<minimum_land_fraction:
                status='mixed_coastal_or_island'
            elif validfrac<0.95:
                status='insufficient_elevation'
            else:
                status='land_candidate_unranked'
            # Longitudes en grados del dominio NOAA; para CSV normalizar solo el centro.
            west_0360=float(jc*region_deg)
            west_180=((west_0360+180)%360)-180
            center_180=((west_0360+region_deg/2+180)%360)-180
            south=float(-90+ir*region_deg)
            area=(R_EARTH_KM**2*np.deg2rad(region_deg)*
                  (np.sin(np.deg2rad(south+region_deg))-np.sin(np.deg2rad(south))))
            rows.append({
                'region_id':f'r{ir:03d}_c{jc:03d}',
                'lat_s':south,'lat_n':south+region_deg,
                'lon_w_0_360':west_0360,'lon_e_0_360':west_0360+region_deg,
                'center_lat':south+region_deg/2,'center_lon_180':center_180,
                'land_fraction_area_approx':round(fraction,6),
                'estimated_land_area_km2':round(area*fraction,2),
                'total_sample_count':int(zv.size),
                'land_center_count':int(here.sum()),
                'valid_land_elevation_count':count,
                'valid_interior_slope_count':int(np.isfinite(sv).sum()),
                'land_elev_p10_m':p10,'land_elev_median_m':p50,'land_elev_p90_m':p90,
                'land_elev_relief_p90_p10_m':relief,
                'land_slope_median_deg':s50,'land_slope_p90_deg':s90,
                'land_roughness_std3_median_m':r50,'land_roughness_std3_p90_m':r90,
                'status':status})
    return rows


def build_land_regions(mosaic: Path, land_zip: Path, output_nc: Path,
                       output_csv: Path, output_json: Path,
                       region_deg: int=2, min_land_fraction: float=0.8) -> dict:
    mosaic=Path(mosaic);land_zip=Path(land_zip)
    with xr.open_dataset(mosaic) as opened:
        if opened.attrs.get('mosaic_schema')!='mars_analog_global_mosaic_v0.6':
            raise ValueError('Entrada no es el mosaico global validado V0.6')
        ds=opened.load()
    z=np.asarray(ds['elevation_m'].values,dtype=np.float32)
    lat=np.asarray(ds.latitude.values,dtype=float)
    lon=np.asarray(ds.longitude.values,dtype=float)
    if z.shape!=(len(lat),len(lon)) or len(lat)<3 or len(lon)<3:
        raise ValueError('Dimensiones del mosaico no válidas')
    mask=land_centers_mask(lat,lon,land_zip)
    slope,rough,interior=_masked_topography(z,lat,lon,mask)
    rows=_regions(lat,lon,z,mask,slope,rough,region_deg,min_land_fraction)
    # Salida ordenada por longitud normalizada -180..180.
    newlon=(lon+180)%360-180
    idx=np.argsort(newlon)
    dsout=xr.Dataset({
        'elevation_m':(('latitude','longitude'),z[:,idx]),
        'land_mask':(('latitude','longitude'),mask[:,idx].astype(np.int8)),
        'land_elevation_m':(('latitude','longitude'),np.where(mask,z,np.nan)[:,idx]),
        'land_interior_slope_deg':(('latitude','longitude'),slope[:,idx]),
        'land_interior_roughness_std3_m':(('latitude','longitude'),rough[:,idx])},
        coords={'latitude':lat,'longitude':newlon[idx]},
        attrs={'planet':'Earth','schema':'global_land_surface_v0.6',
               'mask_source':NE_VERSION,'mask_zip_sha256':sha256_file(land_zip),
               'mosaic_sha256':sha256_file(mosaic),
               'classification_method':'Natural Earth land polygon contains pixel center',
               'terrain_method':'3x3 fully terrestrial neighbors only; spherical longitude wrap',
               'land_mask_warning':'Approximate coastline; lakes, small islands, ice and ambiguous shorelines not resolved.',
               'grid_warning':'Angular 10 arcmin, non-equal-area; ~18.5 km lat spacing, east-west spacing varies with latitude',
               'analog_similarity':'not_computed'})
    dsout.elevation_m.attrs={'units':'m'}
    dsout.land_elevation_m.attrs={'units':'m'}
    dsout.land_interior_slope_deg.attrs={'units':'degree'}
    dsout.land_interior_roughness_std3_m.attrs={'units':'m'}
    dsout.land_mask.attrs={'values':'0=not within mapped land, 1=within mapped land'}
    output_nc=Path(output_nc)
    output_nc.parent.mkdir(parents=True,exist_ok=True)
    dsout.to_netcdf(output_nc)
    output_csv=Path(output_csv)
    output_csv.parent.mkdir(parents=True,exist_ok=True)
    with output_csv.open('w',newline='',encoding='utf-8') as f:
        writer=csv.DictWriter(f,fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)
    groups={status:sum(r['status']==status for r in rows) for status in
            ('land_candidate_unranked','mixed_coastal_or_island',
             'insufficient_elevation','ocean_or_not_mapped_land')}
    result={'status':'land_masked_and_indexed_no_mars_similarity',
            'planet':'Earth','regional_grid_degrees':region_deg,
            'region_count':len(rows),'category_counts':groups,
            'land_centers':int(mask.sum()),'ocean_or_other_centers':int((~mask).sum()),
            'land_interior_slope_centers':int(interior.sum()),
            'coverage_warning':'Land mask derived from generalized Natural Earth polygons, not a high-resolution coastline.',
            'mosaic_sha256':sha256_file(mosaic),'mask_sha256':sha256_file(land_zip),
            'output_nc':str(output_nc),'output_nc_sha256':sha256_file(output_nc),
            'output_csv':str(output_csv),'output_csv_sha256':sha256_file(output_csv),
            'analogs_ranked':False,'note':'La topografía global es un primer filtro; falta clima, geología y perfil marciano.'}
    atomic_json(Path(output_json),result)
    result['report_file']=str(output_json)
    return result
