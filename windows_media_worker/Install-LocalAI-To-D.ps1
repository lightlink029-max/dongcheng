param(
    [string]$InstallRoot = "D:\odooAiwoker\AI",
    [string]$TranslationModel = "qwen3:8b",
    [string]$WhisperModel = "small",
    [string]$Proxy = ""
)

$ErrorActionPreference = "Stop"
$ProgressPreference = "SilentlyContinue"
$installPath = [IO.Path]::GetFullPath($InstallRoot).TrimEnd("\")
if ([IO.Path]::GetPathRoot($installPath) -eq $installPath) {
    throw "Refusing to use a drive root as the installation directory."
}

function Download-File {
    param([string]$Url, [string]$Destination)
    if (Test-Path -LiteralPath $Destination) { return }
    Write-Host "Downloading $Url"
    $parameters = @{Uri=$Url; OutFile=$Destination; UseBasicParsing=$true}
    if ($Proxy) { $parameters.Proxy = $Proxy }
    Invoke-WebRequest @parameters
}

function Set-JsonProperty {
    param($Object, [string]$Name, $Value)
    if ($Object.PSObject.Properties[$Name]) { $Object.$Name = $Value }
    else { $Object | Add-Member -NotePropertyName $Name -NotePropertyValue $Value }
}

New-Item -ItemType Directory -Force -Path $installPath | Out-Null
$cache = Join-Path $installPath "downloads"
New-Item -ItemType Directory -Force -Path $cache | Out-Null
if ($Proxy) {
    $env:HTTPS_PROXY = $Proxy
}

# Ollama standalone keeps both the application and all models on D:.
$ollamaRoot = Join-Path $installPath "ollama"
$ollamaBin = Join-Path $ollamaRoot "bin"
$ollamaModels = Join-Path $ollamaRoot "models"
New-Item -ItemType Directory -Force -Path $ollamaBin,$ollamaModels | Out-Null
$ollamaArchive = Join-Path $cache "ollama-windows-amd64.zip"
Download-File "https://ollama.com/download/ollama-windows-amd64.zip" $ollamaArchive
if (-not (Test-Path (Join-Path $ollamaBin "ollama.exe"))) {
    Expand-Archive -LiteralPath $ollamaArchive -DestinationPath $ollamaBin -Force
}
$ollamaExe = Get-ChildItem $ollamaBin -Filter ollama.exe -Recurse | Select-Object -First 1
if (-not $ollamaExe) { throw "Ollama archive did not contain ollama.exe" }
[Environment]::SetEnvironmentVariable("OLLAMA_MODELS", $ollamaModels, "User")
$env:OLLAMA_MODELS = $ollamaModels

$startup = [Environment]::GetFolderPath("Startup")
$ollamaStartup = Join-Path $startup "LightLinkOllama.cmd"
$startupText = "@echo off`r`nset `"OLLAMA_MODELS=$ollamaModels`"`r`nstart `"`" /min `"$($ollamaExe.FullName)`" serve`r`n"
[IO.File]::WriteAllText($ollamaStartup, $startupText, [Text.Encoding]::ASCII)
try { Invoke-RestMethod "http://127.0.0.1:11434/api/tags" -TimeoutSec 3 | Out-Null }
catch {
    Start-Process -FilePath $ollamaExe.FullName -ArgumentList "serve" -WindowStyle Hidden
    Start-Sleep -Seconds 4
}
Write-Host "Downloading Ollama model $TranslationModel"
& $ollamaExe.FullName pull $TranslationModel
if ($LASTEXITCODE -ne 0) { throw "Ollama model download failed" }

# Faster Whisper is isolated from the packaged desktop application.
$python = @(
    "C:\Users\Admin\AppData\Local\Programs\Python\Python311\python.exe",
    (Get-Command python.exe -ErrorAction SilentlyContinue).Source
) | Where-Object { $_ -and (Test-Path $_) } | Select-Object -First 1
if (-not $python) { throw "Python 3.11 was not found" }
$whisperRoot = Join-Path $installPath "whisper"
$whisperPython = Join-Path $whisperRoot "venv\Scripts\python.exe"
if (-not (Test-Path $whisperPython)) { & $python -m venv (Join-Path $whisperRoot "venv") }
& $whisperPython -c "import faster_whisper" 2>$null
if ($LASTEXITCODE -ne 0) {
    & $whisperPython -m pip install --disable-pip-version-check --retries 2 --timeout 30 faster-whisper
    if ($LASTEXITCODE -ne 0) {
        Write-Host "PyPI failed; retrying faster-whisper from the Aliyun mirror"
        $savedHttpsProxy = $env:HTTPS_PROXY
        $env:HTTPS_PROXY = $null
        & $whisperPython -m pip install --disable-pip-version-check --retries 5 --timeout 60 --index-url "https://mirrors.aliyun.com/pypi/simple/" faster-whisper
        $pipExitCode = $LASTEXITCODE
        $env:HTTPS_PROXY = $savedHttpsProxy
        if ($pipExitCode -ne 0) { throw "faster-whisper installation failed" }
    }
}
Copy-Item (Join-Path $PSScriptRoot "tools\whisper_srt.py") (Join-Path $whisperRoot "whisper_srt.py") -Force
[IO.File]::WriteAllText((Join-Path $whisperRoot "model-name.txt"), $WhisperModel, [Text.UTF8Encoding]::new($false))
$whisperCommand = Join-Path $whisperRoot "whisper-srt.cmd"
$whisperCommandText = "@echo off`r`n`"$whisperPython`" `"$whisperRoot\whisper_srt.py`" %*`r`n"
[IO.File]::WriteAllText($whisperCommand, $whisperCommandText, [Text.Encoding]::ASCII)
Write-Host "Downloading Whisper model $WhisperModel"
& $whisperPython -c "from faster_whisper import WhisperModel; WhisperModel('$WhisperModel', device='cpu', compute_type='int8', download_root=r'$whisperRoot\models')"
if ($LASTEXITCODE -ne 0) { throw "Whisper model download failed" }

# sherpa-onnx official Windows x64 binaries and an English Piper voice.
$sherpaRoot = Join-Path $installPath "sherpa-onnx"
New-Item -ItemType Directory -Force -Path $sherpaRoot | Out-Null
$sherpaArchive = Join-Path $cache "sherpa-onnx-v1.13.7-win-x64-shared-MT-Release.tar.bz2"
$voiceArchive = Join-Path $cache "vits-piper-en_US-lessac-medium.tar.bz2"
Download-File "https://github.com/k2-fsa/sherpa-onnx/releases/download/v1.13.7/sherpa-onnx-v1.13.7-win-x64-shared-MT-Release.tar.bz2" $sherpaArchive
Download-File "https://github.com/k2-fsa/sherpa-onnx/releases/download/tts-models/vits-piper-en_US-lessac-medium.tar.bz2" $voiceArchive
if (-not (Get-ChildItem $sherpaRoot -Filter sherpa-onnx-offline-tts.exe -Recurse -ErrorAction SilentlyContinue)) {
    & tar.exe -xjf $sherpaArchive -C $sherpaRoot
    if ($LASTEXITCODE -ne 0) { throw "sherpa-onnx extraction failed" }
}
$voiceRoot = Join-Path $sherpaRoot "vits-piper-en_US-lessac-medium"
if (-not (Test-Path $voiceRoot)) {
    & tar.exe -xjf $voiceArchive -C $sherpaRoot
    if ($LASTEXITCODE -ne 0) { throw "sherpa voice extraction failed" }
}
$sherpaExe = Get-ChildItem $sherpaRoot -Filter sherpa-onnx-offline-tts.exe -Recurse | Select-Object -First 1
$sherpaModel = Join-Path $voiceRoot "en_US-lessac-medium.onnx"
$sherpaTokens = Join-Path $voiceRoot "tokens.txt"
$sherpaData = Join-Path $voiceRoot "espeak-ng-data"
foreach ($required in @($sherpaExe.FullName,$sherpaModel,$sherpaTokens,$sherpaData)) {
    if (-not (Test-Path $required)) { throw "Missing sherpa component: $required" }
}

# Update the worker configuration without exposing or replacing stored secrets.
$configPath = Join-Path $env:LOCALAPPDATA "LightLinkMediaWorker\config.json"
if (Test-Path $configPath) { $config = Get-Content $configPath -Raw | ConvertFrom-Json }
else { $config = [pscustomobject]@{} }
if (-not $config.PSObject.Properties["local_ai"]) { Set-JsonProperty $config "local_ai" ([pscustomobject]@{}) }
if (-not $config.PSObject.Properties["speech"]) { Set-JsonProperty $config "speech" ([pscustomobject]@{}) }
Set-JsonProperty $config.local_ai "ollama_url" "http://127.0.0.1:11434"
Set-JsonProperty $config.local_ai "translation_model" $TranslationModel
Set-JsonProperty $config.local_ai "whisper_command" $whisperCommand
Set-JsonProperty $config.local_ai "whisper_model" $WhisperModel
Set-JsonProperty $config.speech "sherpa_command" $sherpaExe.FullName
Set-JsonProperty $config.speech "sherpa_model" $sherpaModel
Set-JsonProperty $config.speech "sherpa_tokens" $sherpaTokens
Set-JsonProperty $config.speech "sherpa_data_dir" $sherpaData
$config | ConvertTo-Json -Depth 10 | Set-Content $configPath -Encoding UTF8

# Smoke tests: translation endpoint and generated English audio.
$translation = Invoke-RestMethod -Method Post -Uri "http://127.0.0.1:11434/api/generate" -ContentType "application/json" -Body (@{
    model=$TranslationModel; stream=$false; prompt="Translate into Chinese, return only the translation: warm winter shoes for children"
} | ConvertTo-Json)
if (-not $translation.response) { throw "Ollama translation smoke test failed" }
$ttsTest = Join-Path $sherpaRoot "test-voice.wav"
& $sherpaExe.FullName "--vits-model=$sherpaModel" "--vits-data-dir=$sherpaData" "--vits-tokens=$sherpaTokens" "--output-filename=$ttsTest" "Warm and comfortable winter shoes for children."
if ($LASTEXITCODE -ne 0 -or -not (Test-Path $ttsTest)) { throw "sherpa TTS smoke test failed" }

Write-Host ""
Write-Host "Local AI installation completed." -ForegroundColor Green
Write-Host "Root:       $installPath"
Write-Host "Ollama:     $($ollamaExe.FullName)"
Write-Host "Whisper:    $whisperCommand"
Write-Host "Sherpa TTS: $($sherpaExe.FullName)"
Write-Host "Translation test: $($translation.response.Trim())"
Write-Host "TTS test:   $ttsTest"
