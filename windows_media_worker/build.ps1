$ErrorActionPreference = "Stop"
$Here = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $Here

$BundledPython = "C:\Users\Admin\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe"
$Python = if (Test-Path $BundledPython) { $BundledPython } else { "python" }
if (-not (Test-Path ".venv-build\Scripts\python.exe")) {
    & $Python -m venv .venv-build
}
& .\.venv-build\Scripts\python.exe -m pip install --timeout 600 --retries 10 -r requirements.txt pyinstaller
& .\.venv-build\Scripts\pyinstaller.exe --noconfirm --clean --windowed --onedir `
    --name LightLinkMediaWorker `
    --collect-all imageio_ffmpeg `
    --collect-all yt_dlp `
    app.py

$Package = Join-Path $Here "dist\LightLinkMediaWorker-Windows.zip"
if (Test-Path $Package) { Remove-Item -LiteralPath $Package }
Compress-Archive -Path "dist\LightLinkMediaWorker\*" -DestinationPath $Package -CompressionLevel Optimal
Write-Host "安装包已生成: $Package"
