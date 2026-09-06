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

if (Test-Path -LiteralPath $installPath) {
    $installedProcesses = Get-Process -ErrorAction SilentlyContinue | Where-Object {
        try {
            $_.Path -and $_.Path.StartsWith($installPath, [System.StringComparison]::OrdinalIgnoreCase)
        }
        catch { $false }
    }
    if ($installedProcesses) {
        $installedProcesses | Stop-Process -Force
        $installedProcesses | Wait-Process -Timeout 15 -ErrorAction SilentlyContinue
        Start-Sleep -Milliseconds 500
    }
}

New-Item -ItemType Directory -Force -Path $installPath | Out-Null
& robocopy.exe $SourceDirectory $installPath /MIR /COPY:DAT /DCOPY:DAT /R:2 /W:1 /NP /NFL /NDL /NJH /NJS | Out-Null
if ($LASTEXITCODE -ge 8) {
    throw "Failed to install application files; robocopy exit code: $LASTEXITCODE"
}

Start-Process -FilePath (Join-Path $installPath $ExpectedExe) -WorkingDirectory $installPath
Write-Host "Installed: $installPath"
