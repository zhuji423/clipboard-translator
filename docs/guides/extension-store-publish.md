# Edge Add-ons 上架与运维清单

本项目**只上架 Microsoft Edge Add-ons**（开发者注册免费）。不上架 Chrome Web Store。

## 运维项是否仍合适（相对早期 0.9.0 备忘）

| 项 | 现状 | 是否仍要做 |
|----|------|------------|
| 启用 GitHub Pages（`/docs`） | 引导页 URL 已写进桌面端 / 扩展，但站点需你开启 | **要**（见下文） |
| 备份 `extension/keys/extension.pem` | 已 gitignore；本机若有请备份 | **要**（开发期固定 ID 用） |
| 提交 Edge Unlisted / Hidden | 尚未上架 | **要**（用本指南的 store zip） |
| 上架后改商店 URL | 现为 `EDGE_ADDON_URL`（无 `CHROME_STORE_URL`） | **上架后要** |
| 核对商店扩展 ID 与 NM `allowed_origins` | 商店 ID 可能与开发 ID 不同 | **上架后要** |
| push `main` 打 `v0.9.0` Release | 已发布 **v0.9.2**（含 Setup / portable / NmHost / extension zip） | **已完成**，无需再为 0.9.0 操作 |

说明：浏览器仍要求用户点一次「获取」；exe 只能打开引导页并完成安装后的自动配对。

## 启用 GitHub Pages（展示 `docs/` + onboarding）

目标 URL：`https://zhuji423.github.io/clipboard-translator/onboarding/`

### 网页操作（推荐）

1. 打开仓库 **Settings → Pages**  
   https://github.com/zhuji423/clipboard-translator/settings/pages
2. **Build and deployment → Source** 选 **Deploy from a branch**
3. Branch 选 **`main`**，文件夹选 **`/docs`**，保存
4. 等 1–2 分钟；可用  
   https://zhuji423.github.io/clipboard-translator/  
   与  
   https://zhuji423.github.io/clipboard-translator/onboarding/  
   验证（`docs/README.md` 会变成站点首页，`docs/onboarding/` 为引导页）

### 命令行（需有仓库 admin 权限）

```powershell
gh api repos/zhuji423/clipboard-translator/pages -X POST `
  -f build_type=legacy `
  -f source[branch]=main `
  -f source[path]=/docs
```

若已存在 Pages 配置，改为更新：

```powershell
gh api repos/zhuji423/clipboard-translator/pages -X PUT `
  -f build_type=legacy `
  -f source[branch]=main `
  -f source[path]=/docs
```

## 打 Edge 审核用压缩包

```powershell
.\scripts\build_extension.ps1 -StoreZip
```

产物：`dist\extension\ClipboardTranslator-extension-{version}-edge-store.zip`  
（已去掉 manifest `key`，并去掉 `.map`，适合 Partner Center 上传）

本地侧载仍用 `extension\dist` 或 `-Zip`（保留 `key` 以固定开发 ID）。

## Partner Center 提交步骤

1. 注册 [Edge Add-ons Partner Center](https://partner.microsoft.com/dashboard/microsoftedge/overview)
2. 新建扩展 → 上传上面的 **edge-store.zip**
3. 可见性选 **Hidden / Unlisted**（仅链接可装）
4. 隐私与权限说明应写清：
   - `storage`：在浏览器本地保存桥接端口、令牌和用户设置。
   - `nativeMessaging` / `http://127.0.0.1/*`：仅用于发现并连接配套桌面应用，词典与 LLM Key 不返回扩展。
   - `http://*/*` / `https://*/*`：支持在普通网页主动双击英文单词查词，以及 YouTube 字幕点词 / 划词；普通网页不常驻读取或上传整页，只在用户双击后发送所选单词和最多 500 字符的当前句，且排除输入框和可编辑区域。
   - 扩展不收集用户数据；网页语境仅传到用户本机桌面端，再由用户配置的数据源处理。
5. 提交审核；通过后记下 **商品 URL** 与 **扩展 ID**

## 上架后改仓库

1. `distribution.py` → `EDGE_ADDON_URL` = 商品链接  
2. `docs/onboarding/index.html` 内同名常量  
3. 若商店 ID ≠ `EXTENSION_EDGE_ID`：更新 `EXTENSION_EDGE_ID`、Inno `[Code]` 中 `allowed_origins`，升版并 push（否则 NM 自动配对会被拒绝）

## 备份私钥

```text
extension/keys/extension.pem   ← 勿提交 git；请复制到密码管理器或安全盘
```
