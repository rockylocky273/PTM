# Mars Analog Engine V2.0.4 — 25 auditorías completas de sensibilidad + atlas.
# No sobreescribe el dataset histórico ni los informes V1.3.x.
param([switch]$SoloAuditorias, [switch]$SinDescargas, [switch]$ForzarInstalacion)
$ErrorActionPreference = 'Stop'
Set-Location $PSScriptRoot
$historico = Join-Path $PSScriptRoot '..\mars_analog_engine_v1_3_3'
$dataRoot = Join-Path $historico 'data'
if (-not (Test-Path (Join-Path $dataRoot 'reports\mars_uncertainty_v1_3_2.json'))) {
    if (Test-Path '.\data\reports\mars_uncertainty_v1_3_2.json') {
        $dataRoot = Join-Path $PSScriptRoot 'data'
    } else {
        throw 'No encuentro los datos V1.3.2 en la carpeta histórica V1.3.3. Conservá su directorio data y extraé el ZIP junto a ella.'
    }
}
$historicPython = Join-Path $historico '.venv\Scripts\python.exe'
if ((Test-Path $historicPython) -and -not $ForzarInstalacion) {
    $python = $historicPython
    Write-Host 'Reutilizando el Python histórico.' -ForegroundColor Cyan
} else {
    $python = Join-Path $PSScriptRoot '.venv\Scripts\python.exe'
    if (-not (Test-Path $python)) {
        py -3.12 -m venv .venv
        if ($LASTEXITCODE -ne 0) { throw 'Error creando Python 3.12' }
    }
    & $python -m pip install -e '.[dev]'
    if ($LASTEXITCODE -ne 0) { throw 'Error instalando el paquete' }
}
$out = Join-Path $PSScriptRoot 'data\reports\mars_v2_0'
New-Item -ItemType Directory -Path $out -Force | Out-Null
$oldPath=$env:PYTHONPATH
try {
    $env:PYTHONPATH = Join-Path $PSScriptRoot 'src'
    Write-Host 'V2.0.4 — sensibilidad completa para las 25 celdas GLiM...' -ForegroundColor Cyan
    & $python -m mars_analog.data mars-sensitivity-all-build --data-root $dataRoot --output-dir $out
    if ($LASTEXITCODE -ne 0) { throw 'Error en pruebas de sensibilidad; revisá qué archivo histórico falta.' }
    if ($SoloAuditorias) {
        Write-Host 'Completado: auditorías CSV/JSON/Markdown en data\reports\mars_v2_0.' -ForegroundColor Green
    } else {
        $args = @('-m','mars_analog.data','mars-v2-build','--data-root',$dataRoot,
                  '--output-dir',$out,'--mars-context-km','1600',
                  '--full-sensitivity-report',(Join-Path $out 'candidate_sensitivity_v204.json'))
        if (-not $SinDescargas) { $args += @('--fetch-climate','--fetch-lunar','--climate-limit','25') }
        Write-Host 'Integrando las 25 auditorías al atlas planetario...' -ForegroundColor Cyan
        & $python @args
        if ($LASTEXITCODE -ne 0) { throw 'No se pudo crear el atlas V2.0.4.' }
        $dashboard=Join-Path $out 'mars_analog_dashboard_v2.html'
        if (-not (Test-Path $dashboard)) { throw 'Falta el archivo HTML.' }
        Start-Process $dashboard
        Write-Host 'V2.0.4 lista: atlas actualizado con 25 auditorías.' -ForegroundColor Green
    }
} finally {
    $env:PYTHONPATH=$oldPath
}
