param(
    [string]$RepoPath = "C:\Users\Admin\Documents\Codex\2026-08-27\wo\work\product-hub-production2",
    [string]$QueueRoot = "C:\Users\Admin\Documents\Codex\2026-08-27\wo\work\git-push-queue"
)

$ErrorActionPreference = "Stop"
$SourceDirectory = Split-Path -Parent $MyInvocation.MyCommand.Path
$InstallDirectory = Join-Path $env:LOCALAPPDATA "LightLink\GitPushAgent"
$StartupDirectory = Join-Path $env:APPDATA "Microsoft\Windows\Start Menu\Programs\Startup"
$StartupPath = Join-Path $StartupDirectory "LightLinkGitPushAgent.cmd"
$AgentPath = Join-Path $InstallDirectory "LightLinkGitPushAgent.ps1"
$WrapperPath = Join-Path $InstallDirectory "ssh-github-proxy.cmd"
$KnownHostsPath = Join-Path $InstallDirectory "github_known_hosts"
$SshAdd = "C:\Windows\System32\OpenSSH\ssh-add.exe"
$ExpectedFingerprint = "SHA256:MyMq9L6krEpqchtIgD6SSDue8ZCmrCRkjgk4pptXFxQ"

$agentService = Get-Service -Name "ssh-agent" -ErrorAction SilentlyContinue
if (-not $agentService -or $agentService.Status -ne "Running") {
    throw "The Windows OpenSSH Authentication Agent is not running."
}
$identities = (& $SshAdd -l 2>&1 | Out-String)
if ($LASTEXITCODE -ne 0 -or $identities -notlike "*$ExpectedFingerprint*") {
    throw "The approved GitHub deploy key is not loaded in the Windows SSH agent."
}

New-Item -ItemType Directory -Force -Path $InstallDirectory, $QueueRoot | Out-Null

$agent = Get-Content -Raw -LiteralPath (Join-Path $SourceDirectory "LightLinkGitPushAgent.ps1")
$agent = $agent.Replace("__REPO_PATH__", $RepoPath)
$agent = $agent.Replace("__QUEUE_ROOT__", $QueueRoot)
$agent = $agent.Replace("__SSH_WRAPPER__", $WrapperPath)
Set-Content -LiteralPath $AgentPath -Value $agent -Encoding UTF8

Set-Content -LiteralPath $KnownHostsPath -Encoding ASCII -Value "github.com ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIOMqqnkVzrm0SdG6UOoqKLsabgH5C9okWi0dh2l9GKJl"
$wrapper = @"
@echo off
"C:\Windows\System32\OpenSSH\ssh.exe" -o "ProxyCommand=C:/Progra~1/Git/mingw64/bin/connect.exe -S 127.0.0.1:10808 %%h %%p" -o "UserKnownHostsFile=$($KnownHostsPath.Replace('\', '/'))" -o StrictHostKeyChecking=yes %*
"@
Set-Content -LiteralPath $WrapperPath -Value $wrapper -Encoding ASCII

$account = $env:USERDOMAIN + "\" + $env:USERNAME
& icacls.exe $InstallDirectory /inheritance:r /grant:r "${account}:(OI)(CI)F" "SYSTEM:(OI)(CI)F" | Out-Null
if ($LASTEXITCODE -ne 0) {
    throw "Failed to protect the installation directory."
}

$startup = "@echo off`r`nstart `"`" /min powershell.exe -NoProfile -NonInteractive -ExecutionPolicy Bypass -WindowStyle Hidden -File `"$AgentPath`"`r`n"
Set-Content -LiteralPath $StartupPath -Value $startup -Encoding ASCII

Get-CimInstance Win32_Process -Filter "Name = 'powershell.exe'" |
    Where-Object { $_.CommandLine -like ("*" + $AgentPath + "*") } |
    ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }
Start-Process powershell.exe -WindowStyle Hidden -ArgumentList @(
    "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass", "-File", ('"' + $AgentPath + '"')
)

Write-Host "Installed: $AgentPath"
Write-Host "Startup:   $StartupPath"
Write-Host "Queue:     $QueueRoot"
