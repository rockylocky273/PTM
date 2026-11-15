"""V2.0: offline, noncompensatory presentation of *verified* historical evidence.

This module does NOT compute new geological analogues, retune scores or turn
published process analogues into ground-truth labels. It reads existing
scientific outputs, checks provenance and cross-artifact coherence, and
exports a stand-alone HTML dashboard, CSV files and a Markdown report.
"""
from __future__ import annotations

import csv
import html
import json
import re
from collections import Counter
from pathlib import Path

from .download import atomic_json, sha256_file
from .mars_external_validation_v133 import center_of_region
from .mars_v2_atlas import build_topographic_atlas, build_mars_topographic_atlas
from .mars_v2_presentation import render_dashboard

SCHEMA = "mars_analog_integrated_presentation_v2.2"
INPUTS = {
    "domain": "reports/mars_domain_v1_2_2.json",
    "mars_geology": "reports/mars_geology_points_v1_2_2.json",
    "multicriteria": "reports/mars_multicriteria_v1_3_0.json",
    "correspondence": "reports/mars_geology_correspondence_v1_3_1.json",
    "uncertainty": "reports/mars_uncertainty_v1_3_2.json",
    "benchmark": "reports/mars_external_benchmark_v1_3_3.json",
}
EXPECTED_SCHEMAS = {
    "domain": "mars_analog_reference_domain_audit_v1.2.2",
    "mars_geology": "mars_geology_point_summary_v1.2.2",
    "multicriteria": "mars_analog_multicriteria_evidence_v1.3.0",
    "correspondence": "mars_analog_process_correspondence_v1.3.1",
    "uncertainty": "mars_analog_balanced_uncertainty_v1.3.2",
    "benchmark": "mars_analog_external_validation_v1.3.3",
}
REQUIRED_STATUS = {
    "domain": "numeric_reference_coverage_not_validation",
    "mars_geology": "cartographic_point_observations_no_area_fraction_or_mineralogy",
    "multicriteria": "noncompensatory_evidence_triage_no_joint_similarity_score",
    "correspondence": "process_hypotheses_and_contrasts_no_geological_equivalence_score",
    "uncertainty": "matched_observation_sensitivity_no_analog_probability",
    "benchmark": "external_reference_retrieval_audit_not_analog_accuracy",
}
PROFILES = ("elysium_planitia", "jezero_entorno", "gale_entorno", "olympus_mons", "meridiani_planum", "syrtis_major_planum")
LABELS = {
    "elysium_planitia": "Elysium Planitia", "jezero_entorno": "Jezero (entorno)",
    "gale_entorno": "Gale (entorno)", "olympus_mons": "Olympus Mons",
    "meridiani_planum": "Meridiani Planum", "syrtis_major_planum": "Syrtis Major Planum",
}
LIMITS = [
    "Los rankings topográficos no son comprobaciones de analogía geológica.",
    "GLiM y SIM 3292 son productos cartográficos con taxonomías y resoluciones distintas; sus observaciones puntuales no son fracciones de área.",
    "La geología marciana se basa en nueve consultas por perfil, no en cartografía mineralógica local.",
    "Las 25 regiones analizadas para Elysium fueron preseleccionadas; la sensibilidad interna no constituye validación externa independiente.",
    "Los datos NASA POWER son contexto del ambiente terrestre, nunca equivalencia climática marciana.",
    "Los perfiles con características fuera de rango están marcados; una buena posición no elimina la extrapolación.",
    "La auditoría externa contiene nueve referencias y no permite calcular accuracy, AUC o probabilidad de analogía.",
    "Los centros de celdas de 2 grados no son coordenadas de afloramientos, bases, muestras ni ubicaciones operativas.",
    "Ningún resultado certifica seguridad de rover, aterrizaje, instalación o misión.",
]


def _read_report(path: Path, kind: str) -> dict:
    if not path.is_file():
        raise ValueError(f"Falta {kind}: {path}. Recuperá la carpeta data de V1.3.3.")
    try:
        doc = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ValueError(f"No puedo leer {kind}: {path}") from exc
    if not isinstance(doc, dict) or doc.get("schema_version") != EXPECTED_SCHEMAS[kind]:
        raise ValueError(f"Versión/esquema incorrecto para {kind}: {path}")
    if doc.get("status") != REQUIRED_STATUS[kind]:
        raise ValueError(f"Informe incompleto para {kind}: {path}")
    return doc


def _verified_file(path: str | Path, sha: str, desc: str, root: Path):
    if not isinstance(sha, str) or not re.fullmatch(r"[0-9a-f]{64}", sha):
        raise ValueError(f"SHA-256 inválido para {desc}")
    p = Path(path)
    # Use the location recorded by the original project. No rebasing to
    # arbitrary files with the same name, which would weaken provenance.
    if not p.is_absolute():
        p = root / p
    if not p.is_file():
        raise ValueError(f"Falta fuente histórica {desc}: {p}")
    if sha256_file(p) != sha:
        raise ValueError(f"Archivo alterado respecto al SHA-256 original: {desc}: {p}")


def _verify_recorded_sources(root: Path, inputs: dict, docs: dict):
    # All six reports are required; validate report-level CSV/Markdown if hashes
    # were recorded and original upstream files to avoid mixed project copies.
    for kind, doc in docs.items():
        for key, hash_key in (("csv_file", "csv_sha256"),
                              ("markdown_file", "markdown_sha256"),
                              ("anchor_controls_csv", "anchor_controls_csv_sha256")):
            if key in doc and hash_key in doc:
                _verified_file(doc[key], doc[hash_key], f"{kind}.{key}", root)
        for key, record in doc.get("source_files", {}).items():
            if isinstance(record, dict) and "sha256" in record:
                file = record.get("file", record.get("path"))
                if file is not None:
                    _verified_file(file, record["sha256"], f"{kind}.source.{key}", root)
        # V1.3.2 records sources as a mapping of name -> {file,sha256}.
        for key, record in doc.get("sources", {}).items():
            if isinstance(record, dict) and "file" in record and "sha256" in record:
                _verified_file(record["file"], record["sha256"], f"{kind}.sources.{key}", root)
        # V1.3.0 uses a different provenance key; check where present.
        for key, record in doc.get("source_provenance", {}).items():
            if isinstance(record, dict) and "file" in record and "sha256" in record:
                _verified_file(record["file"], record["sha256"], f"{kind}.provenance.{key}", root)
    # Cross-artifact links: ensures two self-consistent historical reports were
    # NOT combined if they were created from different original generations.
    def cross(kind, record, expected):
        if record != sha256_file(inputs[expected]):
            raise ValueError(f"Versiones históricas incompatibles: {kind} no corresponde a {expected}")
    # Benchmark's independently frozen source set is the spine of the report.
    source_benchmark = docs["benchmark"].get("source_files", {})
    if "reference_domain" in source_benchmark:
        cross("benchmark", source_benchmark["reference_domain"]["sha256"], "domain")
    correspondence = docs["correspondence"].get("source_files", {})
    if "v130" in correspondence:
        cross("correspondence", correspondence["v130"]["sha256"], "multicriteria")
    if "domain" in correspondence:
        cross("correspondence", correspondence["domain"]["sha256"], "domain")
    if "mars_geology" in correspondence:
        cross("correspondence", correspondence["mars_geology"]["sha256"], "mars_geology")
    uncertainty = docs["uncertainty"].get("sources", {})
    if "correspondence_v131" in uncertainty:
        cross("uncertainty", uncertainty["correspondence_v131"]["sha256"], "correspondence")


