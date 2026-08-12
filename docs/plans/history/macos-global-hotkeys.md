---
name: macos-global-hotkeys
status: completed
planned_for: 0.14.0
implemented_in: [0.14.0]
summary: macOS 全局问答与手动输入快捷键；平台默认 ⌥⇧Q / ⌥M
archived_at_version: 0.14.0
---

# macOS 全局快捷键

## 背景

选区问答与 `Ctrl+M` 手动输入原先只接了 Win32 `RegisterHotKey` / `SendInput`。macOS 设置页灰掉并提示「暂不支持」；Qt 还把配置里的 `Ctrl` 显示成 `⌘`，易与系统注销（⌘⇧Q）混淆。

## 方案

- Carbon `RegisterEventHotKey`（ctypes，无 pyobjc）实现 `MacHotkeyBackend`
- `MacSelectionInput`：`CGEvent` 发 ⌘C + `pasteboard_change_count`；需辅助功能权限
- 配置语义：`Ctrl`=⌃，`Cmd`/`Win`/`Meta`=⌘，`Alt`=⌥
- 平台默认：macOS `Alt+Shift+Q` / `Alt+M`；Windows 仍为 `Ctrl+Shift+Q` / `Ctrl+M`
- 设置页启用双端改绑；Mac 下 QKeySequence 与配置字符串做 Ctrl↔Meta 转换
- 手动输入窗挂现有 NSPanel 全屏锚点

## 验收

1. macOS：⌥M 呼出手动输入框并提交翻译
2. macOS：授权辅助功能后，选中文本按 ⌥⇧Q 进入问答
3. 设置改键立即生效；冲突时回滚且不写盘
4. Windows 原有快捷键行为不变
