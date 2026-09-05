param(
    [string]$RepoPath = "__REPO_PATH__",
    [string]$QueueRoot = "__QUEUE_ROOT__",
    [string]$SshWrapper = "__SSH_WRAPPER__",
    [string]$GitExe = "C:\Program Files\Git\cmd\git.exe",
    [switch]$Once,
    [switch]$DryRun
)

$ErrorActionPreference = "Stop"
$ExpectedRemote = "git@github.com:lightlink029-max/dongcheng.git"
$ExpectedBranch = "production"
$RequestDirectory = Join-Path $QueueRoot "requests"
$ResultDirectory = Join-Path $QueueRoot "results"
$ArchiveDirectory = Join-Path $QueueRoot "archive"
$LogPath = Join-Path $QueueRoot "agent.log"

function Write-AgentLog([string]$Message) {
    $line = "{0} {1}" -f (Get-Date -Format "yyyy-MM-dd HH:mm:ss"), $Message
    Add-Content -LiteralPath $LogPath -Value $line -Encoding UTF8
}

function Invoke-Git([string[]]$Arguments) {
    $output = & $GitExe @Arguments 2>&1
    return [pscustomobject]@{
        ExitCode = $LASTEXITCODE
        Output = (($output | ForEach-Object { $_.ToString() }) -join "`n").Trim()
    }
}

function Write-Result([string]$RequestId, [string]$State, [string]$Message, [string]$Commit) {
    $result = [ordered]@{
        schema = 1
        request_id = $RequestId
        state = $State
        message = $Message
        commit = $Commit
        completed_at = (Get-Date).ToUniversalTime().ToString("o")
    }
    $target = Join-Path $ResultDirectory ($RequestId + ".json")
    $temporary = $target + ".tmp"
    $result | ConvertTo-Json -Depth 3 | Set-Content -LiteralPath $temporary -Encoding UTF8
    Move-Item -LiteralPath $temporary -Destination $target -Force
}

function Process-Request([System.IO.FileInfo]$RequestFile) {
    $requestId = [System.IO.Path]::GetFileNameWithoutExtension($RequestFile.Name)
    $commit = ""
    try {
        if ($requestId -notmatch "^[0-9a-fA-F-]{36}$" -or $RequestFile.Length -gt 4096) {
            throw "Invalid request filename or size."
        }
        $request = Get-Content -Raw -LiteralPath $RequestFile.FullName | ConvertFrom-Json
        if ($request.schema -ne 1 -or $request.action -ne "push-production" -or $request.request_id -ne $requestId) {
            throw "Invalid request schema or action."
        }
        $commit = [string]$request.expected_head
        if ($commit -notmatch "^[0-9a-fA-F]{40}$") {
            throw "Invalid expected commit."
        }
        if (-not (Test-Path -LiteralPath (Join-Path $RepoPath ".git"))) {
            throw "Configured repository does not exist."
        }
        if (-not (Test-Path -LiteralPath $GitExe) -or -not (Test-Path -LiteralPath $SshWrapper)) {
            throw "Git or the locked SSH wrapper is unavailable."
        }

        $remote = Invoke-Git @("-C", $RepoPath, "remote", "get-url", "origin")
        if ($remote.ExitCode -ne 0 -or $remote.Output -ne $ExpectedRemote) {
            throw "Repository remote does not match the approved GitHub repository."
        }
        $branch = Invoke-Git @("-C", $RepoPath, "branch", "--show-current")
        if ($branch.ExitCode -ne 0 -or $branch.Output -ne $ExpectedBranch) {
            throw "Repository is not on the production branch."
        }
        $head = Invoke-Git @("-C", $RepoPath, "rev-parse", "HEAD")
        if ($head.ExitCode -ne 0 -or $head.Output -ne $commit) {
            throw "Repository HEAD changed after the request was created."
        }
        $status = Invoke-Git @("-C", $RepoPath, "status", "--porcelain", "--untracked-files=no")
        if ($status.ExitCode -ne 0 -or $status.Output) {
            throw "Repository contains uncommitted tracked changes."
        }

        if ($DryRun) {
            Write-Result $requestId "validated" "Request passed all safety checks; no push was performed." $commit
            Write-AgentLog "Validated $requestId for $commit (dry run)."
            return
        }

        $push = Invoke-Git @(
            "-C", $RepoPath,
            "-c", ("core.sshCommand=" + $SshWrapper),
            "-c", "core.hooksPath=NUL",
            "push", "--porcelain", "origin", "HEAD:refs/heads/production"
        )
        if ($push.ExitCode -ne 0) {
            throw ("SSH push failed: " + $push.Output)
        }
        $remoteHead = Invoke-Git @(
            "-C", $RepoPath,
            "-c", ("core.sshCommand=" + $SshWrapper),
            "-c", "core.hooksPath=NUL",
            "ls-remote", "origin", "refs/heads/production"
        )
        if ($remoteHead.ExitCode -ne 0 -or -not $remoteHead.Output.StartsWith($commit + "`t")) {
            throw "Push returned successfully, but remote verification did not match the requested commit."
        }
        Write-Result $requestId "succeeded" $push.Output $commit
        Write-AgentLog "Pushed $requestId at $commit."
    }
    catch {
        Write-Result $requestId "failed" $_.Exception.Message $commit
        Write-AgentLog "Failed ${requestId}: $($_.Exception.Message)"
    }
    finally {
        $archivePath = Join-Path $ArchiveDirectory $RequestFile.Name
        Move-Item -LiteralPath $RequestFile.FullName -Destination $archivePath -Force -ErrorAction SilentlyContinue
    }
}

New-Item -ItemType Directory -Force -Path $QueueRoot, $RequestDirectory, $ResultDirectory, $ArchiveDirectory | Out-Null
$mutex = New-Object System.Threading.Mutex($false, "Local\LightLinkGitPushAgent")
if (-not $mutex.WaitOne(0)) {
    exit 0
}

try {
    Write-AgentLog "Agent started."
    do {
        $requestFiles = @(Get-ChildItem -LiteralPath $RequestDirectory -File -Filter "*.json" | Sort-Object CreationTimeUtc)
        foreach ($requestFile in $requestFiles) {
            Process-Request $requestFile
        }
        if (-not $Once) {
            Start-Sleep -Seconds 2
        }
    } while (-not $Once)
}
finally {
    $mutex.ReleaseMutex()
    $mutex.Dispose()
}
