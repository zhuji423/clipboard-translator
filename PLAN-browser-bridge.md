# 浏览器字幕点词桥接（MVP）

## 目标

Chrome/Edge 扩展在 YouTube 字幕上点词暂停并查义；API Key 与 LLM 调用留在桌面端。

## 本机协议（仅 `127.0.0.1`）

| 方法 | 路径 | 鉴权 | 说明 |
|------|------|------|------|
| GET | `/health` | 无 | 探测桌面是否在线、是否已有 token |
| POST | `/v1/pair` | 无（一次性短码） | body: `{ "code": "123456" }` → `{ token, port }` |
| POST | `/v1/lookup` | `Authorization: Bearer <token>` | body: `{ word, context, target_lang? }` |

配对码默认 120 秒有效；令牌写入桌面 `config.toml` 的 `[bridge].token` 与扩展 `chrome.storage.local`。

## 配置

```toml
[bridge]
enabled = false
port = 17890
token = ""
```

## 扩展

- 源码：`extension/src`
- 构建：`cd extension && npm install && npm run build`
- 加载：Chrome → 扩展程序 → 开发者模式 → 加载已解压的扩展程序 → 选择 `extension/dist`

## 安全约束

- 只监听回环地址
- 不向扩展返回 API Key
- 限流、限制请求体大小
- 撤销配对会清空桌面 token
