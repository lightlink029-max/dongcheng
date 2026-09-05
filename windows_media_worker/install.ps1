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

function Move-DirectoryWithRetry {
    param([string]$Source, [string]$Destination)
    for ($attempt = 1; $attempt -le 10; $attempt++) {
        try {
            Move-Item -LiteralPath $Source -Destination $Destination -ErrorAction Stop
            return
        }
        catch {
            if ($attempt -eq 10) {
                throw "无法替换程序目录，请关闭 LightLinkMediaWorker、FFmpeg 和打开该目录的窗口后重试。原始错误：$($_.Exception.Message)"
            }
            Start-Sleep -Seconds 1
        }
    }
}

try {
    if (Test-Path -LiteralPath $installPath) {
        Move-DirectoryWithRetry -Source $installPath -Destination $backupPath
    }
    Move-DirectoryWithRetry -Source $stagingPath -Destination $installPath
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
