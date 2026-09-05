# LightLink Windows 本地媒体生产工具

该工作节点主动领取 Odoo 的媒体任务，在 Windows 本地完成素材下载、图片排版、字幕翻译和 FFmpeg 混剪，然后把成品回传 Odoo。Odoo 不再直接调用图片或视频生成云 API。

抖音视频下载由内置的开源 [cmsjin/douyin](https://github.com/cmsjin/douyin) 完成，不调用 Paste2Vid 或其他在线解析网站。首次使用请在配置页点击“登录/更新抖音登录”，在自动打开的 Edge 窗口完成登录；Cookie 使用 Windows DPAPI 加密，只保存在本机 `%LOCALAPPDATA%\\LightLinkMediaWorker\\secrets.json`，不会上传 Odoo、写入配置或日志。仅下载自有或已获授权的公开视频。

## 图形版安装

解压 `LightLinkMediaWorker-Windows.zip`，运行 `LightLinkMediaWorker.exe`。在“连接与配置”中填写 Odoo 地址和工作节点令牌，可勾选开机自启。配置和日志保存在 `%LOCALAPPDATA%\\LightLinkMediaWorker`。

重新生成安装包：在 PowerShell 执行 `build.ps1`。

更新本机现有安装：构建完成后执行 `install.ps1`。脚本会保留带时间戳的上一版本目录，配置文件不在程序目录中，不会被覆盖。

## 源码版安装

1. 安装 Python 3.11+ 和 Microsoft Edge；FFmpeg 由安装包内置。仅下载自有或已获授权的公开视频。
2. `python -m venv .venv`
3. `.venv\\Scripts\\pip install -r requirements.txt`
4. 复制 `config.example.json` 为 `config.json`。
5. 从 Odoo 系统参数复制 `psc.local_worker_token`，填写 Odoo 地址和工作目录。
6. 可选：安装 Ollama 与本地翻译模型，并在配置中填写模型名。
7. 启动桌面程序，先点击“登录/更新抖音登录”，再保存配置并点击“启动工作节点”。

`vendor/douyin` 是 `cmsjin/douyin` 2.0.0 的固定源码快照，按其 MIT 许可证分发；原许可证保存在该目录中。

工作节点不接收入站公网连接；它主动访问 Odoo，因此适用于 Odoo.sh。验证码、登录失效或无权下载时任务会失败并留在 Odoo 中等待处理。

## MuMu 抖音图片选片

安装 MuMu 模拟器并在模拟器中安装、登录抖音，然后在工具配置页点击“检测MuMu”。工具会自动识别新版 MuMu 的动态 ADB 端口及旧版 `127.0.0.1:7555`；自动检测失败时可手工填写 ADB 地址并选择安装目录中的 `adb.exe` 和 MuMu 主程序。

在 Odoo 渠道内容中点击“打开抖音图片搜索”会创建本地选片任务。工具领取任务后自动把产品参考图传入 MuMu 相册并启动抖音；登录、验证码、按图搜索和视频选择由用户完成。选择后在抖音中复制分享链接，回到工具“任务列表”选择对应任务，点击“提交所选任务的视频链接”，一次粘贴多条并同步回 Odoo。之后可在 Odoo 提交正常的视频混剪任务。

任务领取带有工作节点身份和 15 分钟租约。处理期间工具默认每 30 秒续租；如果电脑关机、工具崩溃或断网超过租约时间，任务会在下次领取时自动重新排队，避免永久卡在“处理中”。
