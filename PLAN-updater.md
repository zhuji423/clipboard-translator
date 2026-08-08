# 应用内更新（Windows）

## 目标

从 GitHub 正式版 Releases 检查新版本；用户确认后下载对应产物，覆盖当前安装并自动重启。

## 限制

- PyInstaller 无法在进程内热替换已加载的 exe；实际路径是「下载 → 退出 → 覆盖/静默安装 → 再启动」。
- 仅跟踪正式版 `/releases/latest`（忽略 `preview`），避免每次 push 打扰用户。
- 本阶段只自动覆盖 **Windows 安装版 / 便携版**；源码运行或 macOS 仅提示并打开下载页。
- 发布包未做代码签名；SmartScreen 可能拦截新下载的 Setup/exe。
- CI 未发布 checksum；下载侧校验 GitHub 声明的 `size`（若有）。

## 形态识别

| 形态 | 判定 | 产物 | 应用方式 |
|------|------|------|----------|
| 安装版 | exe 位于 `%LOCALAPPDATA%\Programs\ClipboardTranslator` 或旁有 `unins000.exe` | `*-Setup.exe` | 退出后 `/VERYSILENT` 再启动 |
| 便携版 | 其余 frozen Windows 进程 | `*-portable.exe` | 退出后 `copy` 覆盖原 exe 再启动 |

辅助脚本为临时 `.cmd`（等待 PID 结束 → 覆盖 → 拉起 → 自删）。

## 入口

- 托盘菜单「检查更新」
- 设置对话框「检查更新」

实现见 `updater.py`，UI 接线见 `main.py`。
