# Edge Add-ons 上架清单（正式分发）

本项目**只上架 Microsoft Edge Add-ons**（开发者注册免费，无需支付 Chrome Web Store 的 $5）。  
不上架 Chrome Web Store；普通用户请使用 **Microsoft Edge** 安装扩展。

代码侧已固定扩展公钥与 ID（见根目录 `distribution.py` 的 `EXTENSION_EDGE_ID`）。上架是人工操作，完成后替换商店 URL 即可。

## 准备

1. 注册 [Edge Add-ons Partner Center](https://partner.microsoft.com/dashboard/microsoftedge/overview)（需 Microsoft 账号，**通常免费**）
2. 本地私钥：`extension/keys/extension.pem`（**勿提交 git**；丢失则开发期固定 ID 无法复现；请自行备份）
3. 构建：`.\scripts\build_extension.ps1 -Zip`
4. 上传前：从待上传的 `manifest.json` **删除 `key` 字段**（商店会自行签名；开发期 `key` 仅用于 unpacked 固定 ID）

## Edge Add-ons

1. 新建扩展 → 上传去掉 `key` 后的 zip
2. 可见性选 **Hidden / Unlisted**（仅持有链接可安装，等价未公开）
3. 隐私与权限说明：仅连接本机 `127.0.0.1`、不收集用户数据、需配套桌面应用；写清 `storage` / `nativeMessaging` / YouTube / localhost
4. 提交审核；通过后复制商品 URL 与 **商店分配的扩展 ID**
5. 若商店 ID ≠ `distribution.py` 的 `EXTENSION_EDGE_ID`：以商店 ID 为准，更新 `EXTENSION_EDGE_ID`、Inno `[Code]` 里的 `allowed_origins`，并重新发桌面版（否则 NM 自动配对会被拒绝）

## 上架后改仓库

同步替换下列位置的商店链接（上架前指向引导页）：

- [`distribution.py`](../../distribution.py) → `EDGE_ADDON_URL`
- [`docs/onboarding/index.html`](../onboarding/index.html) 内 `EDGE_ADDON_URL`
- 可选：README「给他人使用」中的链接说明

无需为「只改 URL」单独升版；若顺带改运行时代码则按 `AGENTS.md` 升版。

## GitHub Pages

仓库 Settings → Pages → Deploy from branch，目录选 `/docs`，使  
`https://zhuji423.github.io/clipboard-translator/onboarding/` 可访问。

## 为何不用 Chrome Web Store

Chrome Web Store 开发者注册需一次性约 **$5 USD**。产品决定仅支持 Edge 商店分发；开发者仍可用 Edge / Chromium 的「加载已解压」做本地调试。
