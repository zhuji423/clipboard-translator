---
name: pricing-titlebar-history
status: completed
planned_for: 0.1.0
implemented_in: [0.1.0]
summary: 费用估算、无边框标题栏、按日历史
source_cursor_plan: 费用展示与标题栏按钮_1519070b.plan.md
archived_at_version: 0.8.5
---

> 归档说明：本文件由 Cursor 计划 `费用展示与标题栏按钮_1519070b.plan.md` 入库。状态见文首 YAML；版本对照见 [`VERSION-PLANS.md`](../../VERSION-PLANS.md)。
# 费用展示 + 标题栏置顶/历史按钮

## 范围

1. **标题栏**：`×` 左侧固定两个按钮——置顶（图钉）、历史  
2. **每次翻译账单**：token + 估算 ¥，并对比「若无缓存」突出命中优势  
3. **历史**：查看翻译记录（默认今日；可切换日期；点某一条可回填主窗）

## UI（自定义标题栏）

原生系统标题栏塞不进自定义按钮，改为：

- [`window.py`](c:\my_data\code\cursor\clipboard-translator\window.py)：`FramelessWindowHint` + 自绘顶栏  
- 顶栏布局：`Clipboard Translator` | 弹性空白 | **置顶** | **历史** | **最小化** | **关闭**  
- 拖拽顶栏空白区移动窗口；置顶按钮切换 `WindowStaysOnTopHint`（按下态高亮）  
- 历史：弹出独立小窗 [`HistoryDialog`](c:\my_data\code\cursor\clipboard-translator\history.py)；顶部日期下拉（扫描已有日志文件）+ 列表

主窗底部状态栏扩展为两行信息（或一行换行），示例：

```
完成 · hit 1.2k / miss 80 / out 42
¥0.00012（若无缓存约 ¥0.00128 · 省 91%）
```

本地 LRU 命中时显示：`本地缓存 · ¥0`（不打 API）。

## 计费（官方 V4 Flash，人民币 / 百万 tokens）

写死在 [`pricing.py`](c:\my_data\code\cursor\clipboard-translator\pricing.py)，按 `config` 的 model 选价表（flash / pro）；未知模型默认 flash：

| | flash | pro |
|--|--|--|
| 输入 cache hit | 0.02 | 0.025 |
| 输入 cache miss | 1 | 3 |
| 输出 | 2 | 6 |

公式（与 DeepSeek 一致）：

```
cost = hit/1e6*hit_price + miss/1e6*miss_price + completion/1e6*out_price
no_cache = (hit+miss)/1e6*miss_price + completion/1e6*out_price
saved = no_cache - cost
```

从流式最终 `usage` 取：`prompt_cache_hit_tokens`、`prompt_cache_miss_tokens`、`completion_tokens`（无 usage 则不显示金额）。

## 历史存储（按日分文件，永久保留）

新增 [`history_store.py`](c:\my_data\code\cursor\clipboard-translator\history_store.py)：

- 文件：`clipboard-translator/data/history-YYYY-MM-DD.jsonl`（gitignore `data/`）  
- **永不自动清空、不删旧文件**；仅按日滚动新建文件便于检索  
- 每次翻译成功（含本地 LRU）append 一行：`ts, source, result, hit, miss, out, cost_yuan, saved_yuan, note`  
- 历史窗：日期选择器列出磁盘上全部 `history-*.jsonl`；默认选今天；列表倒序；点击 → 主窗回填原文/译文/费用  
- 与 LLM `messages` 一天一清无关：上下文会话仍日清，**账单日志长期保留**

## 接线

- [`translator.py`](c:\my_data\code\cursor\clipboard-translator\translator.py)：`TranslateResult` 带上完整 usage 数值（hit/miss/completion），不只字符串  
- [`main.py`](c:\my_data\code\cursor\clipboard-translator\main.py)：`finished` 后算价 → 更新状态栏 → `history_store.append`；历史窗信号回填  
- [`config.example.toml`](c:\my_data\code\cursor\clipboard-translator\config.example.toml)：无需用户填单价（代码内置）；`.gitignore` 加 `data/`

## 验收

1. 顶栏关闭键左侧有置顶、历史；置顶切换后窗口层级变化  
2. 连续翻译两次：第二次状态栏 hit 上升，显示实际 ¥ 与「若无缓存」对比  
3. 历史窗默认看今日；切换到昨日及更早日期仍能看到旧记录；旧 jsonl 不被删除  
4. 本地 LRU 命中仍记历史：`cost=0, note=local_cache`
