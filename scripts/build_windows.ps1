#Requires -Version 5.1
<#
.SYNOPSIS
  Build ClipboardTranslator portable (onefile) + onedir for Inno Setup, then optionally compile the installer.
#>
param(
    [switch]$SkipInstaller,
    [string]$InnoCompiler = ""
)

$ErrorActionPreference = "Stop"
$Root = Resolve-Path (Join-Path $PSScriptRoot "..")
Set-Location $Root

function Get-AppVersion {
    $text = Get-Content -Raw (Join-Path $Root "version.py")
    if ($text -match '__version__\s*=\s*"([^"]+)"') {
        return $Matches[1]
    }
    throw "Cannot parse __version__ from version.py"
}

$Version = Get-AppVersion
Write-Host "Building ClipboardTranslator v$Version"

python -m pip install -r requirements.txt -r requirements-build.txt
if ($LASTEXITCODE -ne 0) { throw "pip install failed" }

if (Test-Path (Join-Path $Root "build")) {
    Remove-Item -Recurse -Force (Join-Path $Root "build")
}
if (Test-Path (Join-Path $Root "dist")) {
    Remove-Item -Recurse -Force (Join-Path $Root "dist")
}

python -m PyInstaller --noconfirm --clean clipboard_translator.spec
if ($LASTEXITCODE -ne 0) { throw "PyInstaller failed" }

$PortableSrc = Join-Path $Root "dist\ClipboardTranslator.exe"
$PortableDir = Join-Path $Root "dist\portable"
New-Item -ItemType Directory -Force -Path $PortableDir | Out-Null
$PortableName = "ClipboardTranslator-$Version-portable.exe"
Copy-Item -Force $PortableSrc (Join-Path $PortableDir $PortableName)

$AppDir = Join-Path $Root "dist\app"
if (-not (Test-Path (Join-Path $AppDir "ClipboardTranslator.exe"))) {
    throw "onedir output missing: dist\app\ClipboardTranslator.exe"
}

Write-Host "Portable: $(Join-Path $PortableDir $PortableName)"
Write-Host "App dir:  $AppDir"

if ($SkipInstaller) {
    Write-Host "SkipInstaller set; not compiling Inno Setup."
    exit 0
}

if (-not $InnoCompiler) {
    $candidates = @(
        "${env:LocalAppData}\Programs\Inno Setup 6\ISCC.exe",
        "${env:ProgramFiles(x86)}\Inno Setup 6\ISCC.exe",
        "${env:ProgramFiles}\Inno Setup 6\ISCC.exe"
    )
    foreach ($c in $candidates) {
        if (Test-Path $c) {
            $InnoCompiler = $c
            break
        }
    }
}

if (-not $InnoCompiler -or -not (Test-Path $InnoCompiler)) {
    Write-Warning "ISCC.exe not found. Install Inno Setup 6 or pass -InnoCompiler. onedir/portable are ready."
    exit 0
}

& $InnoCompiler "/DMyAppVersion=$Version" (Join-Path $Root "installer\setup.iss")
if ($LASTEXITCODE -ne 0) { throw "Inno Setup compile failed" }

$Setup = Join-Path $Root "dist\ClipboardTranslator-$Version-Setup.exe"
if (-not (Test-Path $Setup)) {
    throw "Expected installer missing: $Setup"
}
Write-Host "Installer: $Setup"
