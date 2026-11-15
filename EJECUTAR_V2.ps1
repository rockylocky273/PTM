# Mars Analog Engine V2.2 — atlas continuo mundial offline.
# Conserva sin cambios los datos históricos y revisiones científicas.
param(
    [switch]$SinDescargas,
    [switch]$SoloAuditorias,
    [switch]$SoloMapa,
    [switch]$SoloRover,
    [switch]$ForzarAuditorias,
    [switch]$ForzarInstalacion
)
$ErrorActionPreference = 'Stop'
Set-Location $PSScriptRoot
if ($SoloRover) { $SoloMapa = $true }
$historico = Join-Path $PSScriptRoot '..\mars_analog_engine_v1_3_3'
$dataRoot = Join-Path $historico 'data'
if (-not (Test-Path (Join-Path $dataRoot 'reports\mars_uncertainty_v1_3_2.json'))) {
    if (Test-Path '.\data\reports\mars_uncertainty_v1_3_2.json') {
        $dataRoot = Join-Path $PSScriptRoot 'data'
    } else {
        throw 'No encuentro los datos de V1.3.3. Extraé V2.2 junto a esa carpeta y conservá su data histórica.'
    }
}
$historicPython = Join-Path $historico '.venv\Scripts\python.exe'
if ((Test-Path $historicPython) -and -not $ForzarInstalacion) {
    $python = $historicPython
    Write-Host 'Reutilizando Python de V1.3.3.' -ForegroundColor Cyan
} else {
    $python = Join-Path $PSScriptRoot '.venv\Scripts\python.exe'
    if (-not (Test-Path $python)) {
        py -3.12 -m venv .venv
        if ($LASTEXITCODE -ne 0) { throw 'Error creando el entorno de Python 3.12' }
    }
    & $python -m pip install -e '.[dev]'
    if ($LASTEXITCODE -ne 0) { throw 'Error instalando el paquete' }
}
$out = Join-Path $PSScriptRoot 'data\reports\mars_v2_0'
New-Item -ItemType Directory -Path $out -Force | Out-Null
$oldPath=$env:PYTHONPATH
try {
    $env:PYTHONPATH = Join-Path $PSScriptRoot 'src'
    $auditoria = Join-Path $out 'candidate_sensitivity_v204.json'
    $anterior = Join-Path $PSScriptRoot '..\mars_analog_engine_v2_0_4\data\reports\mars_v2_0\candidate_sensitivity_v204.json'
    if (-not $SoloAuditorias -and -not $ForzarAuditorias -and -not (Test-Path $auditoria) -and (Test-Path $anterior)) {
        $auditoria = $anterior
        Write-Host 'Reutilizando las 25 auditorías ya calculadas en V2.0.4.' -ForegroundColor Cyan
    }
    if ($SoloAuditorias -or $ForzarAuditorias -or (-not $SoloMapa -and -not (Test-Path $auditoria))) {
        Write-Host 'Calculando auditorías individuales de sensibilidad...' -ForegroundColor Cyan
        & $python -m mars_analog.data mars-sensitivity-all-build --data-root $dataRoot --output-dir $out
        if ($LASTEXITCODE -ne 0) { throw 'Falló la auditoría V2.0.4; revisá los datos históricos.' }
        $auditoria = Join-Path $out 'candidate_sensitivity_v204.json'
    }
    if ($SoloAuditorias) {
        Write-Host 'Auditorías CSV/JSON/Markdown completadas.' -ForegroundColor Green
    } else {
        $build = @('-m','mars_analog.data','mars-v2-build','--data-root',$dataRoot,
                   '--output-dir',$out,'--mars-context-km','1600')
        if ($auditoria -and (Test-Path $auditoria)) { $build += @('--full-sensitivity-report',$auditoria) }
        if (-not $SinDescargas -and -not $SoloMapa) {
            $build += @('--fetch-climate','--fetch-lunar','--climate-limit','25')
        }
        Write-Host 'Generando el atlas V2.2 con rover 2D + terreno 3D offline...' -ForegroundColor Cyan
        & $python @build
        if ($LASTEXITCODE -ne 0) { throw 'Error al generar atlas V2.1; comprobá los informes y la malla global ETOPO.' }
        $dashboard = Join-Path $out 'mars_analog_dashboard_v2.html'
        if (-not (Test-Path $dashboard)) { throw 'No se generó el archivo HTML' }
        Start-Process $dashboard
        Write-Host 'V2.2 lista. Calculá una ruta en 2D y pulsá Terreno 3D · Explorar.' -ForegroundColor Green
    }
} finally {
    $env:PYTHONPATH = $oldPath
}
