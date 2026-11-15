# Mars Analog Discovery Engine V2.0.2 - ejecución rápida SIN copiar GB de datos.
# Usa el entorno Python y datos V1.3.3 cuando están al lado de esta carpeta.
param([switch]$ForzarInstalacion)
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
    throw 'Faltan datos históricos: poné V2.0.2 junto a V1.3.3, o copiá su carpeta data en V2.0.'
}
if ((Test-Path $previousPython) -and -not $ForzarInstalacion) {
    $python = $previousPython
    Write-Host 'Reutilizando Python V1.3.3; sin instalar paquetes ni copiar datos.'
} else {
    $python = '.\.venv\Scripts\python.exe'
    if (-not (Test-Path $python)) {
        py -3.12 -m venv .venv
        if ($LASTEXITCODE -ne 0) { throw 'No se pudo crear entorno Python 3.12' }
    }
    & $python -m pip install -e '.[dev]'
    if ($LASTEXITCODE -ne 0) { throw 'Error al instalar dependencias V2.0' }
}
$prior = $env:PYTHONPATH
try {
    $env:PYTHONPATH = (Join-Path $PSScriptRoot 'src')
    & $python -m mars_analog.data mars-v2-build --data-root $dataRoot --output-dir '.\data\reports\mars_v2_0'
    if ($LASTEXITCODE -ne 0) { throw 'V2.0.2 detectó datos faltantes o inconsistentes; revisar mensaje de error.' }
} finally {
    $env:PYTHONPATH = $prior
}
$dashboard = '.\data\reports\mars_v2_0\mars_analog_dashboard_v2.html'
if (-not (Test-Path $dashboard)) { throw 'No se creó el panel HTML.' }
Start-Process $dashboard
Write-Host 'V2.0.2 completada: panel HTML abierto; resultados en data\reports\mars_v2_0' -ForegroundColor Green
