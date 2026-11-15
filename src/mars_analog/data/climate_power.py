"""V0.9 NASA POWER monthly point climate context for already-audited candidates.

Intentionally does NOT rerank terrain, compare directly to Martian weather, or
pretend a single coarse-grid point represents an entire 240 km terrain window.
"""
from __future__ import annotations

import calendar
import csv
import hashlib
import json
import math
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import requests

from .download import atomic_json, sha256_file

POWER_URL = "https://power.larc.nasa.gov/api/temporal/monthly/point"
PARAMS = ("T2M", "PRECTOTCORR", "RH2M")
EXPECTED_UNITS = {"T2M": ("C", "degC", "°C"),
                  "PRECTOTCORR": ("mm/day",), "RH2M": ("%",)}
MAX_TOP = 100


def sites_from_audit(path: Path, top: int = 25) -> list[dict]:
    if not 1 <= top <= MAX_TOP:
        raise ValueError("top debe estar entre 1 y 100")
    with Path(path).open(encoding="utf-8") as f:
        audit = json.load(f)
    if audit.get("schema_version") != "mars_analog_ranking_audit_v0.8":
        raise ValueError("Se requiere analog_audit.json de V0.8")
    raw = audit.get("nominal_top_stability")
    if not isinstance(raw, list) or not raw:
        raise ValueError("Auditoría sin candidatos nominales")
    results = []
    for row in raw[:top]:
        ident = row.get("region_id")
        if not isinstance(ident, str) or not ident.startswith("r") or not all(
            c.isalnum() or c == "_" for c in ident
        ):
            raise ValueError("Identificador regional inseguro")
        try:
            lat = float(row["center_lat"])
            lon = float(row["center_lon_180"])
            rank = int(row["rank_original"])
        except (TypeError, ValueError, KeyError) as exc:
            raise ValueError("Coordenadas/rango inválidos en la auditoría") from exc
        if not (math.isfinite(lat) and -90 <= lat <= 90 and math.isfinite(lon) and -180 <= lon <= 180):
            raise ValueError("Coordenadas fuera de rango en auditoría")
        results.append({"region_id": ident, "center_lat": lat,
                        "center_lon_180": lon, "topographic_rank": rank,
                        "top_frequency": row.get("top_frequency")})
    if len({s["region_id"] for s in results}) != len(results):
        raise ValueError("Candidatos duplicados en auditoría")
    return results


def power_request(lat: float, lon: float, start: int, end: int) -> dict:
    if not (2000 <= start <= end <= 2025 and (end - start) <= 25):
        raise ValueError("Rango de años inválido; usar años completos hasta 2025")
    if not (-90 <= lat <= 90 and -180 <= lon <= 180):
        raise ValueError("Coordenadas NASA POWER inválidas")
    return {"parameters": ",".join(PARAMS), "community": "AG",
            "longitude": round(lon, 6), "latitude": round(lat, 6),
            "start": start, "end": end, "format": "JSON"}


def cache_path(base: Path, site: dict, start: int, end: int) -> Path:
    return Path(base) / f"power_{site['region_id']}_{start}_{end}.json"


def _validate_response(payload: dict) -> None:
    params = payload.get("properties", {}).get("parameter", {})
    if not isinstance(params, dict) or any(not isinstance(params.get(k), dict) for k in PARAMS):
        raise ValueError("NASA POWER no devolvió todas las series mensuales requeridas")
    meta = payload.get("parameters", {})
    for key in PARAMS:
        units = meta.get(key, {}).get("units") if isinstance(meta, dict) else None
        if units is not None and units not in EXPECTED_UNITS[key]:
            raise ValueError(f"Unidad no esperada para {key}: {units!r}")


