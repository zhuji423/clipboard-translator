# Windows 安装版 / 便携版自动发布

## 目标

- 产出便携 `*-portable.exe` 与安装包 `*-Setup.exe`
- `push` 到 `main` 时由 GitHub Actions 自动构建
- 滚动更新 Pre-release `preview`；当 `version.py` 尚无对应 `vX.Y.Z` tag 时自动打正式 Release

## 关键路径

- 打包后配置与历史：`%APPDATA%\ClipboardTranslator\`
- 资源（图标、`config.example.toml`）：PyInstaller `_MEIPASS`
- 源码运行时仍使用仓库根目录下的 `config.toml` / `data/`

## 本地构建

```powershell
.\scripts\build_windows.ps1
```

需已安装 Python 依赖；安装 Inno Setup 6 后会顺带编译 Setup。

## CI

见 `.github/workflows/release-windows.yml`。
