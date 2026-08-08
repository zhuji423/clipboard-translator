#Requires -Version 5.1
<#
.SYNOPSIS
  Build the Chrome/Edge MV3 extension into extension/dist and optionally zip it.
#>
param(
    [switch]$Zip
)

$ErrorActionPreference = "Stop"
$Root = Resolve-Path (Join-Path $PSScriptRoot "..")
$Ext = Join-Path $Root "extension"
Push-Location $Ext
try {
    if (-not (Test-Path (Join-Path $Ext "node_modules"))) {
        npm install
        if ($LASTEXITCODE -ne 0) { throw "npm install failed" }
    }

    npm run build
    if ($LASTEXITCODE -ne 0) { throw "extension build failed" }

    function Get-AppVersion {
        $text = Get-Content -Raw (Join-Path $Root "version.py")
        if ($text -match '__version__\s*=\s*"([^"]+)"') {
            return $Matches[1]
        }
        throw "Cannot parse __version__ from version.py"
    }

    if ($Zip) {
        $Version = Get-AppVersion
        $OutDir = Join-Path $Root "dist\extension"
        New-Item -ItemType Directory -Force -Path $OutDir | Out-Null
        $ZipPath = Join-Path $OutDir "ClipboardTranslator-extension-$Version.zip"
        if (Test-Path $ZipPath) { Remove-Item -Force $ZipPath }
        Compress-Archive -Path (Join-Path $Ext "dist\*") -DestinationPath $ZipPath
        Write-Host "Extension zip: $ZipPath"
    }

    Write-Host "Extension dist: $(Join-Path $Ext 'dist')"
}
finally {
    Pop-Location
}
