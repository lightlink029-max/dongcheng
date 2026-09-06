# LightLink Windows 本地媒体生产工具

该工作节点主动领取 Odoo 的媒体任务，在 Windows 本地完成素材下载、图片排版、字幕翻译和 FFmpeg 混剪，然后把成品回传 Odoo。Odoo 不再直接调用图片或视频生成云 API。

抖音视频下载由内置的开源 [cmsjin/douyin](https://github.com/cmsjin/douyin) 完成，不调用 Paste2Vid 或其他在线解析网站。首次使用请在配置页点击“登录/更新抖音登录”，在自动打开的 Edge 窗口完成登录；工具使用 `%LOCALAPPDATA%\\LightLinkMediaWorker\\edge-profile\\douyin` 作为固定的专用浏览器配置目录，后续会保留同一账号的登录状态。Cookie 另使用 Windows DPAPI 加密，只保存在本机 `%LOCALAPPDATA%\\LightLinkMediaWorker\\secrets.json`，不会上传 Odoo、写入配置或日志。仅下载自有或已获授权的公开视频。

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

在 Odoo 渠道内容中点击“打开抖音图片搜索”会创建本地选片任务。工具领取任务后自动把产品参考图传入 MuMu 相册并启动抖音；登录、验证码、按图搜索和视频选择由用户完成。每次在抖音中执行“分享 → 复制链接”，Windows 工具都会自动加入本地选片库并保存视频 ID、选择时间和处理状态。可在“抖音选片与混剪”页删除、重新下载或多选后批量混剪；只有最终成片会回传 Odoo，选片明细和原视频保留在本机。

任务领取带有工作节点身份和 15 分钟租约。处理期间工具默认每 30 秒续租；如果电脑关机、工具崩溃或断网超过租约时间，任务会在下次领取时自动重新排队，避免永久卡在“处理中”。

## 独立本地视频工作台

“抖音选片与混剪”页既能处理 Odoo 下发任务，也能直接点击“新建本地项目”独立使用。项目支持关键词、参考图片、抖音分享链接和本地视频文件；关键词搜索会打开保留登录状态的 LightLink 专用 Edge，图片搜索会传入 MuMu 抖音。

推荐操作顺序：添加素材 → 下载并逐条预览 → 编辑处理设置 → 生成审核稿 → 预览成片 → 确认回传 Odoo。独立本地项目不会上传；只有由 Odoo 下发且仍由当前工作节点持有的任务才显示确认回传结果。

基础剪辑支持顺序、倒序和随机拼接、素材入点/出点、淡入淡出、背景音乐、版权状态、多平台画幅预设和成片版本历史。双击素材可用系统播放器完整播放；“时间轴/版权”提供工具内帧预览和精确入出点。

字幕支持直接使用项目文本，或先识别全部所选视频的原声再翻译为目标语种。工具优先使用已配置的 `whisper_command`，否则自动使用当前运行环境中的 `faster-whisper`；两者均不可用时会回退到项目文本，不再使整个任务失败。外部识别程序仍按“输入视频、输出 SRT、原视频语种”接收三个参数。

配音可选择 Windows 本地音色、sherpa-onnx 本地音色或火山引擎。Windows 音色无需额外安装；sherpa-onnx 需配置程序、VITS 模型、tokens 和 data-dir；火山引擎需配置 App ID、Access Token、Cluster 及控制台提供的音色 ID。生成的视频始终可烧录目标语言字幕，配音和背景音乐会随成片一并输出。`ai_edit_command` 是可选的本地 AI 剪辑程序路径，程序接收输入 JSON 和输出 JSON 两个参数，输出 `{"order": [0, 1]}` 形式且必须包含全部素材索引。
