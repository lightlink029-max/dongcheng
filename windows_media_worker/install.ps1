param(
    [string]$InstallDirectory = "D:\odooAiwoker\LightLinkMediaWorker-Windows"
)

$ErrorActionPreference = "Stop"
$SourceDirectory = Join-Path $PSScriptRoot "dist\LightLinkMediaWorker"
$ExpectedExe = "LightLinkMediaWorker.exe"

if (-not (Test-Path -LiteralPath (Join-Path $SourceDirectory $ExpectedExe))) {
    throw "Built application not found. Run build.ps1 first."
}

$installPath = [System.IO.Path]::GetFullPath($InstallDirectory).TrimEnd("\")
$installParent = Split-Path -Parent $installPath
if (-not $installParent -or $installPath -eq [System.IO.Path]::GetPathRoot($installPath)) {
    throw "Unsafe installation directory."
}
New-Item -ItemType Directory -Force -Path $installParent | Out-Null

$stagingPath = Join-Path $installParent ("LightLinkMediaWorker.update." + [guid]::NewGuid().ToString("N"))
$backupPath = $installPath + ".backup." + (Get-Date -Format "yyyyMMdd-HHmmss")
Copy-Item -LiteralPath $SourceDirectory -Destination $stagingPath -Recurse

$targetExe = Join-Path $installPath $ExpectedExe
Get-Process -Name "LightLinkMediaWorker" -ErrorAction SilentlyContinue |
    Where-Object { $_.Path -eq $targetExe } |
    Stop-Process -Force

try {
    if (Test-Path -LiteralPath $installPath) {
        Move-Item -LiteralPath $installPath -Destination $backupPath
    }
    Move-Item -LiteralPath $stagingPath -Destination $installPath
}
catch {
    if (-not (Test-Path -LiteralPath $installPath) -and (Test-Path -LiteralPath $backupPath)) {
        Move-Item -LiteralPath $backupPath -Destination $installPath
    }
    throw
}

Start-Process -FilePath (Join-Path $installPath $ExpectedExe) -WorkingDirectory $installPath
Write-Host "Installed: $installPath"
if (Test-Path -LiteralPath $backupPath) {
    Write-Host "Backup:    $backupPath"
}
