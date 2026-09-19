$ErrorActionPreference = "Stop"

$projectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location -LiteralPath $projectRoot

$node = Get-Command node -ErrorAction SilentlyContinue
$npm = Get-Command npm.cmd -ErrorAction SilentlyContinue
if (-not $node -or -not $npm) {
  Write-Host "Node.js 22.13 or newer is required: https://nodejs.org/" -ForegroundColor Yellow
  Read-Host "Install it, then press Enter to close"
  exit 1
}

$nodeVersion = [version]((& $node.Source --version).TrimStart("v"))
if ($nodeVersion -lt [version]"22.13.0") {
  Write-Host "The installed Node.js version is too old. Version 22.13 or newer is required." -ForegroundColor Yellow
  Read-Host "Upgrade it, then press Enter to close"
  exit 1
}

$devVarsPath = Join-Path $projectRoot ".dev.vars"
$devVarsContent = if (Test-Path -LiteralPath $devVarsPath) { Get-Content -LiteralPath $devVarsPath -Raw } else { "" }
if ($devVarsContent -notmatch "(?m)^LIGHTLINK_CREDENTIALS_MASTER_KEY=") {
  $masterKeyBytes = New-Object byte[] 32
  $randomGenerator = [System.Security.Cryptography.RandomNumberGenerator]::Create()
  try {
    $randomGenerator.GetBytes($masterKeyBytes)
  } finally {
    $randomGenerator.Dispose()
  }
  $masterKey = [Convert]::ToBase64String($masterKeyBytes)
  $prefix = if ($devVarsContent -and -not $devVarsContent.EndsWith([Environment]::NewLine)) { [Environment]::NewLine } else { "" }
  Add-Content -LiteralPath $devVarsPath -Value ("{0}# Local credential vault; never commit or share this value.{1}LIGHTLINK_CREDENTIALS_MASTER_KEY={2}" -f $prefix, [Environment]::NewLine, $masterKey)
  Write-Host "Initialized the local API credential vault." -ForegroundColor Cyan
}
if ($devVarsContent -notmatch "(?m)^LIGHTLINK_GOOGLE_API_BRIDGE_URL=") {
  $prefix = if ($devVarsContent -and -not $devVarsContent.EndsWith([Environment]::NewLine)) { [Environment]::NewLine } else { "" }
  Add-Content -LiteralPath $devVarsPath -Value ("{0}# Local-only allowlisted bridge for Google API calls.{1}LIGHTLINK_GOOGLE_API_BRIDGE_URL=http://127.0.0.1:8791" -f $prefix, [Environment]::NewLine)
  $devVarsContent = Get-Content -LiteralPath $devVarsPath -Raw
}

if (-not (Test-Path -LiteralPath (Join-Path $projectRoot "node_modules"))) {
  Write-Host "Installing dependencies for the first run..." -ForegroundColor Cyan
  & $npm.Source ci --prefer-offline --no-audit --no-fund
  if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
}

Write-Host "Building LightLink Product Radar..." -ForegroundColor Cyan
& $npm.Source run build
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

$wranglerConfig = Join-Path $projectRoot "dist\server\wrangler.json"
$wrangler = Join-Path $projectRoot "node_modules\wrangler\bin\wrangler.js"
$schemaProbe = & $node.Source --import ./scripts/sites-env.mjs $wrangler d1 execute DB --local --config $wranglerConfig --persist-to .wrangler/state --command "SELECT name FROM sqlite_master WHERE type='table' AND name='scan_runs';" --json 2>$null | Out-String
if ($schemaProbe -notmatch "scan_runs") {
  Write-Host "Initializing the local database..." -ForegroundColor Cyan
  & $node.Source --import ./scripts/sites-env.mjs $wrangler d1 execute DB --local --config $wranglerConfig --persist-to .wrangler/state --file drizzle/0000_swift_the_fallen.sql
  if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
}

