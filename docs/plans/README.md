# 计划文档

## 子目录

| 目录 | 用途 |
|------|------|
| [`design/`](design/) | **长期维护**的设计说明（协议、打包、计费等）。实现变更时同步改这里。 |
| [`history/`](history/) | **已归档**的迭代计划全文（含 YAML：计划对应哪个版本、完成于哪些版本）。 |

**未做功能**不放在本目录，统一见 [`../todo/`](../todo/README.md)。

版本对照总表：[`../VERSION-PLANS.md`](../VERSION-PLANS.md)。

## 每次版本迭代必做

1. **编写计划**：可在 Cursor Plans 起草；定稿后**必须**入库（完成项进 `history/`，未做项进 `../todo/`）。
2. **标注元数据**（文首 YAML）：
   - `planned_for`：计划编写时瞄准的版本
   - `implemented_in`：实际落地的版本列表（未做则为 `[]`）
   - `status`：`completed` / `paused` / `todo`
   - `archived_at_version`：归档进仓库时的当前产品版本
3. **更新** [`../VERSION-PLANS.md`](../VERSION-PLANS.md) 该版本章节：「使用了哪些计划」「完成了哪些工作」。
4. **设计沉淀**：若结论长期有效，更新或新建 `design/*.md`。
5. **不要**把计划正文堆回仓库根目录或只留在本机 `~/.cursor/plans/`。

## design/ 现有文档

| 文件 | 主题 |
|------|------|
| [browser-bridge.md](design/browser-bridge.md) | 本机 HTTP 桥接、Native Messaging 与扩展配对 |
| [updater.md](design/updater.md) | Windows 应用内更新 |
| [windows-release.md](design/windows-release.md) | Windows 打包与 CI 发布 |
| [macos-release.md](design/macos-release.md) | macOS 打包与公证后续 |
| [billing-balance.md](design/billing-balance.md) | 日计费与余额展示 |
