---
name: cross-platform-source-speech
status: completed
planned_for: 0.12.0
implemented_in: [0.12.0]
summary: 原文英语离线朗读，统一使用 Qt 的 Windows/macOS 原生 TTS 后端
---

# 跨平台原文英语朗读

## 目标

在翻译模式的「原文」标题右侧提供小喇叭按钮，离线朗读英文单词、句子与段落，并同时支持 Windows 与 macOS。

## 实现

- 新增 `SpeechService`，经 `QTextToSpeech` 使用当前平台默认原生后端；不硬编码 WinRT、SAPI 或 Darwin。
- 选择音色时优先 en-US，其次 en-GB，最后任意英语音色；缺少英语音色或引擎失败时在状态栏提示。
- 播放中再次点击停止；原文变化、进入问答模式或退出应用时停止，避免朗读旧文本。
- Windows/macOS PyInstaller spec 显式导入 `PySide6.QtTextToSpeech`；macOS CI 同时检查 Darwin 引擎发现与 `.app` 中的 `texttospeech` 插件。

## 验收

1. Windows 和 macOS 均可离线朗读原文英语。
2. 空原文不可朗读，问答模式不显示按钮。
3. TTS 错误不影响翻译流程，并给出可读提示。
