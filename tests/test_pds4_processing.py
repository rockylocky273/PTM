import numpy as np
import pytest
import xarray as xr
from mars_analog.data.pds4_processing import parse_pds4_label,decode_mola,process_mola


def example_xml(dtype='SignedLSB2',unit='m',axes=('Line','Sample')):
    return f"""<?xml version='1.0'?>
<Product_Observational xmlns='http://pds.nasa.gov/pds4/pds/v1'>
  <File_Area_Observational>
    <File><file_name>synthetic.img</file_name></File>
    <Array_2D_Map>
      <offset unit='byte'>4</offset><axis_index_order>Last Index Fastest</axis_index_order>
      <Element_Array><data_type>{dtype}</data_type><unit>{unit}</unit>
        <scaling_factor>2</scaling_factor><value_offset>10</value_offset></Element_Array>
      <Axis_Array><axis_name>{axes[0]}</axis_name><elements>2</elements><sequence_number>1</sequence_number></Axis_Array>
      <Axis_Array><axis_name>{axes[1]}</axis_name><elements>3</elements><sequence_number>2</sequence_number></Axis_Array>
      <Special_Constants><missing_constant>-32768</missing_constant></Special_Constants>
    </Array_2D_Map>
  </File_Area_Observational>
</Product_Observational>"""


def make_pds(tmp_path, xml=None):
    img=tmp_path/'synthetic.img'
    img.write_bytes(b'ABCD'+np.array([[0,100,-32768],[50,-20,3]],dtype='<i2').tobytes())
    label=tmp_path/'synthetic.xml'
    label.write_text(xml if xml is not None else example_xml(),encoding='utf-8')
    return img,label


def test_pds4_decoder_scaling_mask_and_export(tmp_path):
    img,label=make_pds(tmp_path)
    ds,s=decode_mola(img,label)
    assert s['shape']==[2,3]
    assert s['data_type']=='SignedLSB2'
    assert s['missing_samples']==1
    assert s['minimum']==-30
    assert s['maximum']==210
    assert ds['elevation_m'].values[0,0]==10
    assert np.isnan(ds['elevation_m'].values[0,2])
    dest=tmp_path/'out.nc'
    process_mola(img,label,dest)
    with xr.open_dataset(dest) as reopened:
        assert reopened.attrs['georeferenced']=='false'
        assert reopened['elevation_m'].shape==(2,3)


def test_pds4_reject_unsupported_dtype(tmp_path):
    img,label=make_pds(tmp_path,example_xml(dtype='ThisTypeDoesNotExist'))
    with pytest.raises(ValueError,match='no soportado'):
        parse_pds4_label(label,img)


def test_pds4_reject_truncated(tmp_path):
    img,label=make_pds(tmp_path)
    img.write_bytes(b'ABCD')
    with pytest.raises(ValueError,match='truncado'):
        decode_mola(img,label)


def test_pds4_unknown_unit_preserved(tmp_path):
    img,label=make_pds(tmp_path,example_xml(unit='DN'))
    ds,s=decode_mola(img,label)
    assert 'value_native' in ds
    assert s['output_unit']=='DN'
    assert s['georeferenced'] is False


def test_pds4_axis_order_transposes(tmp_path):
    img,label=make_pds(tmp_path,example_xml(axes=('Sample','Line')))
    ds,s=decode_mola(img,label)
    assert ds['elevation_m'].dims==('line','sample')
    assert s['shape']==[3,2]