def _rows_by(rows, key):
    idx = {}
    for r in rows:
        if not isinstance(r, dict) or r.get(key) in idx or not isinstance(r.get(key), str):
            raise ValueError(f"Datos duplicados o incorrectos: {key}")
        idx[r[key]] = r
    return idx


def _int(v, label):
    if isinstance(v, bool):
        raise ValueError(f"{label}: debe ser entero")
    try:
        x = int(v)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{label}: entero inválido") from exc
    if x < 0:
        raise ValueError(f"{label}: valor negativo")
    return x


def _validated_summary(docs):
    domain = _rows_by(docs["domain"]["profiles"], "profile")
    geology = _rows_by(docs["mars_geology"]["profiles"], "profile_id")
    if set(domain) != set(PROFILES) or set(geology) != set(PROFILES):
        raise ValueError("Los seis perfiles MOLA no coinciden con los informes geológicos")
    benchmark = docs["benchmark"]
    direct = [x for x in benchmark["results"] if x["role"] == "documented_direct_target_analogue"]
    s = benchmark["summary"]
    if (len(benchmark["results"]) != _int(s["external_cases"], "Casos externos") or
        len(direct) != _int(s["direct_target_process_analogues"], "Casos directos") or
        sum(x.get("topographic_rank") is None for x in direct) != s["direct_sites_missing_from_ranked_population"]):
        raise ValueError("El resumen externo difiere de sus casos")
    if s.get("validated_analogs") != 0 or s.get("accuracy_or_auc") is not None:
        raise ValueError("No se admite afirmar una validación planetaria no demostrada")
    out_profiles = []
    for p in PROFILES:
        d, g = domain[p], geology[p]
        if _int(g.get("sampled", -1), "Puntos marcianos") != 9 or g.get("status") != "complete":
            raise ValueError("No hay nueve muestras geológicas completas para " + p)
        try:
            units = json.loads(g["unit_code_counts"])
        except (ValueError, TypeError) as exc:
            raise ValueError("Recuentos de geología marciana inválidos: " + p) from exc
        if not isinstance(units, dict) or sum(_int(v, "Conteo unidad") for v in units.values()) != 9:
            raise ValueError("Recuentos marcianos no suman nueve para " + p)
        out_profiles.append({"id": p, "name": LABELS[p],
                             "mapped_points": 9, "units": units,
                             "outside_catalog_minmax": _int(d["outside_catalog_minmax"], "Dominio"),
                             "extreme_tail_features": _int(d["extreme_one_sided_features_95pct"], "Cola"),
                             "domain_flag": d["domain_flag"]})
    correspondence = docs["correspondence"]["rows"]
    if len(correspondence) != docs["correspondence"]["pairs"]:
        raise ValueError("Recuento de correspondencias no coincide")
    corr_index = {(r["mars_profile"], r["earth_region_id"]): r for r in correspondence}
    if len(corr_index) != len(correspondence):
        raise ValueError("Correspondencias duplicadas")
    unc = docs["uncertainty"]
    if unc.get("profile") != "elysium_planitia":
        raise ValueError("La comparación equilibrada debe corresponder a Elysium")
    cases = unc["candidates"]
    if len(cases) != 3 or len({r["earth_region_id"] for r in cases}) != 3:
        raise ValueError("Se esperan tres candidatos volcánicos Elysium únicos")
    candidates = []
    for c in cases:
        rid = c["earth_region_id"]
        relation = corr_index.get(("elysium_planitia", rid))
        if relation is None or relation.get("topographic_rank") != c["topographic_rank_original"]:
            raise ValueError("Puesto o correspondencia incorrecta para " + rid)
        if relation.get("analog_validated") is not False or c.get("analog_validated") is not False:
            raise ValueError("No se admite declarar analogía validada")
        lat, lon = center_of_region(rid)
        obs = c["volcanic_point_diagnostics"]
        if _int(obs["classified"], "Puntos GLiM") != 9:
            raise ValueError("Los tres sitios deben tener nueve puntos GLiM")
        candidates.append({"id": rid, "lat": lat, "lon": lon,
                           "rank": c["topographic_rank_original"],
                           "scale_ranks": c["scale_ranks"],
                           "method_ranks": c["method_ranks"],
                           "weight_summary": c["weight_perturbation_ranks"],
                           "top_k_membership": c["top_k_membership"],
                           "volcanic_samples": obs["volcanic_observed"],
                           "glim_samples": obs["classified"],
                           "leave_one_out": f"{obs['leave_one_out_signal_preserved']}/{obs['leave_one_out_trials']}",
                           "lithology_counts": c["lithology_counts"],
                           "process_relation": relation["broad_process_relation"],
                           "geology_strength": relation["inference_strength"],
                           "validation": "not_validated"})
    candidates.sort(key=lambda c: (c["rank"], c["id"]))
    # NASA POWER is attached to the V1.3.0 evidence ledger, only for the
    # previously investigated regions. No interpolation for unmeasured sites.
    climate_rows = []
    for rec in docs["multicriteria"].get("candidates", []):
        if rec.get("mars_profile") != "elysium_planitia" or rec.get("climate_status") != "complete":
            continue
        vals = rec.get("earth_nasa_power_climate")
        if isinstance(vals, dict):
            climate_rows.append({"earth_region_id":rec["earth_region_id"],
                                 "air_temp_mean_c": vals.get("air_temp_mean_c"),
                                 "precip_annual_mean_mm":vals.get("precip_annual_mean_mm"),
                                 "relative_humidity_mean_pct":vals.get("relative_humidity_mean_pct"),
                                 "seasonal_air_temp_range_c":vals.get("seasonal_air_temp_range_c")})
    anchors = [r for r in correspondence if r["mars_profile"] == "elysium_planitia"]
    anchors.sort(key=lambda r: (r.get("topographic_rank") is None,
                                r.get("topographic_rank") or 10**9))
    return {"profiles": out_profiles, "candidates": candidates,
            "elysium_anchors": anchors,
            "benchmark_cases": benchmark["results"],
            "benchmark_summary": s,
            "correspondence_pairs": len(correspondence),
            "anchor_regions": docs["correspondence"]["glim_sampled_regions"],
            "climate_earth_context": climate_rows,
            "climate_context": "earth_conditions_only_not_martian_similarity"}


