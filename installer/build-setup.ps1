# Build E:\yo-voice\Yo-Voice-Setup.exe (wizard: folder picker + progress bar).
# Prefers Inno Setup (ISCC). If ISCC is missing, packs a self-extracting
# Setup.exe from installer\YoSetup.cs + a zip of dist\Yo-Voice.
# Also copies the result to dist\Yo-Voice-Setup.exe for the source tree.
param(
    [int]$WaitSeconds = 0,
    [switch]$SkipInno,
    [switch]$ForceSfx
)

$ErrorActionPreference = "Stop"
$InstallerDir = $PSScriptRoot
$Root = (Resolve-Path (Join-Path $InstallerDir "..")).Path
$Dist = Join-Path $Root "dist"
$Onedir = Join-Path $Dist "Yo-Voice"
$AppExe = Join-Path $Onedir "Yo-Voice.exe"
$DeliverDir = "E:\yo-voice"
$SetupOut = Join-Path $DeliverDir "Yo-Voice-Setup.exe"
$SetupDistCopy = Join-Path $Dist "Yo-Voice-Setup.exe"
$Iss = Join-Path $InstallerDir "yo-voice.iss"
$StubCs = Join-Path $InstallerDir "YoSetup.cs"
$UninstOut = Join-Path $InstallerDir "Uninstall.exe"
$Ico = Join-Path $Root "assets\yo-voice.ico"
$Csc = Join-Path $env:WINDIR "Microsoft.NET\Framework64\v4.0.30319\csc.exe"
if (-not (Test-Path -LiteralPath $Csc)) {
    $Csc = Join-Path $env:WINDIR "Microsoft.NET\Framework\v4.0.30319\csc.exe"
}

function Get-Iscc {
    foreach ($name in @("iscc", "ISCC")) {
        $cmd = Get-Command $name -ErrorAction SilentlyContinue
        if ($cmd -and $cmd.Source) {
            return $cmd.Source
        }
    }
    foreach ($p in @(
            "${env:ProgramFiles(x86)}\Inno Setup 6\ISCC.exe",
            "${env:ProgramFiles}\Inno Setup 6\ISCC.exe",
            "$env:LOCALAPPDATA\Programs\Inno Setup 6\ISCC.exe",
            "${env:ProgramFiles(x86)}\Inno Setup 5\ISCC.exe"
        )) {
        if ($p -and (Test-Path -LiteralPath $p)) {
            return $p
        }
    }
    return $null
}

function Install-InnoSetup {
    $winget = Get-Command winget -ErrorAction SilentlyContinue
    if (-not $winget) {
        Write-Warning "winget not found; cannot install Inno Setup."
        return $null
    }
    Write-Host "-> winget install JRSoftware.InnoSetup"
    & winget install --id JRSoftware.InnoSetup -e --accept-package-agreements --accept-source-agreements --disable-interactivity
    return (Get-Iscc)
}

function Wait-AppExe {
    param([int]$Seconds)
    if ($Seconds -le 0) {
        return (Test-Path -LiteralPath $AppExe)
    }
    $deadline = (Get-Date).AddSeconds($Seconds)
    Write-Host "-> waiting up to $Seconds s for $AppExe"
    while ((Get-Date) -lt $deadline) {
        if (Test-Path -LiteralPath $AppExe) {
            return $true
        }
        Start-Sleep -Seconds 15
    }
    return (Test-Path -LiteralPath $AppExe)
}

function Compile-UninstallExe {
    if (-not (Test-Path -LiteralPath $Csc)) {
        Write-Warning "csc.exe not found; skipping Uninstall.exe helper."
        return $false
    }
    if (-not (Test-Path -LiteralPath $StubCs)) {
        throw "Missing $StubCs"
    }
    $refs = @(
        "/reference:System.Windows.Forms.dll",
        "/reference:System.Drawing.dll",
        "/reference:System.IO.Compression.dll",
        "/reference:System.IO.Compression.FileSystem.dll"
    )
    $iconArg = @()
    if (Test-Path -LiteralPath $Ico) {
        $iconArg = @("/win32icon:$Ico")
    }
    Write-Host "-> csc Uninstall.exe"
    & $Csc /nologo /optimize+ /target:winexe /platform:x64 @iconArg @refs /out:$UninstOut $StubCs
    if ($LASTEXITCODE -ne 0 -or -not (Test-Path -LiteralPath $UninstOut)) {
        throw "csc failed to build Uninstall.exe"
    }
    return $true
}

function New-OnedirZip {
    param([string]$ZipPath)
    if (Test-Path -LiteralPath $ZipPath) {
        Remove-Item -LiteralPath $ZipPath -Force
    }
    Add-Type -AssemblyName System.IO.Compression
    Add-Type -AssemblyName System.IO.Compression.FileSystem
    Write-Host "-> zip $Onedir -> $ZipPath"
    [System.IO.Compression.ZipFile]::CreateFromDirectory($Onedir, $ZipPath, [System.IO.Compression.CompressionLevel]::Optimal, $false)
}

