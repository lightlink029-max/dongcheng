$ErrorActionPreference = "Stop"
$Here = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $Here

$Python = ".venv\Scripts\python.exe"
if (-not (Test-Path $Python)) {
    py -m venv .venv
}
& $Python -m pip install --timeout 600 --retries 10 -r requirements.txt pyinstaller
if ($LASTEXITCODE -ne 0) { throw "Dependency installation failed with exit code $LASTEXITCODE" }
& $Python -m PyInstaller --noconfirm --clean --windowed --onedir `
    --name LightLinkMediaWorker `
    --collect-all imageio_ffmpeg `
    --collect-all yt_dlp `
    app.py
if ($LASTEXITCODE -ne 0) { throw "PyInstaller failed with exit code $LASTEXITCODE" }

$Package = Join-Path $Here "dist\LightLinkMediaWorker-Windows.zip"
if (Test-Path $Package) { Remove-Item -LiteralPath $Package }
Compress-Archive -Path "dist\LightLinkMediaWorker\*" -DestinationPath $Package -CompressionLevel Optimal
Write-Host "安装包已生成: $Package"
