---
name: browser-vocabulary-learning
status: completed
planned_for: 0.18.0
implemented_in: [0.18.0]
summary: 普通网页与 YouTube 共用的音标、词源、构词和助记查词
source_cursor_plan: null
archived_at_version: 0.18.0
living_doc: plans/design/browser-bridge.md
---

# 浏览器词汇学习增强

## 目标

将现有 YouTube 字幕语境查词扩展到普通网页，并把“词典事实”和“生成式解释”分层：词典负责音标、词性与词源证据，LLM 负责结合当前句选择义项、压缩解释和生成助记。

## 实现

- 普通 HTTP/HTTPS 网页双击单个英文词触发；排除输入框与可编辑区，只发送当前词和最多 500 字符的所在句。
- FreeDictionaryAPI 默认提供音标与词典义；Wiktionary 提供词源证据；可选 Merriam-Webster Key 优先补充权威词源。
- 证据与当前句汇总后只调用一次现有 LLM。没有词源证据时，代码层丢弃模型返回的拆词与词源，避免伪词根。
- YouTube 保留暂停、键盘选词、划词翻译和续播状态机，共用增强后的查词响应和结果卡片。
- 发音走浏览器系统语音；来源链接和外部数据失败警告直接展示在卡片中。

## 验收

- Python 全量测试覆盖三类词典解析、词源多段选择、无证据约束、缓存与协议兼容。
- 扩展测试覆盖英文词校验、当前句提取和 500 字符上限；扩展可成功构建普通网页与 YouTube 两个内容脚本。
