# Build dist\Yo-Voice\ (onedir). Run from repo root or this folder.
$ErrorActionPreference = "Stop"

$Packaging = $PSScriptRoot
$Root = (Resolve-Path (Join-Path $Packaging "..")).Path
$Python = Join-Path $Root ".venv\Scripts\python.exe"
$Spec = Join-Path $Packaging "yo-voice.spec"
$Ico = Join-Path $Root "assets\yo-voice.ico"
$Logo = Join-Path $Root "assets\logo.png"
$Dist = Join-Path $Root "dist"
$Work = Join-Path $Root "build\pyinstaller"

Set-Location $Root

if (-not (Test-Path $Python)) {
    throw "Missing venv interpreter: $Python"
}

& $Python -m pip install --disable-pip-version-check pyinstaller faster-whisper nvidia-cublas-cu12 nvidia-cuda-runtime-cu12 nvidia-cuda-nvrtc-cu12
if ($LASTEXITCODE -ne 0) { throw "pip install pyinstaller/faster-whisper/cuda wheels failed" }

if (-not (Test-Path $Ico)) {
    $src = $Logo
    if (-not (Test-Path $src)) { $src = Join-Path $Root "assets\mascot.png" }
    if (-not (Test-Path $src)) { throw "No logo/mascot PNG to build yo-voice.ico" }
    & $Python -c @"
from pathlib import Path
from PIL import Image
src = Path(r'$src')
out = Path(r'$Ico')
img = Image.open(src).convert('RGBA')
w, h = img.size
side = max(w, h)
canvas = Image.new('RGBA', (side, side), (0, 0, 0, 0))
canvas.paste(img, ((side - w) // 2, (side - h) // 2), img)
master = canvas.resize((256, 256), Image.Resampling.LANCZOS)
master.save(out, format='ICO', sizes=[(16,16),(24,24),(32,32),(48,48),(64,64),(128,128),(256,256)])
print('wrote', out)
"@
    if ($LASTEXITCODE -ne 0) { throw "failed to write $Ico" }
}

New-Item -ItemType Directory -Force -Path $Dist, $Work | Out-Null

& $Python -m PyInstaller --noconfirm --clean --distpath $Dist --workpath $Work $Spec
if ($LASTEXITCODE -ne 0) { throw "PyInstaller failed" }

$Exe = Join-Path $Dist "Yo-Voice\Yo-Voice.exe"
if (-not (Test-Path $Exe)) { throw "Build finished but $Exe is missing" }
Write-Host "Built $Exe"
