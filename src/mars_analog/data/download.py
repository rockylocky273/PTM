"""Descarga HTTP por streaming con límite, caché validada y metadatos reproducibles."""

from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
from typing import Optional
import requests


class DownloadError(RuntimeError):
    pass


def sha256_file(path: Path) -> str:
    sha = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1024 * 1024), b""):
            sha.update(block)
    return sha.hexdigest()


def atomic_json(path: Path, obj: dict):
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    try:
        tmp.write_text(json.dumps(obj, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")
        os.replace(tmp, path)
    finally:
        tmp.unlink(missing_ok=True)


def fetch_file(url: str, destination: Path, dataset_key: str,
               max_mb: int = 100, session: Optional[requests.Session] = None) -> dict:
    """Nunca descarga sin un presupuesto; rechaza HTML de error y parciales.

    No realiza reanudación. Si hay una descarga inconclusa, elimina .part y reintenta.
    """
    if not url.startswith("https://"):
        raise ValueError("Solo se admiten URLs https.")
    if max_mb <= 0:
        raise ValueError("max_mb debe ser positivo.")
    destination = Path(destination)
    destination.parent.mkdir(parents=True, exist_ok=True)
    metadata_path = destination.with_name(destination.name + ".metadata.json")
    if destination.is_file() and metadata_path.exists():
        try:
            existing = json.loads(metadata_path.read_text(encoding="utf-8"))
            if existing.get("url") == url and existing.get("sha256") == sha256_file(destination):
                return {**existing, "cached": True}
        except (OSError, ValueError, TypeError):
            pass

    max_bytes = max_mb * 1024 * 1024
    part = destination.with_name(destination.name + ".part")
    client = session if session is not None else requests.Session()
    size = 0
    sha = hashlib.sha256()
    try:
        with client.get(url, stream=True, timeout=(15, 90), allow_redirects=True) as response:
            response.raise_for_status()
            ctype = response.headers.get("Content-Type", "").lower()
            if "text/html" in ctype:
                raise DownloadError("El servidor devolvió HTML en lugar del archivo esperado.")
            reported = response.headers.get("Content-Length")
            if reported is not None and int(reported) > max_bytes:
                raise DownloadError(f"Archivo excede el máximo de {max_mb} MB según Content-Length.")
            with part.open("wb") as out:
                for chunk in response.iter_content(chunk_size=1024 * 1024):
                    if not chunk:
                        continue
                    size += len(chunk)
                    if size > max_bytes:
                        raise DownloadError(f"Descarga excedió el máximo de {max_mb} MB.")
                    out.write(chunk)
                    sha.update(chunk)
            if size == 0 or (reported is not None and size != int(reported)):
                raise DownloadError("Descarga vacía o truncada.")
            record = {
                "dataset": dataset_key,
                "source": "remote_https",
                "url": url,
                "retrieved_at_utc": datetime.now(timezone.utc).isoformat(),
                "size_bytes": size,
                "sha256": sha.hexdigest(),
                "file": str(destination),
                "cached": False,
            }
            os.replace(part, destination)
            atomic_json(metadata_path, record)
            return record
    except requests.RequestException as exc:
        raise DownloadError(f"No se pudo descargar {url}: {exc}") from exc
    finally:
        part.unlink(missing_ok=True)
        if session is None:
            client.close()
