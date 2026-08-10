# 版本 ↔ 计划 ↔ 完成工作

本文是**迭代对照表**：每个版本「依据哪些计划编写 / 执行」，以及「按计划完成了什么」。  
对外用户可见变更仍以根目录 [`CHANGELOG.md`](../CHANGELOG.md) 为准；计划正文在 [`plans/history/`](plans/history/) 与 [`plans/design/`](plans/design/)。

> 整理入库版本：文档结构整理发生在 **0.8.5** 之后（纯文档，未单独升版）。此后每次升版必须更新本表。

## 状态图例

| 状态 | 含义 |
|------|------|
| completed | 计划已落地，对应版本已发布 |
| paused | 有计划，主动搁置 |
| todo / paused | 尚未排期、暂停，或仅部分被后续工作覆盖（正文在 `todo/`） |
| meta | 流程/文档约定，不对应产品功能版本 |

---

## 按版本

### 0.1.0

| 项 | 内容 |
|----|------|
| 编写/使用的计划 | [`clipboard-llm-translator`](plans/history/clipboard-llm-translator.md)、[`pricing-titlebar-history`](plans/history/pricing-titlebar-history.md)、[`deepseek-prefix-cache`](plans/history/deepseek-prefix-cache.md)、[`history-source-result`](plans/history/history-source-result.md)、[`font-size-and-fen`](plans/history/font-size-and-fen.md) |
| 完成工作 | 剪贴板监听 + LLM 流式翻译；费用估算与历史；标题栏；DeepSeek 前缀缓存友好 messages；字号与「分」展示；引入 `version.py` + `CHANGELOG` |

### 0.1.1

| 项 | 内容 |
|----|------|
| 编写/使用的计划 | [`clipboard-race`](plans/history/clipboard-race.md) |
| 完成工作 | 缓存命中取消进行中任务；剪贴板防抖；复制译文忽略；触发翻译不抢焦点 |

### 0.2.0

| 项 | 内容 |
|----|------|
| 编写/使用的计划 | [`windows-release`](plans/history/windows-release.md)（设计摘要：[design/windows-release](plans/design/windows-release.md)） |
| 完成工作 | PyInstaller + Inno；`paths.py` 用户目录；GHA preview / 正式 Release |

### 0.2.1

| 项 | 内容 |
|----|------|
| 编写/使用的计划 | [`anchor-and-voice-confirm`](plans/history/anchor-and-voice-confirm.md)（计划文内曾写 0.1.2，实际随 0.2.x 发布） |
| 完成工作 | 首次显示右下角锚定；settle + confirm 抑制语音剪贴板闪烁 |

### 0.3.0 – 0.3.3

| 项 | 内容 |
|----|------|
| 编写/使用的计划 | [`daily-billing-balance`](plans/history/daily-billing-balance.md)（设计：[design/billing-balance](plans/design/billing-balance.md)） |
| 完成工作 | 今日已用 + DeepSeek 余额；后续 patch 修正文案、并发刷新与换行展示 |

### 0.4.0

| 项 | 内容 |
|----|------|
| 编写/使用的计划 | [`icon-and-llm-settings`](plans/history/icon-and-llm-settings.md) |
| 完成工作 | 统一剪贴板图标；设置内配置 API URL / Key / 模型并热重载 |

### 0.5.0

| 项 | 内容 |
|----|------|
| 编写/使用的计划 | [`cross-platform-macos`](plans/history/cross-platform-macos.md)（设计：[design/macos-release](plans/design/macos-release.md)） |
| 完成工作 | macOS 运行与 `.app` 打包 / CI；公证列为后续 |

### 0.6.0

| 项 | 内容 |
|----|------|
| 编写/使用的计划 | [`window-edge-resize`](plans/history/window-edge-resize.md) |
| 完成工作 | 无边框主窗四边与四角拖拽缩放 |

### 0.7.0

| 项 | 内容 |
|----|------|
| 编写/使用的计划 | [`icon-cache-and-updater`](plans/history/icon-cache-and-updater.md)（设计：[design/updater](plans/design/updater.md)） |
| 完成工作 | 应用内检查更新；构建前重生 `app.ico`；任务栏图标缓存说明 |

### 0.8.0

| 项 | 内容 |
|----|------|
| 编写/使用的计划 | [`interactive-subtitles-mvp`](plans/history/interactive-subtitles-mvp.md)（设计：[design/browser-bridge](plans/design/browser-bridge.md)） |
| 完成工作 | 本机桥接配对；YouTube 点词查义扩展；设置「浏览器集成」；扩展随 Release 发布 |

### 0.8.1

| 项 | 内容 |
|----|------|
| 编写/使用的计划 | [`subtitle-layout-tip-ux`](plans/history/subtitle-layout-tip-ux.md) |
| 完成工作 | 字幕相对播放器定位避让底栏；查词弹层拖动 / 缩放 |

### 0.8.2 – 0.8.3

| 项 | 内容 |
|----|------|
| 编写/使用的计划 | [`phrase-select-clipboard`](plans/history/phrase-select-clipboard.md) |
| 完成工作 | **0.8.2** 拖选写剪贴板；**0.8.3** 改为 `POST /v1/translate` 直达桌面（解决「常需再 Ctrl+C」） |
| 原理长文 | [`guides/youtube-subtitle-phrase-translate.md`](guides/youtube-subtitle-phrase-translate.md) |

### 0.8.4

