# 文档索引

本目录是 `clipboard-translator` 的**唯一长文与计划存放处**。仓库根目录仅保留面向入口的三份文件：

| 根目录文件 | 用途 |
|------------|------|
| [`../README.md`](../README.md) | 安装、运行、用户向短说明 |
| [`../CHANGELOG.md`](../CHANGELOG.md) | 对外变更史（按版本） |
| [`../AGENTS.md`](../AGENTS.md) | Agent 改本仓库时的工作流约定 |

## 目录结构

```text
docs/
  README.md                 ← 本文件：文档总索引
  REPOSITORY.md             ← 仓库分区：代码 / 扩展 / 文档
  VERSION-PLANS.md          ← 版本 ↔ 计划 ↔ 完成工作（必读）
  onboarding/               ← 扩展安装引导页（GitHub Pages）
  todo/                     ← 未做功能清单与计划正文
  guides/                   ← 功能原理与使用详解
  plans/
    README.md               ← 已完成计划区说明
    design/                 ← 仍有效的设计说明（长期维护）
    history/                ← 已归档的迭代计划（含 YAML 元数据）
```

## 快速入口

| 想了解… | 打开 |
|---------|------|
| 某版本用了哪些计划、完成了什么 | [`VERSION-PLANS.md`](VERSION-PLANS.md) |
| 代码 / `extension/` / `docs/` 怎么分 | [`REPOSITORY.md`](REPOSITORY.md) |
| YouTube 划词→翻译原理 | [`guides/youtube-subtitle-phrase-translate.md`](guides/youtube-subtitle-phrase-translate.md) |
| 扩展安装引导页 | [`onboarding/index.html`](onboarding/index.html) |
| Edge Add-ons 上架清单 | [`guides/extension-store-publish.md`](guides/extension-store-publish.md) |
| 本机桥接 / NM 协议 | [`plans/design/browser-bridge.md`](plans/design/browser-bridge.md) |
| Windows / macOS 打包 | [`plans/design/windows-release.md`](plans/design/windows-release.md)、[`plans/design/macos-release.md`](plans/design/macos-release.md) |
| 应用内更新 | [`plans/design/updater.md`](plans/design/updater.md) |
| 日计费与余额 | [`plans/design/billing-balance.md`](plans/design/billing-balance.md) |
| 未做功能与待排期计划 | [`todo/`](todo/README.md) |

## 迭代时怎么写文档

每次版本迭代（升 `version.py`）时，按 [`plans/README.md`](plans/README.md) 与 [`../AGENTS.md`](../AGENTS.md)：

1. 把本次使用的 Cursor / 书面计划归档进 `plans/history/`（文首 YAML 标注 `planned_for` / `implemented_in`）。
2. 更新 [`VERSION-PLANS.md`](VERSION-PLANS.md) 对应版本小节。
3. 若产出长期有效设计结论，写入或更新 `plans/design/`。
4. 未做完的功能计划放进 [`todo/`](todo/README.md) 并更新其 README 一览表。
5. 用户向短说明只改根目录 `README.md`；变更史只写 `CHANGELOG.md`。
