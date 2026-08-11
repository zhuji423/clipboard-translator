---
name: ctrl-append-translate
status: completed
planned_for: 0.12.0
implemented_in: [0.12.0]
summary: YouTube 字幕 Ctrl/⌘ 追加划词，普通拖选仍单句立即翻译
archived_at_version: 0.12.0
---

# YouTube Ctrl 追加划词翻译

## 交互

| 手势 | 行为 |
|------|------|
| 字幕条拖选，未按修饰键 | 清空会话缓冲 → 只译本句 |
| 字幕条拖选，Ctrl（Win/Linux）或 ⌘（macOS） | 追加进会话缓冲 → 立刻翻译整段拼接原文 |
| 单击单词 | 点词查义；不进缓冲 |

## 实现

- [`extension/src/overlay.ts`](../../../extension/src/overlay.ts)：`PhraseSelectPayload.append = ctrlKey \|\| metaKey`
- [`extension/src/phrase_buffer.ts`](../../../extension/src/phrase_buffer.ts)：追加 / 去重 / 超集替换 / 截断
- [`extension/src/content.ts`](../../../extension/src/content.ts)：会话缓冲 + toast；SPA 换页清空；桌面 `/v1/translate` 不变

## 验证

- 普通拖选两句 → 第二次只译新句
- Ctrl/⌘ 连续两句 → 桌面原文为拼接段
- 重复划同一句不重复追加；单击 + 修饰键仍为查词
