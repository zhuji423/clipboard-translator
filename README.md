# Clipboard Translator

常驻剪切板翻译小工具：复制任意文本 → 自动调用你的 OpenAI 兼容 LLM 端点流式翻译 → PySide6 置顶小窗展示。支持 **Windows** 与 **macOS**。

当前版本见 [`version.py`](version.py)，变更记录见 [`CHANGELOG.md`](CHANGELOG.md)。Agent 工作流见 [`AGENTS.md`](AGENTS.md)。

## 下载（推荐）

- 正式版：[Releases](https://github.com/zhuji423/clipboard-translator/releases)
  - Windows：`ClipboardTranslator-*-Setup.exe` 或 `*-portable.exe`
  - macOS：`ClipboardTranslator-*-macos.zip`（内含 `Clipboard Translator.app`）
- 预览版（跟随 `main` 最新构建）：[preview](https://github.com/zhuji423/clipboard-translator/releases/tag/preview)

Windows 安装版写入开始菜单，可选开机自启；便携版下载即运行。macOS 将 `.app` 拖到「应用程序」即可。均为托盘 / 菜单栏常驻。

Windows 打包版可在托盘或设置中「检查更新」：仅跟踪正式版 Release，确认后下载覆盖并自动重启（设计见 [`PLAN-updater.md`](PLAN-updater.md)）。若覆盖安装后**任务栏**图标仍是旧图，多为系统图标缓存：重启资源管理器或取消固定后再固定快捷方式；托盘图标随新包内 `app.ico` 加载。

### 配置与历史目录

| 平台 | 打包后路径 |
|------|------------|
| Windows | `%APPDATA%\ClipboardTranslator\` |
| macOS | `~/Library/Application Support/ClipboardTranslator/` |

首次运行会从示例生成 `config.toml`。从源码运行时，配置与历史仍在仓库根目录。

### 未签名说明

- Windows：SmartScreen 可能拦截，选「仍要运行」即可。
- macOS：当前发布包**未**公证。首次打开若被拦截：Finder 中对 `.app` **右键 → 打开**，再确认打开。签名与公证见 [`PLAN-macos-release.md`](PLAN-macos-release.md)。

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

也可在运行后打开「设置」填写 API URL、API Key 与模型名（保存后立即生效）。

## 运行

```bash
python main.py
```

托盘 / 菜单栏图标：显示窗口 / 设置 / 翻译历史 / 暂停监听 / 检查更新 / 退出。

## 本地打包

Windows：

```powershell
.\scripts\build_windows.ps1
```

产物在 `dist\`（需本机安装 [Inno Setup 6](https://jrsoftware.org/isinfo.php) 才会生成 Setup）。设计说明见 [`PLAN-windows-release.md`](PLAN-windows-release.md)。

macOS：

```bash
chmod +x scripts/build_macos.sh
./scripts/build_macos.sh
```

产物：`dist/Clipboard Translator.app` 与 `dist/macos/ClipboardTranslator-*-macos.zip`。说明见 [`PLAN-macos-release.md`](PLAN-macos-release.md)。

## YouTube 字幕点词（浏览器扩展）

桌面端负责 LLM 与密钥；Chrome/Edge 扩展只负责字幕交互与本机配对。设计见 [`PLAN-browser-bridge.md`](PLAN-browser-bridge.md)。

1. 运行桌面端 → **设置** → 勾选「启用本机桥接」→ **开始配对**，记下 6 位配对码  
2. 构建扩展：

```powershell
.\scripts\build_extension.ps1
```

3. 浏览器打开 `chrome://extensions`（或 Edge 对应页）→ 开启「开发者模式」→「加载已解压的扩展程序」→ 选择仓库内 `extension/dist`  
4. 点击扩展图标 → 输入配对码 → **连接桌面端**  
5. 打开 YouTube 视频并**开启字幕**：
   - **单击**字幕中的单词：暂停并查看语境释义；关闭弹层后，若本次由扩展暂停则会恢复播放  
   - **拖选**一段字幕（可跨多个词）：在字幕条上按下并拖动，松手后经本机桥接唤起桌面翻译窗；自绘高亮、原文单行；失败时会有提示  

从 Release 下载的 `ClipboardTranslator-extension-*.zip` 解压后，在扩展管理页加载**该解压目录**即可（目录内应有 `manifest.json`）。

说明：首版仅 YouTube；B 站适配后续再加。扩展不会保存 API Key，密钥始终留在桌面端。

## 行为

- 启动时窗口锚定到屏幕可用区域右下角（避开任务栏 / Dock）；可拖动标题栏移动，也可拖边缘 / 四角调整大小，之后不再强拉
- `QClipboard.dataChanged` 事件监听（非轮询）；复制后约 1s 确认再翻译，避免语音工具短暂改写剪贴板造成闪烁
- LLM `stream=true`，首 token 上屏
- `requests.Session` 长连接 + LRU 缓存 + 新复制抢占旧任务（含缓存命中）
- 网页 / 桌面软件 / Steam 等凡是走系统剪切板的来源均可
- 语音误触已用确认窗抑制；仍冲突时可用托盘「暂停监听」
- 状态栏下方展示今日已用（本机估算）与 DeepSeek 账户剩余余额；设计见 [`PLAN-billing-balance.md`](PLAN-billing-balance.md)
- 可选浏览器桥接：YouTube 字幕点词查义写入历史时标记为 `youtube_word_lookup`
