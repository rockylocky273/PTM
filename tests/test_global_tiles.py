import json
from pathlib import Path

import numpy as np
import pytest
import xarray as xr

from mars_analog.data import global_tiles as gt
from mars_analog.data.download import sha256_file


def make_test_nc(path: Path, tile: dict, stride=10, units="m"):
    step = stride / 60
    lat = np.arange(tile["south"] + 1/120, tile["north"], step)
    lon = np.arange(tile["west_0_360"] + 1/120, tile["east_0_360"], step)
    z = np.full((len(lat),len(lon)),2100,dtype="float32")
    z[0,0] = np.nan
    ds = xr.Dataset({"z":(("latitude","longitude"),z,{"units":units})},coords={"latitude":lat,"longitude":lon})
    path.parent.mkdir(parents=True,exist_ok=True)
    ds.to_netcdf(path)


def test_global_plan_is_complete_no_download_and_deterministic(tmp_path):
    p = tmp_path / "plan.json"
    r = gt.save_plan(p, 30, 10)
    a = gt.load_plan(p)
    assert r["tiles"] == 72
    assert len(a["tiles"]) == len({t["id"] for t in a["tiles"]}) == 72
    assert sum((t["north"]-t["south"])*(t["east_0_360"]-t["west_0_360"]) for t in a["tiles"]) == 180*360
    assert a["tiles"][0]["south"] == -90
    assert a["tiles"][-1]["east_0_360"] == 360
    assert not (tmp_path / "raw").exists()
    gt.save_plan(p, 30, 10)
    gt.load_plan(p)


def test_plan_modified_rejected(tmp_path):
    p = tmp_path / "plan.json"
    gt.save_plan(p)
    j = json.loads(p.read_text())
    j["tiles"][0]["north"] = -59
    p.write_text(json.dumps(j))
    with pytest.raises(ValueError,match="editado"):
        gt.load_plan(p)


def test_plan_stride_and_extent_validation():
    with pytest.raises(ValueError):
        gt.create_plan(tile_deg=13)
    with pytest.raises(ValueError):
        gt.create_plan(stride=0)
    tile=gt.create_plan()["tiles"][-1]
    url=gt.build_global_tile_url(tile, 10)
    assert "330.008333" in url and "359.991667" in url
    assert ":10:" in url


def test_verify_realistic_tile_and_failed_units(tmp_path):
    tile=gt.create_plan()["tiles"][0]
    p=tmp_path / "t.nc"
    make_test_nc(p,tile)
    result=gt.verify_tile_file(p,tile,10)
    assert result["shape"] == [180,180]
    assert result["valid_elevation_samples"] == 180*180-1
    assert result["land_mask_status"] == "not_applied"
    make_test_nc(p,tile,units="feet")
    with pytest.raises(ValueError,match="Unidad"):
        gt.verify_tile_file(p,tile,10)


def test_missing_invalid_and_valid_inventory(tmp_path):
    plan=tmp_path / "plan.json"; raw=tmp_path / "raw"; out=tmp_path / "inventory.json"; csv=tmp_path / "inventory.csv"
    gt.save_plan(plan)
    tile=gt.load_plan(plan)["tiles"][0]
    f=gt._target_path(raw,tile,10)
    r=gt.global_inventory(plan,raw,out,csv)
    assert r["validated_tiles"] == 0 and r["missing_tiles"] == 72 and r["complete"] is False
    make_test_nc(f,tile)
    r=gt.global_inventory(plan,raw,out,csv)
    assert r["invalid_tiles"] == 1
    metadata={"url":gt.build_global_tile_url(tile,10),"sha256":sha256_file(f),"size_bytes":f.stat().st_size}
    f.with_name(f.name+".metadata.json").write_text(json.dumps(metadata))
    r=gt.global_inventory(plan,raw,out,csv)
    assert r["validated_tiles"]==1 and r["missing_tiles"]==71 and r["invalid_tiles"]==0
    assert csv.exists() and len(csv.read_text().splitlines()) == 73


def test_fetch_bounded_and_resume_mocked_network(tmp_path,monkeypatch):
    plan=tmp_path / "plan.json"; raw=tmp_path / "raw"
    gt.save_plan(plan)
    calls=[]
    def fake_fetch(url,destination,dataset_key,max_mb):
        calls.append(destination.name)
        tile_id=destination.name.split("_")[1] + "_" + destination.name.split("_")[2]
        tile=next(t for t in gt.load_plan(plan)["tiles"] if t["id"]==tile_id)
        make_test_nc(destination,tile)
        meta={"url":url,"sha256":sha256_file(destination),"size_bytes":destination.stat().st_size}
        destination.with_name(destination.name+".metadata.json").write_text(json.dumps(meta))
        return {**meta,"cached":False}
    monkeypatch.setattr(gt,"fetch_file",fake_fetch)
    r1=gt.fetch_tiles(plan,raw,limit=2)
    assert len(r1["completed"]) == 2
    r2=gt.fetch_tiles(plan,raw,limit=1)
    assert len(r2["completed"]) == 1
    assert len(set(calls))==3
    assert all(not e["qa"]["topography_similarity_status"] == "computed" for e in r1["completed"])
    with pytest.raises(ValueError):
        gt.fetch_tiles(plan,raw,limit=73)
    with pytest.raises(ValueError):
        gt.fetch_tiles(plan,raw,limit=1,tile_id="../../tmp")
