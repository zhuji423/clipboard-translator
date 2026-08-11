# 未做功能（TODO）

本目录收录**尚未实现、暂停或仅部分落地**的功能计划。  
已完成迭代的计划正文在 [`../plans/history/`](../plans/history/)；长期设计说明在 [`../plans/design/`](../plans/design/)。  
版本对照总表：[`../VERSION-PLANS.md`](../VERSION-PLANS.md)。

> 约定：新开未做功能时，把完整计划放进本目录，并在本 README 登记一行；落地后移出（或改状态）并更新 `VERSION-PLANS.md`。

## 一览

| 计划文件 | 状态 | 目标版本 | 一句话 |
|----------|------|----------|--------|
| [immersive-subtitles.md](immersive-subtitles.md) | 待排期 | TBD | 对标 Language Reactor 的沉浸字幕（双语叠字 / B 站 / 学习向播放） |
| [account-sync-byok.md](account-sync-byok.md) | 待排期 | TBD | 自建账户 + BYOK 配置与历史多端同步 |
| [activity-achievements-recall.md](activity-achievements-recall.md) | 待排期 | TBD | 粘贴/翻译频次绿格子成就 + 偶发回想推送 |

## 各项说明

### 1. 沉浸式字幕（大图，待排期）

- **计划**：[immersive-subtitles.md](immersive-subtitles.md)
- **与现状关系**：0.8.x 已落地 YouTube **点词查义**与**划词整段翻译**（本机桥接），属于该大图的 MVP 切片；下列能力仍未做。
- **待做要点**（摘自计划 Phase）：
  - 双语叠字 / 侧栏逐句时间轴（非仅一条交互字幕条）
  - 悬停简释 vs 点击暂停的完整学习交互
  - 复读当前句、上一句 / 下一句、句末自动暂停
  - **B 站**同等字幕适配
  - 可选 Netflix 等站点；无轨时 OCR 兜底（桌面伴侣）
  - 生词本 / 历史与桌面更深同步

### 2. 自建账户与 BYOK 同步（待排期）

- **计划**：[account-sync-byok.md](account-sync-byok.md)
- **为何未做**：当前为单机 `config.toml` + 本地 JSONL 历史，产品重心在翻译与字幕交互。
- **待做要点**：
  - FastAPI + Postgres 自建后端（邮箱登录 / OTP）
  - 网页管理用户自备 API Key（加密存储，选中 active）
  - 桌面拉取 `runtime-config` 后**直连**模型（服务端不中转 LLM）
  - 翻译历史增量 push / pull 与本地合并
  - HTTPS、限流、密钥轮换与隐私说明

### 3. 活动绿格子、成就与回想（待排期）

- **计划**：[activity-achievements-recall.md](activity-achievements-recall.md)
- **与现状关系**：现有 `history-YYYY-MM-DD.jsonl` 已够做日计数热力图；成就/回想为本地派生层。
- **待做要点**：
  - GitHub 式年热力图（颜色 = 当日翻译/问答次数）
  - 连续天数与轻量成就徽章 + 托盘解锁提示
  - 偶发回想推送（时间锚点 / 随机稀疏），隐私默认偏保守
  - Phase A 先绿格子，再成就，再回想

## 已迁出（完成）

| 主题 | 归档 | 版本 |
|------|------|------|
| 扩展分发与 NM 自动配对 | [`../plans/history/extension-distribution.md`](../plans/history/extension-distribution.md) | 0.9.0 |
| Edge Add-ons 人工上架清单 | [`../guides/extension-store-publish.md`](../guides/extension-store-publish.md) | 运维（非代码） |
| 术语括注提示词 | [`../plans/history/term-gloss-prompt.md`](../plans/history/term-gloss-prompt.md) | 0.11.1 |

## 设计文档中的「后续」项（无独立计划稿）

下列来自已完成设计/实现文档中的远期备注，暂不单独成文，避免遗忘：

| 来源 | 未做内容 |
|------|----------|
| [`../plans/design/macos-release.md`](../plans/design/macos-release.md) | macOS 代码签名与 Apple 公证；macOS 开机自启完善 |
| [`../plans/design/updater.md`](../plans/design/updater.md) | 发布包代码签名 / checksum；macOS 应用内自动覆盖更新 |
| [`../plans/design/billing-balance.md`](../plans/design/billing-balance.md) | 多机历史汇总或余额差值口径 |

若某项开始正式排期，应在本目录新建计划文件并从上表删除或改为链接。

## 与 `plans/history` 的关系

- **`docs/todo/`**：未做功能的**现行工作清单**与计划正文（会改、会跟进）。
- **`docs/plans/history/`**：同主题计划的**归档快照**（入库时的原文，便于对照「当时怎么写的」）。

完成某项后：更新计划 YAML 的 `status` / `implemented_in`，从本 README 一览表移除或标「已完成并迁出版本」，并写进 `VERSION-PLANS.md`。
