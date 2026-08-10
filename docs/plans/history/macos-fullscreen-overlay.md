---
name: macos-fullscreen-overlay
status: completed
planned_for: 0.9.7
implemented_in: [0.9.7]
summary: 不可见 NSPanel 锚点 + 子窗口，修复 macOS 原生全屏看不见翻译窗
archived_at_version: 0.9.7
---

# macOS 原生全屏 Space 叠层修复

## 问题

0.9.6 仅对主窗（Qt `QMainWindow` → 普通 `NSWindow`）设置 `canJoinAllSpaces | fullScreenAuxiliary`。在当前 macOS 上，`fullScreenAuxiliary` **只对 `NSPanel` 生效**：对普通 `NSWindow` 窗口服务器仍钉在桌面 Space，浏览器原生全屏后看不到翻译窗。扩展 toast「已发送到桌面端翻译」可见，但桌面端窗口在另一 Space。

## 方案

- 改写 [`macos_window.py`](../../../macos_window.py)：创建不可见、忽略鼠标、`HidesOnDeactivate=NO` 的非激活 `NSPanel` 锚点（`canJoinAllSpaces | fullScreenAuxiliary`），层级与主窗一致。
- 用 `addChildWindow:ordered:` 把翻译窗挂为子窗口；子窗口跟随父面板进入全屏 Space。
- 每次 `show` / 置顶切换后重新挂载（hide 会解除父子关系）；`parentWindow` 判空做幂等；锚点模块级单例并 `retain`。
- 仅用标量参数的 `objc_msgSend`（`alloc`/`init` + `setStyleMask:` 等），避免 arm64 上 ctypes 传 `NSRect` 结构体。
- 保留 Dock 图标；不改 Windows；不引 pyobjc。
- 对外 API 仍为 `apply_overlay_space_behavior`，[`window.py`](../../../window.py) 调用点不变。

## 验证

- 窗口态：复制 / 划词 → 右下角译文正常。
- 浏览器 macOS 原生全屏：复制文字 → 翻译窗浮在右下角并流式出译文。
- 切换 Space / 退出全屏：窗口跟随；Dock 图标仍在。
