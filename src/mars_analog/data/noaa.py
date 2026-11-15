"""Subconjunto NOAA ERDDAP de ETOPO 2022; coordenadas -180..180 a 0..360."""

from pathlib import Path
from urllib.parse import quote
from .quality import validate_bbox
from .download import fetch_file

ERDDAP_URL = "https://oceanwatch.pifsc.noaa.gov/erddap/griddap/ETOPO_2022_v1_60s.nc"


def build_etopo_url(bbox, stride: int = 1):
    """Solicita z[lat_sur:paso:lat_norte][lon_oeste:paso:lon_este].

    V0.1 solo soporta bbox íntegramente en longitud negativa o positiva,
    para evitar requests de 340° que atraviesen 0°/360° accidentalmente.
    """
    w, s, e, n = validate_bbox(bbox)
    if w < 0 <= e:
        raise ValueError("ETOPO V0.1: dividí un bbox que cruza 0° de longitud en dos solicitudes.")
    if not isinstance(stride, int) or stride < 1 or stride > 60:
        raise ValueError("stride debe ser entero entre 1 y 60.")
    west = w + 360 if w < 0 else w
    east = e + 360 if e < 0 else e
    query = f"z[({s:.6f}):{stride}:({n:.6f})][({west:.6f}):{stride}:({east:.6f})]"
    return ERDDAP_URL + "?" + quote(query, safe="[]():.-")


def download_etopo(bbox, directory: Path, stride: int = 1, max_mb: int = 40):
    w, s, e, n = validate_bbox(bbox)
    pixels_est = ((n-s)*60/stride + 1) * ((e-w)*60/stride + 1)
    # presupuestamos 4 bytes por pixel + coords y overhead conservador.
    if pixels_est * 8 > max_mb * 1024 * 1024:
        raise ValueError("Área/resolución excede el presupuesto; incrementá stride o reducí bbox.")
    coords = "_".join(str(x).replace("-", "m").replace(".", "p") for x in (w,s,e,n))
    filename = f"etopo_surface_{coords}_stride{stride}.nc"
    url = build_etopo_url(bbox, stride)
    result = fetch_file(url, Path(directory) / filename,
                        dataset_key="etopo_surface", max_mb=max_mb)
    result["bbox"] = [w,s,e,n]
    result["stride"] = stride
    result["note"] = "ETOPO 2022 ice surface; precisión espacial 60 arcsec (antes de stride)."
    return result