def _read_cache(path: Path, site: dict, start: int, end: int, audit_hash: str):
    if not path.exists():
        return None
    try:
        with path.open(encoding="utf-8") as f:
            obj = json.load(f)
        if (obj.get("schema_version") != "nasa_power_point_v0.9" or
            obj.get("region_id") != site["region_id"] or
            obj.get("center_lat") != site["center_lat"] or
            obj.get("center_lon_180") != site["center_lon_180"] or
            obj.get("audit_sha256") != audit_hash or
            obj.get("start_year") != start or obj.get("end_year") != end):
            raise ValueError("Metadatos de caché incompatibles con auditoría y período")
        _validate_response(obj["response"])
        return obj
    except (OSError, ValueError, KeyError, TypeError) as exc:
        raise ValueError(f"Caché sospechosa en {path}: {exc}") from exc


RETRYABLE_HTTP = frozenset({408, 425, 429, 500, 502, 503, 504})


def _retryable_error(exc: requests.RequestException) -> bool:
    if isinstance(exc, (requests.Timeout, requests.ConnectionError)):
        return True
    if isinstance(exc, requests.HTTPError):
        response = exc.response
        return response is not None and response.status_code in RETRYABLE_HTTP
    return False


def _retry_seconds(exc: requests.RequestException, attempt: int,
                   base_delay: float) -> float:
    # Maximum 30 seconds, including any Retry-After from a 429/503 response.
    delay = min(30.0, base_delay * (2 ** attempt))
    response = getattr(exc, "response", None)
    if response is not None and response.status_code in (429, 503):
        header = response.headers.get("Retry-After")
        if header is not None:
            try:
                seconds = float(header)
                if math.isfinite(seconds) and seconds >= 0:
                    delay = min(30.0, max(delay, seconds))
            except (ValueError, TypeError):
                pass
    return delay


def _download_power_json(site: dict, start: int, end: int, max_kb: int,
                         session=None, connect_timeout: float = 20.0,
                         read_timeout: float = 120.0, retries: int = 2,
                         retry_wait: float = 2.0) -> dict:
    if not (1 <= connect_timeout <= 120 and 1 <= read_timeout <= 600):
        raise ValueError("Timeouts deben estar entre 1 y 120/600 segundos")
    if not (0 <= retries <= 5 and 0 <= retry_wait <= 30):
        raise ValueError("retries debe estar entre 0 y 5; retry-wait entre 0 y 30")
    params = power_request(site["center_lat"], site["center_lon_180"], start, end)
    max_bytes = max_kb * 1024
    client = session if session is not None else requests.Session()
    try:
        for attempt in range(retries + 1):
            raw = bytearray()
            try:
                with client.get(POWER_URL, params=params, stream=True,
                                timeout=(connect_timeout, read_timeout)) as response:
                    response.raise_for_status()
                    length = response.headers.get("Content-Length")
                    if length is not None and int(length) > max_bytes:
                        raise ValueError("Respuesta POWER supera el límite en cabeceras")
                    for chunk in response.iter_content(chunk_size=16384):
                        raw.extend(chunk)
                        if len(raw) > max_bytes:
                            raise ValueError("Respuesta POWER supera el límite de descarga")
                if not raw:
                    raise ValueError("NASA POWER devolvió un cuerpo vacío")
                obj = json.loads(bytes(raw).decode("utf-8"))
                _validate_response(obj)
                return obj
            except requests.RequestException as exc:
                if attempt == retries or not _retryable_error(exc):
                    raise RuntimeError(
                        f"Error al contactar NASA POWER para {site['region_id']} "
                        f"después de {attempt + 1} intento(s): {exc}"
                    ) from exc
                delay = _retry_seconds(exc, attempt, retry_wait)
                print(f"NASA POWER: fallo transitorio para {site['region_id']} "
                      f"(intento {attempt + 1}/{retries + 1}): {exc}. "
                      f"Reintento en {delay:g} s.", file=sys.stderr)
                time.sleep(delay)
            except (json.JSONDecodeError, UnicodeDecodeError) as exc:
                raise ValueError("NASA POWER no devolvió un JSON válido") from exc
    finally:
        if session is None:
            client.close()


