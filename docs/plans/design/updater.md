# 应用内更新（Windows）

## 目标

从 GitHub 正式版 Releases 检查新版本；用户确认后下载对应产物，覆盖当前安装并自动重启。

## 限制

- PyInstaller 无法在进程内热替换已加载的 exe；实际路径是「下载 → 退出 → 覆盖/静默安装 → 再启动」。
- 仅跟踪正式版 `/releases/latest`（忽略 `preview`），避免每次 push 打扰用户。
- 本阶段只自动覆盖 **Windows 安装版 / 便携版**；源码运行或 macOS 仅提示并打开下载页。
- 发布包未做代码签名；SmartScreen 可能拦截新下载的 Setup/exe。
- CI 未发布 checksum；下载侧校验 GitHub 声明的 `size`（若有）。

## 形态识别

| 形态 | 判定 | 产物 | 应用方式 |
|------|------|------|----------|
| 安装版 | exe 位于 `%LOCALAPPDATA%\Programs\ClipboardTranslator` 或旁有 `unins000.exe` | `*-Setup.exe` | 退出后 `/VERYSILENT` 再启动 |
| 便携版 | 其余 frozen Windows 进程 | `*-portable.exe` | 退出后 `copy` 覆盖原 exe 再启动 |

辅助脚本为临时 `.cmd`。便携版不查询旧 PID，而是重试复制，成功后才拉起新版、删除下载包并自删；失败则重新打开旧版并保留下载包。避免使用 `tasklist` / `find` 等外部 PID 查询，因为分离进程环境中子进程可能不退出，令更新永久停在等待阶段。安装版直接交给 Inno Setup 的 `CloseApplications` 处理占用进程。

## 入口

- 托盘菜单「检查更新」
- 设置对话框底部：常显 `vX.Y.Z · YYYY-MM-DD`（日期来自本版 CHANGELOG）+「检查更新」；右侧为确定 / 取消

实现见 `updater.py`，UI 接线见 `main.py` / `settings_dialog.py`。

## 手动检查 UX

- 检查中：设置页禁用按钮并显示「正在检查…」；忙碌时再次点击静默忽略（不弹「请稍候」）。
- 结果：无新版 →「当前已是最新正式版」；有新版 → 确认后再下载或打开 `html_url`。
- 设置窗打开时，结果 / 错误 / 下载进度对话框挂在设置窗上，避免被挡住。

## 后台任务生命周期

- Qt 的信号连接不会替 Python 持有 Worker；控制器必须同时强引用 `QThread` 和 Worker，直到对应线程发出 `finished`。
- 检查与下载使用独立的线程/Worker 引用，避免阶段切换时旧线程的清理覆盖新任务。
- 成功、请求失败和下载失败都是终态，必须解除 busy、恢复检查按钮与主窗口状态。
- GitHub 请求使用有限超时；网络异常必须进入失败终态，不能让界面永久停在「正在检查…」。

## 版本与日期展示

| 字段 | 来源 | 用途 |
|------|------|------|
| 当前版本 | `version.__version__` | 设置页与检查文案；离线可显 |
| 本机发布日期 | 打包内 / 仓库 `CHANGELOG.md` 对应版本行 | 设置页常显 |
| 线上发布日期 | GitHub `/releases/latest` 的 `published_at` | 检查结果；按 UTC+8（Asia/Shanghai）显示 `YYYY-MM-DD` |
| 发布页链接 | 同接口 `html_url` | 非自动覆盖时打开该版页面（回退 `/releases`） |

仅跟踪正式版（忽略 `preview`）。不把 `created_at` 当作上线日。
