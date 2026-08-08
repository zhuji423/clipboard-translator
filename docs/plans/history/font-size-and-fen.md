---
name: font-size-and-fen
status: completed
planned_for: 0.1.0
implemented_in: [0.1.0]
summary: 全局字号设置与费用用分展示
source_cursor_plan: 字号设置与费用分_fd67ffe6.plan.md
archived_at_version: 0.8.5
---

> 归档说明：本文件由 Cursor 计划 `字号设置与费用分_fd67ffe6.plan.md` 入库。状态见文首 YAML；版本对照见 [`VERSION-PLANS.md`](../../VERSION-PLANS.md)。
# 字号设置 + 历史全文 + 费用用「分」

## 1. 历史列表完整展示

改 [`history.py`](c:\my_data\code\cursor\clipboard-translator\history.py)：

- 去掉 56 字截断；原文/译文保留换行（列表内用 `QTextOption.WordWrap` / 自定义 item widget，或 `QListWidget` + `setWordWrap(True)` 并对 item 设够高的 `sizeHint`）
- 选定实现：**每条用自定义 `QWidget`（时间 / 原文标签 / 译文标签 / 费用）塞进 `setItemWidget`**，原文译文 `QLabel` 开 `setWordWrap(True)`，完整文本一一对应
- 点击整卡仍回填主窗

## 2. 设置：修改字体大小

- 标题栏在「历史」左侧加设置齿轮图标（Lucide `settings.svg`，同现有 icons 流程）
- 弹出 `SettingsDialog`：字号滑条或 SpinBox，范围 **10–22**，默认 **12**
- 作用范围：主窗原文/译文/状态、历史列表、设置窗自身
- 持久化：[`config.toml`](c:\my_data\code\cursor\clipboard-translator\config.toml) / example 增加

```toml
[app]
font_size = 12
```

[`config.py`](c:\my_data\code\cursor\clipboard-translator\config.py) 读入；[`main.py`](c:\my_data\code\cursor\clipboard-translator\main.py) / window 提供 `apply_font_size(n)`，改完即时生效并写回 config。

## 3. 费用单位：元太小时改「分」

改 [`pricing.py`](c:\my_data\code\cursor\clipboard-translator\pricing.py) 的 `fmt_yuan`（可改名为 `fmt_money`）：

- 内部仍用「元」存盘（`cost_yuan` 不变）
- 展示规则（保证可读数字大致在 0–100）：
  - `amount_yuan >= 1` → `x.xx元`
  - 否则 → `amount_yuan * 100` 显示为 **分**，例如 `0.00010元 → 0.010分`，`0.0015元 → 0.15分`；格式化到合适小数位（最多 3 位），去掉多余 0
- 状态栏「若无缓存 / 省」同一套格式
- 历史费用行同步

说明：单次翻译常见花费约 `0.0001` 元级，换成「分」后是 `0.01` 分级，比六位小数元更易读；若日后单次 ≥1 元仍显示元。

## 涉及文件

- [`history.py`](c:\my_data\code\cursor\clipboard-translator\history.py) — 完整对照卡片
- [`window.py`](c:\my_data\code\cursor\clipboard-translator\window.py) — 设置按钮 + `apply_font_size`
- [`pricing.py`](c:\my_data\code\cursor\clipboard-translator\pricing.py) — 分/元展示
- [`config.py`](c:\my_data\code\cursor\clipboard-translator\config.py) + `config.example.toml` — `font_size`
- 新建 `settings_dialog.py`；`assets/icons/settings.svg`
- [`main.py`](c:\my_data\code\cursor\clipboard-translator\main.py) — 接线、写回配置

## 验收

1. 历史长原文不再 `…` 截断，译文完整可见  
2. 设置里改大字号，主窗与历史立即变大，重启后保持  
3. 费用显示为 `x.xxx分`（或大额时 `元`），不再出现 `0.00010元` 这种难读形式