Write-Host "Opening http://127.0.0.1:8787" -ForegroundColor Green
$codexChannel = $null
$codexCommand = Get-Command codex -ErrorAction SilentlyContinue
if ($codexCommand) {
  Write-Host "Starting the Codex task channel..." -ForegroundColor Cyan
  $codexChannel = Start-Process -FilePath $node.Source -WindowStyle Hidden -WorkingDirectory $projectRoot -ArgumentList @(
    (Join-Path $projectRoot "scripts\codex-task-channel.mjs")
  ) -PassThru
} else {
  Write-Host "Codex CLI was not found; file imports and the OpenAI API remain available." -ForegroundColor Yellow
}
Start-Process -FilePath "powershell.exe" -WindowStyle Hidden -ArgumentList @(
  "-NoProfile",
  "-WindowStyle", "Hidden",
  "-Command", "Start-Sleep -Seconds 2; Start-Process 'http://127.0.0.1:8787'"
)

# Reuse an available local HTTP proxy for external API calls without forcing
# the whole machine through a TUN adapter. Local LightLink traffic must always
# stay direct. Some proxy clients expose 127.0.0.1:10808 without registering it
# as the Windows user proxy, so detect that listener as a safe local fallback.
if (-not $env:HTTPS_PROXY -and -not $env:HTTP_PROXY) {
  $internetSettings = Get-ItemProperty -LiteralPath "HKCU:\Software\Microsoft\Windows\CurrentVersion\Internet Settings" -ErrorAction SilentlyContinue
  $windowsProxy = if ($internetSettings.ProxyEnable -eq 1) { [string]$internetSettings.ProxyServer } else { "" }
  if ($windowsProxy) {
    $proxyEndpoint = if ($windowsProxy -match "(?:^|;)https=([^;]+)") {
      $Matches[1]
    } elseif ($windowsProxy -match "(?:^|;)http=([^;]+)") {
      $Matches[1]
    } else {
      ($windowsProxy -split ";", 2)[0]
    }
    if ($proxyEndpoint -and $proxyEndpoint -notmatch "^https?://") {
      $proxyEndpoint = "http://$proxyEndpoint"
    }
    if ($proxyEndpoint) {
      $env:HTTPS_PROXY = $proxyEndpoint
      $env:HTTP_PROXY = $proxyEndpoint
      $env:NO_PROXY = "127.0.0.1,localhost"
      Write-Host "Using the Windows proxy for external API calls: $proxyEndpoint" -ForegroundColor Cyan
    }
  }
  if (-not $env:HTTPS_PROXY -and (Get-NetTCPConnection -LocalAddress "127.0.0.1" -LocalPort 10808 -State Listen -ErrorAction SilentlyContinue)) {
    $env:HTTPS_PROXY = "http://127.0.0.1:10808"
    $env:HTTP_PROXY = "http://127.0.0.1:10808"
    $env:NO_PROXY = "127.0.0.1,localhost"
    Write-Host "Using the local proxy for external API calls: http://127.0.0.1:10808" -ForegroundColor Cyan
  }
}

$googleApiBridge = $null
if ($env:HTTPS_PROXY -or $env:HTTP_PROXY) {
  $env:NODE_USE_ENV_PROXY = "1"
  $googleApiBridge = Start-Process -FilePath $node.Source -WindowStyle Hidden -WorkingDirectory $projectRoot -ArgumentList @(
    (Join-Path $projectRoot "scripts\google-api-bridge.mjs")
  ) -PassThru
}

$intelligenceScheduler = Start-Process -FilePath $node.Source -WindowStyle Hidden -WorkingDirectory $projectRoot -ArgumentList @(
  (Join-Path $projectRoot "scripts\intelligence-scheduler.mjs")
) -PassThru

$radarArgs = @("start", "--", "--port", "8787")
if (Test-Path -LiteralPath (Join-Path $projectRoot ".dev.vars")) {
  $radarArgs += @("--env-file", $devVarsPath)
}
try {
  & $npm.Source @radarArgs
} finally {
  if ($googleApiBridge -and -not $googleApiBridge.HasExited) {
    Stop-Process -Id $googleApiBridge.Id -ErrorAction SilentlyContinue
  }
  if ($codexChannel -and -not $codexChannel.HasExited) {
    Stop-Process -Id $codexChannel.Id -ErrorAction SilentlyContinue
  }
  if ($intelligenceScheduler -and -not $intelligenceScheduler.HasExited) {
    Stop-Process -Id $intelligenceScheduler.Id -ErrorAction SilentlyContinue
  }
}
