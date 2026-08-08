# Clipboard Translator

Windows 常驻剪切板翻译小工具：复制任意文本 → 自动调用你的 OpenAI 兼容 LLM 端点流式翻译 → PySide6 置顶小窗展示。

## 安装

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

## 运行

```powershell
python main.py
```

托盘图标右键：显示窗口 / 暂停监听 / 退出。

## 行为

- `QClipboard.dataChanged` 事件监听（非轮询）
- LLM `stream=true`，首 token 上屏
- `requests.Session` 长连接 + LRU 缓存 + 新复制抢占旧任务
- 网页 / 桌面软件 / Steam 等凡是走系统剪切板的来源均可
