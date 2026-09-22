# Start python -m yo from the project venv.
$ErrorActionPreference = "Stop"
$Root = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
Set-Location -LiteralPath $Root
$env:YO_ROOT = $Root
$env:PYTHONUNBUFFERED = "1"
if (-not $env:PYTHONPATH) {
    $env:PYTHONPATH = $Root
} elseif ($env:PYTHONPATH -notlike "*$Root*") {
    $env:PYTHONPATH = "$Root;$env:PYTHONPATH"
}

$VenvPy = Join-Path $Root ".venv\Scripts\python.exe"
if (-not (Test-Path -LiteralPath $VenvPy)) {
    throw "Missing venv at $VenvPy. Run scripts\install.ps1 first."
}

& $VenvPy -m yo @args
exit $LASTEXITCODE
