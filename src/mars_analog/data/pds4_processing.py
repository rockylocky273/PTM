"""Decodificador defensivo PDS4 para raster de topografía MOLA.

Se obtiene formato, shape, orden de bytes, escalado, nodata y unidad desde XML.
NO georreferencia una malla planetaria sin parámetros cartográficos verificados.
"""
from dataclasses import dataclass
from pathlib import Path
from xml.etree import ElementTree as ET

import numpy as np
import xarray as xr

from .download import sha256_file

TYPE_MAP = {
    'SignedLSB2':'<i2','SignedMSB2':'>i2',
    'UnsignedLSB2':'<u2','UnsignedMSB2':'>u2',
    'SignedLSB4':'<i4','SignedMSB4':'>i4',
    'UnsignedLSB4':'<u4','UnsignedMSB4':'>u4',
    'SignedLSB8':'<i8','SignedMSB8':'>i8',
    'UnsignedLSB8':'<u8','UnsignedMSB8':'>u8',
    'SignedByte':'i1','UnsignedByte':'u1',
    'IEEE754LSBSingle':'<f4','IEEE754MSBSingle':'>f4',
    'IEEE754LSBDouble':'<f8','IEEE754MSBDouble':'>f8',
}


def lname(tag):
    return str(tag).rsplit('}',1)[-1]


def child(element, key):
    return next((x for x in element if lname(x.tag)==key),None)


def text_of(element,key,default=None):
    c = child(element,key)
    return default if c is None or c.text is None else c.text.strip()


@dataclass(frozen=True)
class ArraySpec:
    data_file: str
    data_type: str
    dtype: np.dtype
    offset_bytes: int
    axes: tuple[tuple[str,int,int], ...]  # (name, sequence_number, elements)
    scale: float
    value_offset: float
    unit: str | None
    special_constants: tuple[float, ...]


def parse_pds4_label(label_path: Path, data_file: Path) -> ArraySpec:
    label_path, data_file = Path(label_path),Path(data_file)
    root = ET.parse(label_path).getroot()
    selected = None
    for area in root.iter():
        if not lname(area.tag).startswith('File_Area_'):
            continue
        pds_file = child(area,'File')
        fname = text_of(pds_file,'file_name') if pds_file is not None else None
        if not fname or Path(fname).name.casefold()!=data_file.name.casefold():
            continue
        candidates = [x for x in area if lname(x.tag).startswith('Array_2D')]
        if len(candidates)!=1:
            raise ValueError(f'PDS4: se esperaba un Array_2D para {fname}, encontradas {len(candidates)}.')
        selected=(fname,candidates[0])
        break
    if selected is None:
        raise ValueError(f'PDS4: XML no referencia el archivo {data_file.name} dentro de un File_Area*.')
    fname, arr=selected
    order=text_of(arr,'axis_index_order','Last Index Fastest')
    if order!='Last Index Fastest':
        raise ValueError(f'Orden de índices PDS4 no compatible: {order!r}')
    element=child(arr,'Element_Array')
    if element is None: raise ValueError('PDS4: falta Element_Array.')
    dt_name=text_of(element,'data_type')
    if dt_name not in TYPE_MAP:
        raise ValueError(f'PDS4: data_type {dt_name!r} no soportado; no se interpretarán bytes.')
    offset=int(text_of(arr,'offset','0'))
    if offset<0:raise ValueError('PDS4: offset negativo.')
    axis=[]
    for x in arr:
        if lname(x.tag)=='Axis_Array':
            axis.append((text_of(x,'axis_name',''), int(text_of(x,'sequence_number','0')),
                         int(text_of(x,'elements','0'))))
    if len(axis)!=2 or {x[1] for x in axis}!={1,2} or any(x[2]<1 for x in axis):
        raise ValueError('PDS4: ejes 2D incompletos o secuencia inválida.')
    axis=tuple(sorted(axis,key=lambda t:t[1]))
    constants=[]
    special=child(arr,'Special_Constants')
    if special is not None:
        for c in special:
            if lname(c.tag).endswith('_constant') and c.text:
                try:constants.append(float(c.text.strip()))
                except ValueError:pass
    return ArraySpec(fname,dt_name,np.dtype(TYPE_MAP[dt_name]),offset,axis,
                     float(text_of(element,'scaling_factor','1')),
                     float(text_of(element,'value_offset','0')),
                     text_of(element,'unit'),tuple(constants))


