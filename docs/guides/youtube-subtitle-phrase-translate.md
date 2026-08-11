# YouTube 字幕划词翻译：原理与演进

本文说明「在扩展字幕条上拖选一段文字 → 自动复制原文 → 带近期字幕上下文在桌面端翻译」是如何工作的，以及从不可靠到稳定（0.8.2–0.8.5）再到上下文翻译（0.13.0）的演进。

用户向短说明见仓库根目录 [`README.md`](../../README.md)；桥接协议总览见 [`../plans/design/browser-bridge.md`](../plans/design/browser-bridge.md)；版本与计划对照见 [`../VERSION-PLANS.md`](../VERSION-PLANS.md)。

## 你感知到的效果

1. 在 YouTube 开启字幕后，扩展会画出一条可交互的字幕条（隐藏原生字幕）。
2. **在字幕条上按住并拖过若干单词**：词会蓝色高亮。
3. **松手**：
   - 原文尽量写入系统剪贴板（便于你在别处粘贴）；
   - 同时经本机 HTTP 桥接通知桌面端，**不依赖**「剪贴板变化」是否被 Qt 收到；
   - 桌面翻译窗弹出，携带同视频经过的近期字幕，走流式翻译链路。
4. **单击单个词**：仍是点词查义弹层（另一条 API：`/v1/lookup`），不是整段翻译。

## 端到端数据流

```text
[扩展 content / overlay]
  pointerdown → setPointerCapture
  pointermove → 更新起止词索引 + .word-selected
  pointerup   → 按词索引 join(" ") 得到句子
       │
       ├─ navigator.clipboard.writeText(句子)   ← 尽力复制，不作为唯一触发
       │
       └─ chrome.runtime.sendMessage({ type: "TRANSLATE", text, context })
                │
[扩展 background / service worker]
       POST http://127.0.0.1:<port>/v1/translate
       Authorization: Bearer <配对 token>
                │
[桌面 browser_bridge.py]
       校验 token/session → 重新裁剪上下文 → TranslationRequest
                │
[桌面 main.py · UI 线程]
       原文归一化 → 上下文指纹缓存 → 无状态流式 LLM 翻译 → 置顶窗展示
```

## 0.13.0：低成本字幕上下文

- 扩展记录实际显示过的字幕，不要求每句都划词；逐步扩展和明显重叠 cue 会归并。
- 每次划词最多发送前 5 条字幕；单条约 500 Token、总上下文约 2000 Token，超限保留靠近当前句的末尾。
- 选中片段只是当前字幕的一部分时，额外发送当前完整字幕；两者完全相同时不重复。
- 拖选期间 overlay 与字幕上下文同时冻结，避免画面选中旧句却发送下一句语境。
- 切视频、seek、闲置 5 分钟、应用重启或手动清空都会切断旧上下文；上下文不写入历史。

### 关键模块

| 层 | 文件 | 职责 |
|----|------|------|
| 手势与高亮 | `extension/src/overlay.ts` | 禁用原生选区；pointer capture；词索引；自绘高亮；单击 vs 拖选 |
| 页面编排 | `extension/src/content.ts` | 挂上划词回调；写剪贴板；发 `TRANSLATE`；toast |
| 本机请求 | `extension/src/background.ts` | `fetch` `/v1/translate` |
| 协议 | `extension/src/shared.ts` | 消息类型定义 |
| HTTP 桥 | `browser_bridge.py` | `/v1/translate` 鉴权与回调 |
| 翻译入口 | `main.py` | Signal 切回 UI 线程；空白折叠；按来源应用显式上下文与缓存指纹 |

## 为什么必须「桥接直达」，不能只靠剪贴板？

产品本身的主路径是：**系统剪贴板变化 → 桌面监听 → 翻译**。早期划词也尝试「扩展 `writeText` → 等桌面听到」。

在 Chrome/Edge 上这经常失败或需用户再按一次 Ctrl+C，原因包括：

- 扩展写剪贴板后，**Qt `QClipboard.dataChanged` 不一定触发**（焦点、权限、浏览器实现差异）；
- 即使用户「看起来选中了」，扩展侧可能根本没得到有效句子（见下一节手势问题）。

因此从 **0.8.3** 起：复制仍做（同步剪贴板），**翻译触发以 `POST /v1/translate` 为准**。0.13.0 起桥接请求走独立的结构化上下文入口，不依赖剪贴板事件，也不会混入普通桌面复制窗口。

## 演进：哪里坏了，又修了什么

### 阶段 A：只有点词（0.8.0–0.8.1）

扩展只支持单击单词 → `/v1/lookup` → 页内 tip。没有整段划词翻译。

### 阶段 B：划词写剪贴板（0.8.2）—「看起来做了，经常不翻译」

- 松手后 `clipboard.writeText`，指望桌面剪贴板监听。
- **问题**：剪贴板事件不可靠 → 用户常感觉「选了没反应」，不得不手动 Ctrl+C。

