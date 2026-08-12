---
name: macos-http-auto-pair
status: completed
planned_for: "0.17.1"
implemented_in:
  - "0.17.1"
archived_at_version: "0.17.1"
summary: >
  Mac 自动配对改走 HTTP /v1/auto_pair，停用 PyInstaller NmHost，
  避免 Gatekeeper 反复拦截 onefile 解压的 libpython。
source_cursor_plan: mac_http_零点击配对_751523c5.plan.md
---

# macOS HTTP 零点击配对（避开 Gatekeeper）

## 背景

0.17.0 在 Mac 上注册 Native Messaging host 后，Edge 每次启动 onefile `ClipboardTranslatorNmHost` 都会解压新的 `libpython3.12.dylib`，系统反复要求「仍然允许」。

## 实现

1. 桌面 [`browser_bridge.py`](../../browser_bridge.py)：`POST /v1/auto_pair`（loopback + 扩展 Origin 校验）
2. 扩展 `tryAutoPair`：先 HTTP，再 NM，再短码
3. Darwin：`register_native_messaging_host` 改为清理清单；打包不再附带 NmHost

## 验收

- 自动连接成功且无 Gatekeeper 弹窗
- 短码仍可用
