param(
  [string]$ProjectPath = "D:\Codex\2026-09-09\lightlink\outputs\lightlink-product-radar"
)

$ErrorActionPreference = "Stop"
$resolvedProjectPath = (Resolve-Path -LiteralPath $ProjectPath).Path
$runtimeLogDirectory = Join-Path $resolvedProjectPath ".codex\startup"
New-Item -ItemType Directory -Path $runtimeLogDirectory -Force | Out-Null
trap {
  $_ | Out-String | Out-File -LiteralPath (Join-Path $runtimeLogDirectory "startup-bootstrap.err.log") -Append -Encoding utf8
  exit 1
}

$npmPath = (Get-Command npm.cmd -ErrorAction Stop).Source
$nodePath = (Get-Command node.exe -ErrorAction Stop).Source
$codexCommand = Get-Command codex.exe -ErrorAction SilentlyContinue
if ($codexCommand) {
  $codexDirectory = Split-Path $codexCommand.Source -Parent
} else {
  $codexRoot = Join-Path $env:LOCALAPPDATA "OpenAI\Codex\bin"
  $codexBinary = Get-ChildItem -LiteralPath $codexRoot -Recurse -Filter "codex.exe" -File -ErrorAction SilentlyContinue |
    Sort-Object LastWriteTime -Descending |
    Select-Object -First 1
  if (-not $codexBinary) {
    throw "Codex executable was not found."
  }
  $codexDirectory = $codexBinary.DirectoryName
}
$env:PATH = "$codexDirectory;$env:PATH"
$radarProcess = $null
$channelProcess = $null
$intelligenceSchedulerProcess = $null

function Test-LightLinkPort {
  param([int]$Port)
  return [bool](Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue)
}

function Start-LightLinkProcess {
  param(
    [string]$FilePath,
    [string[]]$ArgumentList,
    [string]$Name
  )
  $stamp = Get-Date -Format "yyyyMMdd-HHmmss"
  return Start-Process `
    -FilePath $FilePath `
    -ArgumentList $ArgumentList `
    -WorkingDirectory $resolvedProjectPath `
    -WindowStyle Hidden `
    -RedirectStandardOutput (Join-Path $runtimeLogDirectory "$Name-$stamp.out.log") `
    -RedirectStandardError (Join-Path $runtimeLogDirectory "$Name-$stamp.err.log") `
    -PassThru
}

while ($true) {
  if (-not (Test-LightLinkPort -Port 8787)) {
    if ($null -eq $radarProcess -or $radarProcess.HasExited) {
      $radarProcess = Start-LightLinkProcess -FilePath $npmPath -ArgumentList @("run", "start") -Name "radar-8787"
    }
  }

  if (-not (Test-LightLinkPort -Port 8788)) {
    if ($null -eq $channelProcess -or $channelProcess.HasExited) {
      $channelProcess = Start-LightLinkProcess -FilePath $nodePath -ArgumentList @("scripts/codex-task-channel.mjs") -Name "codex-channel-8788"
    }
  }

  if ($null -eq $intelligenceSchedulerProcess -or $intelligenceSchedulerProcess.HasExited) {
    $intelligenceSchedulerProcess = Start-LightLinkProcess -FilePath $nodePath -ArgumentList @("scripts/intelligence-scheduler.mjs") -Name "intelligence-scheduler"
  }

  Start-Sleep -Seconds 10
}
