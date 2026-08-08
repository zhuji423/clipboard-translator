# Clipboard Translator

Windows 常驻剪切板翻译小工具：复制任意文本 → 自动调用你的 OpenAI 兼容 LLM 端点流式翻译 → PySide6 置顶小窗展示。

当前版本见 [`version.py`](version.py)，变更记录见 [`CHANGELOG.md`](CHANGELOG.md)。Agent 工作流见 [`AGENTS.md`](AGENTS.md)。

## 下载（推荐）

- 正式版：[Releases](https://github.com/zhuji423/clipboard-translator/releases)（`ClipboardTranslator-*-Setup.exe` 或 `*-portable.exe`）
- 预览版（跟随 `main` 最新构建）：[preview](https://github.com/zhuji423/clipboard-translator/releases/tag/preview)

安装版写入开始菜单，可选开机自启；便携版下载即运行。二者均为托盘常驻。

配置与翻译历史目录：`%APPDATA%\ClipboardTranslator\`（首次运行会从示例生成 `config.toml`）。

未签名 EXE 可能被 SmartScreen 拦截，选「仍要运行」即可。

## 从源码安装

```powershell
cd clipboard-translator
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
copy config.example.toml config.toml
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

```powershell
python main.py
```

托盘图标右键：显示窗口 / 设置 / 翻译历史 / 暂停监听 / 退出。

## 本地打包

```powershell
.\scripts\build_windows.ps1
```

产物在 `dist\`（需本机安装 [Inno Setup 6](https://jrsoftware.org/isinfo.php) 才会生成 Setup）。设计说明见 [`PLAN-windows-release.md`](PLAN-windows-release.md)。

## 行为

- 启动时窗口锚定到屏幕可用区域右下角（避开任务栏）；可拖动，之后不再强拉
- `QClipboard.dataChanged` 事件监听（非轮询）；复制后约 1s 确认再翻译，避免语音工具短暂改写剪贴板造成闪烁
- LLM `stream=true`，首 token 上屏
- `requests.Session` 长连接 + LRU 缓存 + 新复制抢占旧任务（含缓存命中）
- 网页 / 桌面软件 / Steam 等凡是走系统剪切板的来源均可
- 语音误触已用确认窗抑制；仍冲突时可用托盘「暂停监听」
- 状态栏下方展示今日已用（本机估算）与 DeepSeek 账户剩余余额；设计见 [`PLAN-billing-balance.md`](PLAN-billing-balance.md)