def _csv(path: Path, fields: list[str], rows: list[dict]):
    with path.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        for r in rows:
            writer.writerow({k: json.dumps(r[k], ensure_ascii=False, sort_keys=True)
                             if isinstance(r.get(k), (dict, list)) else r.get(k) for k in fields})


def _md_table(rows, fields, titles=None):
    titles = titles or fields
    out = ["| " + " | ".join(titles) + " |", "|" + "|".join("---" for _ in fields) + "|"]
    for r in rows:
        out.append("| " + " | ".join(str(r.get(k, "—")).replace("|", "/").replace("\n", " ") for k in fields) + " |")
    return out


def _write_markdown(path: Path, summary: dict, hashes: dict):
    p, c, b = summary["profiles"], summary["candidates"], summary["benchmark_cases"]
    rows_c = [dict(region=c0["id"], rank=c0["rank"], r15=c0["scale_ranks"].get("15km_17x17"),
                   r30=c0["scale_ranks"].get("30km_9x9"),r40=c0["scale_ranks"].get("40km_7x7"),
                   glim=f"{c0['volcanic_samples']}/{c0['glim_samples']}", loo=c0["leave_one_out"])
              for c0 in c]
    rows_p = [dict(profile=x["name"],domain=x["domain_flag"],outside=x["outside_catalog_minmax"],
                   geology=", ".join(f"{code} ({n})" for code,n in x["units"].items())) for x in p]
    atlas_rows = [dict(id=e["id"],name=e["label"],lat=e["center_lat"],lon=e["center_lon"],
                       rank=e["topographic_rank"],glim=e["volcanic_points"],
                       map_status=summary["topographic_atlas"]["maps"][e["id"]]["status"])
                  for e in summary["topographic_atlas"]["entries"]]
    rows_b = [dict(site=x["site_name"],profile=x.get("mars_profile") or "—",
                   rank=x.get("topographic_rank") if x.get("topographic_rank") is not None else "No clasificó",
                   status=x["evaluation_status"]) for x in b]
    lines = ["# Mars Analog Discovery Engine — V2.0", "",
             "**Informe integrado de exploración planetaria, con resultados verificables y límites documentados.**", "",
             "## Hallazgo principal", "",
             "Argentina (r026_c146, centro aproximado 37° S / 67° O) es el candidato más estable de los tres investigados para Elysium: puestos 2, 6 y 16 a 15/30/40 km y dos observaciones GLiM de volcanismo básico entre nueve. El mapa interactivo permite ver la ubicación y los sectores p04/p08. No se ha demostrado equivalencia de procesos ni mineralogía.", "",
             "## Comparación equilibrada de candidatos Elysium", "",
             *_md_table(rows_c, ["region","rank","r15","r30","r40","glim","loo"],
                        ["Región 2°","Puesto 30 km","15 km","30 km","40 km","Volcánicas GLiM","Retirada 1 punto"]),
             "", "## Ubicaciones y atlas topográfico interactivo", "",
             "Las coordenadas corresponden a centros de celdas de 2°; los nombres de país describen únicamente el centro de cada celda. Los mapas regionales son ETOPO y los sitios p04/p08 usan NASADEM cuando está disponible.", "",
             *_md_table(atlas_rows,["name","lat","lon","rank","glim","map_status"],
                        ["Región terrestre","Latitud","Longitud","Puesto","Muestras volcánicas","Mapa"]),
             "", "## Topografía de las seis regiones de Marte", "",
             "Los seis mapas se derivan del mosaico MOLA de Marte, si está presente. Sus longitudes son planetocéntricas Este 0–360° y las elevaciones corresponden al datum marciano, no al nivel del mar terrestre.", "",
             *_md_table([dict(region=x['name'], map_status=summary['mars_topographic_atlas']['maps'][x['id']]['status'],
                             source='MOLA MEGDR') for x in p],['region','map_status','source'],
                        ['Región marciana','Mapa','Fuente']),
             "", "## Dos sectores argentinos con NASADEM", "",
             "- p04: lat. -37.00000, lon. -67.67564; pendiente mediana 1,858°; área GLiM recortada ~1.675,65 km².",
             "- p08: lat. -37.53959, lon. -67.67564; pendiente mediana 1,4907°; área GLiM recortada ~798,53 km².",
             "", "## Seis perfiles marcianos", "",
             *_md_table(rows_p,["profile","outside","geology"],["Perfil","Características fuera de rango","Unidades cartográficas en 9 puntos"]),
             "", "## Auditoría externa", "",
             *_md_table(rows_b,["site","profile","rank","status"],
                        ["Referencia terrestre","Perfil","Puesto","Diagnóstico"]),
             "", "## Interpretación", "",
             f"{summary['benchmark_summary']['direct_sites_missing_from_ranked_population']} de {summary['benchmark_summary']['direct_target_process_analogues']} referencias directas no pertenecen a la población clasificada. No puede calcularse exactitud del motor.",
             "", "## Limitaciones obligatorias", "", *["- " + x for x in LIMITS],
             "", "## Evidencias de origen SHA-256", "", *["- `" + k + "`: `" + v + "`" for k,v in hashes.items()], ""]
    path.write_text("\n".join(lines), encoding="utf-8")


def _h(value):
    return html.escape(str(value), quote=True)


