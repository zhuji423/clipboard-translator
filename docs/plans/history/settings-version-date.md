---
name: settings-version-date
status: completed
planned_for: 0.9.4
implemented_in: [0.9.5]
summary: 设置页常显版本号与发布日期；检查更新对齐 GitHub published_at
source_cursor_plan: 设置页版本日期_e44955eb.plan.md
archived_at_version: 0.9.5
living_doc: plans/design/updater.md
---

> 归档说明：本文件由 Cursor 计划 `设置页版本日期_e44955eb.plan.md` 入库。状态见文首 YAML；版本对照见 [`VERSION-PLANS.md`](../../VERSION-PLANS.md)。

# 设置页版本号与发布日期

## 目标

在设置对话框底部「确定 / 取消」左侧常显当前版本与发布日期，并让「检查更新」结果可对齐、可跳转到 GitHub 正式版发布页。

## 做法

- **当前版本**：`version.__version__`（离线可显）
- **本机发布日期**：解析打包或仓库内 `CHANGELOG.md` 标题 `## [x.y.z] - YYYY-MM-DD`
- **线上最新版日期**：`GET /releases/latest` 的 `published_at`，按 Asia/Shanghai 格式化为日历日
- **链接**：非自动覆盖环境打开该版 `html_url`（回退 `/releases`）

## 不做

- 不补发历史缺失的 GitHub Release
- 不上 WinSparkle、不启动自动检查

## 涉及文件

- `settings_dialog.py`：底部一行 `版本·日期 | 检查更新 | … | 确定 | 取消`
- `updater.py`：`ReleaseInfo.published_at` / `html_url`；日期工具
- `main.py`：检查结果文案
- `clipboard_translator.spec` / `clipboard_translator_macos.spec`：打包附带 `CHANGELOG.md`
