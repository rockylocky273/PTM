"""V0.5: catálogo GLOBAL de teselas ETOPO 2022, descarga acotada y verificable.

Una tesela es un bbox NOAA (lon 0..360), NO una celda H3, ni una
unidad geomorfológica. El catálogo no calcula similitud con Marte.
"""
from __future__ import annotations

import csv
import json
from pathlib import Path
from urllib.parse import quote

import numpy as np
import xarray as xr

from .download import atomic_json, fetch_file, sha256_file
from .noaa import ERDDAP_URL

DATASET_ID = "ETOPO_2022_v1_60s"
TILE_DEGREES_ALLOWED = (10, 15, 20, 30, 45, 60)


def build_global_tile_url(tile: dict, stride: int) -> str:
    """Genera URLs ERDDAP en 0..360 E y -90..90, sin saltos de meridiano.

    Las cotas (grados enteros) definen aristas; el servidor selecciona centros
    de píxel 60'' cercanos. Las teselas colindantes NO se solapan porque las
    aristas enteras caen a medio píxel de centros ETOPO.
    """
    s, n = tile["south"], tile["north"]
    w, e = tile["west_0_360"], tile["east_0_360"]
    if not (isinstance(stride, int) and 1 <= stride <= 60):
        raise ValueError("stride debe ser entero entre 1 y 60")
    if not (-90 <= s < n <= 90 and 0 <= w < e <= 360):
        raise ValueError("Límites de tesela NOAA no válidos")
    # NOAA ETOPO 60s representa cada píxel por su centro a medio minuto
    # de arco; usar centros reales evita solicitar 90°/360° fuera del dominio.
    half_pixel = 1 / 120
    query = (f"z[({s+half_pixel:.6f}):{stride}:({n-half_pixel:.6f})]"
             f"[({w+half_pixel:.6f}):{stride}:({e-half_pixel:.6f})]")
    return ERDDAP_URL + "?" + quote(query, safe="[]():.-")


def create_plan(tile_deg: int = 30, stride: int = 10) -> dict:
    if tile_deg not in TILE_DEGREES_ALLOWED or 180 % tile_deg or 360 % tile_deg:
        raise ValueError(f"tile_deg debe pertenecer a {TILE_DEGREES_ALLOWED} y dividir 180 y 360")
    if not isinstance(stride, int) or not 1 <= stride <= 60:
        raise ValueError("stride debe ser entero entre 1 y 60")
    tiles = []
    for ri, south in enumerate(range(-90, 90, tile_deg)):
        for ci, west in enumerate(range(0, 360, tile_deg)):
            tile = {
                "id": f"t{ri:02d}_{ci:02d}",
                "south": south, "north": south + tile_deg,
                "west_0_360": west, "east_0_360": west + tile_deg,
            }
            tiles.append(tile)
    return {
        "schema_version": "global_tiles_v0.5",
        "dataset": DATASET_ID,
        "domain": "Earth global latitude [-90,90], NOAA longitude [0,360]",
        "tile_deg": tile_deg,
        "stride": stride,
        "nominal_native_resolution_arcsec": 60,
        "sampling_step_arcsec": 60 * stride,
        "note": "Plan de adquisición; NO es máscara de tierra, grid isométrica, ni ranking de análogos.",
        "number_of_tiles": len(tiles),
        "tiles": tiles,
    }


def validate_plan(plan: dict) -> None:
    """Recalcula determinísticamente el plan; no sigue URLs arbitrarias del JSON."""
    if not isinstance(plan, dict):
        raise ValueError("Plan debe ser objeto JSON")
    expected = create_plan(plan.get("tile_deg"), plan.get("stride"))
    if expected != plan:
        raise ValueError("Plan inconsistente, editado o de versión incompatible; recrealo.")


def load_plan(path: Path) -> dict:
    if not Path(path).is_file():
        raise FileNotFoundError(f"No se encontró el plan: {path}; ejecutá global-plan")
    plan = json.loads(Path(path).read_text(encoding="utf-8"))
    validate_plan(plan)
    return plan


def save_plan(path: Path, tile_deg: int = 30, stride: int = 10) -> dict:
    obj = create_plan(tile_deg, stride)
    atomic_json(path, obj)
    # Aproximación para planear RAM: 1/stride muestras por eje de 60''. 
    side = tile_deg * 60 / stride
    return {
        "status": "planned_only_no_download",
        "plan_file": str(path),
        "tiles": obj["number_of_tiles"],
        "tile_degrees": tile_deg,
        "stride": stride,
        "nominal_step_arcsec": stride * 60,
        "approx_samples_total": int(round(len(obj["tiles"]) * side * side)),
        "approx_raw_elevation_mb": round(len(obj["tiles"]) * side * side * 4 / 1024**2, 2),
        "note": "Tamaño orientativo de la variable z: sin sobrecarga NetCDF, red ni validación de puntos."
    }


