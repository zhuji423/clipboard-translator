# AGENTS.md

本文件是 `clipboard-translator` 的 Agent 工作流唯一说明。对目录内做任何改动前，先读本文件并按其执行。

## 范围

- 约束对象：本目录下的代码、配置示例、用户文档与版本记录
- 不把变更史写进本文件；运行时版本与对外日志分别在 `version.py`、`CHANGELOG.md`

## 改代码

- 小步修改，贴合现有 PySide6 / 模块拆分风格；不顺手大重构
- 只改任务需要的文件；不主动改 `config.toml` 中的密钥与个人配置
- 用户可见行为变更（窗口、托盘、翻译流程、设置项）完成后应可本地运行验证
- 需要重启常驻进程时：结束已有 `main.py` 再用项目 `.venv` 启动

## 写说明

| 内容 | 写到哪里 |
|------|----------|
| 安装、运行、用户向用法 | `README.md` |
| 设计方案、分阶段实施笔记 | `PLAN-*.md` |
| Agent 如何改本仓库 | 本文件 `AGENTS.md` |
| 对外变更史 | `CHANGELOG.md`（不要把变更史堆进 README） |

用户向说明保持简短；过程性讨论放 `PLAN-*.md`，完成后不必把整份方案贴进 README。

## 升版与写日志

对任何**用户可见或行为相关**的代码修改，必须在同一次改动中完成版本记录。

### 必须更新的文件

1. `version.py` 中的 `__version__`（唯一版本源）
2. `CHANGELOG.md` 顶部新增对应版本条目

托盘提示等若展示版本号，须与 `version.py` 一致（通常通过 `from version import __version__`）。

### 版本号规则（SemVer）

- **patch** `x.y.Z`：修 bug、小调整、文案/样式微调
- **minor** `x.Y.0`：新功能、配置项、行为增强（向下兼容）
- **major** `X.0.0`：不兼容变更、大幅重构影响使用方式

纯文档 / 注释 / Agent 规则，且不影响运行时行为时，可不升版；若同时改了运行时代码，仍要升版。

### CHANGELOG 写法

- 日期用 `YYYY-MM-DD`
- 分类使用：`Added` / `Changed` / `Fixed` / `Removed`
- 用中文短句，写清「为什么 / 用户能感知到什么」，不要只罗列文件名
- 新条目插在 `[Unreleased]` 之下

示例：

```markdown
## [0.2.0] - 2026-08-08

### Added

- 启动与显示时默认将窗口锚定到屏幕可用区域右下角（避开任务栏）
```

### GitHub Release（勿手打 tag）

- 合并/推送到 `main` 会触发 `.github/workflows/release-windows.yml`
- **每次** push：刷新 Pre-release `preview`（便携 exe + Setup）
- 当 `version.py` 的 `__version__` 尚无对应 `vX.Y.Z` tag 时：CI **自动创建**该 tag 并发布正式 Release
- 日常发布：按本节升版并写好 CHANGELOG 后 push `main` 即可；不要本地 `git tag`（除非热修已发布版本）
- 同版本后续小修若未升号：只更新 `preview`，不会重复发正式版

## 改完自检

- [ ] 行为相关改动已同步升高 `version.py`
- [ ] `CHANGELOG.md` 有对应条目与日期
- [ ] 若 UI/托盘展示版本号，与 `version.py` 一致
- [ ] 用户向用法有变时，已更新 `README.md`
- [ ] 未把密钥或本机路径写进示例配置与文档
- [ ] 若本次应出正式包：已升版，push `main` 后由 CI 打 tag / Release