def _dashboard_html(summary: dict) -> str:
    # Only data records are embedded; all user-provided labels go through JS
    # textContent or escaping, never executable HTML or script interpolation.
    payload = json.dumps(summary, ensure_ascii=False, sort_keys=True).replace("<", "\\u003c").replace(">", "\\u003e").replace("&", "\\u0026")
    css = r"""
:root{color-scheme:light;--ink:#1a2c38;--muted:#566975;--sea:#086e77;--aqua:#ccecea;--bg:#f3f7f8;--line:#dce6e9;--panel:#fff;--amber:#a65a12}
*{box-sizing:border-box}html{scroll-behavior:smooth}body{font:15px/1.52 'Segoe UI',Arial,sans-serif;background:var(--bg);color:var(--ink);margin:0}
.hero{background:linear-gradient(115deg,#102733,#15505b 68%,#176c69);color:#fff;padding:34px max(24px,calc((100vw - 1120px)/2)) 38px}
.eyebrow{font-size:12px;text-transform:uppercase;letter-spacing:.15em;color:#9de0db;font-weight:700}h1{font-size:clamp(30px,4vw,47px);line-height:1.1;letter-spacing:-.035em;margin:10px 0 12px}h2{font-size:24px;letter-spacing:-.02em;margin:0 0 12px}h3{font-size:16px;margin:0 0 10px}.hero p{max-width:790px;color:#dfedf0;margin:0}
.wrap{max-width:1168px;padding:24px;margin:auto}.stats{display:grid;grid-template-columns:repeat(4,1fr);gap:12px;margin-top:-44px;position:relative}.stat,.panel{background:var(--panel);border:1px solid var(--line);box-shadow:0 5px 18px #10303b0d;border-radius:16px}.stat{padding:18px}.stat strong{font-size:29px;display:block;color:#074e5c;font-weight:750;letter-spacing:-.04em}.stat span{color:var(--muted);font-size:12px}
.tabs{display:flex;flex-wrap:wrap;gap:7px;margin:26px 0 17px}.tabs button{border:1px solid #cee1e5;border-radius:30px;padding:9px 16px;font:600 14px 'Segoe UI',Arial,sans-serif;background:#fff;cursor:pointer;color:#294a57}.tabs button[aria-selected=true]{background:#0b6170;color:#fff;border-color:#0b6170}.tabs button:focus-visible{outline:3px solid #55bbb5}.view[hidden]{display:none}.panel{padding:22px;margin-bottom:16px}.lead{color:var(--muted);max-width:900px;margin:0 0 16px}.cols{display:grid;grid-template-columns:1.15fr 1fr;gap:16px}.scroll{overflow-x:auto}table{width:100%;border-collapse:collapse;min-width:630px}th,td{padding:10px 12px;text-align:left;border-bottom:1px solid #e8eef0}th{background:#f5f9f9;color:#516b76;font-size:12px;text-transform:uppercase;letter-spacing:.045em}td{font-size:13px}tbody tr:hover{background:#f8fbfb}code{background:#eff6f5;color:#075c62;padding:3px 6px;border-radius:5px}.small{font-size:12px;color:var(--muted)}.pill{display:inline-block;border-radius:12px;padding:3px 9px;background:#e8f0f2;color:#315662;font-size:12px}.pill.warn{background:#fff1dc;color:#804617}.pill.ok{background:#e1f3ec;color:#23654b}
.metric{display:grid;grid-template-columns:125px 1fr 33px;align-items:center;gap:8px;margin:11px 0;font-size:13px}.track{height:10px;background:#e9eff1;border-radius:12px;overflow:hidden}.fill{height:100%;border-radius:12px;background:linear-gradient(90deg,#0b8290,#57bcb2)}.rangewrap{position:relative}.sect{margin:18px 0}.gridlegend{color:#607887;font-size:12px}.geoplot{width:100%;max-height:320px;aspect-ratio:720/300;display:block;background:#f8fbfb;border-radius:8px;border:1px solid #e1ebee}
section .note{border-left:3px solid #b5d4d7;padding:9px 13px;background:#f5fafb;border-radius:0 10px 10px 0;color:#3d5965}.note.warning{border-left-color:#dc9c4e;background:#fff9ed}.source{word-break:break-word}.source a{color:#08737b}.kicker{font-size:11px;font-weight:750;color:#437783;text-transform:uppercase;letter-spacing:.1em}.spot{padding:13px 15px;border:1px solid #deeaeb;border-radius:12px;margin:8px 0}.spot strong{display:block;margin:0 0 4px}.spot .small{line-height:1.5}.barline{display:grid;grid-template-columns:140px 1fr 45px;gap:11px;align-items:center;margin:10px 0}.hint{font-size:12px;color:#667f86}.caption{font-size:12px;color:#536d78;margin:8px 0 0}footer{padding:24px 0 10px;color:var(--muted);font-size:12px}
@media(max-width:740px){.stats{grid-template-columns:repeat(2,1fr)}.cols{grid-template-columns:1fr}.panel{padding:16px}.wrap{padding:14px}.hero{padding:30px 20px 68px}}
"""
    javascript = r"""
'use strict';
const DATA=JSON.parse(document.getElementById('dataset').textContent);
const $=s=>document.querySelector(s);const esc=x=>String(x??'—');
const make=(tag,txt,cls)=>{const el=document.createElement(tag);if(txt!==undefined)el.textContent=esc(txt);if(cls)el.className=cls;return el};
const cell=(tr,x)=>tr.appendChild(make('td',x));
const table=(id,rows,fn)=>{const tbody=document.querySelector('#'+id+' tbody');tbody.replaceChildren();rows.forEach(r=>{const tr=document.createElement('tr');fn(tr,r);tbody.appendChild(tr)})};
for(const btn of document.querySelectorAll('.tabs button')){btn.addEventListener('click',()=>{for(const t of document.querySelectorAll('.tabs button')){t.setAttribute('aria-selected',t===btn?'true':'false')}for(const v of document.querySelectorAll('.view'))v.hidden=v.id!=='view-'+btn.dataset.view;});}
const scaleCols=[['15km_17x17','15 km'],['30km_9x9','30 km'],['40km_7x7','40 km']];
const fmtRank=n=>n===null||n===undefined?'—':'#'+n;
const candidateNames={'r026_c146':'Argentina · volcánica básica','r069_c067':'Candidato piroclástico','r067_c038':'Candidato volcánico intermedio'};
table('candidates',DATA.candidates,(tr,r)=>{cell(tr,candidateNames[r.id]||r.id);cell(tr,r.id);cell(tr,fmtRank(r.rank));scaleCols.forEach(([k])=>cell(tr,fmtRank(r.scale_ranks[k])));cell(tr,r.volcanic_samples+'/'+r.glim_samples);cell(tr,r.leave_one_out)});
const ranks=$('#rank-chart');DATA.candidates.forEach(r=>{const container=make('div',null,'spot');container.appendChild(make('strong',candidateNames[r.id]||r.id));scaleCols.forEach(([k,n])=>{let v=r.scale_ranks[k];let line=make('div',null,'barline');line.appendChild(make('span',n));let track=make('div',null,'track');let fill=make('div',null,'fill');fill.style.width=(v?Math.max(2,100*(51-Math.min(v,50))/50):0)+'%';track.appendChild(fill);line.appendChild(track);line.appendChild(make('b',fmtRank(v)));container.appendChild(line)});ranks.appendChild(container)});
table('profiles',DATA.profiles,(tr,r)=>{cell(tr,r.name);cell(tr,r.outside_catalog_minmax+'/5');cell(tr,`${r.extreme_tail_features}/5`);cell(tr,Object.entries(r.units).map(([k,v])=>k+' ('+v+')').join(', '));cell(tr,r.domain_flag)});
const select=$('#profile-filter');for(let p of DATA.profiles){let o=make('option',p.name);o.value=p.id;select.appendChild(o)};
function fillAnchors(){const p=select.value;const rows=DATA.correspondence_rows.filter(r=>r.mars_profile===p).sort((a,b)=>(a.topographic_rank??1e8)-(b.topographic_rank??1e8));table('anchors',rows,(tr,r)=>{cell(tr,r.earth_region_id);cell(tr,fmtRank(r.topographic_rank));cell(tr,r.broad_process_relation);cell(tr,r.research_triage)})} select.addEventListener('change',fillAnchors);fillAnchors();
table('bench',DATA.benchmark_cases,(tr,r)=>{cell(tr,r.site_name);cell(tr,r.mars_profile||'No aplica');cell(tr,fmtRank(r.topographic_rank));cell(tr,r.evaluation_status)});
table('climate',DATA.climate_earth_context,(tr,r)=>{cell(tr,r.earth_region_id);cell(tr,r.air_temp_mean_c);cell(tr,r.precip_annual_mean_mm);cell(tr,r.relative_humidity_mean_pct);cell(tr,r.seasonal_air_temp_range_c)});
const grid=$('#geo-grid');const NS='http://www.w3.org/2000/svg';const addSvg=(tag,attrs,txt)=>{const e=document.createElementNS(NS,tag);for(const[k,v]of Object.entries(attrs))e.setAttribute(k,v);if(txt!==undefined)e.textContent=txt;grid.appendChild(e);return e;};
const xy=(lon,lat)=>[28+(lon+180)*1.83,25+(90-lat)*1.37];
for(let lon=-180;lon<=180;lon+=60){let [x]=xy(lon,0);addSvg('line',{x1:x,y1:15,x2:x,y2:275,stroke:'#d6e4e7','stroke-width':1});addSvg('text',{x:x+2,y:291,fill:'#66818a','font-size':'11'},lon+'°')}
for(let lat=-60;lat<=60;lat+=30){let [,y]=xy(0,lat);addSvg('line',{x1:24,y1:y,x2:705,y2:y,stroke:'#d6e4e7','stroke-width':1});addSvg('text',{x:2,y:y+4,fill:'#66818a','font-size':'11'},lat+'°')}
DATA.candidates.forEach((r,i)=>{let [x,y]=xy(r.lon,r.lat);addSvg('circle',{cx:x,cy:y,r:7,fill:['#087982','#e09a42','#536b9a'][i],stroke:'#fff','stroke-width':'2'});addSvg('text',{x:x+11,y:y-7,fill:'#234655','font-size':'11','font-weight':'700'},r.id)});
$('#bench-summary').textContent=`${DATA.benchmark_summary.direct_sites_missing_from_ranked_population} de ${DATA.benchmark_summary.direct_target_process_analogues} referencias directas no entraron en el catálogo clasificado; análogos validados por el motor: 0.`;
const sources=$('#source-hashes');for(const[k,v]of Object.entries(DATA.input_hashes)){const el=make('div',null,'spot');el.appendChild(make('strong',k));el.appendChild(make('code',v));sources.appendChild(el)};
"""
    markup = """<!DOCTYPE html><html lang="es"><head><meta charset="utf-8"/><meta name="viewport" content="width=device-width, initial-scale=1"/><title>Mars Analog Discovery Engine V2.0 — Panel científico</title><style>"""+css+"""</style></head><body><header class="hero"><div class="eyebrow">Mars Analog Discovery Engine / 2.0</div><h1>De Marte a la Tierra.<br>Con evidencia, no suposiciones.</h1><p>Motor de análisis de topografía, unidades geológicas, incertidumbre y referencias externas. Resultados reproducibles de seis perfiles marcianos y regiones terrestres, sin puntuación planetaria inventada.</p></header><main class="wrap"><div class="stats"><div class="stat"><strong>6</strong><span>Perfiles MOLA</span></div><div class="stat"><strong>"""+str(summary["anchor_regions"])+"""</strong><span>Regiones terrestres con GLiM</span></div><div class="stat"><strong>"""+str(summary["correspondence_pairs"])+"""</strong><span>Correspondencias analizadas</span></div><div class="stat"><strong>9</strong><span>Referencias científicas externas</span></div></div>
<nav class="tabs" aria-label="Secciones del informe"><button data-view="candidates" aria-selected="true">Candidatos</button><button data-view="mars" aria-selected="false">Seis perfiles</button><button data-view="reference" aria-selected="false">Validación externa</button><button data-view="method" aria-selected="false">Método y fuentes</button></nav>
<section class="view" id="view-candidates"><div class="panel"><div class="kicker">Hallazgo principal</div><h2>Elysium Planitia: tres hipótesis volcánicas</h2><p class="lead">Argentina muestra la mayor estabilidad topográfica de los tres candidatos examinados a varias escalas, pero <b>ninguno es un análogo geológico validado</b>. La presencia de unidades volcánicas GLiM permite plantear hipótesis, no demostrar igualdad de materiales ni de procesos eruptivos.</p><div class="scroll"><table id="candidates"><thead><tr><th>Candidato</th><th>Celda</th><th>Base</th><th>15 km</th><th>30 km</th><th>40 km</th><th>GLiM</th><th>Retirada</th></tr></thead><tbody></tbody></table></div><p class="caption">Puestos: número menor = mayor similitud topográfica en ese experimento. GLiM: número de observaciones volcánicas entre nueve muestras; NO porcentaje de área.</p></div><div class="cols"><div class="panel"><h3>Estabilidad por escala</h3><p class="small">La barra larga indica mejor posición relativa hasta el puesto 50; no representa una probabilidad ni calidad geológica.</p><div id="rank-chart"></div></div><div class="panel"><h3>Grilla terrestre de referencia</h3><p class="small">Centros de celdas de 2°. Es un gráfico de coordenadas, no un mapa de accesibilidad ni una localización exacta de afloramientos.</p><svg id="geo-grid" class="geoplot" role="img" aria-label="Coordenadas aproximadas de los tres candidatos terrestres" viewBox="0 0 720 305"></svg><p class="caption">Proyección equirectangular; sin capa topográfica de fondo. La celda de Argentina se centra en 37° S, 67° O.</p></div></div><div class="panel"><h3>Condiciones ambientales terrestres — NASA POWER</h3><p class="small">Solo las regiones previamente estudiadas con datos climáticos completos. No se compara este clima con Marte ni se rellenan regiones faltantes.</p><div class="scroll"><table id="climate"><thead><tr><th>Región</th><th>Temp. media (°C)</th><th>Precipitación anual (mm)</th><th>Humedad relativa (%)</th><th>Amplitud estacional (°C)</th></tr></thead><tbody></tbody></table></div></div></section>
<section class="view" id="view-mars" hidden><div class="panel"><h2>Perfiles marcianos y límites de dominio</h2><p class="lead">Cada perfil tiene nueve puntos cartográficos SIM 3292. Que un parámetro esté en el rango terrestre no confirma correspondencia geológica.</p><div class="scroll"><table id="profiles"><thead><tr><th>Perfil</th><th>Fuera de rango</th><th>Cola extrema</th><th>Unidades en 9 muestras</th><th>Diagnóstico</th></tr></thead><tbody></tbody></table></div></div><div class="panel"><h3>Comparación de observaciones GLiM disponibles</h3><p class="small">El filtro muestra las regiones terrestres con muestreo existente para cada perfil; puede haber regiones con muy buen puesto topográfico sin evidencia geológica comparable.</p><label for="profile-filter">Perfil: </label><select id="profile-filter" style="padding:8px;border:1px solid #cee1e5;border-radius:8px;margin:8px"></select><div class="scroll"><table id="anchors"><thead><tr><th>Celda terrestre</th><th>Puesto</th><th>Interpretación del proceso</th><th>Próxima acción</th></tr></thead><tbody></tbody></table></div></div></section>
<section class="view" id="view-reference" hidden><div class="panel"><h2>Auditoría externa: resultado inconcluso</h2><p class="lead" id="bench-summary"></p><p class="note warning">Una analogía publicada se refiere a un proceso y una escala concretos. Si un sitio no figura en nuestro catálogo de 240 km, <b>no significa que la analogía científica haya sido refutada</b>.</p><div class="scroll"><table id="bench"><thead><tr><th>Referencia</th><th>Perfil</th><th>Puesto</th><th>Diagnóstico</th></tr></thead><tbody></tbody></table></div><p class="caption">No se calcula accuracy, AUC, tasa de éxito ni porcentaje de parecido. Los controles de alcance no se usan como negativos geológicos ficticios.</p></div></section>
<section class="view" id="view-method" hidden><div class="panel"><h2>Qué demuestra el motor y qué no</h2><p class="lead">Trazabilidad e integración de hallazgos observados, sin fusionar indebidamente topografía, geología y clima.</p><ol><li><b>Topografía:</b> MOLA y ETOPO, perfiles de 240 km y rankings por características del relieve.</li><li><b>Geología:</b> SIM 3292 (Marte), GLiM (Tierra) y categorías de proceso únicamente a nivel de hipótesis.</li><li><b>Robustez:</b> escalas de 15, 30 y 40 km, tres funciones de distancia y 60 escenarios de pesos.</li><li><b>Ambiente:</b> NASA POWER exclusivamente como condiciones terrestres históricas para trabajo de campo.</li><li><b>Controles:</b> diagnóstico de dominio y referencias externas independientes, sin calibración oportunista.</li></ol><div class="note warning">Los resultados NO certifican terreno apto para rovers, bases, aterrizajes ni equivalencia mineralógica o climática.</div></div><div class="panel"><h3>Limitaciones documentadas</h3><ul>"""+"".join("<li>"+_h(x)+"</li>" for x in LIMITS)+"""</ul></div><div class="panel"><h3>Huella SHA-256 de los informes originales</h3><p class="small">Se comprueban los hashes originales disponibles y su coherencia entre versiones. Los archivos de origen permanecen intactos.</p><div id="source-hashes" class="source"></div></div></section>
<footer>Generado localmente por Mars Analog Engine V2.0 · Panel estático sin dependencias web · Clasificación científica: exploratoria</footer></main><script type="application/json" id="dataset">"""+payload+"""</script><script>"""+javascript+"""</script></body></html>"""
    return markup


