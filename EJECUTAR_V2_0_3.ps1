# Mars Analog Engine V2.0.3 - climática, auditorías, mapamundi, Luna.
# Reutiliza Python y data de V1.3.3 para no duplicar descargas científicas.
param([switch]$ForzarInstalacion, [switch]$SinDescargas)
$ErrorActionPreference = 'Stop'
Set-Location $PSScriptRoot
$previous = '..\mars_analog_engine_v1_3_3'
$previousPython = Join-Path $previous '.venv\Scripts\python.exe'
$previousData = Join-Path $previous 'data'
if (Test-Path (Join-Path $previousData 'reports\mars_external_benchmark_v1_3_3.json')) {
    $dataRoot = $previousData
} elseif (Test-Path '.\data\reports\mars_external_benchmark_v1_3_3.json') {
    $dataRoot = '.\data'
} else {
    throw 'Faltan datos históricos: extraé V2.0.3 junto a mars_analog_engine_v1_3_3, o copiá su carpeta data.'
}
if ((Test-Path $previousPython) -and -not $ForzarInstalacion) {
    $python = $previousPython
    Write-Host 'Python histórico reutilizado, sin instalación.' -ForegroundColor Cyan
} else {
    $python = '.\.venv\Scripts\python.exe'
    if (-not (Test-Path $python)) {
        py -3.12 -m venv .venv
        if ($LASTEXITCODE -ne 0) { throw 'No se pudo crear el entorno Python 3.12' }
    }
    & $python -m pip install -e '.[dev]'
    if ($LASTEXITCODE -ne 0) { throw 'Fallo instalando dependencias' }
}
$prior = $env:PYTHONPATH
try {
    $env:PYTHONPATH = (Join-Path $PSScriptRoot 'src')
    $args = @('-m','mars_analog.data','mars-v2-build','--data-root',$dataRoot,'--output-dir','.\data\reports\mars_v2_0','--mars-context-km','1600')
    if (-not $SinDescargas) {
        $args += @('--fetch-climate','--fetch-lunar','--climate-limit','25')
        Write-Host 'Reutilizando clima histórico; completando datos faltantes y LOLA lunar (si hay Internet)...' -ForegroundColor Cyan
    } else {
        Write-Host 'Modo sin descargas: clima y Luna solo desde archivos guardados.' -ForegroundColor Yellow
    }
    & $python @args
    if ($LASTEXITCODE -ne 0) { throw 'V2.0.3 no pudo construir el panel. Revisá el error arriba.' }
} finally {
    $env:PYTHONPATH = $prior
}
$dashboard = '.\data\reports\mars_v2_0\mars_analog_dashboard_v2.html'
if (-not (Test-Path $dashboard)) { throw 'No se creó el panel HTML.' }
Start-Process $dashboard
Write-Host 'V2.0.3: panel HTML abierto. Auditorías y CSV en data\reports\mars_v2_0' -ForegroundColor Green
