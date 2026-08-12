# 仓库分区说明

目标：**代码归代码，扩展归扩展，文档归 `docs/`**，避免计划与说明散落在根目录。

## 顶层布局

```text
clipboard-translator/
  ├── main.py, *.py           # 桌面端（PySide6）运行时代码
  ├── distribution.py         # 引导页 / 商店 URL、扩展 ID、NM 常量
  ├── native_messaging.py     # Chrome/Edge Native Messaging 注册（Windows + macOS）
  ├── native_host/            # Native Messaging host（stdio）
  ├── config.example.toml     # 配置示例（勿提交个人密钥）
  ├── version.py              # 唯一版本源
  ├── requirements*.txt
  ├── *.spec                  # PyInstaller 规格
  ├── assets/                 # 图标等静态资源
  ├── installer/              # Windows Inno Setup
  ├── scripts/                # 构建 / 维护脚本
  ├── tests/                  # 桌面端与桥接测试
  ├── extension/              # 浏览器扩展（独立 Node 工程）
  │     ├── src/              # TypeScript 源码
  │     ├── dist/             # 构建产物（通常 gitignore）
  │     └── package.json
  ├── docs/                   # 全部长文、计划、原理（本目录体系）
  │     └── onboarding/       # 扩展安装引导页（GitHub Pages）
  ├── .github/                # CI
  ├── README.md               # 用户入口（短）
  ├── CHANGELOG.md            # 变更史
  └── AGENTS.md               # Agent 工作流
```

运行时还会出现（勿当文档）：

- `config.toml`、`data/`：本机配置与历史（源码运行时在仓库根；打包后在用户目录）
- `.venv/`、`build/`、`dist/`：本地环境与构建产物
- `__pycache__/`：字节码缓存

## 分区约定

| 分区 | 放什么 | 不放什么 |
|------|--------|----------|
| 根目录 `*.py` | 桌面端模块、入口 | 计划稿、长篇设计 |
| `extension/` | 扩展源码与构建配置 | 桌面 Python、产品计划 |
| `docs/` | 计划、设计、原理、版本对照 | 可执行代码 |
| `scripts/` | 自动化脚本 | 用户说明正文 |
| `tests/` | 测试 | 功能实现 |

## 历史迁移说明（0.8.5 文档整理时）

原先根目录的 `PLAN-*.md` 已迁至 [`plans/design/`](plans/design/)。  
本机 Cursor 计划（`~/.cursor/plans/*.plan.md`）中与本仓库相关的条目已归档至 [`plans/history/`](plans/history/)，未完成者见 [`todo/`](todo/README.md)。

版本与计划对照见 [`VERSION-PLANS.md`](VERSION-PLANS.md)。
