---
name: youtube-inline-phrase-translation
status: completed
planned_for: 0.16.0
implemented_in: [0.16.0]
summary: 键盘短语在字幕旁出译文；Space 关弹层并续播
archived_at_version: 0.16.0
---

# YouTube 键盘短语页内译文

## 背景

0.15.0 键盘选词后，多词 `Enter` 仍走桌面 `/v1/translate`，翻译窗抢焦点导致 Space 无法续播。看课场景需要译文留在字幕旁。

## 方案

- `/v1/translate` 增加 `inline: true`：桥接线程同步收齐流式译文并返回，不唤起桌面窗
- 键盘短语提交走 inline + tip；鼠标拖选保持桌面窗
- Space / tip「关闭并继续」：关 tip、退键盘模式、`video.play()`

## 验收

1. 键盘扩选 → Enter：tip 出译文，桌面不抢焦点
2. 一次 Space 续播
3. 鼠标拖选仍唤起桌面翻译
