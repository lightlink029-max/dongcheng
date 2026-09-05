# LightLink Windows 本地媒体生产工具

该工作节点主动领取 Odoo 的媒体任务，在 Windows 本地完成素材下载、图片排版、字幕翻译和 FFmpeg 混剪，然后把成品回传 Odoo。Odoo 不再直接调用图片或视频生成云 API。

## 图形版安装

解压 `LightLinkMediaWorker-Windows.zip`，运行 `LightLinkMediaWorker.exe`。在“连接与配置”中填写 Odoo 地址和工作节点令牌，可勾选开机自启。配置和日志保存在 `%LOCALAPPDATA%\\LightLinkMediaWorker`。

重新生成安装包：在 PowerShell 执行 `build.ps1`。

## 源码版安装

1. 安装 Python 3.11+、FFmpeg、yt-dlp；仅下载自有或已获授权的公开视频。
2. `python -m venv .venv`
3. `.venv\\Scripts\\pip install -r requirements.txt`
4. 复制 `config.example.json` 为 `config.json`。
5. 从 Odoo 系统参数复制 `psc.local_worker_token`，填写 Odoo 地址和工作目录。
6. 可选：安装 Ollama 与本地翻译模型，并在配置中填写模型名。
7. 启动桌面程序，保存配置后点击“启动工作节点”。

工作节点不接收入站公网连接；它主动访问 Odoo，因此适用于 Odoo.sh。验证码、登录失效或无权下载时任务会失败并留在 Odoo 中等待处理。

任务领取带有工作节点身份和 15 分钟租约。处理期间工具默认每 30 秒续租；如果电脑关机、工具崩溃或断网超过租约时间，任务会在下次领取时自动重新排队，避免永久卡在“处理中”。
