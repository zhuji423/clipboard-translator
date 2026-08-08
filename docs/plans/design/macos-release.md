# macOS 打包与后续签名

## 当前

- 源码与 PyInstaller onedir + `BUNDLE` 产出 `Clipboard Translator.app`
- CI：`.github/workflows/release-macos.yml`（`macos-latest`）
- 本地：`./scripts/build_macos.sh`
- 配置/历史：`~/Library/Application Support/ClipboardTranslator`
- 产物未签名：用户需在 Finder 中右键 → 打开（首次 Gatekeeper）

## 后续（需 Apple Developer Program）

1. 准备 Developer ID Application 证书与 App 专用密码 / API Key
2. `codesign --deep --force --options runtime --sign "Developer ID Application: …" "Clipboard Translator.app"`
3. `notarytool submit` + `stapler staple`
4. CI secrets：`MACOS_CERTIFICATE`, `MACOS_CERTIFICATE_PWD`, `APPLE_ID` / `APP_STORE_CONNECT_API_KEY` 等
5. 可选自启：Login Items / `SMAppService` / LaunchAgent（应用内设置项）

未完成前，Windows 自启仍由 Inno Setup 任务负责；macOS 请手动将应用加入「登录时打开」。
