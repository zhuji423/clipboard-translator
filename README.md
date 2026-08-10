# Clipboard Translator

常驻剪切板翻译与快捷问答工具：复制任意文本 → 自动流式翻译；Windows 选中文本按 `Ctrl+Shift+Q` → 一步复制并连续问答；按 `Ctrl+M` → 呼出半透明手动输入框。使用你的 OpenAI 兼容 LLM 端点，通过 PySide6 置顶小窗展示。支持 **Windows** 与 **macOS**。

当前版本见 [`version.py`](version.py)，变更记录见 [`CHANGELOG.md`](CHANGELOG.md)。Agent 工作流见 [`AGENTS.md`](AGENTS.md)。全部设计/计划/原理文档见 [`docs/`](docs/README.md)；版本与计划对照见 [`docs/VERSION-PLANS.md`](docs/VERSION-PLANS.md)。

## 下载（推荐）

- 正式版：[Releases](https://github.com/zhuji423/clipboard-translator/releases)
  - Windows：优先 `ClipboardTranslator-*-Setup.exe`（含 Native Messaging host）；或 `*-portable.exe` + 同目录下的 `*-NmHost.exe`
  - macOS：`ClipboardTranslator-*-macos.zip`（内含 `Clipboard Translator.app`）
- 预览版（跟随 `main` 最新构建）：[preview](https://github.com/zhuji423/clipboard-translator/releases/tag/preview)
- 扩展安装引导：[onboarding](https://zhuji423.github.io/clipboard-translator/onboarding/)（桌面端首次运行 / 设置 / 托盘也会打开）

Windows 安装版写入开始菜单，可选开机自启，并注册 Edge（及 Chromium）Native Messaging；便携版需将 NmHost 与主程序放在同一目录。macOS 将 `.app` 拖到「应用程序」即可。均为托盘 / 菜单栏常驻。扩展正式分发仅支持 **Microsoft Edge Add-ons**（不上架 Chrome 网上应用店）。

Windows 打包版可在托盘或设置中「检查更新」：仅跟踪正式版 Release，确认后下载覆盖并自动重启（设计见 [`docs/plans/design/updater.md`](docs/plans/design/updater.md)）。若覆盖安装后**任务栏**图标仍是旧图，多为系统图标缓存：重启资源管理器或取消固定后再固定快捷方式；托盘图标随新包内 `app.ico` 加载。

### 配置与历史目录

| 平台 | 打包后路径 |
|------|------------|
| Windows | `%APPDATA%\ClipboardTranslator\` |
| macOS | `~/Library/Application Support/ClipboardTranslator/` |

首次运行会从示例生成 `config.toml`。从源码运行时，配置与历史仍在仓库根目录。

### 未签名说明

- Windows：SmartScreen 可能拦截，选「仍要运行」即可。
- macOS：当前发布包**未**公证。首次打开若被拦截：Finder 中对 `.app` **右键 → 打开**，再确认打开。签名与公证见 [`docs/plans/design/macos-release.md`](docs/plans/design/macos-release.md)。

## 从源码安装

```bash
cd clipboard-translator
python -m venv .venv
# Windows:
#   .\.venv\Scripts\Activate.ps1
# macOS / Linux:
#   source .venv/bin/activate
pip install -r requirements.txt
cp config.example.toml config.toml   # Windows 可用 copy
```

编辑 `config.toml`，填入你的端点：

```toml
[llm]
base_url = "https://your-endpoint/v1"
api_key = "sk-xxx"
model = "your-model"
```

也可在运行后打开「设置」填写 API URL、API Key 与模型名，并修改 Windows 问答快捷键（保存后立即生效）。

## 运行

```bash
python main.py
```

托盘 / 菜单栏图标：显示窗口 / 手动输入翻译 / 设置 / 历史记录 / 清空问答上下文 / 暂停监听 / 安装浏览器扩展 / 检查更新 / 退出。

## 本地打包

Windows：

```powershell
.\scripts\build_windows.ps1
```

产物在 `dist\`（需本机安装 [Inno Setup 6](https://jrsoftware.org/isinfo.php) 才会生成 Setup）。设计说明见 [`docs/plans/design/windows-release.md`](docs/plans/design/windows-release.md)。

macOS：

```bash
chmod +x scripts/build_macos.sh
./scripts/build_macos.sh
```

产物：`dist/Clipboard Translator.app` 与 `dist/macos/ClipboardTranslator-*-macos.zip`。说明见 [`docs/plans/design/macos-release.md`](docs/plans/design/macos-release.md)。

## YouTube 字幕点词与划词翻译（浏览器扩展）

桌面端负责 LLM 与密钥；**Edge** 扩展只负责字幕交互与本机配对。协议见 [`docs/plans/design/browser-bridge.md`](docs/plans/design/browser-bridge.md)；划词原理与版本演进见 [`docs/guides/youtube-subtitle-phrase-translate.md`](docs/guides/youtube-subtitle-phrase-translate.md)。

### 效果（你想要的「选中即译」）

在 YouTube **开启字幕**后，扩展会显示一条可拖选的字幕条：

| 操作 | 结果 |
|------|------|
| **拖选**一段字幕（按住拖过多个词，松手） | 原文写入系统剪贴板（尽力而为），并经本机桥接 `POST /v1/translate` **立刻**唤起桌面翻译窗流式翻译 |
| **单击**单个单词 | 暂停视频，页内弹层显示语境释义（`/v1/lookup`）；关闭弹层后按需恢复播放 |

翻译**不依赖**「浏览器剪贴板变化是否被 Qt 听到」：复制是同步剪贴板，触发翻译以桥接为准。拖选过程使用 pointer capture + 自绘高亮，播放中控制栏弹出也不易丢手势；原文在桌面侧会折叠为单行。

### 给他人使用（推荐）

1. 安装并运行 Windows **Setup**（或便携版 + 同目录 NmHost）  
2. 用 **Microsoft Edge** 按引导页安装扩展（Edge Add-ons 上架后为一键获取；上架前引导页会说明过渡方式）  
3. 扩展一般会 **自动配对** 桌面端；失败时在桌面 **设置 → 开始配对**，扩展弹窗输入 6 位码  
4. 打开 YouTube、**开启字幕**，在扩展字幕条上拖选或单击即可  

桌面端也可随时用 **设置 / 托盘 → 安装浏览器扩展** 打开引导页。本机桥接默认启用；密钥始终留在桌面端。

### 开发者：本地构建扩展

```powershell
.\scripts\build_extension.ps1
```

Edge → `edge://extensions` → 打开「开发人员模式」→「加载解压缩的扩展」→ 选择仓库内 **`extension/dist` 文件夹**（须已 `build_extension`，目录内有 `manifest.json`）。  
本地侧载不会打开远程引导页；点工具栏扩展图标即可配对/自动连接。普通用户请走 Edge 商店 / 引导页。

从 Release 下载的 `ClipboardTranslator-extension-*.zip` 解压后加载该目录（须含 `manifest.json`）仅作过渡。改完扩展源码后需重新构建并在扩展管理页「重新加载」，再刷新 YouTube；桌面桥接相关改动需重启 `main.py`。

说明：首版仅 YouTube；B 站适配后续再加。

### 文档索引

| 文档 | 内容 |
|------|------|
| [`docs/README.md`](docs/README.md) | 文档总索引与目录说明 |
| [`docs/VERSION-PLANS.md`](docs/VERSION-PLANS.md) | 各版本使用了哪些计划、完成了哪些工作 |
| [`docs/guides/youtube-subtitle-phrase-translate.md`](docs/guides/youtube-subtitle-phrase-translate.md) | 划词→复制→翻译链路与 0.8.2–0.8.5 演进 |
| [`docs/plans/design/browser-bridge.md`](docs/plans/design/browser-bridge.md) | 本机 HTTP 协议、配对与安全约束 |
| [`docs/onboarding/`](docs/onboarding/index.html) | 扩展安装引导页（可部署为 GitHub Pages） |
| [`docs/todo/`](docs/todo/README.md) | 未做功能清单与计划（沉浸字幕、账户同步等） |
| [`AGENTS.md`](AGENTS.md) | Agent 改本仓库时的升版与文档约定 |

## 行为

- 启动时窗口锚定到屏幕可用区域右下角（避开任务栏 / Dock）；可拖动标题栏移动，也可拖边缘 / 四角调整大小，之后不再强拉
- `QClipboard.dataChanged` 事件监听（非轮询）；复制后约 1s 确认再翻译，避免语音工具短暂改写剪贴板造成闪烁
- Windows 默认按 `Ctrl+Shift+Q` 一步复制当前选区并回答；快捷键可在设置中修改，普通 `Ctrl+C` 自动翻译保持不变
- Windows 默认按 `Ctrl+M` 呼出半透明手动输入框；`Enter` 提交翻译，`Shift+Enter` 换行，`Esc` 关闭，位置、尺寸和透明度会自动记住
- 问答上下文仅在当前进程内连续，翻译与问答会话严格隔离；可从主窗或托盘手动清空
- LLM `stream=true`，首 token 上屏
- `requests.Session` 长连接 + LRU 缓存 + 新复制抢占旧任务（含缓存命中）
- 网页 / 桌面软件 / Steam 等凡是走系统剪切板的来源均可；YouTube 字幕划词另走本机桥接直达（见上节）
- 语音误触已用确认窗抑制；仍冲突时可用托盘「暂停监听」
- 状态栏下方展示今日已用（本机估算）与 DeepSeek 账户剩余余额；设计见 [`docs/plans/design/billing-balance.md`](docs/plans/design/billing-balance.md)
- 可选浏览器桥接：点词查义写入历史时标记为 `youtube_word_lookup`；划词整段翻译走与剪贴板相同的主窗翻译路径