| 项 | 内容 |
|----|------|
| 编写/使用的计划 | [`phrase-newline-and-interrupt`](plans/history/phrase-newline-and-interrupt.md) |
| 完成工作 | 词索引空格拼句；拖选期间冻结字幕重绘；间隙起拖吸附 |

### 0.8.5

| 项 | 内容 |
|----|------|
| 编写/使用的计划 | [`phrase-select-stability`](plans/history/phrase-select-stability.md) |
| 完成工作 | pointer capture + 自绘高亮；桌面空白归一化；失败 toast |
| 附带文档整理 | 建立本 `docs/` 体系；归档本机 Cursor 计划；根目录 `PLAN-*` 迁入 `plans/design/` |

### 0.9.0

| 项 | 内容 |
|----|------|
| 编写/使用的计划 | [`extension-distribution`](plans/history/extension-distribution.md)（设计：[design/browser-bridge](plans/design/browser-bridge.md)） |
| 完成工作 | 引导页 + 首次运行/设置/托盘/Inno 打开扩展安装说明；默认启用 bridge；NM host 与 HKCU 注册；扩展 `nativeMessaging` 自动配对（短码兜底）；popup 状态与托盘提示；公钥固定扩展 ID；商店上架运维清单 |
| 上架后续 | [`guides/extension-store-publish.md`](guides/extension-store-publish.md)（人工 Unlisted，替换商店 URL） |

### 0.9.1

| 项 | 内容 |
|----|------|
| 编写/使用的计划 | 延续 [`extension-distribution`](plans/history/extension-distribution.md) |
| 完成工作 | 正式分发改为仅 Edge Add-ons；引导页与安装入口去掉 Chrome 商店路径；上架清单改为 Edge-only |

### 0.9.2

| 项 | 内容 |
|----|------|
| 编写/使用的计划 | 延续 [`extension-distribution`](plans/history/extension-distribution.md) |
| 完成工作 | 开发人员模式侧载时不打开未部署的远程 onboarding（避免 404） |

### 0.9.3

| 项 | 内容 |
|----|------|
| 编写/使用的计划 | 桥接稳定性小修 |
| 完成工作 | 忽略客户端提前断开导致的 ConnectionResetError 控制台噪音 |

### 0.9.5

| 项 | 内容 |
|----|------|
| 编写/使用的计划 | [`settings-version-date`](plans/history/settings-version-date.md)、[`update-check-feedback`](plans/history/update-check-feedback.md)（设计：[design/updater](plans/design/updater.md)） |
| 完成工作 | 设置页展示版本号与发布日期；解析正式版日期/链接；检查状态可见；结果挂设置窗；修复 Worker 提前回收与更新脚本等待管道阻塞 |

### 0.9.6

| 项 | 内容 |
|----|------|
| 编写/使用的计划 | [`macos-clipboard-poll`](plans/history/macos-clipboard-poll.md) |
| 完成工作 | macOS 后台用 `NSPasteboard.changeCount` 轮询补齐剪贴板监听；主窗加入全屏 Space 叠层；Windows 路径不变 |

### 0.9.7

| 项 | 内容 |
|----|------|
| 编写/使用的计划 | [`macos-fullscreen-overlay`](plans/history/macos-fullscreen-overlay.md) |
| 完成工作 | 修正全屏叠层：`fullScreenAuxiliary` 仅对 NSPanel 生效；用不可见锚点 Panel + `addChildWindow` 让翻译窗出现在原生全屏 Space 上；保留 Dock |

### 0.10.0

| 项 | 内容 |
|----|------|
| 编写/使用的计划 | [`clipboard-question-hotkey`](plans/history/clipboard-question-hotkey.md) |
| 完成工作 | 保留 Ctrl+C 自动翻译；新增 Windows 可配置的一步问答快捷键；隔离连续问答会话；统一翻译/问答历史；按 generation 持有任务线程，并在 Qt 确认销毁后释放引用 |

### 0.11.0

| 项 | 内容 |
|----|------|
| 编写/使用的计划 | [`manual-input-translation`](plans/history/manual-input-translation.md) |
| 完成工作 | 新增 Ctrl+M 半透明手动输入翻译框；支持置顶、拖动、透明度/尺寸调整与状态持久化；提交后复用现有翻译管线、缓存、历史和费用统计 |

---

## 未完成 / 暂停（todo）

现行清单与说明见 [`todo/README.md`](todo/README.md)。

| 计划 | 状态 | 目标版本 | 说明 |
|------|------|----------|------|
| [`immersive-subtitles`](todo/immersive-subtitles.md) | todo | TBD | 沉浸字幕大图；点词/划词 MVP 已在 0.8.x 部分落地 |
| [`account-sync-byok`](todo/account-sync-byok.md) | todo | TBD | 自建账户与 BYOK 同步 |

归档快照仍保留在 [`plans/history/`](plans/history/)（入库时原文）。

---

## 元计划

| 计划 | 完成情况 |
|------|----------|
| [`agents-md-workflow`](plans/history/agents-md-workflow.md) | 约定收拢为根目录 `AGENTS.md`；规则文件改为指向它 |

---

## 计划文件命名约定（后续新增）

1. Cursor 侧可继续用中文计划名；**入库仓库时**使用英文 kebab-case：`plans/history/<slug>.md`。
2. 文首必须含 YAML：`status`、`planned_for`、`implemented_in`、`summary`、`source_cursor_plan`（若有）、`archived_at_version`。
3. 长期有效结论同步进 `plans/design/`；一次性迭代过程进 `history/`。
4. 升版同一批改动中更新本文件对应章节。
