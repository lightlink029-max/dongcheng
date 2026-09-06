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
    --collect-all playwright `
    --paths "vendor\douyin" `
    --collect-submodules auth `
    --collect-submodules config `
    --collect-submodules control `
    --collect-submodules core `
    --collect-submodules storage `
    --collect-submodules utils `
    --add-data "vendor\douyin;vendor\douyin" `
    app.py
if ($LASTEXITCODE -ne 0) { throw "PyInstaller failed with exit code $LASTEXITCODE" }

$SelectorApk = Join-Path (Split-Path -Parent $Here) "android_selector\release\LightLinkSelector.apk"
if (-not (Test-Path $SelectorApk)) {
    throw "LightLinkSelector.apk not found. Wait for the Android build workflow first."
}
Copy-Item -LiteralPath $SelectorApk -Destination "dist\LightLinkMediaWorker\LightLinkSelector.apk" -Force

$Package = Join-Path $Here "dist\LightLinkMediaWorker-Windows.zip"
if (Test-Path $Package) { Remove-Item -LiteralPath $Package }
Compress-Archive -Path "dist\LightLinkMediaWorker\*" -DestinationPath $Package -CompressionLevel Optimal
Write-Host "安装包已生成: $Package"