function Build-Sfx {
    if (-not (Test-Path -LiteralPath $Csc)) {
        throw "csc.exe not found; cannot build SFX Setup.exe"
    }
    New-Item -ItemType Directory -Force -Path $Dist | Out-Null
    $stub = Join-Path $Dist "Yo-Voice-Setup.stub.exe"
    $zip = Join-Path $Dist "Yo-Voice-payload.zip"
    $refs = @(
        "/reference:System.Windows.Forms.dll",
        "/reference:System.Drawing.dll",
        "/reference:System.IO.Compression.dll",
        "/reference:System.IO.Compression.FileSystem.dll"
    )
    $iconArg = @()
    if (Test-Path -LiteralPath $Ico) {
        $iconArg = @("/win32icon:$Ico")
    }
    Write-Host "-> csc Setup stub"
    & $Csc /nologo /optimize+ /target:winexe /platform:x64 @iconArg @refs /out:$stub $StubCs
    if ($LASTEXITCODE -ne 0 -or -not (Test-Path -LiteralPath $stub)) {
        throw "csc failed to build Setup stub"
    }
    New-OnedirZip -ZipPath $zip
    $zipLen = [int64](Get-Item -LiteralPath $zip).Length
    Write-Host "-> append payload ($zipLen bytes) -> $SetupOut"
    $out = [System.IO.File]::Create($SetupOut)
    try {
        $inStub = [System.IO.File]::OpenRead($stub)
        try { $inStub.CopyTo($out) } finally { $inStub.Dispose() }
        $inZip = [System.IO.File]::OpenRead($zip)
        try { $inZip.CopyTo($out) } finally { $inZip.Dispose() }
        $lenBytes = [BitConverter]::GetBytes($zipLen)
        $out.Write($lenBytes, 0, 8)
        $magic = [System.Text.Encoding]::ASCII.GetBytes("YOVSETUP")
        $out.Write($magic, 0, 8)
    }
    finally {
        $out.Dispose()
    }
    Remove-Item -LiteralPath $stub -Force -ErrorAction SilentlyContinue
    Remove-Item -LiteralPath $zip -Force -ErrorAction SilentlyContinue
    if (-not (Test-Path -LiteralPath $SetupOut)) {
        throw "SFX Setup.exe was not written"
    }
}

function Build-Inno {
    param([string]$Iscc)
    New-Item -ItemType Directory -Force -Path $Dist | Out-Null
    New-Item -ItemType Directory -Force -Path $DeliverDir | Out-Null
    Write-Host "-> ISCC $Iss"
    & $Iscc $Iss
    if ($LASTEXITCODE -ne 0) {
        throw "ISCC failed with exit $LASTEXITCODE"
    }
    if (-not (Test-Path -LiteralPath $SetupOut)) {
        throw "ISCC did not produce $SetupOut"
    }
}

if (-not (Wait-AppExe -Seconds $WaitSeconds)) {
    throw "Missing $AppExe - build the PyInstaller onedir first, then re-run this script."
}

New-Item -ItemType Directory -Force -Path $DeliverDir | Out-Null

[void](Compile-UninstallExe)

$usedInno = $false
if (-not $ForceSfx) {
    $iscc = $null
    if (-not $SkipInno) {
        $iscc = Get-Iscc
        if (-not $iscc) {
            $iscc = Install-InnoSetup
        }
    }
    if ($iscc) {
        try {
            Build-Inno -Iscc $iscc
            $usedInno = $true
        }
        catch {
            Write-Warning "Inno Setup compile failed: $($_.Exception.Message)"
            Write-Warning "Falling back to self-extracting Setup.exe"
        }
    }
    else {
        Write-Warning "ISCC.exe not found; building self-extracting Setup.exe"
    }
}

if (-not $usedInno) {
    Build-Sfx
}

if ((Resolve-Path -LiteralPath $SetupOut).Path -ne (Join-Path $Dist "Yo-Voice-Setup.exe")) {
    Copy-Item -LiteralPath $SetupOut -Destination $SetupDistCopy -Force
}

$item = Get-Item -LiteralPath $SetupOut
Write-Host ""
Write-Host "Setup: $($item.FullName)"
Write-Host ("Size:  {0:N1} MB" -f ($item.Length / 1MB))
if ($usedInno) {
    Write-Host "Kind:  Inno Setup"
}
else {
    Write-Host "Kind:  self-extracting (YoSetup.cs)"
}
Write-Host "Install: double-click E:\yo-voice\Yo-Voice-Setup.exe, choose the folder, wait for the progress bar."
Write-Host "Uninstall: Settings > Apps, or Uninstall.exe in the folder you chose."