### 阶段 C：桥接 `/v1/translate`（0.8.3）—「能翻译了，但手势仍飘」

- background 增加 `TRANSLATE` → `POST /v1/translate`。
- 桌面 `on_translate` → UI 线程翻译。
- **仍存问题**：手势仍半依赖浏览器原生 `Selection`，播放中、控件栏弹出时成功率低；flex 换行选区会带 `\n`，原文变成「一词一行」。

### 阶段 D：词索引拼句 + 拖选冻结重绘（0.8.4）

| 问题 | 修复 |
|------|------|
| `Selection.toString()` 在 flex 换行字幕上插入换行 | 按 `data-word-index` 取词，`join(" ")` 拼句，不再用 DOM Selection 文本 |
| 播放时 cue 刷新打断拖选 | `selecting` 期间 `render` 只记 `pendingCue`，松手后再重绘 |
| 从词缝起拖难命中 | 近邻吸附最近单词 |

### 阶段 E：自控手势 + 空白归一化（0.8.5）—当前稳定方案

此前约 40% 成功率的根因（对照 0.8.4）：

1. **两套机制打架**：CSS 仍是 `user-select: text`，同时又用自定义 pointer 算索引；用户以为浏览器已选中，扩展侧可能未进入有效划词。
2. **松手打不准**：在 `requestAnimationFrame` 后用 `elementFromPoint` / 36px 近邻找终点；光标已离开字幕条或落在 YouTube 底栏时终点丢失 → 静默失败。
3. **按下未命中**：近邻阈值过小，词缝/条外缘 `pointerdown` 直接 return，无高亮、无请求。
4. **事件被抢走**：未 `setPointerCapture`；播放后控制栏出现时 pointer 被播放器接住 → `pointercancel` 只清状态、**不发翻译**。
5. **无过程态**：没有 `pointermove` 更新终点、无自绘高亮 → 「没选中」与「选了但没发出」无法区分。
6. **桌面空白**：`_normalize_clipboard_text` 只 `strip()`，剪贴板路径一旦带 `\n` 会原样进原文框。

**0.8.5 对应改动：**

| 位置 | 改动 |
|------|------|
| `overlay.ts` | `user-select: none`；`touch-action: none`；`setPointerCapture`；`pointermove` 更新 `endIndex`；`.word-selected` 自绘高亮；近邻约 64px；失败 toast |
| `main.py` | `re.sub(r"\s+", " ", raw).strip()`，剪贴板与桥接共用 |
| 版本 / 扩展 | `0.8.5`，重建 `extension/dist` |

## 手势状态机（扩展侧）

```text
idle
  │ pointerdown 命中/吸附到词
  ▼
selecting (capture 中)
  │ pointermove → endIndex + 高亮
  │
  ├─ pointerup：起止不同或位移 > 阈值 → onPhraseSelect → 桥接翻译
  ├─ pointerup：几乎未移动且同词 → onWordClick → 查词
  └─ pointercancel / 无效 → toast，flush pendingCue
```

拖选期间字幕 cue 更新只写入 `pendingCue`，避免 DOM 被换掉导致索引失效。

## 桌面侧归一化

`_normalize_clipboard_text`（剪贴板监听与 `_on_bridge_translate_requested` 共用）：

1. 所有空白（含换行、多空格）折叠为单个空格；
2. `strip`；
3. 再按 `min_chars` / `max_chars` 过滤截断。

因此无论扩展拼句是否完美，原文框应保持**单行句子**。

## 安全与边界

- 桥接只绑 `127.0.0.1`；扩展不持有 LLM API Key。
- `/v1/translate` 需配对 token；正文长度上限约 8000。
- 首版仅 YouTube 交互字幕条；**不**解析页面幻灯片等其它蓝区选中。
- 系统任意处「复制即翻译」仍走剪贴板监听；字幕划词是**并行增强路径**。

## 本地验证清单

1. 桌面端已启用桥接并与扩展配对；用项目 `.venv` 运行的 `main.py`。
2. 重建并重载扩展：`.\scripts\build_extension.ps1` → 扩展管理页重新加载 → 刷新 YouTube。
3. 暂停拖选、播放中拖选、词缝起拖、拖出字幕条再松手、单击单词。
4. 确认：桌面窗出现、原文单行、失败时有 toast；剪贴板中有对应原文（尽力而为）。

## 相关代码锚点

- 手势：`SubtitleOverlay.beginSelectFromPoint` / `finishSelect`（`extension/src/overlay.ts`）
- 发送：`sendPhraseToDesktop`（`extension/src/content.ts`）
- HTTP：`translate`（`extension/src/background.ts`）
- 路由：`/v1/translate`（`browser_bridge.py`）
- 入口：`AppController._on_bridge_translate_requested`（`main.py`）
