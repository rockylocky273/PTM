"""Comandos mínimos, controlados y auditables para el prototipo V0.1."""

import argparse
import json
from pathlib import Path
import sys

from .catalog import DATASETS
from .quality import parse_bbox


def make_parser():
    p = argparse.ArgumentParser(prog="mars-data", description="Mars Analog Engine: módulo de datos V2.0")
    sub = p.add_subparsers(dest="command", required=True)
    sub.add_parser("catalog", help="Mostrar datasets registrados (no descarga)")
    sub.add_parser("nasa-collections", help="Descubrir MODIS y GPM en NASA CMR")
    for name in ("nasa-search", "nasa-download"):
        cmd = sub.add_parser(name, help="Consultar archivos NASA; descargar solo si se solicita")
        cmd.add_argument("--dataset", choices=["modis_lst", "gpm_monthly"], required=True)
        cmd.add_argument("--start", required=True, help="YYYY-MM-DD, inclusive")
        cmd.add_argument("--end", required=True, help="YYYY-MM-DD, límite superior de consulta")
        cmd.add_argument("--count", type=int, default=1, help="Máximo 5 granulas")
        cmd.add_argument("--bbox", help="OESTE,SUR,ESTE,NORTE; sin antimeridiano")
        if name == "nasa-download":
            cmd.add_argument("--max-mb", type=int, default=300)
            cmd.add_argument("--dir", default="data/raw/earthdata")
    e = sub.add_parser("etopo", help="Descargar solo subconjunto ETOPO desde NOAA")
    e.add_argument("--bbox", required=True, help="Ejemplo: --bbox=-69,-24,-68,-23")
    e.add_argument("--stride", type=int, default=1, help="Stride en muestras de 60 arcsec")
    e.add_argument("--max-mb", type=int, default=40)
    e.add_argument("--dir", default="data/raw/etopo")
    m = sub.add_parser("mola", help="Descargar IMG, XML, HDR globales de 4 px/grado")
    m.add_argument("--max-mb", type=int, default=25)
    m.add_argument("--dir", default="data/raw/mola")
    e2 = sub.add_parser("etopo-inspect", help="Leer y normalizar ETOPO NetCDF sin descargar")
    e2.add_argument("--file", help="Ruta .nc; por defecto última descarga de data/raw/etopo")
    e2.add_argument("--output", default="data/processed/etopo_normalized.nc", help="Salida NetCDF")
    m2 = sub.add_parser("mola-inspect", help="Decodificar MOLA IMG utilizando su XML PDS4")
    m2.add_argument("--img", default="data/raw/mola/megt90n000cb.img")
    m2.add_argument("--xml", default="data/raw/mola/megt90n000cb.xml")
    m2.add_argument("--output", default="data/processed/mola_decoded.nc")
    m3 = sub.add_parser("mola-georef", help="Georreferenciar MOLA global 4 pix/grado con definición PDS confirmada")
    m3.add_argument("--input", default="data/processed/mola_decoded.nc")
    m3.add_argument("--output", default="data/processed/mola_georeferenced.nc")
    t3 = sub.add_parser("terrain-features", help="Calcular pendiente y rugosidad de ETOPO o MOLA (sin descarga)")
    t3.add_argument("--planet", choices=["earth","mars"], required=True)
    t3.add_argument("--input", help="NetCDF normalizado/georreferenciado, por defecto según planeta")
    t3.add_argument("--output", help="NetCDF de características, por defecto según planeta")
    s4 = sub.add_parser("scale-demo", help="Piloto: ETOPO y MOLA en escala nominal ~15 km, sin ranking")
    s4.add_argument("--earth", default="data/processed/etopo_normalized.nc")
    s4.add_argument("--mars", default="data/features/mars_terrain.nc")
    s4.add_argument("--target-km", type=float, default=15.0)
    s4.add_argument("--cells", type=int, default=5)
    s4.add_argument("--mars-lat", type=float, default=0.0)
    s4.add_argument("--mars-lon", type=float, default=150.0)
    s4.add_argument("--earth-output", default="data/processed/earth_coarse_15km.nc")
    s4.add_argument("--report", default="data/reports/scale_demo.json")
    g5 = sub.add_parser("global-plan", help="Planificar teselas mundiales ETOPO, sin descargar")
    g5.add_argument("--tile-deg", type=int, default=30)
    g5.add_argument("--stride", type=int, default=10)
    g5.add_argument("--plan", default="data/catalog/global_etopo_plan.json")
    gf = sub.add_parser("global-fetch", help="Descargar teselas ETOPO de forma limitada y con caché")
    gf.add_argument("--plan", default="data/catalog/global_etopo_plan.json")
    gf.add_argument("--dir", default="data/raw/global_etopo")
    gf.add_argument("--limit", type=int, default=1)
    gf.add_argument("--max-mb", type=int, default=5)
    gf.add_argument("--tile-id", default=None)
    gi = sub.add_parser("global-inventory", help="Auditar cobertura y archivos descargados, SIN ranking")
    gi.add_argument("--plan", default="data/catalog/global_etopo_plan.json")
    gi.add_argument("--dir", default="data/raw/global_etopo")
    gi.add_argument("--report", default="data/reports/global_inventory.json")
    gi.add_argument("--csv", default="data/reports/global_inventory.csv")
    lm = sub.add_parser("landmask-download", help="Descargar polígonos de tierra Natural Earth 50m (no NASA)")
    lm.add_argument("--output", default="data/raw/naturalearth/ne_50m_land.zip")
    lm.add_argument("--max-mb", type=int, default=15)
    gm = sub.add_parser("global-mosaic", help="Unir solo las 72 teselas ETOPO verificadas en NetCDF global")
    gm.add_argument("--plan", default="data/catalog/global_etopo_plan.json")
    gm.add_argument("--dir", default="data/raw/global_etopo")
    gm.add_argument("--output", default="data/processed/earth_global_mosaic.nc")
    gr = sub.add_parser("global-regions", help="Máscara tierra/océano y catálogo de regiones sin score marciano")
    gr.add_argument("--mosaic", default="data/processed/earth_global_mosaic.nc")
    gr.add_argument("--landmask", default="data/raw/naturalearth/ne_50m_land.zip")
    gr.add_argument("--region-deg", type=int, default=2)
    gr.add_argument("--min-land-fraction", type=float, default=0.8)
    gr.add_argument("--output", default="data/processed/earth_global_land.nc")
    gr.add_argument("--csv", default="data/catalog/earth_regions.csv")
    gr.add_argument("--report", default="data/reports/global_regions.json")
    mp = sub.add_parser("mars-profile", help="Perfil topográfico marciano de una ventana; sin geología")
    mp.add_argument("--mars", default="data/processed/mola_georeferenced.nc")
    mp.add_argument("--name", default="elysium_pilot")
    mp.add_argument("--lat", type=float, default=1.98)
    mp.add_argument("--lon", type=float, default=155.0)
    mp.add_argument("--spacing-km", type=float, default=30.)
    mp.add_argument("--samples", type=int, default=9)
    mp.add_argument("--output", default="data/profiles/elysium_pilot.json")
    a7 = sub.add_parser("analog-screen", help="Ranking EXPLORATORIO solo topográfico, no confirma análogos")
    a7.add_argument("--profile", default="data/profiles/elysium_pilot.json")
    a7.add_argument("--earth", default="data/processed/earth_global_land.nc")
    a7.add_argument("--catalog", default="data/catalog/earth_regions.csv")
    a7.add_argument("--top", type=int, default=25)
    a7.add_argument("--min-separation-km", type=float, default=250.)
    a7.add_argument("--max-abs-lat", type=float, default=65.)
    a7.add_argument("--min-patch-coverage", type=float, default=0.95)
    a7.add_argument("--output-csv", default="data/results/topography_ranking.csv")
    a7.add_argument("--report", default="data/reports/topography_screen.json")
    a8 = sub.add_parser("analog-audit", help="Auditar ranking topográfico V0.7 y probar su sensibilidad; sin descargas")
    a8.add_argument("--profile", default="data/profiles/elysium_pilot.json")
    a8.add_argument("--ranking", default="data/results/topography_ranking.csv")
    a8.add_argument("--screen-report", default="data/reports/topography_screen.json")
    a8.add_argument("--top", type=int, default=25)
    a8.add_argument("--min-separation-km", type=float, default=250.)
    a8.add_argument("--scenarios", type=int, default=60)
    a8.add_argument("--seed", type=int, default=2026)
    a8.add_argument("--output-csv", default="data/results/topography_stability.csv")
    a8.add_argument("--report", default="data/reports/analog_audit.json")
    c9 = sub.add_parser("climate-fetch", help="Descargar contexto climático NASA POWER solo para candidatos auditados")
    c9.add_argument("--audit", default="data/reports/analog_audit.json")
    c9.add_argument("--dir", default="data/raw/power")
    c9.add_argument("--start", type=int, default=2015)
    c9.add_argument("--end", type=int, default=2024)
    c9.add_argument("--top", type=int, default=25)
    c9.add_argument("--limit", type=int, default=5)
    c9.add_argument("--max-kb", type=int, default=1024)
    c9.add_argument("--connect-timeout", type=float, default=20.,
                    help="Tiempo máximo de conexión en segundos (predeterminado: 20)")
    c9.add_argument("--read-timeout", type=float, default=120.,
                    help="Tiempo máximo de inactividad de lectura en segundos (predeterminado: 120)")
    c9.add_argument("--retries", type=int, default=2,
                    help="Reintentos adicionales ante errores transitorios (predeterminado: 2)")
    c9.add_argument("--retry-wait", type=float, default=2.,
                    help="Pausa inicial de reintento, segundos (predeterminado: 2)")
    cr = sub.add_parser("climate-summary", help="Resumir NASA POWER sin cambiar ranking topográfico")
    cr.add_argument("--audit", default="data/reports/analog_audit.json")
    cr.add_argument("--dir", default="data/raw/power")
    cr.add_argument("--start", type=int, default=2015)
    cr.add_argument("--end", type=int, default=2024)
    cr.add_argument("--top", type=int, default=25)
    cr.add_argument("--csv", default="data/results/environment_context.csv")
    cr.add_argument("--report", default="data/reports/environment_context.json")
    ev = sub.add_parser("environment-plan", help="Muestra espacial y por rango topográfico, sin descargar")
    ev.add_argument("--ranking", default="data/results/topography_ranking.csv")
    ev.add_argument("--audit", default="data/reports/analog_audit.json")
    ev.add_argument("--sample-size", type=int, default=125)
    ev.add_argument("--anchor-top", type=int, default=25)
    ev.add_argument("--min-separation-km", type=float, default=250.)
    ev.add_argument("--seed", type=int, default=2026)
    ev.add_argument("--output", default="data/catalog/environment_plan.json")
    cf = sub.add_parser("environment-fetch", help="POWER de muestra estratificada con caché V0.9")
    cf.add_argument("--plan", default="data/catalog/environment_plan.json")
    cf.add_argument("--old-dir", default="data/raw/power")
    cf.add_argument("--dir", default="data/raw/power_global")
    cf.add_argument("--start", type=int, default=2015)
    cf.add_argument("--end", type=int, default=2024)
    cf.add_argument("--limit", type=int, default=5)
    cf.add_argument("--max-kb", type=int, default=1024)
    cf.add_argument("--connect-timeout", type=float, default=20.)
    cf.add_argument("--read-timeout", type=float, default=180.)
    cf.add_argument("--retries", type=int, default=0)
    cf.add_argument("--retry-wait", type=float, default=2.)
    cs = sub.add_parser("environment-summary", help="Resumir muestra climática sin alterar ranking")
    cs.add_argument("--plan", default="data/catalog/environment_plan.json")
    cs.add_argument("--old-dir", default="data/raw/power")
    cs.add_argument("--dir", default="data/raw/power_global")
    cs.add_argument("--start", type=int, default=2015)
    cs.add_argument("--end", type=int, default=2024)
    cs.add_argument("--csv", default="data/results/environment_sample.csv")
    cs.add_argument("--report", default="data/reports/environment_sample.json")
    ls = sub.add_parser("landcover-search", help="Descubrir NASA MODIS MCD12C1 IGBP global por CMR")
    ls.add_argument("--year", type=int, default=2024)
    ld = sub.add_parser("landcover-download", help="Descargar MCD12C1 HDF4 con Earthdata Login")
    ld.add_argument("--year", type=int, default=2024)
    ld.add_argument("--dir", default="data/raw/modis_landcover")
    ld.add_argument("--max-mb", type=int, default=1000)
    lsm = sub.add_parser("landcover-summary", help="Clasificar cobertura MODIS en las regiones del ranking")
    lsm.add_argument("--hdf", required=True, help="Ruta exacta .hdf que descargó landcover-download")
    lsm.add_argument("--ranking", default="data/results/topography_ranking.csv")
    lsm.add_argument("--year", type=int, default=2024)
    lsm.add_argument("--csv", default="data/results/landcover_context.csv")
    lsm.add_argument("--report", default="data/reports/landcover_context.json")
    ed = sub.add_parser("environment-diagnostic", help="Cruce descriptivo, sin score marciano")
    ed.add_argument("--plan", default="data/catalog/environment_plan.json")
    ed.add_argument("--climate", default="data/results/environment_sample.csv")
    ed.add_argument("--landcover", default="data/results/landcover_context.csv")
    ed.add_argument("--csv", default="data/results/environment_diagnostic.csv")
    ed.add_argument("--report", default="data/reports/environment_diagnostic.json")
    ap = sub.add_parser("appeears-layers", help="Consultar capas AppEEARS sin descargar ni autenticar")
    ap.add_argument("--product", default="MCD12Q1.061")
    apt = sub.add_parser("appeears-plan", help="Plan puntual para solicitar cobertura del suelo selectiva (sin red)")
    apt.add_argument("--environment-plan", default="data/catalog/environment_plan.json")
    apt.add_argument("--output", default="data/catalog/appeears_landcover_plan.json")
    apt.add_argument("--year", type=int, default=2024)
    apt.add_argument("--limit", type=int, default=5)
    apt.add_argument("--points-per-region", type=int, choices=[1,5], default=5)
    apt.add_argument("--spacing-km", type=float, default=60.0)
    apt.add_argument("--product", default="MCD12Q1.061")
    apt.add_argument("--layer", default="LC_Type1")
    auth = sub.add_parser("appeears-auth-check", help="Comprobar inicio de sesión AppEEARS SIN enviar tareas ni mostrar tokens")
    auth.add_argument("--username", help="Nombre de usuario Earthdata, NO correo; nunca poner la contraseña aquí")
    aps = sub.add_parser("appeears-submit", help="Enviar una solicitud AppEEARS SOLO con --confirm")
    aps.add_argument("--plan", default="data/catalog/appeears_landcover_plan.json")
    aps.add_argument("--job", default="data/catalog/appeears_landcover_job.json")
    aps.add_argument("--confirm", action="store_true")
    aps.add_argument("--username", help="Usuario Earthdata (no escribir contraseñas en argumentos)")
    apsc = sub.add_parser("appeears-status", help="Consultar estado de tarea AppEEARS")
    apsc.add_argument("--job", default="data/catalog/appeears_landcover_job.json")
    apsc.add_argument("--username")
    apf = sub.add_parser("appeears-files", help="Listar archivos de salida de AppEEARS sin descargarlos")
    apf.add_argument("--job", default="data/catalog/appeears_landcover_job.json")
    apf.add_argument("--username")
    apd = sub.add_parser("appeears-download", help="Descargar solo salidas de texto del task terminado")
    apd.add_argument("--job", default="data/catalog/appeears_landcover_job.json")
    apd.add_argument("--dir", default="data/raw/appeears_landcover")
    apd.add_argument("--max-mb", type=int, default=20)
    apd.add_argument("--username")
    apv = sub.add_parser("appeears-preview", help="Ver encabezados CSV de datos descargados")
    apv.add_argument("--dir", default="data/raw/appeears_landcover")
    # V1.1: GLiM Level I, global mapped lithology through public feature-layer queries.
    gm = sub.add_parser("geology-metadata", help="Verificar capa pública GLiM y atributos; sin puntos")
    gm.add_argument("--timeout", type=float, default=30.)
    gp = sub.add_parser("geology-plan", help="Muestreo geológico desde el plan ambiental; sin red")
    gp.add_argument("--environment-plan", default="data/catalog/environment_plan.json")
    gp.add_argument("--output", default="data/catalog/geology_plan.json")
    gp.add_argument("--limit", type=int, default=6)
    gp.add_argument("--region-ids", help="IDs separados por coma; para Argentina: r026_c146")
    gp.add_argument("--points-per-region", type=int, choices=[1,5,9], default=5)
    gp.add_argument("--spacing-km", type=float, default=60.)
    gf11 = sub.add_parser("geology-fetch", help="Consultar una cantidad limitada de puntos GLiM, guardando caché")
    gf11.add_argument("--plan", default="data/catalog/geology_plan.json")
    gf11.add_argument("--dir", default="data/raw/geology_glim")
    gf11.add_argument("--limit", type=int, default=10)
    gf11.add_argument("--timeout", type=float, default=60.)
    gs = sub.add_parser("geology-summary", help="Informe litológico por región; sin reclasificar el ranking")
    gs.add_argument("--plan", default="data/catalog/geology_plan.json")
    gs.add_argument("--dir", default="data/raw/geology_glim")
    gs.add_argument("--csv", default="data/results/geology_context.csv")
    gs.add_argument("--report", default="data/reports/geology_context.json")
    # V1.1.1: recortes de polígonos volcánicos y planificación ETOPO local.
    gb = sub.add_parser("geology-boundaries-fetch", help="Recortar polígonos GLiM de puntos volcánicos ya clasificados")
    gb.add_argument("--plan", default="data/catalog/geology_argentina_plan.json")
    gb.add_argument("--point-dir", default="data/raw/geology_glim")
    gb.add_argument("--dir", default="data/processed/glim_boundaries")
    gb.add_argument("--region-id", default="r026_c146")
    gb.add_argument("--limit", type=int, default=2)
    gb.add_argument("--radius-km", type=float, default=25.)
    gb.add_argument("--timeout", type=float, default=120.)
    gbs = sub.add_parser("geology-boundaries-summary", help="Resumen verificable de recortes GeoJSON GLiM")
    gbs.add_argument("--plan", default="data/catalog/geology_argentina_plan.json")
    gbs.add_argument("--point-dir", default="data/raw/geology_glim")
    gbs.add_argument("--dir", default="data/processed/glim_boundaries")
    gbs.add_argument("--region-id", default="r026_c146")
    gbs.add_argument("--radius-km", type=float, default=25.)
    gbs.add_argument("--csv", default="data/results/geology_argentina_boundaries.csv")
    gbs.add_argument("--report", default="data/reports/geology_argentina_boundaries.json")
    gtb = sub.add_parser("geology-terrain-bboxes", help="Preparar áreas ETOPO de 1 arcmin en torno a muestras volcánicas")
    gtb.add_argument("--plan", default="data/catalog/geology_argentina_plan.json")
    gtb.add_argument("--point-dir", default="data/raw/geology_glim")
    gtb.add_argument("--region-id", default="r026_c146")
    gtb.add_argument("--half-width-km", type=float, default=30.)
    gtb.add_argument("--output", default="data/catalog/geology_argentina_terrain_rois.json")
    # V1.1.2: NASADEM 1 arcsecond + GLiM overlay, explicit Earthdata download.
    ndp = sub.add_parser("nasadem-plan", help="Plan de teselas NASADEM para áreas volcánicas, sin red")
    ndp.add_argument("--rois", default="data/catalog/geology_argentina_terrain_rois.json")
    ndp.add_argument("--output", default="data/catalog/nasadem_argentina_plan.json")
    nds = sub.add_parser("nasadem-search", help="Consultar teselas NASADEM en CMR; no requiere login ni descarga")
    nds.add_argument("--plan", default="data/catalog/nasadem_argentina_plan.json")
    nds.add_argument("--output", default="data/catalog/nasadem_argentina_search.json")
    ndd = sub.add_parser("nasadem-download", help="Descargar teselas NASADEM desde Earthdata, sin persistir claves")
    ndd.add_argument("--plan", default="data/catalog/nasadem_argentina_plan.json")
    ndd.add_argument("--search", default="data/catalog/nasadem_argentina_search.json")
    ndd.add_argument("--dir", default="data/raw/nasadem")
    ndd.add_argument("--limit", type=int, default=1)
    ndd.add_argument("--max-mb", type=float, default=60.)
    nda = sub.add_parser("nasadem-analyze", help="Superponer GLiM y NASADEM 30 m; no calcula seguridad de rover")
    nda.add_argument("--plan", default="data/catalog/nasadem_argentina_plan.json")
    nda.add_argument("--dir", default="data/raw/nasadem")
    nda.add_argument("--boundaries-csv", default="data/results/geology_argentina_boundaries.csv")
    nda.add_argument("--point-id", required=True)
    nda.add_argument("--etopo", help="NetCDF ETOPO normalizado específico para el sector")
    nda.add_argument("--output-nc", help="NetCDF de capas local, por defecto según punto")
    nda.add_argument("--report", help="Informe JSON según punto")
    nda.add_argument("--slope-threshold-deg", type=float, default=5.0)
    ndc = sub.add_parser("nasadem-compare", help="Comparación p04/p08 sin ranking de seguridad")
    ndc.add_argument("--p04", default="data/reports/nasadem_argentina_p04.json")
    ndc.add_argument("--p08", default="data/reports/nasadem_argentina_p08.json")
    ndc.add_argument("--output", default="data/reports/nasadem_argentina_comparison.json")
    # V1.2: catálogos científicos de regiones marcianas y rankings independientes.
    sub.add_parser("mars-targets", help="Seis centros de nomenclatura IAU/USGS; NO litologías")
    mb = sub.add_parser("mars-profiles-build", help="Construir perfiles multirregión desde MOLA, sin red")
    mb.add_argument("--mars", default="data/processed/mola_georeferenced.nc")
    mb.add_argument("--targets", default="all", help="all o IDs separados por coma (mars-targets)")
    mb.add_argument("--spacing-km", type=float, default=30.)
    mb.add_argument("--samples", type=int, default=9)
    mb.add_argument("--dir", default="data/profiles/v1_2")
    mb.add_argument("--manifest", default="data/catalog/mars_profiles_v1_2.json")
    ms = sub.add_parser("mars-profiles-screen", help="Buscar análogos topográficos separados, sin alterar V0.7")
    ms.add_argument("--manifest", default="data/catalog/mars_profiles_v1_2.json")
    ms.add_argument("--earth", default="data/processed/earth_global_land.nc")
    ms.add_argument("--catalog", default="data/catalog/earth_regions.csv")
    ms.add_argument("--dir", default="data/results/mars_profiles_v1_2")
    ms.add_argument("--report", default="data/reports/mars_profiles_screen_v1_2.json")
    ms.add_argument("--top", type=int, default=25)
    ms.add_argument("--min-separation-km", type=float, default=250.)
    ms.add_argument("--max-abs-lat", type=float, default=65.)
    ms.add_argument("--min-patch-coverage", type=float, default=.95)
    mc = sub.add_parser("mars-profiles-compare", help="Cruce de puestos terrestres entre perfiles; sin score mixto")
    mc.add_argument("--screen-report", default="data/reports/mars_profiles_screen_v1_2.json")
    mc.add_argument("--watch", default="r026_c146,r068_c061")
    mc.add_argument("--top-n", type=int, default=25)
    mc.add_argument("--csv", default="data/results/mars_profiles_watch_v1_2.csv")
    mc.add_argument("--report", default="data/reports/mars_profiles_compare_v1_2.json")
    # V1.2.1: auditoría numérica y sensibilidad a la escala (sin cambios históricos).
    ar = sub.add_parser("mars-audit-rankings", help="Correlaciones, saturación, métricas alternativas y sensibilidad de pesos")
    ar.add_argument("--screen-report", default="data/reports/mars_profiles_screen_v1_2.json")
    ar.add_argument("--manifest", default="data/catalog/mars_profiles_v1_2.json")
    ar.add_argument("--dir", default="data/reports/mars_audit_v1_2_1")
    ar.add_argument("--top-ks", default="25,50,100")
    ar.add_argument("--scenarios", type=int, default=60)
    ar.add_argument("--seed", type=int, default=2026)
    ar.add_argument("--watch", default="r026_c146,r068_c061")
    asc = sub.add_parser("mars-audit-scales", help="Muestreo MOLA/ETOPO multiescala con ventana física fija de 240 km")
    asc.add_argument("--screen-report", default="data/reports/mars_profiles_screen_v1_2.json")
    asc.add_argument("--manifest", default="data/catalog/mars_profiles_v1_2.json")
    asc.add_argument("--earth", default="data/processed/earth_global_land.nc")
    asc.add_argument("--mars", default="data/processed/mola_georeferenced.nc")
    asc.add_argument("--catalog", default="data/catalog/earth_regions.csv")
    asc.add_argument("--scales", default="15:17,30:9,40:7")
    asc.add_argument("--top-k", type=int, default=25)
    asc.add_argument("--dir", default="data/reports/mars_audit_v1_2_1/scales")
    # V1.2.2: USGS SIM 3292 layer, provenance and domain checks (no new combined score).
    mgm = sub.add_parser("mars-geology-source", help="Validar metadatos de la capa cartográfica de Marte")
    mgm.add_argument("--timeout", type=float, default=45.)
    mgp = sub.add_parser("mars-geology-plan", help="Diseñar muestras de unidades geológicas marcianas; sin red")
    mgp.add_argument("--manifest", default="data/catalog/mars_profiles_v1_2.json")
    mgp.add_argument("--points-per-profile", type=int, default=9, choices=[1,5,9])
    mgp.add_argument("--radius-km", type=float, default=100.)
    mgp.add_argument("--output", default="data/catalog/mars_geology_plan_v1_2_2.json")
    mgf = sub.add_parser("mars-geology-fetch", help="Consultar códigos de unidades marcianas con caché por punto")
    mgf.add_argument("--plan", default="data/catalog/mars_geology_plan_v1_2_2.json")
    mgf.add_argument("--dir", default="data/raw/mars_geology_v1_2_2")
    mgf.add_argument("--limit", type=int, default=10)
    mgf.add_argument("--timeout", type=float, default=45.)
    mgs = sub.add_parser("mars-geology-summary", help="Resumir muestras marcianas; NO porcentajes de área")
    mgs.add_argument("--plan", default="data/catalog/mars_geology_plan_v1_2_2.json")
    mgs.add_argument("--dir", default="data/raw/mars_geology_v1_2_2")
    mgs.add_argument("--csv", default="data/results/mars_geology_points_v1_2_2.csv")
    mgs.add_argument("--report", default="data/reports/mars_geology_points_v1_2_2.json")
    md = sub.add_parser("mars-domain-report", help="Auditar extrapolación fuera del rango ETOPO terrestre")
    md.add_argument("--audit", default="data/reports/mars_audit_v1_2_1/rank_audit_report.json")
    md.add_argument("--csv", default="data/results/mars_domain_v1_2_2.csv")
    md.add_argument("--report", default="data/reports/mars_domain_v1_2_2.json")
    me = sub.add_parser("mars-evidence-matrix", help="Poner evidencias Tierra/Marte lado a lado SIN score conjunto")
    me.add_argument("--mars", default="data/reports/mars_geology_points_v1_2_2.json")
    me.add_argument("--domain", default="data/reports/mars_domain_v1_2_2.json")
    me.add_argument("--glim", default="data/results/geology_top25.csv")
    me.add_argument("--screen", default="data/reports/mars_profiles_screen_v1_2.json")
    me.add_argument("--watch", default="r026_c146,r068_c061")
    me.add_argument("--csv", default="data/results/mars_evidence_matrix_v1_2_2.csv")
    me.add_argument("--report", default="data/reports/mars_evidence_matrix_v1_2_2.json")
    # V1.3.0: integración multicriterio NO compensatoria; conserva fuentes originales.
    mmb = sub.add_parser("mars-multicriteria-build", help="Integrar evidencias con gates, sin score planetario")
    mmb.add_argument("--matrix", default="data/reports/mars_evidence_matrix_v1_2_2.json")
    mmb.add_argument("--domain", default="data/reports/mars_domain_v1_2_2.json")
    mmb.add_argument("--mars-geology", default="data/reports/mars_geology_points_v1_2_2.json")
    mmb.add_argument("--glim", default="data/results/geology_top25.csv")
    mmb.add_argument("--screen", default="data/reports/mars_profiles_screen_v1_2.json")
    mmb.add_argument("--climate-report", default="data/reports/environment_sample.json")
    mmb.add_argument("--without-climate", action="store_true", help="No incluir clima terrestre aunque haya informe")
    mmb.add_argument("--audit-report", default="data/reports/mars_audit_v1_2_1/rank_audit_report.json")
    mmb.add_argument("--scales-report", default="data/reports/mars_audit_v1_2_1/scales/multiscale_audit_report.json")
    mmb.add_argument("--shortlist-top", type=int, default=25)
    mmb.add_argument("--csv", default="data/results/mars_multicriteria_v1_3_0.csv")
    mmb.add_argument("--report", default="data/reports/mars_multicriteria_v1_3_0.json")
    mmb.add_argument("--markdown", default="data/reports/mars_multicriteria_v1_3_0.md")
    mmr = sub.add_parser("mars-multicriteria-review", help="Ver diagnóstico por perfil a partir del informe V1.3.0")
    mmr.add_argument("--report", default="data/reports/mars_multicriteria_v1_3_0.json")
    mmr.add_argument("--profile", default="all")
    # V1.3.1: hipótesis geológicas sin equivalencia ni score combinado.
    gcb = sub.add_parser("mars-geology-correspondence-build", help="Comparar TODOS los candidatos GLiM con procesos cartográficos marcianos")
    gcb.add_argument("--multicriteria", default="data/reports/mars_multicriteria_v1_3_0.json")
    gcb.add_argument("--mars-geology", default="data/reports/mars_geology_points_v1_2_2.json")
    gcb.add_argument("--domain", default="data/reports/mars_domain_v1_2_2.json")
    gcb.add_argument("--glim", default="data/results/geology_top25.csv")
    gcb.add_argument("--screen", default="data/reports/mars_profiles_screen_v1_2.json")
    gcb.add_argument("--top-n", type=int, default=25)
    gcb.add_argument("--csv", default="data/results/mars_geology_correspondence_v1_3_1.csv")
    gcb.add_argument("--report", default="data/reports/mars_geology_correspondence_v1_3_1.json")
    gcb.add_argument("--markdown", default="data/reports/mars_geology_correspondence_v1_3_1.md")
    gcr = sub.add_parser("mars-geology-correspondence-review", help="Inspeccionar relaciones geológicas sin puntuación de similitud")
    gcr.add_argument("--report", default="data/reports/mars_geology_correspondence_v1_3_1.json")
    gcr.add_argument("--profile", default="elysium_planitia")
    gcr.add_argument("--region", default="all")
    gcr.add_argument("--limit", type=int, default=25)
    gcl = sub.add_parser("mars-geology-local-review", help="Anexar evidencia local NASADEM+GLiM de Argentina; NO equivalencia con Marte")
    gcl.add_argument("--p04", default="data/reports/nasadem_argentina_p04.json")
    gcl.add_argument("--p08", default="data/reports/nasadem_argentina_p08.json")
    gcl.add_argument("--report", default="data/reports/mars_geology_argentina_local_v1_3_1.json")
    # V1.3.2: comparación EQUILIBRADA con incertidumbre explícita.
    ubu = sub.add_parser('mars-uncertainty-build', help='Comparar rivales volcánicos con las mismas pruebas de escala, método y muestreo GLiM')
    ubu.add_argument('--correspondence',default='data/reports/mars_geology_correspondence_v1_3_1.json')
    ubu.add_argument('--screen',default='data/reports/mars_profiles_screen_v1_2.json')
    ubu.add_argument('--manifest',default='data/catalog/mars_profiles_v1_2.json')
    ubu.add_argument('--audit',default='data/reports/mars_audit_v1_2_1/rank_audit_report.json')
    ubu.add_argument('--scales',default='data/reports/mars_audit_v1_2_1/scales/multiscale_audit_report.json')
    ubu.add_argument('--profile',default='elysium_planitia')
    ubu.add_argument('--candidates',default='r026_c146,r069_c067,r067_c038')
    ubu.add_argument('--top-ks',default='10,25,50')
    ubu.add_argument('--csv',default='data/results/mars_uncertainty_v1_3_2.csv')
    ubu.add_argument('--report',default='data/reports/mars_uncertainty_v1_3_2.json')
    ubu.add_argument('--markdown',default='data/reports/mars_uncertainty_v1_3_2.md')
    ubr = sub.add_parser('mars-uncertainty-review',help='Revisar diagnóstico V1.3.2 verificado sin score')
    ubr.add_argument('--report',default='data/reports/mars_uncertainty_v1_3_2.json')
    ubr.add_argument('--region',default='all')
    # V2.0.4: extender las pruebas históricas idénticas a TODAS las 25 anclas.
    sab = sub.add_parser('mars-sensitivity-all-build',help='Sensibilidad completa para las 25 regiones GLiM: 3 métodos, 3 escalas, 60 pesos, nueve muestras')
    sab.add_argument('--data-root',default='data')
    sab.add_argument('--output-dir',default='data/reports/mars_v2_0')
    sar = sub.add_parser('mars-sensitivity-all-review',help='Revisar auditoría ampliada con integridad SHA-256')
    sar.add_argument('--report',default='data/reports/mars_v2_0/candidate_sensitivity_v204.json')
    sar.add_argument('--region',default='all')
    # V1.3.3: bibliografía científica externa y controles de alcance, sin tuning.
    eb = sub.add_parser('mars-external-benchmark-build',
                        help='Auditar referencias NASA/USGS congeladas frente a rankings V1.2 sin validar analogías')
    eb.add_argument('--benchmark',default='config/external_benchmarks_v1_3_3.json')
    eb.add_argument('--screen',default='data/reports/mars_profiles_screen_v1_2.json')
    eb.add_argument('--manifest',default='data/catalog/mars_profiles_v1_2.json')
    eb.add_argument('--catalog',default='data/catalog/earth_regions.csv')
    eb.add_argument('--domain',default='data/reports/mars_domain_v1_2_2.json')
    eb.add_argument('--scales',default='data/reports/mars_audit_v1_2_1/scales/multiscale_audit_report.json')
    eb.add_argument('--csv',default='data/results/mars_external_benchmark_v1_3_3.csv')
    eb.add_argument('--report',default='data/reports/mars_external_benchmark_v1_3_3.json')
    eb.add_argument('--markdown',default='data/reports/mars_external_benchmark_v1_3_3.md')
    er = sub.add_parser('mars-external-benchmark-review',help='Revisar comparación con fuentes externas y control SHA-256')
    er.add_argument('--report',default='data/reports/mars_external_benchmark_v1_3_3.json')
    er.add_argument('--case',default='all')
    # V2.0: tablero e informe integrados desde seis evidencias ya calculadas.
    # V2.1: high-resolution DEM import for the rover tab. No synthetic upsampling.
    rg = sub.add_parser('mars-rover-import-geotiff',
                        help='Importar DEM GeoTIFF local a JSON físico para simulación exploratoria')
    rg.add_argument('--input',required=True,help='GeoTIFF con elevaciones originales en metros')
    rg.add_argument('--output',default='data/rover/terrain_imported_v21.json')
    rg.add_argument('--size',type=int,default=128,help='Celdas nativas por eje (32..256)')
    rg.add_argument('--row',type=int,default=None,help='Fila central del recorte (opcional)')
    rg.add_argument('--col',type=int,default=None,help='Columna central del recorte (opcional)')
    rg.add_argument('--cell-size-m',type=float,default=None,
                    help='Metros por píxel si la fuente no declara unidades (cuadrícula cuadrada)')
    v2 = sub.add_parser('mars-v2-build', help='Exportar panel HTML e informe V2.0 sin descargas ni score planetario')
    v2.add_argument('--data-root', default='data', help='Carpeta de datos históricos (p. ej. data)')
    v2.add_argument('--output-dir', default='data/reports/mars_v2_0')
    v2.add_argument('--fetch-climate',action='store_true',help='Completar clima NASA POWER para regiones sin datos históricos (red)')
    v2.add_argument('--fetch-lunar',action='store_true',help='Descargar LOLA LDEM_4 oficial (2 MB) si aún no existe')
    v2.add_argument('--climate-limit',type=int,default=25,help='Máximo 25 solicitudes NASA POWER nuevas')
    v2.add_argument('--full-sensitivity-report',default=None,help='Informe V2.0.4 para habilitar las 25 auditorías completas')
    v2.add_argument('--mars-context-km',type=float,default=1600.0,help='Mapa MOLA amplio; default 1600 km')
    return p


