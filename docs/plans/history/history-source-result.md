---
name: history-source-result
status: completed
planned_for: 0.1.0
implemented_in: [0.1.0]
summary: 历史列表同时展示原文与译文
source_cursor_plan: 历史原文译文对照_654c2d41.plan.md
archived_at_version: 0.8.5
---

> 归档说明：本文件由 Cursor 计划 `历史原文译文对照_654c2d41.plan.md` 入库。状态见文首 YAML；版本对照见 [`VERSION-PLANS.md`](../../VERSION-PLANS.md)。
# 历史列表原文/译文一一对应

## 问题

[`history.py`](c:\my_data\code\cursor\clipboard-translator\history.py) 的 `_item_text` 只渲染了原文截断 + 费用行，看不到译文：

```python
return f"{entry.ts[-8:]}  {preview}\n{cost}"
```

数据里已有完整 `entry.source` / `entry.result`，无需改存储。

## 改动（仅 UI）

改 `_item_text` 为三行结构：

```
16:23:34
原文：It's the mic, scratching…
译文：麦克风蹭到衣服、头发…
0.00015元 · hit 412 / miss 67 / out 28 · 省 0.00038元
```

规则：
- 原文/译文各自单行预览，换行压成空格，超过约 56 字加 `…`
- 本地缓存条目费用行仍为 `本地缓存 · 0元`
- 列表项字高略增（`setSizeHint` 或依赖换行自动撑开），保证三行可读
- 点击回填逻辑不变（完整 `source`/`result`）

只动 [`history.py`](c:\my_data\code\cursor\clipboard-translator\history.py)；改完重启验证历史窗。
