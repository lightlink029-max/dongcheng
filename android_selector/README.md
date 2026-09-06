# LightLink 选片 APK

MuMu 中的本地抖音多选工具。Odoo 任务启动后，Windows 工具通过 ADB 配置当前任务和本机接收通道。

1. 在抖音图片搜索结果中打开视频。
2. 点“分享 → 更多 → LightLink 选片”，可重复选择多个视频。
3. 打开“LightLink 选片”，勾选、删除或提交链接。
4. Windows 工具收到链接后负责下载、批量混剪并只把最终成片回传 Odoo。

APK 与 Windows 工具只通过 `adb reverse` 映射的本机 HTTP 端口通信，并校验每次启动随机生成的令牌。
