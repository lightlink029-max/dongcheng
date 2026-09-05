param(
    [string]$RepoPath = "C:\Users\Admin\Documents\Codex\2026-08-27\wo\work\product-hub-production2",
    [string]$QueueRoot = "C:\Users\Admin\Documents\Codex\2026-08-27\wo\work\git-push-queue",
    [int]$WaitSeconds = 60
)

$ErrorActionPreference = "Stop"
$git = "C:\Program Files\Git\cmd\git.exe"
$branch = (& $git -C $RepoPath branch --show-current).Trim()
if ($LASTEXITCODE -ne 0 -or $branch -ne "production") {
    throw "Repository is not on the production branch."
}
$commit = (& $git -C $RepoPath rev-parse HEAD).Trim()
if ($LASTEXITCODE -ne 0 -or $commit -notmatch "^[0-9a-f]{40}$") {
    throw "Unable to resolve the current commit."
}

$requestId = [guid]::NewGuid().ToString()
$requestDirectory = Join-Path $QueueRoot "requests"
$resultDirectory = Join-Path $QueueRoot "results"
New-Item -ItemType Directory -Force -Path $requestDirectory, $resultDirectory | Out-Null
$target = Join-Path $requestDirectory ($requestId + ".json")
$temporary = $target + ".tmp"
[ordered]@{
    schema = 1
    action = "push-production"
    request_id = $requestId
    expected_head = $commit
    requested_at = (Get-Date).ToUniversalTime().ToString("o")
} | ConvertTo-Json | Set-Content -LiteralPath $temporary -Encoding UTF8
Move-Item -LiteralPath $temporary -Destination $target

$resultPath = Join-Path $resultDirectory ($requestId + ".json")
$deadline = (Get-Date).AddSeconds($WaitSeconds)
while ((Get-Date) -lt $deadline -and -not (Test-Path -LiteralPath $resultPath)) {
    Start-Sleep -Milliseconds 500
}
if (-not (Test-Path -LiteralPath $resultPath)) {
    throw "The local Git push agent did not return a result within $WaitSeconds seconds."
}
$result = Get-Content -Raw -LiteralPath $resultPath | ConvertFrom-Json
$result | ConvertTo-Json -Depth 3
if ($result.state -ne "succeeded") {
    exit 1
}
