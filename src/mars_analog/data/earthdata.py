"""Adaptador al catálogo CMR y descargas Earthdata, sin efectos en importación."""

from datetime import datetime, timezone
from pathlib import Path
import json

from .catalog import get_dataset
from .download import atomic_json, sha256_file
from .quality import validate_bbox, validate_time


def _ea():
    try:
        import earthaccess
    except ImportError as exc:
        raise RuntimeError("Instalá dependencias con: python -m pip install -e .") from exc
    return earthaccess


def collection_summary(item) -> dict:
    meta = item.get("meta", {})
    umm = item.get("umm", {})
    return {
        "concept_id": meta.get("concept-id"),
        "revision_id": meta.get("revision-id"),
        "title": umm.get("EntryTitle"),
        "short_name": umm.get("ShortName"),
        "version": umm.get("Version"),
    }


def discover_collections(keys=("modis_lst", "gpm_monthly")) -> dict:
    ea = _ea()
    found = {}
    for key in keys:
        spec = get_dataset(key)
        if spec.access_method != "earthaccess":
            raise ValueError(f"{key} no es una colección Earthdata")
        items = ea.search_datasets(short_name=spec.short_name, count=10)
        found[key] = {
            "requested": spec.to_dict(),
            "collections": [collection_summary(item) for item in items],
        }
    return found


def query_granules(key: str, start: str, end: str, count: int = 2,
                   bbox=None):
    spec = get_dataset(key)
    if spec.access_method != "earthaccess":
        raise ValueError(f"{key} no pertenece a Earthdata")
    validate_time(start, end)
    if count < 1 or count > 5:
        raise ValueError("Para V0.1 count debe estar entre 1 y 5.")
    params = dict(short_name=spec.short_name, version=spec.version,
                  temporal=(start, end), count=count)
    if bbox is not None:
        params["bounding_box"] = validate_bbox(bbox)
    return _ea().search_data(**params)


def granule_summary(item) -> dict:
    meta = item.get("meta", {})
    umm = item.get("umm", {})
    return {
        "concept_id": meta.get("concept-id"),
        "producer_granule_id": umm.get("GranuleUR") or meta.get("native-id"),
        "size_mb": getattr(item, "size", None),
        "links": item.data_links(access="external"),
    }


def download_granules(key: str, start: str, end: str, directory: Path,
                      count: int = 1, bbox=None, max_mb: int = 300,
                      login: bool = True) -> list[dict]:
    """Inspecciona el tamaño estimado ANTES de pedir la descarga.

    Earthaccess administra autenticación y streaming. Mantener el mismo
    directorio evita descargas duplicadas si se reejecuta.
    """
    if max_mb <= 0:
        raise ValueError("max_mb debe ser > 0")
    granules = query_granules(key, start, end, count=count, bbox=bbox)
    if not granules:
        return []
    metadata = [granule_summary(item) for item in granules]
    if any(row["size_mb"] is None for row in metadata):
        raise ValueError("NASA no informó el tamaño de alguna granula; cancelo para evitar descarga inesperada.")
    total_mb = sum(float(row["size_mb"]) for row in metadata)
    if total_mb > max_mb:
        raise ValueError(f"Tamaño estimado {total_mb:.2f} MB > presupuesto {max_mb} MB.")

    ea = _ea()
    if login:
        ea.login()  # .netrc, variables de entorno o login manual, según earthaccess
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    files = ea.download(granules, local_path=str(directory), threads=2, access="https")
    records = []
    for p in files:
        path = Path(p)
        if not path.is_file():
            raise RuntimeError(f"Descarga no verificada: {path}")
        records.append({
            "dataset": key,
            "path": str(path),
            "size_bytes": path.stat().st_size,
            "sha256": sha256_file(path),
            "retrieved_at_utc": datetime.now(timezone.utc).isoformat(),
        })
    atomic_json(directory / "download_manifest.json", {
        "dataset": key, "query": {"start": start, "end": end, "bbox": bbox},
        "granules": metadata, "files": records,
        "estimated_total_mb": total_mb,
    })
    return records
