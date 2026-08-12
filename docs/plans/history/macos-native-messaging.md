---
name: macos-native-messaging
status: completed
planned_for: "0.17.0"
implemented_in:
  - "0.17.0"
archived_at_version: "0.17.0"
summary: >
  macOS 曾补齐 Native Messaging 打包与注册；随后因 Gatekeeper 拦截 onefile
  libpython，在 0.17.1 改为 HTTP /v1/auto_pair（见 macos-http-auto-pair）。
source_cursor_plan: mac_自动连接失败_a558b0cc.plan.md
---

# macOS Native Messaging 零点击配对

## 背景

扩展「自动连接」依赖 `sendNativeMessage("com.clipboard_translator.bridge")`。此前仅 Windows 写入 HKCU 并附带 `ClipboardTranslatorNmHost.exe`；macOS 直接跳过注册，浏览器报 `Specified native messaging host not found.`，用户只能反复短码配对。

## 0.17.0 实现（Mac 路径已由 0.17.1 取代）

1. Darwin 写入 Edge/Chrome `NativeMessagingHosts` 清单
2. 打包嵌入 `ClipboardTranslatorNmHost`（PyInstaller onefile）
3. 开发模式 shell launcher

## 后续

实机发现 Edge 每次启动 onefile host 都会解压新的 `libpython`，Gatekeeper 反复要求「仍然允许」。**0.17.1** 改为 [`macos-http-auto-pair`](macos-http-auto-pair.md)：Mac 停用 NM，扩展走 `POST /v1/auto_pair`。