def fetch_candidate_climate(audit: Path, dest: Path, start: int = 2015,
                            end: int = 2024, top: int = 25, limit: int = 5,
                            max_kb: int = 1024, session=None,
                            connect_timeout: float = 20.0,
                            read_timeout: float = 120.0,
                            retries: int = 2,
                            retry_wait: float = 2.0) -> dict:
    if not (1 <= limit <= 50 and 64 <= max_kb <= 10240):
        raise ValueError("limit debe estar en [1,50] y max-kb en [64,10240]")
    sites = sites_from_audit(audit, top)
    audit_hash = sha256_file(Path(audit))
    fetched, cached, completed = 0, 0, []
    for site in sites:
        path = cache_path(dest, site, start, end)
        old = _read_cache(path, site, start, end, audit_hash)
        if old is not None:
            cached += 1
            continue
        if fetched >= limit:
            break
        response = _download_power_json(site, start, end, max_kb,
                                        session=session,
                                        connect_timeout=connect_timeout,
                                        read_timeout=read_timeout,
                                        retries=retries,
                                        retry_wait=retry_wait)
        obj = {"schema_version": "nasa_power_point_v0.9", "source": "NASA POWER monthly point",
               "source_url": POWER_URL, "parameters": list(PARAMS),
               "community": "AG", "temporal": "monthly", "region_id": site["region_id"],
               "center_lat": site["center_lat"], "center_lon_180": site["center_lon_180"],
               "topographic_rank": site["topographic_rank"], "start_year": start,
               "end_year": end, "audit_sha256": audit_hash,
               "retrieved_at_utc": datetime.now(timezone.utc).isoformat(),
               "response": response}
        atomic_json(path, obj)
        fetched += 1
        completed.append({"region_id": site["region_id"], "file": str(path),
                          "sha256": sha256_file(path)})
    # Measure all expected cached entries, not only those traversed until limit.
    total_cached = sum(cache_path(dest, s, start, end).is_file() for s in sites)
    return {"status": "environment_data_acquisition_only_no_analog_reranking",
            "source": "NASA POWER (meteorological variables, model-based coarse grid)",
            "audit_sha256": audit_hash, "candidates_requested": len(sites),
            "new_downloads": fetched, "already_cached_before_run": cached,
            "total_cached": total_cached, "pending": len(sites) - total_cached,
            "start_year": start, "end_year": end,
            "downloaded": completed,
            "note": "Series climáticas en un punto central por candidato; no caracterizan toda la ventana topográfica."}


def _safe_month(raw, k: str, low: float, high: float):
    if raw is None:
        return None
    try:
        v = float(raw)
    except (TypeError, ValueError):
        return None
    return v if math.isfinite(v) and v != -999.0 and low <= v <= high else None


def summarize_power(payload: dict, start: int, end: int) -> dict:
    _validate_response(payload)
    ser = payload["properties"]["parameter"]
    expected = [(y, m, f"{y:04d}{m:02d}") for y in range(start, end+1) for m in range(1,13)]
    cleaned = {
        "T2M": {k: _safe_month(ser["T2M"].get(k), k, -120, 80) for _,_,k in expected},
        "PRECTOTCORR": {k: _safe_month(ser["PRECTOTCORR"].get(k), k, 0, 2000) for _,_,k in expected},
        "RH2M": {k: _safe_month(ser["RH2M"].get(k), k, 0, 100) for _,_,k in expected},
    }
    months_all_valid = [k for _,_,k in expected if all(cleaned[p][k] is not None for p in PARAMS)]
    complete_years = []
    annual_precips = []
    weighted_temp = []
    weighted_humidity = []
    for y in range(start, end+1):
        months = [(y,m,f"{y:04d}{m:02d}") for m in range(1,13)]
        if all(k in months_all_valid for _,_,k in months):
            daycounts = [calendar.monthrange(y,m)[1] for _,m,_ in months]
            annual_precips.append(sum(cleaned["PRECTOTCORR"][k]*days for (_,_,k),days in zip(months,daycounts)))
            weighted_temp.append(sum(cleaned["T2M"][k]*days for (_,_,k),days in zip(months,daycounts))/sum(daycounts))
            weighted_humidity.append(sum(cleaned["RH2M"][k]*days for (_,_,k),days in zip(months,daycounts))/sum(daycounts))
            complete_years.append(y)
    if complete_years:
        monthly_climatology = []
        for m in range(1,13):
            vals = [cleaned["T2M"][f"{y:04d}{m:02d}"] for y in complete_years]
            monthly_climatology.append(sum(vals)/len(vals))
        out = {"air_temp_mean_c": round(sum(weighted_temp)/len(weighted_temp),3),
               "precip_annual_mean_mm": round(sum(annual_precips)/len(annual_precips),3),
               "relative_humidity_mean_pct": round(sum(weighted_humidity)/len(weighted_humidity),3),
               "seasonal_air_temp_range_c": round(max(monthly_climatology)-min(monthly_climatology),3)}
    else:
        out = {"air_temp_mean_c": None, "precip_annual_mean_mm": None,
               "relative_humidity_mean_pct": None, "seasonal_air_temp_range_c": None}
    return {"status": "complete" if len(months_all_valid)==len(expected) else "partial",
            "expected_months": len(expected), "complete_months": len(months_all_valid),
            "complete_years": len(complete_years), **out}


