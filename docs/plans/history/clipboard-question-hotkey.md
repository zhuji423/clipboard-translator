---
name: clipboard-question-hotkey
status: completed
planned_for: 0.10.0
implemented_in: [0.10.0]
summary: Windows 一步复制问答快捷键与独立连续会话
source_cursor_plan: null
archived_at_version: 0.10.0
---

# Windows 一步复制问答快捷键

## 目标

保留现有 `Ctrl+C → 剪贴板确认 → 自动翻译` 行为；新增可配置的全局快捷键，默认 `Ctrl+Shift+Q`。用户选中文本后按一次快捷键，应用自动复制选区并直接流式回答。

## 关键设计

- 使用 Win32 `RegisterHotKey`，不安装全局键盘钩子；设置冲突时恢复原快捷键且不写配置
- 热键触发后先等待修饰键释放，再用 `SendInput` 模拟 `Ctrl+C`
- 以 `GetClipboardSequenceNumber` 确认本次复制确实产生了新剪贴板内容；超时或非文本不使用旧剪贴板
- 在发送复制前武装问答捕获，只消费该轮剪贴板事件，避免同时触发现有自动翻译
- 翻译和问答使用独立模型会话；问答上下文只在当前进程内连续，可手动清空
- 问答不使用翻译 LRU；两种任务共享 generation 失效规则，但线程/Worker 各自持有到结束
- 历史 JSONL 增加 `mode`，缺少字段的旧记录按 `translate` 读取

## 验收

1. 普通 `Ctrl+C` 仍只走原有自动翻译流程。
2. 选中文本按问答快捷键只发起一次问答，不先翻译。
3. 连续问答能追问；翻译内容不进入问答 messages。
4. 无选区、复制失败、非文本和快捷键冲突均有明确反馈，不误用旧内容。
5. 设置中修改快捷键立即生效，应用退出时注销。
6. Windows 源码版与冻结版均完成桌面验证。