def _latest_nc():
    files = sorted(Path("data/raw/etopo").glob("*.nc"), key=lambda f:f.stat().st_mtime,reverse=True)
    if not files:
        raise ValueError("No encontré archivos ETOPO en data/raw/etopo. Usá --file RUTA.")
    return files[0]


def main(argv=None):
    parser = make_parser()
    args = parser.parse_args(argv)
    try:
        if args.command == "catalog":
            obj = {key: spec.to_dict() for key, spec in DATASETS.items()}
        elif args.command == "nasa-collections":
            from .earthdata import discover_collections
            obj = discover_collections()
        elif args.command == "nasa-search":
            from .earthdata import query_granules, granule_summary
            found = query_granules(args.dataset, args.start, args.end,
                                   count=args.count, bbox=parse_bbox(args.bbox) if args.bbox else None)
            obj = [granule_summary(g) for g in found]
        elif args.command == "nasa-download":
            from .earthdata import download_granules
            obj = download_granules(args.dataset, args.start, args.end,
                                    count=args.count, bbox=parse_bbox(args.bbox) if args.bbox else None,
                                    max_mb=args.max_mb, directory=Path(args.dir))
        elif args.command == "etopo":
            from .noaa import download_etopo
            obj = download_etopo(parse_bbox(args.bbox), Path(args.dir), args.stride, args.max_mb)
        elif args.command == "mola":
            from .pds import download_mola
            obj = download_mola(Path(args.dir), args.max_mb)
        elif args.command == "etopo-inspect":
            from .etopo_processing import process_etopo
            obj = process_etopo(Path(args.file) if args.file else _latest_nc(), Path(args.output))
        elif args.command == "mola-inspect":
            from .pds4_processing import process_mola
            obj = process_mola(Path(args.img), Path(args.xml), Path(args.output))
        elif args.command == "mola-georef":
            from .mola_georeference import process_mola_georef
            obj = process_mola_georef(Path(args.input),Path(args.output))
        elif args.command == "terrain-features":
            from .terrain_features import process_terrain_features
            source = Path(args.input) if args.input else Path(
                "data/processed/etopo_normalized.nc" if args.planet == "earth" else
                "data/processed/mola_georeferenced.nc")
            output = Path(args.output) if args.output else Path(
                "data/features/earth_terrain.nc" if args.planet == "earth" else
                "data/features/mars_terrain.nc")
            obj = process_terrain_features(source,output,args.planet)
        elif args.command == "scale-demo":
            from .scale_comparison import process_nominal_scale
            obj = process_nominal_scale(Path(args.earth),Path(args.mars),
                                        Path(args.earth_output),Path(args.report),
                                        args.target_km,args.cells,args.mars_lat,args.mars_lon)
        elif args.command == "global-plan":
            from .global_tiles import save_plan
            obj = save_plan(Path(args.plan), args.tile_deg, args.stride)
        elif args.command == "global-fetch":
            from .global_tiles import fetch_tiles
            obj = fetch_tiles(Path(args.plan), Path(args.dir), args.limit, args.max_mb, args.tile_id)
        elif args.command == "global-inventory":
            from .global_tiles import global_inventory
            obj = global_inventory(Path(args.plan), Path(args.dir), Path(args.report), Path(args.csv))
        elif args.command == "landmask-download":
            from .landmask import download_landmask
            obj = download_landmask(Path(args.output), args.max_mb)
        elif args.command == "global-mosaic":
            from .global_surface import assemble_global
            obj = assemble_global(Path(args.plan), Path(args.dir), Path(args.output))
        elif args.command == "global-regions":
            from .global_surface import build_land_regions
            obj = build_land_regions(Path(args.mosaic),Path(args.landmask),Path(args.output),
                                     Path(args.csv),Path(args.report),args.region_deg,args.min_land_fraction)
        elif args.command == "mars-profile":
            from .analog_screen import create_mars_profile
            obj = create_mars_profile(Path(args.mars),Path(args.output),args.name,
                                      args.lat,args.lon,args.spacing_km,args.samples)
        elif args.command == "analog-screen":
            from .analog_screen import screen_earth
            obj = screen_earth(Path(args.profile),Path(args.earth),Path(args.catalog),
                               Path(args.output_csv),Path(args.report),args.top,
                               args.min_separation_km,args.max_abs_lat,args.min_patch_coverage)
        elif args.command == "analog-audit":
            from .analog_audit import audit_ranking
            obj = audit_ranking(Path(args.profile),Path(args.ranking),Path(args.screen_report),
                                Path(args.output_csv),Path(args.report),args.top,
                                args.min_separation_km,args.scenarios,args.seed)
        elif args.command == "climate-fetch":
            from .climate_power import fetch_candidate_climate
            obj = fetch_candidate_climate(Path(args.audit), Path(args.dir), args.start,
                                          args.end, args.top, args.limit, args.max_kb,
                                          connect_timeout=args.connect_timeout,
                                          read_timeout=args.read_timeout,
                                          retries=args.retries,
                                          retry_wait=args.retry_wait)
        elif args.command == "climate-summary":
            from .climate_power import build_environment_report
            obj = build_environment_report(Path(args.audit), Path(args.dir),
                                           Path(args.csv), Path(args.report),
                                           args.start, args.end, args.top)
        elif args.command == "environment-plan":
            from .environment_global import build_environment_plan
            obj = build_environment_plan(Path(args.ranking),Path(args.audit),Path(args.output),
                                         args.sample_size,args.anchor_top,args.min_separation_km,args.seed)
        elif args.command == "environment-fetch":
            from .environment_global import fetch_environment
            obj = fetch_environment(Path(args.plan),Path(args.old_dir),Path(args.dir),
                                    args.start,args.end,args.limit,args.max_kb,
                                    args.connect_timeout,args.read_timeout,args.retries,args.retry_wait)
        elif args.command == "environment-summary":
            from .environment_global import summarize_environment
            obj = summarize_environment(Path(args.plan),Path(args.old_dir),Path(args.dir),
                                        Path(args.csv),Path(args.report),args.start,args.end)
        elif args.command == "landcover-search":
            from .landcover_modis import search_modis_landcover
            obj = search_modis_landcover(args.year)
        elif args.command == "landcover-download":
            from .landcover_modis import download_modis_landcover
            obj = download_modis_landcover(args.year,Path(args.dir),args.max_mb)
        elif args.command == "landcover-summary":
            from .landcover_modis import summarize_modis_landcover
            obj = summarize_modis_landcover(Path(args.hdf),Path(args.ranking),
                                            Path(args.csv),Path(args.report),args.year)
        elif args.command == "environment-diagnostic":
            from .environment_diagnostic import produce_diagnostic
            obj = produce_diagnostic(Path(args.plan),Path(args.climate),Path(args.landcover),
                                     Path(args.csv),Path(args.report))
        elif args.command == "appeears-layers":
            from .appeears_landcover import get_layers
            obj = get_layers(args.product)
        elif args.command == "appeears-plan":
            from .appeears_landcover import build_point_plan
            obj = build_point_plan(Path(args.environment_plan), Path(args.output),
                                   args.year,args.limit,args.points_per_region,
                                   args.spacing_km,args.product,args.layer)
        elif args.command == "appeears-auth-check":
            from .appeears_landcover import authenticate
            authenticate(username=args.username)
            obj = {"status":"authenticated", "service":"NASA AppEEARS", "note":"Token no mostrado ni guardado; no se envió ninguna tarea"}
        elif args.command == "appeears-submit":
            from .appeears_landcover import submit_plan, authenticate
            if not args.confirm: raise ValueError('Para enviar a NASA agregá --confirm')
            token = authenticate(username=args.username)
            obj = submit_plan(Path(args.plan),Path(args.job),token)
        elif args.command == "appeears-status":
            from .appeears_landcover import task_status, authenticate
            obj = task_status(Path(args.job),authenticate(username=args.username))
        elif args.command == "appeears-files":
            from .appeears_landcover import bundle_files, authenticate
            obj = bundle_files(Path(args.job),authenticate(username=args.username))
        elif args.command == "appeears-download":
            from .appeears_landcover import download_bundle, authenticate
            obj = download_bundle(Path(args.job),Path(args.dir),args.max_mb,
                                  authenticate(username=args.username))
        elif args.command == "appeears-preview":
            from .appeears_landcover import preview_csv
            obj = preview_csv(Path(args.dir))
        elif args.command == "geology-metadata":
            from .geology_glim import inspect_layer
            obj = inspect_layer(timeout=args.timeout)
        elif args.command == "geology-plan":
            from .geology_glim import build_plan
            obj = build_plan(Path(args.environment_plan),Path(args.output),
                             args.limit,args.points_per_region,args.spacing_km,args.region_ids)
        elif args.command == "geology-fetch":
            from .geology_glim import fetch_points
            obj = fetch_points(Path(args.plan),Path(args.dir),args.limit,args.timeout)
        elif args.command == "geology-summary":
            from .geology_glim import summarize
            obj = summarize(Path(args.plan),Path(args.dir),Path(args.csv),Path(args.report))
        elif args.command == "geology-boundaries-fetch":
            from .geology_refinement import fetch_boundary_clips
            obj = fetch_boundary_clips(Path(args.plan), Path(args.point_dir), Path(args.dir),
                                       args.region_id, args.limit, args.radius_km, args.timeout)
        elif args.command == "geology-boundaries-summary":
            from .geology_refinement import summarize_boundary_clips
            obj = summarize_boundary_clips(Path(args.plan), Path(args.point_dir), Path(args.dir),
                                           Path(args.csv), Path(args.report), args.region_id, args.radius_km)
        elif args.command == "geology-terrain-bboxes":
            from .geology_refinement import terrain_bboxes
            obj = terrain_bboxes(Path(args.plan), Path(args.point_dir), Path(args.output),
                                 args.region_id, args.half_width_km)
        elif args.command == "nasadem-plan":
            from .nasadem_highres import build_plan
            obj = build_plan(Path(args.rois), Path(args.output))
        elif args.command == "nasadem-search":
            from .nasadem_highres import search_tiles
            obj = search_tiles(Path(args.plan), Path(args.output))
        elif args.command == "nasadem-download":
            from .nasadem_highres import download_tiles
            obj = download_tiles(Path(args.plan), Path(args.search), Path(args.dir),
                                 limit=args.limit, max_mb=args.max_mb)
        elif args.command == "nasadem-analyze":
            from .nasadem_highres import analyze_area
            point = args.point_id
            if not point.startswith('r026_c146_p') or len(point)>32:
                raise ValueError('Indicar ID argentino esperado, p04 o p08')
            stem = point.rsplit('_',1)[-1]
            out = args.output_nc or f'data/processed/nasadem_argentina_{stem}.nc'
            rep = args.report or f'data/reports/nasadem_argentina_{stem}.json'
            obj = analyze_area(Path(args.plan), Path(args.dir), Path(args.boundaries_csv),
                               point, Path(out), Path(rep),
                               Path(args.etopo) if args.etopo else None,
                               slope_threshold_deg=args.slope_threshold_deg)
        elif args.command == "nasadem-compare":
            from .nasadem_highres import compare_areas
            obj = compare_areas(Path(args.p04),Path(args.p08),Path(args.output))
        elif args.command == "mars-targets":
            from .mars_profiles_v12 import targets_catalog
            obj = targets_catalog()
        elif args.command == "mars-profiles-build":
            from .mars_profiles_v12 import build_profiles
            obj = build_profiles(Path(args.mars),args.targets,args.spacing_km,args.samples,
                                 Path(args.dir),Path(args.manifest))
        elif args.command == "mars-profiles-screen":
            from .mars_profiles_v12 import screen_profiles
            obj = screen_profiles(Path(args.manifest),Path(args.earth),Path(args.catalog),
                                  Path(args.dir),Path(args.report),args.top,
                                  args.min_separation_km,args.max_abs_lat,args.min_patch_coverage)
        elif args.command == "mars-profiles-compare":
            from .mars_profiles_v12 import compare_profiles
            obj = compare_profiles(Path(args.screen_report),Path(args.csv),Path(args.report),
                                   args.watch,args.top_n)
        elif args.command == "mars-audit-rankings":
            from .mars_profiles_audit_v121 import audit_rankings
            obj = audit_rankings(Path(args.screen_report),Path(args.manifest),Path(args.dir),
                                 tuple(int(k) for k in args.top_ks.split(',')),
                                 args.scenarios,args.seed,
                                 tuple(v.strip() for v in args.watch.split(',') if v.strip()))
        elif args.command == "mars-audit-scales":
            from .mars_profiles_audit_v121 import audit_scales
            obj = audit_scales(Path(args.screen_report),Path(args.manifest),
                               Path(args.earth),Path(args.mars),Path(args.catalog),
                               Path(args.dir),args.scales,args.top_k)
        elif args.command == "mars-geology-source":
            from .mars_geology_v122 import source_metadata
            obj = source_metadata(timeout=args.timeout)
        elif args.command == "mars-geology-plan":
            from .mars_geology_v122 import plan_geology
            obj = plan_geology(Path(args.manifest),Path(args.output),
                               args.points_per_profile,args.radius_km)
        elif args.command == "mars-geology-fetch":
            from .mars_geology_v122 import fetch_geology
            obj = fetch_geology(Path(args.plan),Path(args.dir),args.limit,args.timeout)
        elif args.command == "mars-geology-summary":
            from .mars_geology_v122 import summarize_geology
            obj = summarize_geology(Path(args.plan),Path(args.dir),Path(args.csv),Path(args.report))
        elif args.command == "mars-domain-report":
            from .mars_domain_v122 import evaluate_domain
            obj = evaluate_domain(Path(args.audit),Path(args.csv),Path(args.report))
        elif args.command == "mars-evidence-matrix":
            from .mars_domain_v122 import evidence_matrix
            obj = evidence_matrix(Path(args.mars),Path(args.domain),Path(args.glim),
                                  Path(args.screen),Path(args.csv),Path(args.report),args.watch)
        elif args.command == "mars-multicriteria-build":
            from .mars_multicriteria_v130 import build_multicriteria
            obj = build_multicriteria(Path(args.matrix),Path(args.domain),
                Path(args.mars_geology),Path(args.glim),Path(args.screen),
                Path(args.csv),Path(args.report),Path(args.markdown),args.shortlist_top,
                None if args.without_climate else Path(args.climate_report),
                Path(args.audit_report),Path(args.scales_report))
        elif args.command == "mars-multicriteria-review":
            from .mars_multicriteria_v130 import review_multicriteria
            obj = review_multicriteria(Path(args.report),args.profile)
        elif args.command == "mars-geology-correspondence-build":
            from .mars_geology_correspondence_v131 import build_correspondences
            obj = build_correspondences(Path(args.multicriteria),Path(args.mars_geology),
                Path(args.domain),Path(args.glim),Path(args.screen),Path(args.csv),
                Path(args.report),Path(args.markdown),args.top_n)
        elif args.command == "mars-geology-correspondence-review":
            from .mars_geology_correspondence_v131 import review_correspondences
            obj = review_correspondences(Path(args.report),args.profile,args.region,args.limit)
        elif args.command == "mars-geology-local-review":
            from .mars_geology_correspondence_v131 import review_local_nasadem
            obj = review_local_nasadem(Path(args.p04),Path(args.p08),Path(args.report))
        elif args.command == 'mars-uncertainty-build':
            from .mars_uncertainty_v132 import build_uncertainty
            obj = build_uncertainty(Path(args.correspondence),Path(args.screen),
                Path(args.manifest),Path(args.audit),Path(args.scales),
                Path(args.csv),Path(args.report),Path(args.markdown),
                args.profile, tuple(x.strip() for x in args.candidates.split(',') if x.strip()),
                tuple(int(x.strip()) for x in args.top_ks.split(',')))
        elif args.command == 'mars-uncertainty-review':
            from .mars_uncertainty_v132 import review_uncertainty
            obj = review_uncertainty(Path(args.report),args.region)
        elif args.command == 'mars-sensitivity-all-build':
            from .mars_sensitivity_v204 import build_all_sensitivity
            obj=build_all_sensitivity(Path(args.data_root),Path(args.output_dir))
        elif args.command == 'mars-sensitivity-all-review':
            from .mars_sensitivity_v204 import review_all_sensitivity
            obj=review_all_sensitivity(Path(args.report),args.region)
        elif args.command == 'mars-external-benchmark-build':
            from .mars_external_validation_v133 import build_external_validation
            obj=build_external_validation(Path(args.benchmark),Path(args.screen),Path(args.manifest),
                Path(args.catalog),Path(args.domain),Path(args.scales),
                Path(args.csv),Path(args.report),Path(args.markdown))
        elif args.command == 'mars-external-benchmark-review':
            from .mars_external_validation_v133 import review_external_validation
            obj=review_external_validation(Path(args.report),args.case)
        elif args.command == 'mars-rover-import-geotiff':
            from .rover_geotiff_v21 import import_rover_geotiff
            obj=import_rover_geotiff(Path(args.input),Path(args.output),size=args.size,
                                    center_col=args.col,center_row=args.row,
                                    cell_size_m=args.cell_size_m)
        elif args.command == 'mars-v2-build':
            from .mars_v2 import build_v2
            obj = build_v2(Path(args.data_root), Path(args.output_dir),
                           fetch_climate=args.fetch_climate,fetch_lunar=args.fetch_lunar,
                           climate_download_limit=args.climate_limit,
                           mars_context_km=args.mars_context_km,
                           full_sensitivity_report=(Path(args.full_sensitivity_report) if args.full_sensitivity_report else None))
        print(json.dumps(obj, indent=2, ensure_ascii=False, default=str))
        return 0
    except (ValueError, RuntimeError, OSError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
