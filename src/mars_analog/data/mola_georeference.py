"""Georreferenciar exclusivamente el producto global MOLA MEGDR 4 pix/grado.

La malla canonical MEGT90N000CB está descrita en el catálogo oficial PDS:
 - 720 filas x 1440 columnas, cubriendo latitudes 90 a -90 y longitudes 0 a 360E
 - centro del pixel (i,j) lat 90-(i+.5)/4, lon (j+.5)/4.
 - marco areocéntrico / longitud positiva al este, estándar IAU2000.

No es un CRS de la Tierra y no se presupone validez para otros productos/tile.
Referencias: https://pds-geosciences.wustl.edu/missions/mgs/megdr.html
https://pds.nasa.gov/ds-view/pds/viewProfile.jsp?dsid=MGS-M-MOLA-5-MEGDR-L3-V1.0
"""
from pathlib import Path
import numpy as np
import xarray as xr
from .download import sha256_file

EXPECTED_SOURCE = 'megt90n000cb.img'
EXPECTED_LABEL = 'megt90n000cb.xml'
SHAPE = (720, 1440)


def georeference_meg004(ds: xr.Dataset) -> tuple[xr.Dataset, dict]:
    """Retorna una malla areocéntrica de Marte; verifica identidad y geometría.

    La georreferenciación se asigna por definición verificada del producto PDS,
    no por heurísticas que funcionarían accidentalmente con archivos distintos.
    """
    attrs = ds.attrs
    if attrs.get('dataset') != 'NASA_PDS4_MOLA_MEGDR':
        raise ValueError('MOLA: el NetCDF no declara el producto PDS4 esperado.')
    if (str(attrs.get('source_file', '')).lower() != EXPECTED_SOURCE or
            str(attrs.get('source_label', '')).lower() != EXPECTED_LABEL):
        raise ValueError('MOLA: producto desconocido; georreferenciación solo para MEGT90N000CB.')
    if 'elevation_m' not in ds:
        raise ValueError('MOLA: se requiere elevation_m en metros.')
    if ds['elevation_m'].dims != ('line', 'sample') or ds['elevation_m'].shape != SHAPE:
        raise ValueError(f'MOLA: dimensiones esperadas {SHAPE} en ejes line/sample.')
    if str(ds['elevation_m'].attrs.get('units', '')).lower() != 'm':
        raise ValueError('MOLA: no se ha confirmado unidad de elevación en metros.')
    if not attrs.get('source_sha256') or not attrs.get('label_sha256'):
        raise ValueError('MOLA: faltan huellas de procedencia de IMG/XML.')

    # PDS fija los límites de la cobertura en bordes de píxel.
    lat = 90.0 - (np.arange(SHAPE[0], dtype='float64') + 0.5) / 4.0
    lon = (np.arange(SHAPE[1], dtype='float64') + 0.5) / 4.0
    geo = ds.rename({'line': 'latitude', 'sample': 'longitude'}).assign_coords(
        latitude=('latitude', lat), longitude=('longitude', lon))
    geo['latitude'].attrs.update({'standard_name': 'latitude', 'units':'degrees_north',
                                 'reference':'planetocentric IAU2000'})
    geo['longitude'].attrs.update({'standard_name':'longitude', 'units':'degrees_east',
                                  'reference':'0..360 east_positive IAU2000'})
    geo.attrs.update({
        'planet': 'Mars', 'georeferenced': 'true',
        'georeference_source':'NASA PDS MOLA MEGDR meg004 global product documentation',
        'planetocentric_latitude': 'true',
        'longitude_positive': 'east', 'longitude_range':'0_360',
        'horizontal_coordinates': 'IAU2000 MOLA; NOT Earth WGS84/EPSG:4326',
        'latitude_pixel_centers': '90-(line+0.5)/4 degrees, 0-based',
        'longitude_pixel_centers': '(sample+0.5)/4 degrees east, 0-based',
        'grid_resolution_degrees': 0.25,
        'planetary_radius_m_for_terrain': 3396000.0,
        'radius_note':'Spherical approximation for coarse terrain derivatives; not a precise Mars geodesic',
        'georeference_note': 'Global canonical MEGT90N000CB, coordinates assigned from PDS documented spatial extent',
    })
    return geo, {'planet':'Mars', 'shape':[720,1440], 'georeferenced':True,
                 'resolution_deg':0.25, 'latitude_first_center':float(lat[0]),
                 'latitude_last_center':float(lat[-1]),
                 'longitude_first_center':float(lon[0]),
                 'longitude_last_center':float(lon[-1]),
                 'coordinate_system':'MOLA planetocentric IAU2000 east-positive',
                 'source_sha256':str(attrs['source_sha256'])}


def process_mola_georef(source: Path, output: Path) -> dict:
    source, output = Path(source), Path(output)
    with xr.open_dataset(source) as opened:
        ds=opened.load()
    geo, summary = georeference_meg004(ds)
    output.parent.mkdir(parents=True, exist_ok=True)
    geo.to_netcdf(output)
    summary['output_file']=str(output)
    summary['output_sha256']=sha256_file(output)
    return summary
