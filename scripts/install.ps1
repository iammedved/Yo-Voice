# Requires Python 3.12. Creates .venv, installs requirements, optional HKCU autostart.
param(
    [switch]$NoAutostart,
    [switch]$Launch
)

$ErrorActionPreference = "Stop"
$Root = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
Set-Location -LiteralPath $Root
$env:YO_ROOT = $Root
if (-not $env:PYTHONPATH) {
    $env:PYTHONPATH = $Root
} elseif ($env:PYTHONPATH -notlike "*$Root*") {
    $env:PYTHONPATH = "$Root;$env:PYTHONPATH"
}

function Get-Python312 {
    if (Get-Command py -ErrorAction SilentlyContinue) {
        $exe = & py -3.12 -c "import sys; print(sys.executable)" 2>$null
        if ($LASTEXITCODE -eq 0 -and $exe) {
            return ([string]$exe).Trim()
        }
    }
    foreach ($name in @("python3.12", "python")) {
        if (-not (Get-Command $name -ErrorAction SilentlyContinue)) {
            continue
        }
        $out = & $name -c "import sys; print('%d.%d' % sys.version_info[:2]); print(sys.executable)" 2>$null
        if ($LASTEXITCODE -ne 0 -or -not $out) {
            continue
        }
        $lines = @($out)
        if ($lines.Count -ge 2 -and $lines[0].Trim() -eq "3.12") {
            return $lines[1].Trim()
        }
    }
    return $null
}

$Python = Get-Python312
if (-not $Python) {
    Write-Error "Python 3.12 is required (py -3.12 or python 3.12 on PATH)."
    exit 1
}

Write-Host "-> virtualenv ($Python)"
& $Python -m venv (Join-Path $Root ".venv")
$VenvPy = Join-Path $Root ".venv\Scripts\python.exe"
if (-not (Test-Path -LiteralPath $VenvPy)) {
    throw "venv python missing: $VenvPy"
}

& $VenvPy -m pip install --upgrade pip wheel
if ($LASTEXITCODE -ne 0) {
    throw "pip bootstrap failed"
}

Write-Host "-> dependencies (Whisper/NLLB models download on first use, not now)"
$Req = Join-Path $Root "requirements.txt"
$Lines = Get-Content -LiteralPath $Req
$Core = @($Lines | Where-Object { $_ -notmatch '^\s*nvidia-' })
$Nvidia = @($Lines | Where-Object { $_ -match '^\s*nvidia-' })
$CoreFile = Join-Path $env:TEMP "yo-voice-requirements-core.txt"
$Core | Set-Content -LiteralPath $CoreFile -Encoding UTF8
& $VenvPy -m pip install -r $CoreFile
if ($LASTEXITCODE -ne 0) {
    throw "pip install failed"
}
& $VenvPy -m pip install -e $Root
if ($LASTEXITCODE -ne 0) {
    throw "editable install failed"
}
foreach ($pkg in $Nvidia) {
    $name = ([string]$pkg).Trim()
    if (-not $name -or $name.StartsWith("#")) {
        continue
    }
    & $VenvPy -m pip install $name
    if ($LASTEXITCODE -ne 0) {
        Write-Warning "Optional CUDA package failed (ignored): $name"
    }
}

if (-not $NoAutostart) {
    & $VenvPy -c "from yo.autostart_win import enable; print(enable())"
    if ($LASTEXITCODE -ne 0) {
        throw "autostart registration failed"
    }
    Write-Host "-> autostart HKCU Run Yo-Voice"
}

Write-Host ""
Write-Host "Yo-Voice (Ёхо) installed."
Write-Host "  Run:  powershell -File `"$(Join-Path $Root 'scripts\run.ps1')`""
Write-Host "  Or:   `"$(Join-Path $Root 'scripts\yo-voice.cmd')`""
Write-Host "  Hotkey after the background process starts: ё or ``"
Write-Host "First listen downloads the recognition model (~0.8 GB)."

if ($Launch) {
    Write-Host "-> launching"
    & (Join-Path $Root "scripts\run.ps1")
}