def decode_mola(img_path: Path, xml_path: Path) -> tuple[xr.Dataset,dict]:
    img_path,xml_path=Path(img_path),Path(xml_path)
    if not img_path.is_file() or not xml_path.is_file():
        raise FileNotFoundError('Faltan IMG o XML de MOLA en la ruta indicada.')
    spec=parse_pds4_label(xml_path,img_path)
    shape=tuple(axis[2] for axis in spec.axes)
    nbytes=spec.offset_bytes + int(np.prod(shape)) * spec.dtype.itemsize
    if img_path.stat().st_size<nbytes:
        raise ValueError(f'Archivo IMG truncado: se necesitan al menos {nbytes} bytes.')
    raw=np.memmap(img_path,mode='r',dtype=spec.dtype,offset=spec.offset_bytes,shape=shape,order='C')
    missing=np.zeros(shape,dtype=bool)
    for value in spec.special_constants:
        if np.isnan(value):missing|=np.isnan(raw)
        else:missing|=(raw==value)
    missing |= ~np.isfinite(raw)
    physical=np.asarray(raw,dtype=np.float64)*spec.scale + spec.value_offset
    physical[missing]=np.nan
    dims=tuple('line' if a[0].lower()=='line' else 'sample' if a[0].lower()=='sample' else f'axis_{a[1]}' for a in spec.axes)
    if len(set(dims))!=2:
        raise ValueError('PDS4: nombres de ejes duplicados.')
    if 'line' in dims and 'sample' in dims:
        original=xr.DataArray(physical,dims=dims).transpose('line','sample')
    else:
        original=xr.DataArray(physical,dims=dims)
    unit=(spec.unit or '').strip()
    # No inventar conversion si el XML no acredita unidades de longitud.
    if unit.lower() in ('m','meter','meters','metre','metres'):
        array=original
        variable='elevation_m'
        output_unit='m'
    elif unit.lower() in ('km','kilometer','kilometers','kilometre','kilometres'):
        array=original*1000.0
        variable='elevation_m'
        output_unit='m'
    else:
        array=original
        variable='value_native'
        output_unit=unit or 'not_specified'
    if not np.isfinite(array.values).any():
        raise ValueError('MOLA: la matriz no contiene valores válidos después de aplicar nodata.')
    ds=array.to_dataset(name=variable)
    ds[variable].attrs['units']=output_unit
    ds.attrs={
        'dataset':'NASA_PDS4_MOLA_MEGDR',
        'source_file':img_path.name,
        'source_label':xml_path.name,
        'source_sha256':sha256_file(img_path),
        'label_sha256':sha256_file(xml_path),
        'planet':'Mars',
        'georeferenced':'false',
        'georeference_note':'Coordinates remain pixel indices; do not overlay geographically without reading validated cartographic metadata',
        'data_type':spec.data_type,
        'scale':float(spec.scale),
        'value_offset':float(spec.value_offset),
        'special_constants':str(spec.special_constants),
    }
    values=ds[variable].values
    summary={
        'dataset':'mola_topography',
        'source_img':str(img_path),'source_xml':str(xml_path),
        'source_sha256':ds.attrs['source_sha256'],
        'label_sha256':ds.attrs['label_sha256'],
        'data_type':spec.data_type,'offset_bytes':spec.offset_bytes,
        'axes':[{'name':a[0],'sequence':a[1],'elements':a[2]} for a in spec.axes],
        'shape':list(values.shape),
        'scale':spec.scale,'value_offset':spec.value_offset,
        'raw_unit':spec.unit,'output_variable':variable,'output_unit':output_unit,
        'special_constants':list(spec.special_constants),
        'valid_samples':int(np.isfinite(values).sum()),
        'missing_samples':int(np.isnan(values).sum()),
        'minimum':float(np.nanmin(values)),
        'maximum':float(np.nanmax(values)),
        'mean':float(np.nanmean(values)),
        'georeferenced':False,
        'note':'Coordenadas de píxeles, NO coordenadas marcianas todavía. La proyección se integrará en siguiente etapa.',
    }
    return ds,summary


def process_mola(img_path:Path,xml_path:Path,output:Path | None=None)->dict:
    ds,summary=decode_mola(img_path,xml_path)
    if output is not None:
        output=Path(output)
        output.parent.mkdir(parents=True,exist_ok=True)
        ds.to_netcdf(output)
        summary['output_file']=str(output)
        summary['output_sha256']=sha256_file(output)
    return summary
