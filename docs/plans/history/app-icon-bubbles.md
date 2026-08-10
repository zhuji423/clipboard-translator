---
name: app-icon-bubbles
status: completed
planned_for: 0.9.8
implemented_in: [0.9.8, 0.9.9]
summary: 应用图标换成双气泡 A/译；Dock 安全区缩放
archived_at_version: 0.9.9
---

# 应用图标：双气泡 A / 译

## 问题

旧图标（深色剪影 / 纯蓝底白剪贴板）在菜单栏里偏沉，与轻快产品气质不符。

## 方案

- 采用备选 B：蜜桃奶油底 + 双气泡「A」与「译」
- 源图入库 [`assets/app-icon-source.png`](../../../assets/app-icon-source.png)
- [`scripts/generate_app_icon.py`](../../../scripts/generate_app_icon.py) 优先从此 PNG 生成 `app.png` / `app.ico` / `app.icns`；无源图时回退 SVG 蓝底剪贴板
- 生成时将画布外近黑角抠成透明，避免托盘出现黑方块
- 0.9.9：生成时再缩到约 80% 居中（Dock 安全区），避免内容贴边导致比旁边 App 显得更大

## 验证

- 本地跑 `python scripts/generate_app_icon.py` 产出新图标
- Dock / 托盘可见新双气泡图标（需重启进程或重打包 `.app`）
- Dock 上与相邻图标视觉大小接近
