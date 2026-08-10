---
name: manual-input-translation
status: completed
planned_for: 0.11.0
implemented_in: [0.11.0]
summary: 半透明手动输入翻译框
source_cursor_plan: 手动输入翻译框 V1
archived_at_version: 0.11.0
---

# 半透明手动输入翻译框 V1

## 目标

- 解决页面、图片或视频画面里的文字无法复制时，仍能快速送入桌面端翻译的问题。
- 第一版不做 OCR/ASR，只提供全局 `Ctrl+M` 呼出的半透明输入入口。

## 完成范围

- 新增置顶浮动输入框，支持输入、拖动、调透明度和尺寸。
- `Enter` 提交翻译，`Shift+Enter` 换行，`Esc` 关闭。
- 提交后复用现有翻译管线、缓存、历史和费用统计。
- 保存窗口位置、尺寸与透明度，为后续 OCR 自动填入预留入口。

## 后续方向

- 框选屏幕区域后 OCR 识别，并把结果自动填入该输入框由用户确认。