def build_environment_report(audit: Path, dest: Path, csv_output: Path,
                             report_output: Path, start: int = 2015,
                             end: int = 2024, top: int = 25) -> dict:
    sites = sites_from_audit(audit, top)
    audit_hash = sha256_file(Path(audit))
    rows = []
    files = []
    for site in sites:
        file = cache_path(dest,site,start,end)
        entry = {**site, "status": "not_downloaded", "expected_months": (end-start+1)*12,
                 "complete_months": 0, "complete_years": 0,
                 "air_temp_mean_c": None, "precip_annual_mean_mm": None,
                 "relative_humidity_mean_pct": None, "seasonal_air_temp_range_c": None}
        obj = _read_cache(file,site,start,end,audit_hash)
        if obj:
            entry.update(summarize_power(obj["response"],start,end))
            files.append({"region_id":site["region_id"],"sha256":sha256_file(file)})
        rows.append(entry)
    csv_output = Path(csv_output)
    csv_output.parent.mkdir(parents=True, exist_ok=True)
    fields = list(rows[0])
    tmp = csv_output.with_name(csv_output.name+".tmp")
    try:
        with tmp.open("w",newline="",encoding="utf-8") as f:
            writer = csv.DictWriter(f,fieldnames=fields)
            writer.writeheader()
            writer.writerows(rows)
        tmp.replace(csv_output)
    finally:
        tmp.unlink(missing_ok=True)
    result = {"schema_version":"mars_analog_environment_context_v0.9",
              "status":"descriptive_climate_only_topography_rank_unchanged",
              "NASA_power_endpoint": POWER_URL,
              "source_description":"NASA POWER monthly meteorological context (MERRA-2 based)",
              "parameters":list(PARAMS),"years":[start,end],
              "audit_sha256":audit_hash,"candidates":len(sites),
              "climate_complete":sum(row["status"]=="complete" for row in rows),
              "climate_partial":sum(row["status"]=="partial" for row in rows),
              "climate_pending":sum(row["status"]=="not_downloaded" for row in rows),
              "source_files":files, "csv_file":str(csv_output),
              "csv_sha256":sha256_file(csv_output),
              "limitations":[
                  "NASA POWER es un servicio climático NASA; no es una medición local ni equivale a MODIS LST",
                  "Un punto central no representa toda la ventana topográfica (aprox. 240 km de lado)",
                  "La precipitación se integra desde la tasa mensual mm/día por días del mes",
                  "No hay clasificación de suelo, litología ni equivalencia térmica Tierra-Marte",
                  "El orden del ranking topográfico V0.7 permanece intacto",
              ]}
    atomic_json(report_output, result)
    result["report_file"] = str(report_output)
    return result