def _target_path(directory: Path, tile: dict, stride: int) -> Path:
    return Path(directory) / f"etopo_{tile['id']}_stride{stride}.nc"


def verify_tile_file(path: Path, tile: dict, stride: int) -> dict:
    """QA de contenido sin atribuir al signo de z la condición tierra/océano."""
    with xr.open_dataset(path, decode_cf=True, mask_and_scale=True) as opened:
        for key in ("z", "latitude", "longitude"):
            if key not in opened:
                raise ValueError(f"Archivo ETOPO sin {key}: {path}")
        var = opened["z"]
        if var.dims != ("latitude", "longitude"):
            raise ValueError(f"Dimensiones inesperadas de z en {path}: {var.dims}")
        if str(var.attrs.get("units", "")).lower() not in ("m", "meter", "meters", "metre", "metres"):
            raise ValueError(f"Unidad de z no confirmada en metros: {path}")
        lat = np.asarray(opened.latitude.values, dtype=float)
        lon = np.asarray(opened.longitude.values, dtype=float)
        if lat.size == 0 or lon.size == 0 or not np.all(np.isfinite(lat)) or not np.all(np.isfinite(lon)):
            raise ValueError(f"Coordenadas vacías o no finitas: {path}")
        if not (np.all(np.diff(lat) > 0) and np.all(np.diff(lon) > 0)):
            raise ValueError(f"Coordenadas no monótonas: {path}")
        # Margen de 1 pixel original (60'') para la selección de aristas.
        eps = 1/60 + 1e-4
        if not (lat.min() >= tile["south"]-eps and lat.max() <= tile["north"]+eps and
                lon.min() >= tile["west_0_360"]-eps and lon.max() <= tile["east_0_360"]+eps):
            raise ValueError(f"Coordenadas no coinciden con tesela: {path}")
        # La distancia esperada es stride * resolución angular original.
        step = stride / 60
        expected_lat = (tile["north"] - tile["south"]) / step
        expected_lon = (tile["east_0_360"] - tile["west_0_360"]) / step
        if abs(lat.size - expected_lat) > 2 or abs(lon.size - expected_lon) > 2:
            raise ValueError(f"Tesela incompleta o dimensión incorrecta: {path}")
        if (lat[0] > tile["south"] + step + eps or lat[-1] < tile["north"] - step - eps or
            lon[0] > tile["west_0_360"] + step + eps or lon[-1] < tile["east_0_360"] - step - eps):
            raise ValueError(f"Cobertura interna insuficiente: {path}")
        if lat.size > 1 and not np.allclose(np.diff(lat), step, rtol=1e-3, atol=1e-4):
            raise ValueError(f"Espaciado latitud incorrecto: {path}")
        if lon.size > 1 and not np.allclose(np.diff(lon), step, rtol=1e-3, atol=1e-4):
            raise ValueError(f"Espaciado longitud incorrecto: {path}")
        data = np.asarray(var.values, dtype=float)
        finite = np.isfinite(data)
        if not finite.any():
            raise ValueError(f"Tesela sin valores válidos: {path}")
    good = data[finite]
    return {
        "shape": list(data.shape),
        "valid_elevation_samples": int(finite.sum()),
        "missing_elevation_samples": int(data.size-finite.sum()),
        "elevation_min_m": float(good.min()),
        "elevation_max_m": float(good.max()),
        "elevation_p10_m": float(np.percentile(good, 10)),
        "elevation_p90_m": float(np.percentile(good, 90)),
        "longitude_convention": "0_360",
        "land_mask_status": "not_applied",
        "topography_similarity_status": "not_computed",
    }


def _verify_cached_record(destination: Path, url: str) -> bool:
    meta = destination.with_name(destination.name + ".metadata.json")
    if not destination.is_file() or not meta.is_file():
        return False
    try:
        item = json.loads(meta.read_text(encoding="utf-8"))
        return item.get("url") == url and item.get("sha256") == sha256_file(destination)
    except (OSError, ValueError, TypeError):
        return False