def build_v2(data_root: Path = Path("data"), output_dir: Path = Path("data/reports/mars_v2_0"),
             *, fetch_climate:bool=False, fetch_lunar:bool=False,
             climate_download_limit:int=25, mars_context_km:float=1600.0,
             full_sensitivity_report:Path|None=None) -> dict:
    data_root = Path(data_root)
    output_dir = Path(output_dir)
    root = data_root.resolve().parent
    inputs = {name: data_root / name_rel for name, name_rel in INPUTS.items()}
    docs = {k: _read_report(v, k) for k,v in inputs.items()}
    _verify_recorded_sources(root, inputs, docs)
    summary = _validated_summary(docs)
    hashes = {k: sha256_file(p) for k,p in inputs.items()}
    output_dir.mkdir(parents=True, exist_ok=True)
    summary["input_hashes"] = hashes
    summary["topographic_atlas"] = build_topographic_atlas(data_root, summary)
    # Climate is a separate terrestrial fieldwork context, not Martian similarity.
    by_climate = {r['earth_region_id']:r for r in summary['climate_earth_context']}
    for entry in summary['topographic_atlas']['entries']:
        entry['climate_earth_context']=by_climate.get(entry['id'])
    full_sensitivity_doc=None
    if full_sensitivity_report is not None:
        from .mars_sensitivity_v204 import review_all_sensitivity, SCHEMA as S204
        verified=review_all_sensitivity(Path(full_sensitivity_report))
        full_sensitivity_doc=json.loads(Path(full_sensitivity_report).read_text(encoding='utf-8'))
        if verified['count'] != len(summary['topographic_atlas']['entries']):
            raise ValueError('Auditoría V2.0.4 no cubre todas las regiones del atlas')
        # Source report and historical three-way must match the SAME V1.3.3 installation.
        for key,expect in [('correspondence_v131','correspondence'),('historical_three_way_v132','uncertainty')]:
            if full_sensitivity_doc['source_files'][key]['sha256'] != hashes[expect]:
                raise ValueError('V2.0.4 mezcla versiones de datos históricos: '+key)
        by_id={r['earth_region_id']:r for r in verified['rows']}
        if set(by_id)!={e['id'] for e in summary['topographic_atlas']['entries']}:
            raise ValueError('Regiones de auditoría V2.0.4 distintas del atlas')
        for e in summary['topographic_atlas']['entries']:
            r=by_id[e['id']]
            if r['topographic_rank_original'] != e['topographic_rank']:
                raise ValueError('Ranking original de auditoría V2.0.4 distinto: '+e['id'])
            e['method_ranks']={'original':r['topographic_rank_original'],
                               'robust_log_l2':r['rank_log_l2'],
                               'empirical_percentile_l1':r['rank_percentile_l1']}
            e['scale_ranks']={'15km_17x17':r['rank_15km'],
                              '30km_9x9':r['rank_30km'],
                              '40km_7x7':r['rank_40km']}
            e['weight_top25_of_60']=r['weight_top25_of_60']
            e['weight_top10_of_60']=r['weight_top10_of_60']
            e['weight_rank_median']=r['weight_rank_median']
            e['glim_leave_one_out_preserved']=r['glim_leave_one_out_preserved']
            e['sensitivity_full_v204']=True
        summary['full_sensitivity_v204']={
            'coverage':verified['count'],'counts':full_sensitivity_doc['counts'],
            'report_sha256':sha256_file(Path(full_sensitivity_report)),
            'profile':'elysium_planitia','weight_scenarios':60,
        }
    else:
        summary['full_sensitivity_v204']=None
    from .mars_v203_climate import build_candidate_climate
    from .mars_v203_audits import build_audits
    from .moon_v203 import build_lunar_atlas
    climate=build_candidate_climate(data_root,summary['topographic_atlas']['entries'],
                                    summary['climate_earth_context'],
                                    fetch=fetch_climate,max_downloads=climate_download_limit)
    summary['climate_v203']={k:v for k,v in climate.items() if k!='rows'}
    for entry in summary['topographic_atlas']['entries']:
        entry['climate_earth_context']=climate['rows'].get(entry['id'],entry['climate_earth_context'])
    summary['candidate_audits']=build_audits(summary['topographic_atlas']['entries'],
                                             docs['correspondence']['rows'],climate)
    summary['mars_topographic_atlas']=build_mars_topographic_atlas(data_root,summary['profiles'],
                                                                   context_km=mars_context_km)
    summary['lunar_atlas']=build_lunar_atlas(data_root,fetch=fetch_lunar)
    summary['world_land']=json.loads(Path(__file__).with_name('world_land_v203.json').read_text(encoding='utf-8'))
    from .earth_continuous_v205 import build_continuous_earth
    summary['continuous_terrain_v205']=build_continuous_earth(data_root)
    from .rover_v21 import build_rover_terrain
    # Adds native NASADEM windows, preserving absolute elevations and physical
    # pixel spacing; never interpolate ETOPO or MOLA to claim rover-level detail.
    summary['rover_terrain_v21'] = build_rover_terrain(data_root)
    summary["correspondence_rows"] = docs["correspondence"]["rows"]
    summary["limitations"] = LIMITS
    # Prepare all outputs before writing: failures cannot leave a partly valid dashboard.
    from .rover_ui_v21 import add_rover_dashboard
    from .rover_ui_v22 import upgrade_rover_3d
    page = upgrade_rover_3d(add_rover_dashboard(render_dashboard(summary)))
    if "Mars Analog" not in page or "</html>" not in page:
        raise ValueError("Panel HTML incompleto")
    candidates = output_dir / "elysium_candidates_v2.csv"
    profiles = output_dir / "mars_profiles_v2.csv"
    cases = output_dir / "external_references_v2.csv"
    geo_index = output_dir / "elysium_candidates_geographic_atlas_v2.csv"
    mars_index = output_dir / "mars_topography_profiles_v2.csv"
    html_path = output_dir / "mars_analog_dashboard_v2.html"
    markdown = output_dir / "mars_analog_report_v2.md"
    json_path = output_dir / "mars_analog_report_v2.json"
    _csv(candidates, ["id","lat","lon","rank","scale_ranks","method_ranks","volcanic_samples","glim_samples","leave_one_out","process_relation","validation"], summary["candidates"])
    _csv(geo_index, ["id","label","country","center_lat","center_lon","topographic_rank","volcanic_points","is_priority","lithology_counts","relief_context_m"], summary["topographic_atlas"]["entries"])
    _csv(mars_index,["id","name","center_lat","center_lon_east","features","geology_units"],list(summary["mars_topographic_atlas"]["profiles"].values()))
    _csv(profiles, ["id","name","mapped_points","units","outside_catalog_minmax","extreme_tail_features","domain_flag"], summary["profiles"])
    _csv(cases, ["case_id","site_name","role","mars_profile","earth_region_id","topographic_rank","evaluation_status","validation_outcome"], summary["benchmark_cases"])
    _write_markdown(markdown, summary, hashes)
    with markdown.open('a',encoding='utf-8') as fp:
        fp.write('\n\n## Auditorías individuales V2.0.3\n\n')
        for a in summary['candidate_audits']:
            fp.write('### '+a['label']+' · '+a['id']+'\n\n')
            fp.write('\n'.join('- '+v for v in a['findings'])+'\n\n')
        if full_sensitivity_doc:
            fp.write('## Pruebas completas de sensibilidad V2.0.4\n\n')
            fp.write(f"Todas las {full_sensitivity_doc['candidate_count']} celdas GLiM tienen tres funciones de distancia, tres escalas y 60 perturbaciones de pesos. No es validación externa.\n\n")
        fp.write('## V2.2 · Simulación rover 2D y 3D sobre topografía local\n\n')
        fp.write(f"DEM reales disponibles: {summary['rover_terrain_v21']['available_sites']}/2 sectores NASADEM de Argentina. ")
        fp.write('Algoritmo A* con pendientes calculadas desde metros por celda, datos nulos bloqueados y coste de ruta heurístico; no energía Joules ni seguridad certificada.\n\n')
        fp.write('La resolución NASADEM (~30 m) es insuficiente para detectar rocas y escalones a escala de rover, y MOLA regional (~15 km) no se usa en planificación física de ruta.\n\n')
        fp.write('La vista WebGL2 3D conserva la malla DEM y reutiliza las rutas A*. Ofrece cámaras orbital, aérea y de seguimiento, con LOD y 3D de respaldo. Exageración vertical y tamaño del vehículo son solo recursos gráficos, no resultados medidos.\n\n')
        fp.write('## Atlas lunar independiente\n\n')
        fp.write('La topografía lunar procede de NASA LRO LOLA LDEM_4, 4 píxeles por grado. '
                 'No se ha calculado un ranking Tierra–Luna ni analogía lunar validada.\n\n')
        for r in summary['lunar_atlas']['regions']:
            fp.write('- '+r['name']+': '+r['process']+'; mapa '+summary['lunar_atlas']['maps'][r['id']]['status']+'\n')
    html_path.write_text(page, encoding="utf-8")
    climate_csv=output_dir/'candidate_climate_v203.csv'
    audit_csv=output_dir/'candidate_audits_v203.csv'
    audit_json=output_dir/'candidate_audits_v203.json'
    lunar_csv=output_dir/'lunar_regions_v203.csv'
    world_csv=output_dir/'world_candidates_v203.csv'
    _csv(climate_csv,['id','country','center_lat','center_lon','status','air_temp_mean_c',
         'precip_annual_mean_mm','relative_humidity_mean_pct','seasonal_air_temp_range_c',
         'climate_descriptor','source_detail'],[
         {'id':e['id'],'country':e['country'],'center_lat':e['center_lat'],'center_lon':e['center_lon'],
          'status':(e.get('climate_earth_context') or {}).get('status','missing'),
          **(e.get('climate_earth_context') or {})} for e in summary['topographic_atlas']['entries']])
    _csv(audit_csv,['id','label','center_lat','center_lon','topographic_rank_elysium',
        'relief_context_m','sampled_glim_points','volcanic_observed_points','climate_status',
        'individual_multiscale_tested','method_ranks','scale_ranks','weight_top25_of_60','glim_leave_one_out_preserved','findings'],summary['candidate_audits'])
    atomic_json(audit_json,{'schema_version':'mars_analog_candidate_audits_v2.0.4',
        'status':'existing_evidence_individual_review_not_geological_validation',
        'audits':summary['candidate_audits']})
    # Explicit V2.0.4 filenames for the now-complete individual audit set.
    audit_csv_v204=output_dir/'candidate_audits_v204.csv'
    audit_json_v204=output_dir/'candidate_audits_v204.json'
    audit_csv_v204.write_bytes(audit_csv.read_bytes())
    audit_json_v204.write_bytes(audit_json.read_bytes())
    _csv(lunar_csv,['id','name','lat','lon_east','process'],summary['lunar_atlas']['regions'])
    _csv(world_csv,['id','label','center_lat','center_lon','topographic_rank',
        'volcanic_points'],summary['topographic_atlas']['entries'])
    # Keep a machine-readable rover provenance and DEM-resolution summary
    # without duplicating the entire grid in the external report JSON.
    rover_manifest=output_dir/'rover_terrain_manifest_v21.json'
    from .download import atomic_json as _atomic_rover_json
    _atomic_rover_json(rover_manifest,{
        'schema_version':'mars_analog_rover_manifest_v2.1',
        'status':'regional_reconnaissance_only_not_rover_safety',
        'available_sites':summary['rover_terrain_v21']['available_sites'],
        'sites':[{k:v for k,v in site.items() if k!='elevation_m'}
                 for site in summary['rover_terrain_v21']['sites']],
        'limitations':[summary['rover_terrain_v21']['resolution_warning'],
                       summary['rover_terrain_v21']['mars_warning']],
    })
    output_files = {'rover_manifest':rover_manifest,'climate_csv':climate_csv,'audits_csv':audit_csv,
                    'audits_csv_v204':audit_csv_v204,'audits_json_v204':audit_json_v204,
                    'audits_json':audit_json,'moon_regions_csv':lunar_csv,
                    'world_candidates_csv':world_csv,
                    "dashboard_html": html_path, "report_markdown": markdown,
                    "candidates_csv": candidates, "atlas_locations_csv": geo_index, "mars_topography_csv":mars_index, "profiles_csv": profiles, "benchmarks_csv": cases}
    doc = {"schema_version":SCHEMA,
           "status":"integrated_exploratory_dashboard_not_scientific_analog_validation",
           "mars_profiles": len(summary["profiles"]), "glim_regions": summary["anchor_regions"],
           "earth_mars_correspondences": summary["correspondence_pairs"],
           "three_way_elysium_candidates": summary["candidates"],
           "earth_climate_context":summary["climate_earth_context"],
           "benchmark_summary": summary["benchmark_summary"],
           "rover_v22":{"rendering":"offline_webgl2_native_dem",
                         "views":["2d_route_planning","3d_orbit","3d_aerial","3d_follow"],
                         "elevation_rescaled":False,"physical_route_unchanged":True,
                         "small_obstacles_resolved":False},
           "rover_v21":{"available_sites":summary['rover_terrain_v21']['available_sites'],
                        "resolution_warning":summary['rover_terrain_v21']['resolution_warning']},
           "climate_v203":summary['climate_v203'],
           "full_sensitivity_v204":summary['full_sensitivity_v204'],
           "individual_audits":len(summary['candidate_audits']),
           "continuous_terrain_v205":{k:v for k,v in summary['continuous_terrain_v205'].items() if not k.endswith("_data_uri")},
           "lunar_atlas":{'regions':len(summary['lunar_atlas']['regions']),
                          'maps_available':sum(x['status']=='available' for x in summary['lunar_atlas']['maps'].values()),
                          'source':summary['lunar_atlas']['source']},
           "topographic_atlas": {"candidate_regions":len(summary["topographic_atlas"]["entries"]),
                                 "local_sites":len(summary["topographic_atlas"]["local_sites"]),
                                 "map_source_status":summary["topographic_atlas"]["map_source_status"],
                                 "source_files":summary["topographic_atlas"]["sources"]},
           "mars_topographic_atlas": {"profiles":len(summary['mars_topographic_atlas']['profiles']),
                                      "maps_available":sum(m.get('status')=='available' for m in summary['mars_topographic_atlas']['maps'].values()),
                                      "source_files":summary['mars_topographic_atlas']['sources']},
           "source_reports": {
               **{k:{"file":str(v),"sha256":hashes[k]} for k,v in inputs.items()},
               **({"sensitivity_all_v204":{"file":str(full_sensitivity_report),"sha256":sha256_file(Path(full_sensitivity_report))}}
                  if full_sensitivity_report else {})},
           "outputs": {k:{"file":str(v),"sha256":sha256_file(v)} for k,v in output_files.items()},
           "limitations": LIMITS,"analog_accuracy":None,"combined_similarity_score":None}
    atomic_json(json_path, doc)
    return {"schema_version":SCHEMA,"status":doc["status"],
            "mars_profiles":doc["mars_profiles"],"earth_mars_correspondences":doc["earth_mars_correspondences"],
            "candidates":len(summary["candidates"]),"benchmark":doc["benchmark_summary"],
            "dashboard_html":str(html_path),"atlas_maps_available":sum(m.get("status")=="available" for m in summary["topographic_atlas"]["maps"].values()),
            "atlas_regions":len(summary["topographic_atlas"]["entries"]),
            "mars_topo_maps_available":doc["mars_topographic_atlas"]["maps_available"],
            "lunar_maps_available":doc['lunar_atlas']['maps_available'],
            "world_continuous_topography":summary['continuous_terrain_v205']['status'],
            "world_topography_arcmin":summary['continuous_terrain_v205']['nominal_resolution_arcmin'],
            "rover_real_dem_sites":summary['rover_terrain_v21']['available_sites'],
            "rover_3d":"offline_webgl2_with_2d_fallback",
            "climate_complete":climate['complete'],"climate_partial":climate['partial'],
            "climate_missing":climate['missing'],"individual_audits":len(summary['candidate_audits']),
            "full_sensitivity_audits":(summary['full_sensitivity_v204']['coverage'] if summary['full_sensitivity_v204'] else 0),
            "markdown_report":str(markdown),
            "report_json":str(json_path),"report_sha256":sha256_file(json_path)}
