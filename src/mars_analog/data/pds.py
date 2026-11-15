"""Importación controlada de datos PDS4 MOLA, global 4 píxeles/grado."""

from pathlib import Path
from .download import fetch_file, atomic_json

MOLA_BASE = "https://pds-geosciences.wustl.edu/mgs/urn-nasa-pds-mgs_mola_topography_derived/meg004/"
MOLA_FILES = ("megt90n000cb.img", "megt90n000cb.xml", "megt90n000cb.hdr")


def download_mola(directory: Path, max_mb: int = 25):
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    records = []
    for name in MOLA_FILES:
        records.append(fetch_file(MOLA_BASE + name, directory / name,
                                  dataset_key="mola_topography", max_mb=max_mb))
    atomic_json(directory / "mola_manifest.json", {
        "body": "Mars",
        "product": "MOLA MEGDR global topography 4 px/degree",
        "files": records,
        "important": "Leer la estructura, el endianness, el escalado y la proyección desde el XML PDS4 antes de procesar IMG.",
    })
    return records
