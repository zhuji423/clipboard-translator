---
name: youtube-keyboard-subtitle-selection
status: completed
planned_for: 0.15.0
implemented_in: [0.15.0]
summary: YouTube 字幕暂停后用方向键完成单词查义与短语翻译
source_cursor_plan: null
archived_at_version: 0.15.0
---

# YouTube 字幕纯键盘查词

## 一句话目标

把「听到生词 -> 暂停 -> 移动鼠标 -> 选词 -> 复制」缩短为纯键盘闭环：按 `Space` 暂停后自动选中当前字幕最后一个词，用方向键调整选区，再按 `Enter` 查义或翻译。

## 用户流程

1. 视频播放时按 `Space` 暂停。
2. 当前交互字幕的最后一个单词自动高亮；这个词通常就是用户刚听到并想查询的词。
3. 按 `Left` / `Right` 在当前字幕内逐词移动。
4. 按 `Shift+Left` / `Shift+Right` 从锚点扩展或收缩短语选区。
5. 按 `Enter` 智能提交：
   - 只选中一个词：调用现有语境查词链路，在页内弹层显示词义，不写系统剪贴板。
   - 选中多个词：调用现有短语翻译链路，同步剪贴板并唤起桌面翻译窗。
6. 按 `Esc` 先关闭查词弹层；无弹层时再次按下则退出键盘模式但保持暂停。
7. 按 `Space` 关闭弹层、退出键盘模式并恢复播放。

`Up` / `Down` 继续交给 YouTube 控制音量；退出键盘模式后，左右键恢复 YouTube 原有的进退行为。

## 交互状态机

- **进入**：视频产生暂停事件且当前字幕包含可选单词时进入；默认锚点和当前游标均为最后一个 `word` token。
- **例外**：鼠标点词查义所触发的插件内部暂停不得重新进入键盘模式，避免高亮末词覆盖用户点击的词。
- **移动**：普通左右键移动当前游标并折叠为单词选区；Shift+左右键保留锚点、移动另一端，从而扩选或收缩。
- **边界**：到达首词或末词后停止，不循环跳转。
- **请求**：移动到新词时不自动调用模型，只有按 `Enter` 才提交；开始新查询时使旧请求失效，旧响应不得覆盖新结果。
- **退出**：视频恢复播放、字幕消失、YouTube SPA 切换视频或扩展销毁时清空键盘选区。
- **避让**：输入框、搜索框、评论编辑区和其他 `contenteditable` 元素获得焦点时不拦截按键；带 `Ctrl`、`Alt` 或 `Meta` 的方向键保持原行为。

## 实现摘要（0.15.0）

- [`extension/src/word_selection.ts`](../../../extension/src/word_selection.ts)：可单测选区状态机
- [`extension/src/overlay.ts`](../../../extension/src/overlay.ts)：键盘选区高亮 / 游标 outline、cue 冻结、提交复用点词与划词回调
- [`extension/src/content.ts`](../../../extension/src/content.ts)：`pause`/`play` 生命周期、capture 按键拦截、`pauseOwned` 保护

## 本期不做

- 不增加 B 站或通用网页字幕适配。
- 不解析 YouTube 逐词时间戳；当前字幕末词作为暂停时的默认候选。
- 不新增快捷键配置页；首版按键固定，后续根据实际使用再决定是否开放映射。
- 不增加自动查词、自动复制单词或按方向键即调用模型，避免剪贴板污染和不必要费用。