def fetch_tiles(plan_path: Path, directory: Path, limit: int = 1,
                max_mb: int = 5, tile_id: str | None = None) -> dict:
    plan = load_plan(plan_path)
    if not isinstance(limit, int) or not 1 <= limit <= len(plan["tiles"]):
        raise ValueError("limit debe estar entre 1 y el número de teselas")
    if not isinstance(max_mb, int) or not 1 <= max_mb <= 100:
        raise ValueError("max_mb debe ser un entero entre 1 y 100 por tesela")
    tiles = plan["tiles"]
    if tile_id is not None:
        tiles = [tile for tile in tiles if tile["id"] == tile_id]
        if not tiles:
            raise ValueError(f"tile-id desconocido: {tile_id}")
    selected = []
    for tile in tiles:
        url = build_global_tile_url(tile, plan["stride"])
        dest = _target_path(directory,tile,plan["stride"])
        if tile_id is None and _verify_cached_record(dest,url):
            try:
                verify_tile_file(dest,tile,plan["stride"])
            except (OSError, ValueError, RuntimeError) as exc:
                raise ValueError(
                    f"Tesela cacheada corrupta o incompatible ({tile['id']}): {exc}. "
                    "Revisá global-inventory y eliminá manualmente el archivo y su .metadata.json "
                    "solo si querés descargar esa tesela otra vez."
                ) from exc
            continue
        selected.append((tile,url,dest))
        if len(selected) >= limit:
            break
    done=[]
    for tile,url,dest in selected:
        # Descarga atómica y cacheada; el QA se ejecuta incluso si vino del caché.
        rec = fetch_file(url,dest,dataset_key="etopo_global_tile",max_mb=max_mb)
        qa = verify_tile_file(dest,tile,plan["stride"])
        done.append({"tile_id":tile["id"],"file":str(dest),"cached":rec.get("cached",False),
                     "size_bytes":rec["size_bytes"],"sha256":rec["sha256"],"qa":qa})
    return {
        "status":"partial_acquisition_not_global_analysis",
        "plan_file":str(plan_path),
        "fetched_in_this_run":len(done),
        "completed":done,
        "message":"Volvé a ejecutar para obtener teselas siguientes. La integridad y cobertura total se ven con global-inventory."
    }


def global_inventory(plan_path: Path, directory: Path, output_json: Path,
                     output_csv: Path | None = None) -> dict:
    plan = load_plan(plan_path)
    rows=[]
    for tile in plan["tiles"]:
        url=build_global_tile_url(tile,plan["stride"])
        path=_target_path(directory,tile,plan["stride"])
        row={"tile_id":tile["id"],"south":tile["south"],"north":tile["north"],
             "west_0_360":tile["west_0_360"],"east_0_360":tile["east_0_360"],
             "file":str(path),"status":"not_downloaded","sha256":""}
        if path.exists():
            if not _verify_cached_record(path,url):
                row["status"]="invalid_integrity_or_metadata"
            else:
                try:
                    qa=verify_tile_file(path,tile,plan["stride"])
                    row.update(qa)
                    row["status"]="validated"
                    row["sha256"]=sha256_file(path)
                except (OSError,ValueError,RuntimeError) as exc:
                    row["status"]="invalid_netcdf"
                    row["error"]=str(exc)
        rows.append(row)
    good=sum(row["status"]=="validated" for row in rows)
    invalid=sum(row["status"].startswith("invalid") for row in rows)
    report={
        "schema_version":"global_inventory_v0.5",
        "plan_sha256":sha256_file(plan_path),"plan_file":str(plan_path),
        "dataset":DATASET_ID,"total_tiles":len(rows),
        "validated_tiles":good,"missing_tiles":len(rows)-good-invalid,
        "invalid_tiles":invalid,
        "coverage_fraction_tiles":round(good/len(rows),6),
        "complete":good==len(rows),
        "land_mask_status":"not_applied",
        "analogs_ranked":False,
        "warning":"Fracción de teselas no equivale a fracción de superficie terrestre emergida; aún no hay máscara tierra/océano ni score de Marte.",
        "tiles":rows,
    }
    atomic_json(output_json,report)
    if output_csv is not None:
        output_csv=Path(output_csv)
        output_csv.parent.mkdir(parents=True,exist_ok=True)
        fields=["tile_id","status","south","north","west_0_360","east_0_360", "sha256",
                "valid_elevation_samples","missing_elevation_samples","elevation_min_m","elevation_max_m",
                "elevation_p10_m","elevation_p90_m","land_mask_status","file","error"]
        with output_csv.open("w",newline="",encoding="utf-8") as f:
            w=csv.DictWriter(f,fieldnames=fields,extrasaction="ignore")
            w.writeheader(); w.writerows(rows)
    return {k:v for k,v in report.items() if k!="tiles"} | {
        "report_file":str(output_json), "csv_file":str(output_csv) if output_csv else None
    }
