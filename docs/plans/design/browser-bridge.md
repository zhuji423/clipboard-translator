# 浏览器字幕点词桥接

## 目标

**Microsoft Edge** 扩展在 YouTube 字幕上点词暂停并查义、划词整段翻译（普通拖选单句；Ctrl/⌘ 拖选可在扩展侧追加多句后再发同一 `POST /v1/translate`）；API Key 与 LLM 调用留在桌面端。正式分发仅走 Edge Add-ons（不上架 Chrome Web Store）。

## 本机协议（仅 `127.0.0.1`）

| 方法 | 路径 | 鉴权 | 说明 |
|------|------|------|------|
| GET | `/health` | 无 | 探测桌面是否在线、是否已有 token（引导页也会轮询） |
| POST | `/v1/pair` | 无（一次性短码） | body: `{ "code": "123456" }` → `{ token, port }` |
| POST | `/v1/lookup` | `Authorization: Bearer <token>` | body: `{ word, context, target_lang? }` |
| POST | `/v1/translate` | `Authorization: Bearer <token>` | body: `{ text }` → 桌面主窗整段翻译（划词） |

配对码默认 120 秒有效；令牌写入桌面 `config.toml` 的 `[bridge].token` 与扩展 `chrome.storage.local`。

## Native Messaging（零点击配对）

| 项 | 值 |
|----|-----|
| Host 名 | `com.clipboard_translator.bridge` |
| 程序 | `ClipboardTranslatorNmHost.exe`（与主程序同目录） |
| 请求 | `{ "type": "get_bridge_credentials" }` |
| 响应 | `{ "ok": true, "port": 17890, "token": "..." }`（不返回 API Key） |

Windows：Setup 与打包版首次运行写入 `HKCU\...\NativeMessagingHosts\...`，manifest 落在 `%APPDATA%\ClipboardTranslator\native_messaging\`。  
扩展在启动 / popup「自动连接」时 `sendNativeMessage`；失败回退短码 `/v1/pair`。

常量见仓库根目录 [`distribution.py`](../../../distribution.py)；扩展 ID 由构建时嵌入的公钥固定。

## 配置

```toml
[bridge]
enabled = true
port = 17890
token = ""
```

## 分发与引导

- 用户引导页：[`../../onboarding/index.html`](../../onboarding/index.html)（建议 GitHub Pages `/docs` → `/onboarding/`）
- 桌面：首次运行、设置「安装浏览器扩展」、托盘菜单、Inno 结束页均可打开引导 URL
- Edge Add-ons：上架后把 `distribution.py` / 引导页内的 `EDGE_ADDON_URL` 换成正式链接（清单见 [`../../guides/extension-store-publish.md`](../../guides/extension-store-publish.md)）

## 扩展

- 源码：`extension/src`
- 构建：`cd extension && npm install && npm run build`（或仓库根目录 `.\scripts\build_extension.ps1`）
- 普通用户：Edge Add-ons / 引导页；开发者才在 Edge 加载 `extension/dist`
- 划词翻译原理：[`../../guides/youtube-subtitle-phrase-translate.md`](../../guides/youtube-subtitle-phrase-translate.md)
- 版本与计划对照：[`../../VERSION-PLANS.md`](../../VERSION-PLANS.md)

## 安全约束

- 只监听回环地址
- 不向扩展 / NM 返回 API Key
- NM `allowed_origins` 钉死扩展 ID
- 限流、限制请求体大小
- 撤销配对会清空桌面 token
