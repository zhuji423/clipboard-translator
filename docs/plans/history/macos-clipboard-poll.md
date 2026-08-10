---
name: macos-clipboard-poll
status: completed
planned_for: 0.9.6
implemented_in: [0.9.6]
summary: macOS 后台剪贴板轮询 + 全屏 Space 叠层
archived_at_version: 0.9.6
---

# macOS 后台剪贴板监听与全屏叠层

## 问题

1. Qt 文档与实机验证：`QClipboard.dataChanged` 在 macOS 上对**其他应用**的剪贴板变更，往往只在本进程被激活时才会发出。托盘 / 菜单栏常驻时，用户在别处 ⌘C 会「完全没反应」。Windows 无此限制。
2. macOS 系统全屏会进入独立 Space；仅有 `WindowStaysOnTopHint` 的窗口留在桌面 Space，全屏后「看不见翻译窗」。

## 方案

- 新增 [`macos_clipboard.py`](../../../macos_clipboard.py)：用 ctypes 调 `NSPasteboard.generalPasteboard.changeCount`，约 300ms 轮询；计数前进时再走原有 `on_clipboard_changed`（settle / confirm 不变）。
- 新增 [`macos_window.py`](../../../macos_window.py)：对主窗 `setCollectionBehavior: canJoinAllSpaces | fullScreenAuxiliary`，在 `show` / 置顶切换后应用。
- 仅 `sys.platform == "darwin"` 启用；Windows 仍只靠 `dataChanged` / 原有置顶。
- 不引入 pyobjc 依赖。

## 验证

- 应用在后台时 `pbcopy` / 其他 App ⌘C → 约 1s 内出现翻译窗。
- Edge / YouTube 等系统全屏时，置顶翻译窗仍可见。
- Windows 路径未改行为。
