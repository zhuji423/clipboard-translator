#Requires -Version 5.1
<#
.SYNOPSIS
  Build the Chrome/Edge MV3 extension into extension/dist and optionally zip it.

.PARAMETER Zip
  Create dist/extension/ClipboardTranslator-extension-{version}.zip (includes manifest key for local ID).

.PARAMETER StoreZip
  Create a Partner Center upload zip with manifest "key" removed (required for Edge Add-ons).
#>
param(
    [switch]$Zip,
    [switch]$StoreZip
)

$ErrorActionPreference = "Stop"
$Root = Resolve-Path (Join-Path $PSScriptRoot "..")
$Ext = Join-Path $Root "extension"
Push-Location $Ext
try {
    if (-not (Test-Path (Join-Path $Ext "node_modules"))) {
        cmd /c "npm install"
        if ($LASTEXITCODE -ne 0) { throw "npm install failed" }
    }

    cmd /c "npm run build"
    if ($LASTEXITCODE -ne 0) { throw "extension build failed" }

    function Get-AppVersion {
        $text = Get-Content -Raw (Join-Path $Root "version.py")
        if ($text -match '__version__\s*=\s*"([^"]+)"') {
            return $Matches[1]
        }
        throw "Cannot parse __version__ from version.py"
    }

    $Version = Get-AppVersion
    $OutDir = Join-Path $Root "dist\extension"
    New-Item -ItemType Directory -Force -Path $OutDir | Out-Null

    if ($Zip) {
        $ZipPath = Join-Path $OutDir "ClipboardTranslator-extension-$Version.zip"
        if (Test-Path $ZipPath) { Remove-Item -Force $ZipPath }
        Compress-Archive -Path (Join-Path $Ext "dist\*") -DestinationPath $ZipPath
        Write-Host "Extension zip: $ZipPath"
    }

    if ($StoreZip) {
        $Stage = Join-Path $Root "dist\extension\store-stage"
        if (Test-Path $Stage) { Remove-Item -Recurse -Force $Stage }
        New-Item -ItemType Directory -Force -Path $Stage | Out-Null
        Copy-Item -Recurse -Force (Join-Path $Ext "dist\*") $Stage
        Get-ChildItem -Path $Stage -Filter "*.map" -Recurse | Remove-Item -Force
        $ManifestPath = Join-Path $Stage "manifest.json"
        $StripJs = Join-Path $Stage "_strip_key.js"
        @(
            "const fs = require('fs');"
            "const p = process.argv[2];"
            "const m = JSON.parse(fs.readFileSync(p, 'utf8'));"
            "delete m.key;"
            "fs.writeFileSync(p, JSON.stringify(m, null, 2) + '\n');"
        ) | Set-Content -Encoding ASCII -Path $StripJs
        node $StripJs $ManifestPath
        if ($LASTEXITCODE -ne 0) { throw "Failed to strip manifest key" }
        Remove-Item -Force $StripJs
        $StorePath = Join-Path $OutDir "ClipboardTranslator-extension-$Version-edge-store.zip"
        if (Test-Path $StorePath) { Remove-Item -Force $StorePath }
        Compress-Archive -Path (Join-Path $Stage "*") -DestinationPath $StorePath
        Remove-Item -Recurse -Force $Stage
        Write-Host "Edge store zip (no key): $StorePath"
    }

    Write-Host "Extension dist: $(Join-Path $Ext 'dist')"
}
finally {
    Pop-Location
}
