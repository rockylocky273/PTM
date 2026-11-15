"""Validaciones de parámetros geográficos y temporales (sin reproyección)."""

from datetime import date
from math import isfinite


def parse_bbox(raw: str) -> tuple[float, float, float, float]:
    """Devuelve west,south,east,north desde texto 'w,s,e,n'.

    En V0.1 no se aceptan recuadros que crucen el antimeridiano.
    """
    parts = raw.split(",")
    if len(parts) != 4:
        raise ValueError("Usá --bbox=OESTE,SUR,ESTE,NORTE (cuatro valores).")
    try:
        values = tuple(float(v.strip()) for v in parts)
    except ValueError as exc:
        raise ValueError("El bbox debe contener cuatro números.") from exc
    validate_bbox(values)
    return values


def validate_bbox(bbox):
    if len(bbox) != 4:
        raise ValueError("bbox requiere cuatro valores.")
    w, s, e, n = bbox
    if not all(isfinite(x) for x in bbox):
        raise ValueError("Coordenadas no finitas.")
    if not (-180 <= w < e <= 180 and -90 <= s < n <= 90):
        raise ValueError("bbox inválido o cruza antimeridiano (no soportado en V0.1).")
    return (float(w), float(s), float(e), float(n))


def validate_time(start: str, end: str):
    try:
        a, b = date.fromisoformat(start), date.fromisoformat(end)
    except ValueError as exc:
        raise ValueError("Fechas con formato YYYY-MM-DD.") from exc
    if a >= b:
        raise ValueError("La fecha inicial debe ser anterior a la final.")
    return start, end
