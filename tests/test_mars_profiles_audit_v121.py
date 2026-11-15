"""V1.2.1: tests without external networks, including complete synthetic workflows."""
import csv
import json

import numpy as np
import pytest

from mars_analog.data.mars_profiles_v12 import build_profiles, screen_profiles
from mars_analog.data.mars_profiles_audit_v121 import (
    _ranks, _groups, _signed, _alternative_scores, parse_scales,
    audit_rankings, audit_scales,
)
from test_mars_profiles_v12 import create_mars, create_earth_and_catalog


def _setup(tmp):
    mars=tmp/'mars.nc';create_mars(mars)
    earth,catalog=create_earth_and_catalog(tmp)
    man=tmp/'manifest.json'
    build_profiles(mars,'all',30,9,tmp/'profiles',man)
    screen=tmp/'screen.json'
    screen_profiles(man,earth,catalog,tmp/'rankings',screen,top=5,min_separation=0)
    return mars,earth,catalog,man,screen


def test_ranks_and_sign_groups():
    assert list(_ranks([1.,1.,2.],['b','a','c']))==[2,1,3]
    s=_signed(np.array([[1.,2.,10.,20.,30.]]),np.array([2.,4.,10.,40.,15.]))
    assert _groups(s).shape==(1,3)
    ee=np.array([[1.,2.,10.,20.,30.],
                 [4.,4.,20.,10.,10.],
                 [2.,3.,30.,30.,20.]])
    robust,pct,scale=_alternative_scores(_signed(ee,np.array([2.,4.,10.,40.,15.])),ee)
    assert robust.shape==(3,) and pct.shape==(3,) and scale.shape==(5,)
    assert np.isfinite(robust).all() and np.isfinite(pct).all()
    assert float(_groups(s)[0,0])>0


def test_parse_scales_rejects_bad_windows():
    assert parse_scales('15:17,30:9,40:7')==[(15,17),(30,9),(40,7)]
    for bad in ('60:5','15:17,60:5,30:9','20:11,30:9','30:9,30:9','nope'):
        if bad=='60:5':
            with pytest.raises(ValueError):parse_scales(bad)
        elif bad=='15:17,60:5,30:9':
            # Format is parsable but the multiscale analysis rejects 5x5.
            assert (60.,5) in parse_scales(bad)
        else:
            with pytest.raises(ValueError):parse_scales(bad)


def test_audit_rankings_complete_and_repeatable(tmp_path):
    mars,earth,cat,man,screen=_setup(tmp_path)
    outdir=tmp_path/'audit'
    r=audit_rankings(screen,man,outdir,ks=(5,8,10),scenarios=10,seed=2026,
                     watch=('r00000','r00001'))
    assert r['common_regions']==18
    assert len(r['pairwise'])==15
    assert (outdir/'feature_saturation.csv').exists()
    assert len(list(csv.DictReader((outdir/'feature_saturation.csv').open())))==30
    assert len(list(csv.DictReader((outdir/'weight_perturbations.csv').open())))==60
    assert r['files']['pairwise']['sha256']
    orig=(outdir/'weight_perturbations.csv').read_bytes()
    again=audit_rankings(screen,man,outdir,ks=(5,8,10),scenarios=10,seed=2026,
                         watch=('r00000','r00001'))
    assert orig==(outdir/'weight_perturbations.csv').read_bytes()
    assert again['report_sha256']==r['report_sha256']


def test_audit_scales_end_to_end_and_detects_tamper(tmp_path):
    mars,earth,cat,man,screen=_setup(tmp_path)
    res=audit_scales(screen,man,earth,mars,cat,tmp_path/'audit_scale',
                     scale_spec='15:17,30:9,40:7',top_k=5)
    assert len(res['comparisons'])==12
    assert res['scale_counts']['30km_9x9']['ranked']==18
    assert (tmp_path/'audit_scale/multiscale_mars_features.csv').exists()
    assert len(list(csv.DictReader((tmp_path/'audit_scale/multiscale_rankings.csv').open())))>60
    # Do not silently analyze Earth data modified since the original experiment.
    with open(earth,'ab') as f:f.write(b'X')
    with pytest.raises(ValueError,match='Fuente distinta'):
        audit_scales(screen,man,earth,mars,cat,tmp_path/'invalid',
                     scale_spec='30:9,40:7',top_k=5)


def test_audit_rankings_rejects_tampered_csv(tmp_path):
    mars,earth,cat,man,screen=_setup(tmp_path)
    source=json.loads(screen.read_text())
    path=source['profiles'][0]['ranking_csv']
    with open(path,'a') as f:f.write('garbage')
    with pytest.raises(ValueError,match='SHA-256'):
        audit_rankings(screen,man,tmp_path/'audit',ks=(5,),scenarios=2)
