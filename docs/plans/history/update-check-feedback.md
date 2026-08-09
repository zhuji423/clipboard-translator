---
name: update-check-feedback
status: completed
planned_for: 0.9.5
implemented_in: [0.9.5]
summary: 检查更新反馈与 Worker 生命周期修复
source_cursor_plan: 检查更新反馈修复_d166b5d1.plan.md
archived_at_version: 0.9.5
living_doc: plans/design/updater.md
---

> 归档说明：本文件由 Cursor 计划 `检查更新反馈修复_d166b5d1.plan.md` 入库。状态见文首 YAML；版本对照见 [`VERSION-PLANS.md`](../../VERSION-PLANS.md)。

# 检查更新反馈与 Worker 生命周期修复

## 问题

检查更新进入忙碌状态后会永久停在「正在检查…」。根因是控制器只保存了 `QThread`，检查与下载 Worker 都只是局部变量；方法返回后 Worker 被 Python 回收，线程仍存活却不会执行任务或发出终态信号。

原 Cursor 计划只处理了检查过程的可见反馈，没有验证后台任务生命周期，因此不能仅凭 UI 状态将功能判定为完成。

## 做法

- 检查中：禁用「检查更新」，版本标签旁显示「正在检查…」
- 忙碌再点：静默忽略，不再弹误导框
- 结果 / 错误 / 下载进度：设置窗打开时 parent 用设置对话框
- 下载中：按钮保持禁用，状态改为「正在下载…」
- 控制器分别强引用检查与下载阶段的线程和 Worker，直到对应线程发出 `finished`
- 成功、请求失败和下载失败都必须清除 busy、恢复按钮并释放线程/Worker 引用
- 更新应用脚本不再运行外部 PID 查询；便携版重试覆盖，复制成功后才删除下载包并重启新版

## 验证

- 强制垃圾回收后，运行中的检查 Worker 与下载 Worker 仍然存活
- 无新版时显示「当前已是最新正式版」并恢复设置页状态
- GitHub 请求失败或下载失败时显示警告并恢复设置页状态
- 隔离便携版能下载新 exe、等待旧进程退出、覆盖原文件并从同一路径重启
- 完整测试集通过后，才将本计划视为 `completed`
