"""Catálogo inicial; los nombres de colecciones deben comprobarse en CMR en ejecución.

NO confundir el listado documental con una verificación de accesibilidad en tiempo real.
"""

from dataclasses import dataclass, asdict
from typing import Optional


@dataclass(frozen=True)
class Dataset:
    key: str
    provider: str
    title: str
    access_method: str
    source: str
    short_name: Optional[str] = None
    version: Optional[str] = None
    units: Optional[str] = None
    resolution: Optional[str] = None
    note: str = ""

    def to_dict(self):
        return asdict(self)


DATASETS = {
    "modis_lst": Dataset(
        key="modis_lst", provider="NASA EOSDIS (LP DAAC)",
        title="MODIS/Terra LST monthly CMG V061",
        access_method="earthaccess", short_name="MOD11C3", version="061",
        source="https://doi.org/10.5067/MODIS/MOD11C3.061",
        units="LST: Kelvin (aplicar factor y QA según SDS)", resolution="0.05 grados",
        note="LST es temperatura de superficie, no del aire; comprobar factores de escala y flags."
    ),
    "gpm_monthly": Dataset(
        key="gpm_monthly", provider="NASA EOSDIS (GES DISC)",
        title="GPM IMERG Final Monthly V07",
        access_method="earthaccess", short_name="GPM_3IMERGM", version="07",
        source="https://doi.org/10.5067/GPM/IMERG/3B-MONTH/07",
        units="precipitación: mm/h (no asumir mm/mes)", resolution="0.1 grados",
        note="La acumulación mensual requiere integrar con la duración del período, usando metadatos."
    ),
    "etopo_surface": Dataset(
        key="etopo_surface", provider="NOAA NCEI / NOAA ERDDAP",
        title="ETOPO 2022, superficie del hielo, 60 arcsec",
        access_method="erddap_subset",
        source="https://oceanwatch.pifsc.noaa.gov/erddap/griddap/ETOPO_2022_v1_60s.html",
        units="metros sobre datum vertical EGM2008", resolution="60 arcsec",
        note="Subconjunto por bounding box. Incluye elevación y batimetría; aplicar máscara terrestre."
    ),
    "mola_topography": Dataset(
        key="mola_topography", provider="NASA PDS Geosciences Node",
        title="Mars Global Surveyor MOLA MEGDR topography 4 px/grado",
        access_method="pds4_file",
        source="https://pds-geosciences.wustl.edu/missions/mgs/megdr.html",
        units="según etiqueta PDS4 (datos codificados)", resolution="4 px/grado",
        note="Producto marciano global de prueba: descargar IMG, XML y HDR sin asumir lectura de IMG como TIFF."
    ),
}


def get_dataset(key: str) -> Dataset:
    try:
        return DATASETS[key]
    except KeyError as exc:
        raise ValueError(f"Dataset no reconocido: {key}. Opciones: {', '.join(DATASETS)}") from exc
